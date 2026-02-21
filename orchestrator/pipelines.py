from typing import Any, Dict, Optional
import uuid
from FIOS.orchestrator.triggers import triggers, EventType

from FIOS.ingestion.validators.schemas import IngestionPayload, RawJobData, RawProposalData, RawConversationData
from FIOS.ingestion.cleaners.normalizer import clean_budget, normalize_proposal_status, clean_text

from FIOS.database.connection import async_session_maker
from FIOS.database.models.jobs import Job, JobOutcome
from FIOS.database.models.proposals import Proposal, ProposalStatus
from FIOS.database.models.conversations import Conversation
from FIOS.database.models.clients import Client
from FIOS.database.models.analytics import Analytics
import json
import re
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_ts(ts_str: Optional[str]) -> Optional[datetime]:
    """Try to parse a message timestamp string into a datetime.

    Supports: '09:05 AM', '14:30', '2026-02-20T09:05:00', '2026-02-20 09:05'
    NOTE: we avoid strptime('%p') because it is locale-sensitive and can hang
    in minimal shell environments. Instead we parse AM/PM manually.
    """
    if not ts_str:
        return None
    ts = ts_str.strip()

    # 1. ISO / long formats first (no locale issues)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue

    # 2. AM/PM — manual parse (locale-safe)
    import re as _re
    ampm_match = _re.match(r'^(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)$', ts)
    if ampm_match:
        h, m, period = int(ampm_match.group(1)), int(ampm_match.group(2)), ampm_match.group(3).upper()
        if period == "PM" and h != 12:
            h += 12
        elif period == "AM" and h == 12:
            h = 0
        try:
            return datetime(2000, 1, 1, h, m)
        except ValueError:
            pass

    # 3. Plain 24-hour HH:MM
    try:
        return datetime.strptime(ts, "%H:%M")
    except ValueError:
        pass

    return None


def _compute_analytics(messages: list) -> dict:
    """
    Derive rich analytics from a list of message dicts.

    Keys returned
    -------------
    total_messages        : int
    client_messages       : int
    freelancer_messages   : int
    client_ratio          : float  (percentage, 1 decimal)
    response_delay_avg_mins: float  (average client→freelancer reply delay)
    conversation_stage    : str    (negotiating | active | inactive)
    last_activity_ago     : str    (human-readable age of last message)
    """
    total = len(messages)
    if total == 0:
        return {
            "total_messages": 0,
            "client_messages": 0,
            "freelancer_messages": 0,
            "client_ratio": 0,
            "response_delay_avg_mins": 0,
            "conversation_stage": "inactive",
            "last_activity_ago": "unknown",
        }

    client_msgs  = [m for m in messages if m.get("role") == "client"]
    free_msgs    = [m for m in messages if m.get("role", "freelancer") == "freelancer"]
    client_count = len(client_msgs)
    free_count   = len(free_msgs)

    # --- Response delay (client → freelancer) --------------------------------
    delays = []
    prev_client_ts = None
    for m in messages:
        ts = _parse_ts(m.get("time"))
        if m.get("role") == "client":
            prev_client_ts = ts
        elif m.get("role", "freelancer") == "freelancer" and prev_client_ts and ts:
            diff = (ts - prev_client_ts).total_seconds() / 60
            if 0 < diff < 2880:  # ignore unrealistic gaps > 2 days
                delays.append(diff)
            prev_client_ts = None

    avg_delay = round(sum(delays) / len(delays), 1) if delays else 0.0

    # --- Conversation stage -------------------------------------------------
    all_text = " ".join(m.get("text", "") for m in messages[-10:]).lower()
    negotiation_kw = {"price", "rate", "budget", "quote", "offer", "milestone", "contract", "payment", "hourly"}
    stage = "active"
    if any(k in all_text for k in negotiation_kw):
        stage = "negotiating"
    else:
        # Check last-activity recency (use last_message_timestamp from outside if available)
        last_msg = messages[-1] if messages else None
        last_ts = _parse_ts(last_msg.get("time")) if last_msg else None
        if last_ts is None:
            stage = "active"   # can't tell, assume active

    # --- Last-activity string ----------------------------------------------
    # We can't do real wall-clock diff from time strings alone without date
    # so we report the raw time of last message as a best-effort preview.
    last_time_str = messages[-1].get("time", "unknown") if messages else "unknown"
    last_activity_ago = f"last msg at {last_time_str}"

    # --- Longest single response delay -----------------------------------
    longest_delay = round(max(delays), 1) if delays else 0.0

    # --- Project duration (first → last message, using index as proxy) ---
    # Full date not always available; we count message span as a rough proxy.
    # If ISO timestamps exist we use wall-clock days, else use None.
    project_duration_days: Optional[int] = None
    first_iso = _parse_ts(messages[0].get("time")) if messages else None
    last_iso  = _parse_ts(messages[-1].get("time")) if messages else None
    if first_iso and last_iso:
        delta = (last_iso - first_iso).total_seconds()
        if delta > 0:
            project_duration_days = int(delta / 86400)

    # --- Message activity by day (needs full ISO dates) -------------------
    activity_by_day: dict = {}
    for m in messages:
        t = _parse_ts(m.get("time"))
        if t and t.year > 2000:  # only real ISO dates
            day_key = t.strftime("%Y-%m-%d")
            activity_by_day[day_key] = activity_by_day.get(day_key, 0) + 1

    # --- Client score (computed inline, stored in analytics) --------------
    client_score = _compute_client_score(messages, delays)

    return {
        "total_messages": total,
        "client_messages": client_count,
        "freelancer_messages": free_count,
        "client_ratio": round((client_count / total) * 100, 1) if total > 0 else 0,
        "response_delay_avg_mins": avg_delay,
        "longest_response_delay_mins": longest_delay,
        "project_duration_days": project_duration_days,
        "message_activity_by_day": activity_by_day,
        "conversation_stage": stage,
        "last_activity_ago": last_activity_ago,
        "client_score": client_score,
    }


def _compute_client_score(messages: list, delays: list = None) -> dict:
    """
    Score a client's communication quality from 0-10.

    Scoring dimensions
    ------------------
    response_speed   : fast replies = high score (weight 30%)
    message_length   : longer msgs = more engaged (weight 20%)
    scope_changes    : frequent scope-change keywords = negative (weight 20%)
    urgency_abuse    : excessive urgency without milestones (weight 15%)
    risk_signals     : outside-Upwork / free-work requests (weight 15%)
    """
    if not messages:
        return {"score": 0.0, "label": "Unknown", "breakdown": {}}

    client_msgs = [m for m in messages if m.get("role") == "client"]
    if not client_msgs:
        return {"score": 5.0, "label": "Neutral", "breakdown": {}}

    all_client_text = " ".join(m.get("text", "") for m in client_msgs).lower()

    # 1. Response speed (based on avg delay provided by caller)
    avg_d = (sum(delays) / len(delays)) if delays else None
    if avg_d is None:
        speed_score = 5.0
    elif avg_d <= 5:
        speed_score = 10.0
    elif avg_d <= 30:
        speed_score = 8.0
    elif avg_d <= 120:
        speed_score = 5.0
    elif avg_d <= 480:
        speed_score = 3.0
    else:
        speed_score = 1.0

    # 2. Message length (avg words per client message)
    avg_words = sum(len(m.get("text", "").split()) for m in client_msgs) / len(client_msgs)
    length_score = min(10.0, avg_words / 10)  # 10+ words per msg = full score

    # 3. Scope change signals (negative)
    scope_kw = {"change", "also add", "actually", "by the way", "one more thing",
                "additional", "extend", "update the scope", "modify"}
    scope_hits = sum(1 for kw in scope_kw if kw in all_client_text)
    scope_penalty = min(10.0, scope_hits * 1.5)
    scope_score = max(0.0, 10.0 - scope_penalty)

    # 4. Urgency abuse (without milestone language)
    urgency_kw = {"urgent", "asap", "immediately", "right now", "rush"}
    milestone_kw = {"milestone", "contract", "payment", "escrow"}
    urgency_hits = sum(1 for kw in urgency_kw if kw in all_client_text)
    has_milestones = any(kw in all_client_text for kw in milestone_kw)
    if urgency_hits > 0 and not has_milestones:
        urgency_score = max(0.0, 10.0 - urgency_hits * 2.5)
    else:
        urgency_score = 10.0 if not urgency_hits else 7.0

    # 5. Risk signals (outside-platform, free work)
    risk_kw = {"paypal", "crypto", "wire transfer", "free test", "free work",
               "no contract", "outside upwork", "without contract"}
    risk_hits = sum(1 for kw in risk_kw if kw in all_client_text)
    risk_score = max(0.0, 10.0 - risk_hits * 5.0)

    # Weighted composite
    score = round(
        speed_score  * 0.30 +
        length_score * 0.20 +
        scope_score  * 0.20 +
        urgency_score* 0.15 +
        risk_score   * 0.15,
        1
    )

    if score >= 8:   label = "Excellent"
    elif score >= 6: label = "Good"
    elif score >= 4: label = "Fair"
    else:            label = "Poor"

    return {
        "score": score,
        "label": label,
        "breakdown": {
            "response_speed":   round(speed_score, 1),
            "message_length":  round(length_score, 1),
            "scope_changes":   round(scope_score, 1),
            "urgency_abuse":   round(urgency_score, 1),
            "risk_signals":    round(risk_score, 1),
        }
    }


class IngestionPipeline:
    """Handles raw data input, validation, and storage."""

    async def process_raw_input(self, data_type: str, raw_payload: Dict[str, Any]):
        """
        Master Pipeline Flow:
        Raw JSON -> Validation -> Normalization -> Storage -> Embedding -> Trigger Events
        """
        print(f"1. Receiving raw {data_type} data...")

        # 1. Validation
        payload = IngestionPayload(**raw_payload)

        record_ids = []

        # 2. Storage (Save to Postgres via Models)
        async with async_session_maker() as session:
            if payload.type == "job_details":
                job_data = payload.data
                b_info = clean_budget(job_data.get("budget", ""))

                new_job = Job(
                    title=job_data.get("title", "Unknown"),
                    description=f"{job_data.get('description', '')}\n\n---RAW PAGE DATA---\n{job_data.get('raw_text', '')}",
                    budget_type=b_info["budget_type"],
                    budget_min=b_info["min"],
                    budget_max=b_info["max"],
                    skills_required=job_data.get("skills", []),
                    category="Extracted Job"
                )
                session.add(new_job)
                await session.flush()
                record_ids.append(str(new_job.id))

                from FIOS.orchestrator.triggers import EventPayload
                await triggers.trigger(EventPayload(event_type=EventType.NEW_JOB_UPLOADED, data={"id": new_job.id, "data": job_data}))

            elif payload.type == "proposals":
                from FIOS.memory.retrieval import memory
                for prop in payload.data:
                    prop_id = prop.get("proposal_link")
                    if prop_id:
                        # Deduplicate using Chroma DB directly to avoid complex migrations
                        w_col = memory.collection("winning_proposals")
                        l_col = memory.collection("losing_proposals")
                        res1 = w_col.get(where={"proposal_id": prop_id}, limit=1)
                        res2 = l_col.get(where={"proposal_id": prop_id}, limit=1)
                        if (res1 and res1.get("ids") and len(res1["ids"]) > 0) or (res2 and res2.get("ids") and len(res2["ids"]) > 0):
                            print(f"[FIOS] Proposal {prop_id} already synced. Skipping insert.")
                            continue

                    status = normalize_proposal_status(prop.get("outcome", prop.get("status", "")))

                    dummy_job = Job(
                        title=prop.get("job_title", prop.get("title", "Unknown Job")),
                        description=prop.get("job_description", "Extracted from proposals list"),
                        budget_type="fixed", budget_min=0.0, budget_max=0.0,
                        meta_data={"proposal_link": prop_id}
                    )
                    session.add(dummy_job)
                    await session.flush()

                    new_proposal = Proposal(
                        job_id=dummy_job.id,
                        cover_letter=clean_text(prop.get("proposal_text", prop.get("raw_text", ""))),
                        bid_amount=float(prop.get("bid_amount", 0.0) or 0.0),
                        status=status,
                        connects_spent=0
                    )
                    session.add(new_proposal)
                    await session.flush()
                    record_ids.append(str(new_proposal.id))
                    
                    # Dispatch to Embedder immediately since we have the prop_id safely scoped
                    try:
                        from FIOS.memory.embedder import embed_proposal_incremental
                        outcome = "pending"
                        if "hired" in status.lower() or "active" in status.lower():
                            outcome = "won"
                        elif "declined" in status.lower() or "withdrawn" in status.lower() or "archived" in status.lower():
                            outcome = "lost"
                            
                        await embed_proposal_incremental(
                            proposal_id=prop_id or str(new_proposal.id),
                            text=new_proposal.cover_letter,
                            outcome=outcome,
                            job_title=dummy_job.title
                        )
                        print(f"[FIOS] Embedded Proposal: {prop_id}")
                    except Exception as e:
                        print("Embed error:", e)

            elif payload.type == "conversation":
                conv_data = payload.data
                room_id = conv_data.get("room_id")
                messages = conv_data.get("messages", [])

                # ── BUG FIX: query existing_conv BEFORE using it ──────────
                from sqlalchemy import select
                stmt = select(Conversation).where(Conversation.room_id == room_id)
                result = await session.execute(stmt)
                existing_conv = result.scalar_one_or_none()
                # ─────────────────────────────────────────────────────────

                if existing_conv:
                    # Smart Merge: only add non-duplicate messages
                    existing_keys = {m.get("message_id") or f"{m.get('sender')}:{m.get('time')}" for m in existing_conv.messages_json}
                    new_msgs = [m for m in messages if (m.get("message_id") or f"{m.get('sender')}:{m.get('time')}") not in existing_keys]

                    if new_msgs:
                        from copy import deepcopy
                        updated_msgs = deepcopy(existing_conv.messages_json)
                        updated_msgs.extend(new_msgs)
                        existing_conv.messages_json = updated_msgs

                        # Update Sync Metadata
                        if updated_msgs:
                            last_msg = updated_msgs[-1]
                            existing_conv.last_message_id = last_msg.get("message_id")
                            existing_conv.last_message_timestamp = last_msg.get("time")
                            existing_conv.last_message_preview = last_msg.get("text", "")[:200]
                            existing_conv.message_count_synced = len(updated_msgs)
                            existing_conv.sync_status = conv_data.get("sync_status", "partially_synced")

                            # Phase 1: Rich Analytics
                            existing_conv.analytics = _compute_analytics(updated_msgs)

                        session.add(existing_conv)
                        await session.flush()

                        # Trigger Summary refresh if significant new info
                        if len(new_msgs) > 3 or not existing_conv.summary:
                            await self.trigger_ai_summary(existing_conv.id, existing_conv.messages_json)

                    record_ids.append(str(existing_conv.id))
                else:
                    new_conv = Conversation(
                        thread_name=conv_data.get("thread_name", "Unknown Thread"),
                        room_id=room_id,
                        messages_json=messages,
                        sync_status=conv_data.get("sync_status", "fully_synced"),
                        message_count_synced=len(messages)
                    )
                    if messages:
                        last_msg = messages[-1]
                        new_conv.last_message_id = last_msg.get("message_id")
                        new_conv.last_message_timestamp = last_msg.get("time")
                        new_conv.last_message_preview = last_msg.get("text", "")[:200]
                        new_conv.analytics = _compute_analytics(messages)

                    session.add(new_conv)
                    await session.flush()
                    record_ids.append(str(new_conv.id))

                    await self.trigger_ai_summary(new_conv.id, messages)

                from FIOS.orchestrator.triggers import EventPayload
                await triggers.trigger(EventPayload(event_type=EventType.CONVERSATION_UPDATED, data={"id": record_ids[-1], "data": conv_data}))

            elif payload.type == "stealth_proposal_job_merge":
                merge_data = payload.data
                prop_data = merge_data.get("proposal", {})
                job_data = merge_data.get("job", {})

                new_job = Job(
                    title=job_data.get("title", prop_data.get("title", "Unknown Stealth Job")),
                    description=clean_text(job_data.get("raw_text", prop_data.get("raw_text", ""))),
                    budget_type="fixed", budget_min=0.0, budget_max=0.0,
                    category="Stealth Extracted Job",
                    meta_data={
                        "client_info": prop_data.get("client_info"),
                        "hiring_activity": prop_data.get("hiring_activity"),
                        "bid_amount": prop_data.get("bid_amount")
                    }
                )
                session.add(new_job)
                await session.flush()
                record_ids.append(str(new_job.id))

                status = normalize_proposal_status(prop_data.get("status", ""))
                new_proposal = Proposal(
                    job_id=new_job.id,
                    cover_letter=clean_text(prop_data.get("cover_letter", prop_data.get("raw_text", ""))),
                    bid_amount=0.0,
                    status=status,
                    connects_spent=0
                )
                session.add(new_proposal)
                await session.flush()
                record_ids.append(str(new_proposal.id))

                from FIOS.orchestrator.triggers import EventPayload
                await triggers.trigger(EventPayload(event_type=EventType.NEW_JOB_UPLOADED, data={"id": new_job.id, "data": job_data}))

            await session.commit()

        # ── Phase 3: Write sync log entry ─────────────────────────────────────
        if payload.type in ("conversation", "stealth_proposal_job_merge"):
            try:
                from FIOS.main import _append_sync_log
                import datetime as _dt
                _append_sync_log({
                    "ts": _dt.datetime.utcnow().isoformat() + "Z",
                    "type": payload.type,
                    "room_id": payload.data.get("room_id") if isinstance(payload.data, dict) else None,
                    "records_saved": len(record_ids),
                    "record_ids": record_ids,
                })
            except Exception:
                pass  # Never let logging crash the pipeline

        # ── Incremental embedding into vector memory ──────────────────────
        try:
            from FIOS.memory.embedder import embed_conversation_incremental, embed_job_incremental
            if payload.type == "conversation":
                room_id = payload.data.get("room_id") if isinstance(payload.data, dict) else None
                msgs = payload.data.get("messages", []) if isinstance(payload.data, dict) else []
                if room_id and msgs:
                    await embed_conversation_incremental(room_id, msgs)
            elif payload.type == "job":
                jdata = payload.data if isinstance(payload.data, dict) else {}
                await embed_job_incremental(str(record_ids[0]) if record_ids else "", jdata.get("title", ""), jdata.get("description", ""))
        except Exception:
            pass  # Never crash the pipeline for embedding

        print(f"-> Successfully saved {len(record_ids)} records to Database.")
        return record_ids

    async def get_thread_status(self, room_id: str):
        """Checks if a conversation thread exists and returns detailed metadata."""
        async with async_session_maker() as session:
            from sqlalchemy import select
            stmt = select(Conversation).where(Conversation.room_id == room_id)
            result = await session.execute(stmt)
            conv = result.scalar_one_or_none()
            if conv:
                return {
                    "exists": True,
                    "messageCount": len(conv.messages_json),
                    "lastSync": conv.updated_at.strftime("%Y-%m-%d %H:%M") if conv.updated_at else "Unknown",
                    "syncStatus": conv.sync_status,
                    "lastMessageId": conv.last_message_id,
                    "lastMessageTimestamp": conv.last_message_timestamp,
                    "lastMessagePreview": conv.last_message_preview,
                    "summary": conv.summary or "",
                    "actionItems": conv.action_items,
                    "riskFlags": conv.risk_flags,
                    "analytics": conv.analytics,
                }
            return {"exists": False}

    async def get_aggregate_analytics(self) -> dict:
        """Returns aggregate analytics across all synced conversations."""
        async with async_session_maker() as session:
            from sqlalchemy import select, func
            stmt = select(Conversation)
            result = await session.execute(stmt)
            convs = result.scalars().all()

            total_threads = len(convs)
            total_messages = sum(c.analytics.get("total_messages", 0) for c in convs if c.analytics)
            all_delays = [c.analytics.get("response_delay_avg_mins", 0) for c in convs if c.analytics and c.analytics.get("response_delay_avg_mins", 0) > 0]
            avg_delay = round(sum(all_delays) / len(all_delays), 1) if all_delays else 0

            all_risks: list[str] = []
            for c in convs:
                all_risks.extend(c.risk_flags or [])

            stage_counts: dict[str, int] = {}
            for c in convs:
                stage = (c.analytics or {}).get("conversation_stage", "unknown")
                stage_counts[stage] = stage_counts.get(stage, 0) + 1

            return {
                "total_threads": total_threads,
                "total_messages": total_messages,
                "avg_response_delay_mins": avg_delay,
                "stage_breakdown": stage_counts,
                "top_risk_flags": list(set(all_risks))[:10],
            }

    async def trigger_ai_summary(self, conversation_id: uuid.UUID, messages: list):
        """Calls the internal AI service to extract Action Items, Risks, and Summaries."""
        from FIOS.copilot.ai import _call_ai, SYSTEM_PROMPT
        try:
            # Use last 100 messages for significantly richer context
            conv_text = "\n".join([
                f"{m.get('sender', 'Unknown')} [{m.get('role', 'freelancer')}]: {m.get('text', '')}"
                for m in messages[-100:]
            ])
            prompt = (
                "You are an expert Upwork freelancer assistant. Analyze this conversation and extract intelligence. "
                "You MUST respond ONLY with a valid JSON block containing exactly these keys:\n"
                "- 'summary': A concise 2-3 sentence overview of current relationship status and key decisions.\n"
                "- 'action_items': A list of strings detailing specific tasks, deadlines, or deliverables mentioned.\n"
                "- 'risk_flags': A list of strings for red flags ONLY if present. "
                "Common Upwork red flags include: requesting payment outside Upwork (PayPal, Crypto, Wire), "
                "asking for free work or 'test tasks', scope creep (adding features without updating contract), "
                "urgency without milestones, ghost hiring (no response after interview). Leave empty [] if none.\n"
                "- 'conversation_stage': One of 'negotiating', 'active', or 'inactive'.\n\n"
                f"Conversation (latest 40 messages):\n{conv_text}"
            )

            raw_response = await _call_ai(prompt, SYSTEM_PROMPT)

            # Extract JSON from potential markdown code blocks
            import re
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
            json_str = json_match.group(1) if json_match else raw_response

            # Fallback: find first JSON object
            if not json_match:
                obj_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
                if obj_match:
                    json_str = obj_match.group(0)

            try:
                import json
                intel = json.loads(json_str)
                summary = intel.get("summary", "")
                action_items = intel.get("action_items", [])
                risk_flags = intel.get("risk_flags", [])
                ai_stage = intel.get("conversation_stage")

                update_vals = dict(
                    summary=summary,
                    action_items=action_items,
                    risk_flags=risk_flags,
                )

                # Merge AI stage into analytics if we got one
                async with async_session_maker() as session:
                    from sqlalchemy import select as sel, update
                    conv_r = await session.execute(sel(Conversation).where(Conversation.id == conversation_id))
                    conv_obj = conv_r.scalar_one_or_none()
                    if conv_obj:
                        if ai_stage:
                            merged_analytics = dict(conv_obj.analytics or {})
                            merged_analytics["conversation_stage"] = ai_stage
                            update_vals["analytics"] = merged_analytics

                        stmt = update(Conversation).where(Conversation.id == conversation_id).values(**update_vals)
                        await session.execute(stmt)
                        await session.commit()
                        print(f"✅ AI CRM Intelligence Updated for {conversation_id}")
                    else:
                        print(f"❌ Conversation {conversation_id} no longer exists in DB.")

            except json.JSONDecodeError:
                print(f"❌ Failed to parse Gemini JSON: {raw_response[:200]}")

        except Exception as e:
            print(f"❌ Failed to generate AI intelligence: {e}")


pipeline = IngestionPipeline()
