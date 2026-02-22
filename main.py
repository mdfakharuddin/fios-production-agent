import os
import sys
# Allow imports with 'FIOS.' prefix when run from within the FIOS directory
current_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(current_dir) == "FIOS":
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
else:
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager
import re

from FIOS.core.config import settings

# Initialize Background Scheduler
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Events
    print(f"Starting {settings.PROJECT_NAME}...")
    scheduler.start()

    # Run background embedder on startup
    try:
        from FIOS.memory.embedder import run_full_embed
        import asyncio
        asyncio.create_task(run_full_embed())
        print("[Startup] Background embedder task launched.")
    except Exception as e:
        print(f"[Startup] Embedder launch skipped: {e}")

    # Build brain snapshot from existing data
    try:
        from FIOS.brain_store import rebuild_brain
        rebuild_brain()
    except Exception as e:
        print(f"[Startup] Brain rebuild skipped: {e}")

    yield
    # Shutdown Events
    print(f"Shutting down {settings.PROJECT_NAME}...")
    scheduler.shutdown()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Update for production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.PROJECT_NAME} API"}


# ── Orchestrator (Single Entry Intelligence) ─────────────────────────────
from pydantic import BaseModel
from typing import Optional, Dict

class BrainRequest(BaseModel):
    event_type: str
    room_id: Optional[str] = None
    job_context: Optional[dict] = None
    mode: Optional[str] = "deep"
    user_preferences: Optional[dict] = None
    query: Optional[str] = None
    context: Optional[str] = None
    session_id: Optional[str] = None # Added for active session tracking
    outcome: Optional[str] = None
    amount: Optional[float] = None
    data: Optional[dict] = None

# Late import allows components to bootstrap
from FIOS.orchestrator import agent_router

@app.post("/brain/execute")
async def brain_execute(request: BrainRequest):
    result = await agent_router.route(request)
    return result

# ── Brain API (for external agents: n8n, OpenClaw, etc.) ──────────────────

@app.get("/api/v1/brain/snapshot")
async def brain_snapshot():
    """Returns the full brain state. Used by n8n/OpenClaw agents."""
    from FIOS.brain_store import load_brain
    return {"status": "ok", "brain": load_brain()}


@app.post("/api/v1/brain/rebuild")
async def brain_rebuild():
    """Force a full brain rebuild from database."""
    from FIOS.brain_store import rebuild_brain
    brain = rebuild_brain()
    return {"status": "ok", "brain": brain}


@app.post("/api/v1/brain/note")
async def brain_add_note(body: dict):
    """Add a strategic note to the brain (from external agents)."""
    from FIOS.brain_store import load_brain, save_brain
    note = body.get("note", "")
    if not note:
        return {"status": "error", "message": "note required"}
    brain = load_brain()
    brain.setdefault("strategic_notes", []).append({
        "text": note,
        "source": body.get("source", "manual"),
        "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    })
    save_brain(brain)
    return {"status": "ok", "total_notes": len(brain["strategic_notes"])}


@app.post("/api/v1/research/job")
async def perform_job_research(body: dict):
    """Deep research into a job. Called by n8n or other agents."""
    from FIOS.agents.layer4_research.research_agent import research_agent
    from FIOS.brain_store import load_brain
    
    job_data = body.get("job_data", {})
    if not job_data:
        return {"status": "error", "message": "job_data required"}
    
    brain_data = load_brain()
    research = await research_agent.analyze_market_alignment(job_data, brain_data)
    
    return {"status": "ok", "research": research}

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": settings.PROJECT_NAME}


@app.post("/api/chat")
async def legacy_chat(body: dict):
    """
    Backward-compatible chat endpoint used by older extension scripts.
    Maps to the unified brain router.
    """
    req = BrainRequest(
        event_type="free_chat",
        room_id=body.get("conversation_id"),
        query=body.get("message", ""),
        context=body.get("context"),
        data=body.get("metadata"),
    )
    return await agent_router.route(req)


@app.post("/api/job/analyze")
async def legacy_job_analyze(body: dict):
    """
    Backward-compatible job analysis endpoint.
    """
    req = BrainRequest(
        event_type="job_analysis",
        job_context=body.get("job_data") or {},
        query=(body.get("job_data") or {}).get("description", ""),
    )
    return await agent_router.route(req)

from FIOS.orchestrator.pipelines import pipeline

@app.post("/api/v1/ingest")
async def ingest_upwork_data(payload: dict):
    """Webhook endpoint for the Chrome Extension."""
    data_type = payload.get("type", "unknown")
    raw_data = payload.get("data", [])
    
    print(f"Received {len(raw_data) if isinstance(raw_data, list) else 1} records of type: {data_type} from Chrome Extension.")
    
    # Forward to n8n if configured
    if settings.N8N_WEBHOOK_URL:
        import asyncio, httpx
        async def _forward():
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(settings.N8N_WEBHOOK_URL, json=payload, timeout=5.0)
            except Exception as e:
                print(f"[Webhook] Failed to forward to n8n: {e}")
        asyncio.create_task(_forward())

    try:
        # Pass the entire payload dict to the pipeline which handles Pydantic validation
        record_ids = await pipeline.process_raw_input(data_type, payload)
        
        # Trigger brain rebuild to update stats in background
        from FIOS.brain_store import rebuild_brain
        import asyncio
        asyncio.create_task(asyncio.to_thread(rebuild_brain))

        return {"status": "success", "message": f"Ingested {len(record_ids)} items.", "record_ids": record_ids}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.post("/api/v1/ingest/conversation")
async def manual_ingest_conversation(payload: dict):
    """Dedicated endpoint for manual, full-DOM conversation tree extraction."""
    try:
        # Wrap the normalized payload into the format expected by process_raw_input
        wrapped_payload = {
            "type": "conversation",
            "data": payload,
            "url": payload.get("conversation_link") or payload.get("url") or "manual://conversation",
            "timestamp": payload.get("timestamp") or __import__("datetime").datetime.utcnow().isoformat() + "Z",
        }
        record_ids = await pipeline.process_raw_input("conversation", wrapped_payload)
        return {"status": "success", "message": "Conversation saved successfully.", "records": len(record_ids)}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.post("/api/v1/ingest/proposal")
async def manual_ingest_proposal(payload: dict):
    """Dedicated endpoint for manual, full-DOM individual proposal extraction."""
    try:
        wrapped_payload = {
            "type": "proposals",
            "data": [payload], # pipeline.process_raw_input expects list for proposals typically
            "url": payload.get("proposal_link") or payload.get("url") or "manual://proposal",
            "timestamp": payload.get("timestamp") or __import__("datetime").datetime.utcnow().isoformat() + "Z",
        }
        record_ids = await pipeline.process_raw_input("proposals", wrapped_payload)
        return {"status": "success", "message": "Proposal saved successfully.", "records": len(record_ids)}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

# ===========================================================================
# FIOS SYNC PANEL & STATUS
# ===========================================================================

@app.get("/api/v1/sync/stats")
async def get_sync_stats():
    """Return counts specifically for the new Popup FIOS Sync Panel."""
    try:
        from FIOS.memory.retrieval import memory
        stats = memory.get_stats()
        proposals = stats.get("winning_proposals", 0) + stats.get("losing_proposals", 0)
        conversations = stats.get("conversations", 0)
        return {"proposals": proposals, "conversations": conversations}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/sync/status/conversation")
async def check_conversation_sync(room_id: str):
    """Check if a specific room_id exists in vector memory."""
    try:
        from FIOS.memory.retrieval import memory
        col = memory.collection("conversations")
        result = col.get(where={"room_id": room_id}, limit=1)
        if result and result.get("ids") and len(result["ids"]) > 0:
            # We have entries. If we want we can check count of messages...
            return {"status": "has_new_messages"} # Safest prompt to allow appending new messages
        return {"status": "not_found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/sync/status/proposal")
async def check_proposal_sync(proposal_id: str):
    """Wait and Check if a proposal exists in vector memory by proposal link Hash."""
    try:
        from FIOS.memory.retrieval import memory
        
        # Searching winning and losing collections
        w_col = memory.collection("winning_proposals")
        l_col = memory.collection("losing_proposals")
        
        res1 = w_col.get(where={"proposal_id": proposal_id}, limit=1)
        res2 = l_col.get(where={"proposal_id": proposal_id}, limit=1)
        
        if (res1 and res1.get("ids") and len(res1["ids"]) > 0) or (res2 and res2.get("ids") and len(res2["ids"]) > 0):
            return {"status": "synced"}
            
        return {"status": "not_found"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


def _money_to_float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace(",", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*([kKmM]?)", s)
    if not m:
        return 0.0
    num = float(m.group(1))
    unit = m.group(2).lower()
    if unit == "k":
        num *= 1000
    elif unit == "m":
        num *= 1_000_000
    return num


@app.post("/api/v1/opportunities/ingest")
async def opportunities_ingest(body: dict):
    """
    Store and rank scanned opportunities from the extension.
    Input: { jobs: [{title, description, budget, client_spend, client_hire_rate}] }
    """
    from FIOS.analytics.focus_engine import score_opportunity
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.jobs import Job

    jobs = body if isinstance(body, list) else body.get("jobs", [])
    if not jobs:
        return {"status": "error", "message": "jobs required"}

    ranked = []
    try:
        async with async_session_maker() as session:
            for job in jobs[:200]:
                title = (job.get("title") or "Untitled Job").strip()
                description = (job.get("description") or "").strip()
                budget = _money_to_float(job.get("budget") or job.get("client_spend") or 0)
                client_hire_rate = _money_to_float(job.get("client_hire_rate") or job.get("hire_rate") or 0)
                client_score = max(0.0, min(10.0, client_hire_rate / 10)) if client_hire_rate else None

                score = await score_opportunity(
                    job_title=title,
                    job_description=description,
                    budget=budget,
                    client_score=client_score,
                )

                fit_score = round(score.get("opportunity_score", 0), 1)
                win_probability = round((score.get("factor_scores", {}) or {}).get("win_probability", 0), 1)
                priority = (score.get("priority_level") or "LOW").lower()

                new_job = Job(
                    title=title,
                    description=description[:12000],
                    budget_type="fixed",
                    budget_min=budget,
                    budget_max=budget,
                    category="Opportunity Scan",
                    meta_data={
                        "source": "shadow_scanner",
                        "priority": priority,
                        "win_probability": win_probability,
                        "fit_score": fit_score,
                        "risk_level": score.get("risk_level"),
                        "reasoning": score.get("reasoning", []),
                    },
                )
                session.add(new_job)
                await session.flush()

                ranked.append({
                    "job_id": str(new_job.id),
                    "title": title,
                    "win_probability": win_probability,
                    "fit_score": fit_score,
                    "priority": priority,
                    "risk_level": score.get("risk_level"),
                })

            await session.commit()

        ranked.sort(key=lambda x: (x["fit_score"], x["win_probability"]), reverse=True)
        return {"status": "ok", "count": len(ranked), "opportunities": ranked}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/v1/opportunities/ranked")
async def opportunities_ranked(limit: int = 50):
    """Return ranked opportunity jobs already stored in the DB."""
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.jobs import Job
    from sqlalchemy import select

    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Job).where(Job.category == "Opportunity Scan").order_by(Job.updated_at.desc())
            )
            jobs = result.scalars().all()

        items = []
        for j in jobs:
            meta = j.meta_data or {}
            items.append({
                "job_id": str(j.id),
                "title": j.title,
                "win_probability": meta.get("win_probability", 0),
                "fit_score": meta.get("fit_score", 0),
                "priority": meta.get("priority", "low"),
                "risk_level": meta.get("risk_level", "unknown"),
                "updated_at": j.updated_at.isoformat() if j.updated_at else "",
            })

        items.sort(key=lambda x: (x["fit_score"], x["win_probability"]), reverse=True)
        return {"status": "ok", "count": len(items), "opportunities": items[:limit]}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/conversations/check")
async def check_thread(room_id: str):
    """Check if a thread exists and return metadata."""
    return await pipeline.get_thread_status(room_id)

@app.get("/api/v1/conversations/analytics")
async def aggregate_analytics():
    """Return aggregate analytics across all synced conversation threads."""
    try:
        return await pipeline.get_aggregate_analytics()
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.post("/api/v1/conversations/{room_id}/retrigger-summary")
async def retrigger_summary(room_id: str):
    """Manually force AI summary/action-item/risk re-generation for a thread."""
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.conversations import Conversation
    from sqlalchemy import select
    try:
        async with async_session_maker() as session:
            stmt = select(Conversation).where(Conversation.room_id == room_id)
            result = await session.execute(stmt)
            conv = result.scalar_one_or_none()
            if not conv:
                return {"status": "error", "message": "Thread not found"}
            messages = conv.messages_json or []

        await pipeline.trigger_ai_summary(conv.id, messages)
        return {"status": "success", "message": f"Summary re-triggered for {room_id}"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

# ---------------------------------------------------------------------------
# Phase 2: CRM Global Dashboard endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/crm/conversations")
async def crm_list_conversations(
    page: int = 1,
    per_page: int = 50,
    stage: str = "",
    has_risk: bool = False,
    search: str = "",
):
    """Return paginated conversation list for the CRM popup dashboard."""
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.conversations import Conversation
    from sqlalchemy import select
    try:
        async with async_session_maker() as session:
            stmt = select(Conversation).order_by(Conversation.updated_at.desc())
            result = await session.execute(stmt)
            all_convs = result.scalars().all()

        items = []
        for c in all_convs:
            analytics = c.analytics or {}
            conv_stage = analytics.get("conversation_stage", "active")
            risks = c.risk_flags or []

            # Filters
            if stage and conv_stage != stage:
                continue
            if has_risk and len(risks) == 0:
                continue
            if search and search.lower() not in (c.thread_name or "").lower():
                continue

            # Summary snippet (first 100 chars)
            summary_snippet = (c.summary or "")[:100]

            items.append({
                "id": str(c.id),
                "room_id": c.room_id,
                "thread_name": c.thread_name,
                "sync_status": c.sync_status,
                "message_count": c.message_count_synced,
                "last_message_preview": c.last_message_preview or "",
                "last_message_timestamp": c.last_message_timestamp or "",
                "updated_at": c.updated_at.isoformat() if c.updated_at else "",
                "conversation_stage": conv_stage,
                "client_ratio": analytics.get("client_ratio", 0),
                "response_delay_avg_mins": analytics.get("response_delay_avg_mins", 0),
                "longest_delay_mins": analytics.get("longest_response_delay_mins", 0),
                "project_duration_days": analytics.get("project_duration_days"),
                "client_score": analytics.get("client_score", {}),
                "risk_flag_count": len(risks),
                "risk_flags": risks,
                "tags": c.tags or [],
                "follow_up_at": c.follow_up_at or "",
                "notes": c.notes or "",
                "revenue_tracking": c.revenue_tracking or {},
                "summary_snippet": summary_snippet,
                "action_items": c.action_items or [],
            })

        # Pagination
        total = len(items)
        start = (page - 1) * per_page
        paginated = items[start: start + per_page]

        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "conversations": paginated,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.patch("/api/v1/crm/conversations/{room_id}")
async def crm_update_conversation(room_id: str, body: dict):
    """Update CRM fields: tags, revenue_tracking, follow_up_at, notes."""
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.conversations import Conversation
    from sqlalchemy import select, update
    allowed = {"tags", "revenue_tracking", "follow_up_at", "notes"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return {"status": "error", "message": "No valid fields to update"}
    try:
        async with async_session_maker() as session:
            stmt = update(Conversation).where(Conversation.room_id == room_id).values(**updates)
            await session.execute(stmt)
            await session.commit()
        return {"status": "success", "updated": list(updates.keys())}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/v1/crm/stats")
async def crm_stats():
    """Dashboard summary cards: thread counts, messages, risk flags."""
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.conversations import Conversation
    from sqlalchemy import select
    try:
        async with async_session_maker() as session:
            result = await session.execute(select(Conversation))
            convs = result.scalars().all()

        total_threads = len(convs)
        total_messages = sum(c.message_count_synced for c in convs)
        risk_count = sum(1 for c in convs if c.risk_flags)
        follow_ups = sum(1 for c in convs if c.follow_up_at)

        all_delays = [
            (c.analytics or {}).get("response_delay_avg_mins", 0)
            for c in convs
            if (c.analytics or {}).get("response_delay_avg_mins", 0) > 0
        ]
        avg_delay = round(sum(all_delays) / len(all_delays), 1) if all_delays else 0

        # Stage breakdown
        stages: dict[str, int] = {}
        for c in convs:
            s = (c.analytics or {}).get("conversation_stage", "active")
            stages[s] = stages.get(s, 0) + 1

        fully_synced = sum(1 for c in convs if c.sync_status == "fully_synced")

        return {
            "total_threads": total_threads,
            "total_messages": total_messages,
            "fully_synced": fully_synced,
            "open_risk_flags": risk_count,
            "pending_follow_ups": follow_ups,
            "avg_response_delay_mins": avg_delay,
            "stage_breakdown": stages,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Phase 3A: Smart Search across all thread message content
# ---------------------------------------------------------------------------

@app.get("/api/v1/crm/search")
async def crm_search(q: str = "", limit: int = 30):
    """Full-text keyword search across all synced conversation messages."""
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.conversations import Conversation
    from sqlalchemy import select
    if not q:
        return {"results": [], "query": q}
    try:
        q_lower = q.lower()
        async with async_session_maker() as session:
            result = await session.execute(select(Conversation))
            convs = result.scalars().all()

        results = []
        for c in convs:
            matches = []
            for m in (c.messages_json or []):
                text = m.get("text", "")
                if q_lower in text.lower():
                    # Highlight: surround match with **
                    idx = text.lower().find(q_lower)
                    snippet = text[max(0, idx - 40): idx + len(q) + 60]
                    matches.append({
                        "message_id": m.get("message_id", ""),
                        "sender": m.get("sender", ""),
                        "role": m.get("role", ""),
                        "time": m.get("time", ""),
                        "snippet": f"…{snippet}…",
                    })
            if matches:
                results.append({
                    "room_id": c.room_id,
                    "thread_name": c.thread_name,
                    "match_count": len(matches),
                    "matches": matches[:5],  # top 5 per thread
                })

        results.sort(key=lambda x: x["match_count"], reverse=True)
        return {"query": q, "total_threads": len(results), "results": results[:limit]}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Phase 3B: Sync History Log
# ---------------------------------------------------------------------------
import json as _json
import os as _os
_SYNC_LOG_PATH = _os.path.join(_os.path.dirname(__file__), "sync_history.json")

def _append_sync_log(entry: dict):
    """Thread-unsafe append to a small JSON log file (fine for single-process use)."""
    try:
        log = []
        if _os.path.exists(_SYNC_LOG_PATH):
            with open(_SYNC_LOG_PATH, "r") as f:
                log = _json.load(f)
        log.insert(0, entry)
        log = log[:200]  # keep last 200 events
        with open(_SYNC_LOG_PATH, "w") as f:
            _json.dump(log, f)
    except Exception:
        pass


@app.get("/api/v1/crm/sync-log")
async def crm_sync_log(limit: int = 20):
    """Return the last N sync events."""
    try:
        if not _os.path.exists(_SYNC_LOG_PATH):
            return {"events": []}
        with open(_SYNC_LOG_PATH, "r") as f:
            log = _json.load(f)
        return {"events": log[:limit]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Phase 3C: Backup & Export  (JSON + CSV)
# ---------------------------------------------------------------------------

@app.get("/api/v1/crm/export")
async def crm_export(format: str = "json"):
    """Export all conversations as JSON or CSV (streamed as file download)."""
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.conversations import Conversation
    from sqlalchemy import select
    from fastapi.responses import StreamingResponse
    import io, csv

    try:
        async with async_session_maker() as session:
            result = await session.execute(select(Conversation))
            convs = result.scalars().all()

        rows = []
        for c in convs:
            analytics = c.analytics or {}
            rows.append({
                "room_id": c.room_id,
                "thread_name": c.thread_name,
                "sync_status": c.sync_status,
                "message_count": c.message_count_synced,
                "conversation_stage": analytics.get("conversation_stage", ""),
                "client_ratio": analytics.get("client_ratio", 0),
                "response_delay_avg_mins": analytics.get("response_delay_avg_mins", 0),
                "client_score": (analytics.get("client_score") or {}).get("score", ""),
                "risk_flag_count": len(c.risk_flags or []),
                "tags": ", ".join(c.tags or []),
                "follow_up_at": c.follow_up_at or "",
                "notes": c.notes or "",
                "summary": (c.summary or "")[:200],
                "updated_at": c.updated_at.isoformat() if c.updated_at else "",
            })

        if format == "csv":
            buf = io.StringIO()
            if rows:
                writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            return StreamingResponse(
                iter([buf.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=fios_threads.csv"}
            )
        else:
            buf = io.BytesIO(_json.dumps(rows, indent=2).encode())
            return StreamingResponse(
                iter([buf.getvalue()]),
                media_type="application/json",
                headers={"Content-Disposition": "attachment; filename=fios_threads.json"}
            )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# ===========================================================================
# COPILOT API — Persistent AI Assistant
# ===========================================================================

@app.post("/api/v1/copilot/voice/extract")
async def copilot_voice_extract():
    """Extract freelancer voice profile from past wins/chats."""
    from FIOS.copilot.voice import voice_engine
    try:
        result = await voice_engine.extract_voice_profile()
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/copilot/voice/profile")
async def copilot_voice_profile():
    """Get the current freelancer voice profile."""
    from FIOS.copilot.voice import voice_engine
    try:
        profile = voice_engine.get_voice_profile()
        return {"status": "ok", "profile": profile}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/v1/copilot/conversation")
async def copilot_conversation(body: dict):
    """Full conversation assistant: summary, signals, reply suggestions."""
    from FIOS.copilot.context import copilot_context
    from FIOS.copilot.ai import copilot_ai
    try:
        room_id = body.get("room_id", "")
        strict_voice = body.get("strict_voice_mode", True)
        if not room_id:
            return {"status": "error", "message": "room_id required"}
        ctx = await copilot_context.for_conversation(room_id)
        result = await copilot_ai.conversation_assist(ctx, strict_voice_mode=strict_voice)
        result["client_score"] = ctx.get("client_score", {})
        result["analytics"] = ctx.get("analytics", {})
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.post("/api/v1/copilot/job-assist")
async def copilot_job_assist(body: dict):
    """Job page assistant: win probability, pricing, proposal drafts."""
    from FIOS.copilot.context import copilot_context
    from FIOS.copilot.ai import copilot_ai
    try:
        title = body.get("title", "")
        description = body.get("description", "")
        strict_voice = body.get("strict_voice_mode", True)
        if not description:
            return {"status": "error", "message": "description required"}
        ctx = await copilot_context.for_job_page(title, description)
        result = await copilot_ai.job_page_assist(ctx, strict_voice_mode=strict_voice)
        result["freelancer_profile"] = ctx.get("freelancer_profile", {})
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.post("/api/v1/copilot/reply-suggest")
async def copilot_reply_suggest(body: dict):
    """Strategic reply suggestion with brain context."""
    from FIOS.copilot.context import copilot_context
    from FIOS.copilot.ai import copilot_ai
    try:
        messages = body.get("messages", [])
        signals = body.get("signals", {})
        strict_voice = body.get("strict_voice_mode", True)
        if not messages:
            return {"status": "error", "message": "messages required"}
        # Build brain context from conversation
        last_sender_text = " ".join(m.get("text", "") for m in messages[-3:])
        brain_ctx = await copilot_context.build(
            page_type="conversation",
            job_title="Active conversation",
            job_description=last_sender_text[:500],
            messages=messages,
        )
        result = await copilot_ai.suggest_replies(messages, signals, strict_voice_mode=strict_voice, brain_ctx=brain_ctx)
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.post("/api/v1/copilot/proposal-rewrite")
async def copilot_proposal_rewrite(body: dict):
    """Generate a differentiated proposal with brain context."""
    from FIOS.copilot.context import copilot_context
    from FIOS.copilot.ai import copilot_ai
    try:
        draft = body.get("draft", "")
        job_description = body.get("job_description", "")
        job_title = body.get("job_title", "")
        strict_voice = body.get("strict_voice_mode", True)
        if not draft:
            return {"status": "error", "message": "draft required"}
        ctx = await copilot_context.for_proposal_writing(job_description, draft, job_title)
        rewritten = await copilot_ai.rewrite_proposal(
            draft, 
            ctx.get("winning_proposals", []), 
            job_description,
            recent_wins=ctx.get("winning_proposals", []),
            strict_voice_mode=strict_voice,
            brain_ctx=ctx
        )
        # Run evaluation for standout scoring
        eval_result = await copilot_ai.evaluate_proposal_draft(rewritten, job_description)
        return {
            "status": "ok", 
            "rewritten": rewritten, 
            "portfolio_matches": ctx.get("portfolio_matches", []),
            "standout_score": eval_result.get("standout_score"),
            "genericness_warning": eval_result.get("genericness_warning"),
            "authority_injection_highlight": eval_result.get("authority_injection_highlight"),
            "CTA_strength_feedback": eval_result.get("CTA_strength_feedback"),
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.post("/api/v1/copilot/evaluate-draft")
async def copilot_evaluate_draft(body: dict):
    """Evaluate a proposal draft for weaknesses and strengthening suggestions."""
    from FIOS.copilot.ai import copilot_ai
    try:
        draft = body.get("draft", "")
        job_description = body.get("job_description", "")
        if not draft:
            return {"status": "error", "message": "draft required"}
        result = await copilot_ai.evaluate_proposal_draft(draft, job_description)
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.post("/api/v1/copilot/watchdog")
async def copilot_watchdog_check(body: dict):
    """Detect optimal follow-up window and flag ghost risk for inactive threads."""
    from FIOS.copilot.context import copilot_context
    from FIOS.copilot.ai import copilot_ai
    try:
        room_id = body.get("room_id", "")
        if not room_id:
            return {"status": "error", "message": "room_id required"}
        ctx = await copilot_context.for_conversation(room_id)
        messages = ctx.get("messages", [])
        analytics = ctx.get("analytics", {})
        result = await copilot_ai.watchdog_check(messages, analytics)
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/v1/copilot/memory-stats")
async def copilot_memory_stats():
    """Return vector memory statistics and freelancer profile."""
    try:
        from FIOS.memory.retrieval import memory
        return {
            "status": "ok",
            "stats": memory.get_stats(),
            "profile": memory.get_freelancer_profile(),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ===========================================================================
# STRATEGY API — Win Pattern Intelligence
# ===========================================================================

@app.get("/api/v1/copilot/strategy/overview")
async def copilot_strategy_overview(force: bool = False):
    """
    Return cross-thread strategic intelligence.
    Uses cached data by default. Pass ?force=true to recompute.
    """
    from FIOS.copilot.strategy import compute_strategy, save_strategy_to_db, get_cached_strategy
    try:
        # Ensure table exists
        from FIOS.database.models.strategic_metrics import StrategicMetrics
        from FIOS.database.connection import engine
        from FIOS.database.models.base import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        if not force:
            cached = await get_cached_strategy()
            if cached:
                return {"status": "ok", "source": "cached", **cached}

        # Compute fresh
        metrics = await compute_strategy()
        await save_strategy_to_db(metrics)

        return {"status": "ok", "source": "computed", **metrics}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.post("/api/v1/copilot/strategy/refresh")
async def copilot_strategy_refresh():
    """Force-recompute strategy metrics (called after outcome changes)."""
    from FIOS.copilot.strategy import compute_strategy, save_strategy_to_db
    try:
        from FIOS.database.models.strategic_metrics import StrategicMetrics
        from FIOS.database.connection import engine
        from FIOS.database.models.base import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        metrics = await compute_strategy()
        saved = await save_strategy_to_db(metrics)
        return {"status": "ok", "saved": saved, **metrics}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# ===========================================================================
# OUTCOME INTELLIGENCE — Win Probability & Analytics
# ===========================================================================

@app.post("/api/v1/copilot/insights/win-probability")
async def copilot_win_probability(body: dict):
    """
    Compute win probability for a job.
    Input: {title, description, niche, budget, proposal_text, bid_amount, client_score}
    Returns: {win_probability, confidence_level, contributing_factors, risk_flags}
    """
    from FIOS.analytics.outcome_engine import compute_win_probability
    try:
        result = await compute_win_probability(
            job_title=body.get("title", ""),
            job_description=body.get("description", ""),
            niche=body.get("niche", ""),
            budget=body.get("budget", 0),
            proposal_text=body.get("proposal_text", ""),
            bid_amount=body.get("bid_amount", 0),
            client_score=body.get("client_score"),
        )
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/v1/copilot/insights/outcome-analytics")
async def copilot_outcome_analytics():
    """Return cross-thread outcome analytics."""
    from FIOS.analytics.outcome_engine import compute_outcome_analytics
    try:
        # Ensure table exists
        from FIOS.database.models.strategic_metrics import StrategicMetrics
        from FIOS.database.connection import engine
        from FIOS.database.models.base import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        result = await compute_outcome_analytics()
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# ===========================================================================
# PRICING INTELLIGENCE — Adaptive Bid Suggestions
# ===========================================================================

@app.post("/api/v1/copilot/insights/pricing")
async def copilot_pricing(body: dict):
    """
    Adaptive pricing suggestion for a job.
    Input: {title, description, budget, niche, win_probability}
    Returns: recommended_bid, ranges, risks, reasoning
    """
    from FIOS.analytics.pricing_engine import suggest_pricing
    try:
        result = await suggest_pricing(
            job_title=body.get("title", ""),
            job_description=body.get("description", ""),
            budget=body.get("budget", 0),
            niche=body.get("niche", ""),
            win_probability=body.get("win_probability"),
        )
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/v1/copilot/insights/proposal-performance")
async def copilot_proposal_performance():
    """Return cross-proposal performance analytics."""
    from FIOS.analytics.pricing_engine import analyze_proposal_performance
    try:
        result = await analyze_proposal_performance()
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# ===========================================================================
# BEHAVIORAL INTELLIGENCE — Negotiation & Follow-Up
# ===========================================================================

@app.get("/api/v1/copilot/insights/negotiation")
async def copilot_negotiation():
    """Cross-thread negotiation pattern analysis."""
    from FIOS.analytics.behavior_engine import analyze_negotiation_patterns
    try:
        result = await analyze_negotiation_patterns()
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.post("/api/v1/copilot/insights/followup")
async def copilot_followup(body: dict):
    """Per-thread follow-up recommendation with ghost probability."""
    from FIOS.analytics.behavior_engine import suggest_followup
    try:
        room_id = body.get("room_id", "")
        if not room_id:
            return {"status": "error", "message": "room_id required"}
        result = await suggest_followup(room_id)
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/v1/copilot/insights/followup-timing")
async def copilot_followup_timing():
    """Cross-thread follow-up timing analytics."""
    from FIOS.analytics.behavior_engine import analyze_followup_timing
    try:
        result = await analyze_followup_timing()
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# ===========================================================================
# FOCUS ALLOCATION & STRATEGY
# ===========================================================================

@app.get("/api/v1/copilot/strategy/revenue")
async def copilot_revenue():
    """Revenue concentration analysis."""
    from FIOS.analytics.focus_engine import analyze_revenue_concentration
    try:
        result = await analyze_revenue_concentration()
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.post("/api/v1/copilot/strategy/opportunity-score")
async def copilot_opportunity_score(body: dict):
    """Score any job opportunity 0-100."""
    from FIOS.analytics.focus_engine import score_opportunity
    try:
        result = await score_opportunity(
            job_title=body.get("title", ""),
            job_description=body.get("description", ""),
            niche=body.get("niche", ""),
            budget=body.get("budget", 0),
            client_score=body.get("client_score"),
            win_probability=body.get("win_probability"),
        )
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/v1/copilot/strategy/distractions")
async def copilot_distractions():
    """Identify low-ROI distraction patterns."""
    from FIOS.analytics.focus_engine import detect_distractions
    try:
        result = await detect_distractions()
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/v1/copilot/strategy/daily-brief")
async def copilot_daily_brief():
    """Daily strategic brief with priority jobs, risks, and recommendations."""
    from FIOS.analytics.focus_engine import generate_daily_brief
    try:
        result = await generate_daily_brief()
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# ===========================================================================
# CLIENT GROWTH INTELLIGENCE
# ===========================================================================

@app.get("/api/v1/copilot/strategy/growth")
async def copilot_growth_dashboard():
    """Executive growth dashboard with CLV, nurture targets, expansion pipeline."""
    from FIOS.analytics.client_growth_engine import generate_growth_dashboard
    try:
        result = await generate_growth_dashboard()
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/v1/copilot/strategy/client-profiles")
async def copilot_client_profiles():
    """All client CLV profiles sorted by lifetime value."""
    from FIOS.analytics.client_growth_engine import compute_client_profiles
    try:
        profiles = await compute_client_profiles()
        return {"status": "ok", "total_clients": len(profiles), "profiles": profiles}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.post("/api/v1/copilot/strategy/repeat-predict")
async def copilot_repeat_predict(body: dict):
    """Predict repeat probability for a specific client."""
    from FIOS.analytics.client_growth_engine import predict_repeat
    try:
        name = body.get("client_name", "")
        if not name:
            return {"status": "error", "message": "client_name required"}
        result = await predict_repeat(name)
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/v1/copilot/strategy/upsell-opportunities")
async def copilot_upsell():
    """Detect upsell/expansion opportunities across active threads."""
    from FIOS.analytics.client_growth_engine import detect_upsell_opportunities
    try:
        result = await detect_upsell_opportunities()
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/v1/copilot/strategy/client-segments")
async def copilot_client_segments():
    """Client quality segmentation into 5 tiers."""
    from FIOS.analytics.client_growth_engine import get_segmented_clients
    try:
        segments = await get_segmented_clients()
        return {"status": "ok", "segments": segments}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

        return {"status": "error", "message": str(e)}


# ===========================================================================
# NICHE DOMINANCE & MARKET POSITIONING
# ===========================================================================

@app.get("/api/v1/copilot/strategy/niche-strength")
async def copilot_niche_strength():
    """Analysis of win rate, revenue, stress, and repeats by niche."""
    from FIOS.analytics.positioning_engine import analyze_niche_strength
    try:
        result = await analyze_niche_strength()
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/v1/copilot/strategy/concentration-risk")
async def copilot_concentration_risk():
    """Detect overexposure to single niches, clients, or budget bands."""
    from FIOS.analytics.positioning_engine import analyze_concentration_risk
    try:
        result = await analyze_concentration_risk()
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/v1/copilot/strategy/portfolio-gaps")
async def copilot_portfolio_gaps():
    """Missing categories, sample recommendations, rising keywords."""
    from FIOS.analytics.positioning_engine import analyze_portfolio_gaps
    try:
        result = await analyze_portfolio_gaps()
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/v1/copilot/strategy/competition-signals")
async def copilot_competition_signals():
    """Lightweight trend analysis for emerging/declining niches."""
    from FIOS.analytics.positioning_engine import analyze_competition_signals
    try:
        result = await analyze_competition_signals()
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/v1/copilot/strategy/positioning")
async def copilot_positioning():
    """Executive summary of strategic positioning and focus niches."""
    from FIOS.analytics.positioning_engine import generate_positioning_summary
    try:
        result = await generate_positioning_summary()
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

        return {"status": "error", "message": str(e)}


# ===========================================================================
# ADAPTIVE PATTERN LEARNING
# ===========================================================================

@app.get("/api/v1/copilot/insights/adaptive")
async def copilot_adaptive_insights():
    """Returns top active patterns, declining patterns, and growth directions."""
    from FIOS.analytics.adaptive_patterns import generate_adaptive_insights
    try:
        result = await generate_adaptive_insights()
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.post("/api/v1/copilot/insights/proposal-drift")
async def copilot_proposal_drift(body: dict):
    """Detect if a new proposal deviates from historically winning patterns."""
    from FIOS.analytics.adaptive_patterns import detect_style_drift
    try:
        draft = body.get("proposal_text", "")
        bid = body.get("bid_amount", 0.0)
        result = await detect_style_drift(proposal_text=draft, bid_amount=bid)
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

        return {"status": "error", "message": str(e)}


# ===========================================================================
# DECISION SIMULATION COPILOT
# ===========================================================================

@app.post("/api/v1/copilot/simulate/strategy")
async def copilot_simulate_strategy(body: dict):
    from FIOS.copilot.simulation import simulator
    try:
        context_str = body.get("context", "")
        if not context_str:
            return {"status": "error", "message": "context required"}
        result = await simulator.simulate_strategy(context_str)
        return {"status": "ok", "simulations": result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.post("/api/v1/copilot/simulate/pricing")
async def copilot_simulate_pricing(body: dict):
    from FIOS.copilot.simulation import simulator
    try:
        job_title = body.get("job_title", "")
        job_description = body.get("job_description", "")
        base_price = body.get("base_price", 0.0)
        result = await simulator.simulate_pricing(job_title, job_description, base_price)
        return {"status": "ok", "simulations": result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.post("/api/v1/copilot/simulate/negotiation")
async def copilot_simulate_negotiation(body: dict):
    from FIOS.copilot.simulation import simulator
    try:
        messages = body.get("messages", "")
        client_pushback = body.get("client_pushback", "")
        if not client_pushback:
            return {"status": "error", "message": "client_pushback required"}
        result = await simulator.simulate_negotiation(messages, client_pushback)
        return {"status": "ok", "simulations": result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# ===========================================================================
# MEMORY RECALL ASSISTANT
# ===========================================================================

@app.post("/api/v1/copilot/memory-recall")
async def copilot_memory_recall(body: dict):
    """Fast retrieval of similar past jobs, winning proposals, and portfolio matches."""
    from FIOS.memory.recall import build_memory_recall
    try:
        title = body.get("job_title", "")
        desc = body.get("job_description", "")
        strict_voice = body.get("strict_voice_mode", True)
        if not title and not desc:
            return {"status": "error", "message": "job_title or job_description required"}
            
        result = await build_memory_recall(job_title=title, job_description=desc, strict_voice_mode=strict_voice)
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# ===========================================================================
# TELEMETRY & TRUST MEASUREMENT
# ===========================================================================

@app.post("/api/v1/telemetry/trust")
async def copilot_telemetry_trust(body: dict):
    """
    Log user interactions with Copilot outputs to measure trust.
    Expected body events: 'reply_copied', 'proposal_used', 'suggestion_overridden'
    """
    try:
        import os, json, time
        event_type = body.get("event_type", "unknown")
        details = body.get("details", {})
        
        log_entry = {
            "timestamp": time.time(),
            "event_type": event_type,
            "details": details
        }
        
        log_dir = os.path.join(settings.DATA_DIR, "analytics")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "telemetry.jsonl")
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
            
        return {"status": "ok", "logged": True}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("FIOS.main:app", host="127.0.0.1", port=8000, reload=True)
