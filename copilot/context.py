"""
FIOS Brain — Strategic Context Assembly Layer

Constructs the Brain Context Protocol object before every AI call:
{
  freelancer_profile: { niches, strongest_categories, average_price_range, win_patterns, positioning_style, authority_strength },
  historical_recall: { similar_wins, similar_losses, pricing_history_for_similar_jobs, negotiation_patterns },
  current_context:   { page_type, job_summary, client_behavior, conversation_stage, urgency_level },
  strategic_frame:   { objective, avoid, prioritize }
}
"""

from typing import Dict, Any, List, Optional
import json


class BrainContext:
    """Assembles the full Brain Context Protocol object for every AI call."""

    # ── Helper: compress messages ─────────────────────────────────────────

    def _compress_messages(self, messages: List[Dict]) -> str:
        if not messages:
            return "No messages yet."
        recent = messages[-10:]
        lines = []
        for msg in recent:
            sender = msg.get("sender", "unknown")
            text = msg.get("text", "")
            if len(text) > 250:
                text = text[:247] + "..."
            lines.append(f"{sender}: {text}")
        return "\n".join(lines)

    # ── Helper: extract pricing history ───────────────────────────────────

    def _extract_pricing(self, proposals: List[Dict]) -> List[Dict]:
        pricing = []
        for p in proposals:
            meta = p.get("metadata", {})
            bid = meta.get("bid_amount")
            if bid:
                try:
                    pricing.append({
                        "amount": float(bid),
                        "outcome": meta.get("outcome", "unknown"),
                        "job_title": meta.get("job_title", "")
                    })
                except (ValueError, TypeError):
                    pass
        return pricing

    # ── Helper: extract negotiation patterns ──────────────────────────────

    def _extract_negotiations(self, threads: List[Dict]) -> List[str]:
        patterns = []
        for t in threads:
            meta = t.get("metadata", {})
            if "risk_flags" in meta:
                patterns.extend(meta.get("risk_flags", []))
            if "action_items" in meta:
                patterns.append(str(meta.get("action_items")))
        return list(set([str(p) for p in patterns if p]))[:5]

    # ── Core: Build Brain Context ─────────────────────────────────────────

    async def build(
        self,
        page_type: str,           # "job" | "conversation" | "invitation" | "proposal"
        job_title: str = "",
        job_description: str = "",
        messages: Optional[List[Dict]] = None,
        client_data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Assembles the full Brain Context Protocol object.
        This is called before EVERY AI interaction.
        """
        from memory.retrieval import memory

        # ── 1. Freelancer Profile ─────────────────────────────────────
        raw_profile = memory.get_freelancer_profile()
        freelancer_profile = {
            "niches": raw_profile.get("niches", []),
            "strongest_categories": raw_profile.get("strongest_categories", raw_profile.get("niches", [])),
            "average_price_range": raw_profile.get("average_price_range", "Unknown"),
            "win_patterns": raw_profile.get("win_patterns", []),
            "positioning_style": raw_profile.get("positioning_style", "Professional and specific"),
            "authority_strength": raw_profile.get("authority_strength", "Moderate"),
            "total_proposals": raw_profile.get("total_proposals", 0),
            "win_rate_pct": raw_profile.get("win_rate_pct", 0),
        }

        # ── 2. Historical Recall via Vector Search ────────────────────
        query = f"{job_title}\n{job_description[:500]}"
        if messages:
            query += f"\n{self._compress_messages(messages)[-300:]}"

        similar_wins_raw = []
        similar_losses_raw = []
        similar_threads_raw = []

        try:
            similar_wins_raw = memory.search_similar("winning_proposals", query, n=3, max_distance=1.0)
            similar_losses_raw = memory.search_similar("losing_proposals", query, n=2, max_distance=1.1)
            if page_type == "conversation":
                similar_threads_raw = memory.search_similar("conversations", query, n=2, max_distance=1.0)
        except Exception as e:
            print(f"[BrainContext] Vector search error: {e}")

        similar_wins = []
        for w in similar_wins_raw:
            meta = w.get("metadata", {})
            doc = w.get("document", "")
            similar_wins.append({
                "title": meta.get("job_title", "Unknown"),
                "bid": meta.get("bid_amount", "unknown"),
                "outcome": "won",
                "proposal_snippet": doc[:300] + "..." if len(doc) > 300 else doc
            })

        similar_losses = []
        for l in similar_losses_raw:
            meta = l.get("metadata", {})
            doc = l.get("document", "")
            similar_losses.append({
                "title": meta.get("job_title", "Unknown"),
                "bid": meta.get("bid_amount", "unknown"),
                "outcome": "lost",
                "proposal_snippet": doc[:200] + "..." if len(doc) > 200 else doc
            })

        historical_recall = {
            "similar_wins": similar_wins,
            "similar_losses": similar_losses,
            "pricing_history_for_similar_jobs": self._extract_pricing(similar_wins_raw + similar_losses_raw),
            "negotiation_patterns": self._extract_negotiations(similar_threads_raw),
        }

        # ── 3. Current Context ────────────────────────────────────────
        conversation_stage = "unknown"
        urgency_level = "normal"
        client_behavior = client_data or {"note": "No deep client data available"}

        if messages:
            total = len(messages)
            if total <= 3:
                conversation_stage = "opening"
            elif total <= 10:
                conversation_stage = "negotiation"
            else:
                conversation_stage = "ongoing"

            # Detect urgency signals
            last_msgs = " ".join(m.get("text", "").lower() for m in messages[-3:])
            urgency_words = {"urgent", "asap", "immediately", "rush", "deadline", "right now", "today"}
            if any(w in last_msgs for w in urgency_words):
                urgency_level = "high"

        current_context = {
            "page_type": page_type,
            "job_summary": f"Title: {job_title}\nDescription: {job_description[:800]}" if job_title else "Embedded in conversation",
            "client_behavior": client_behavior,
            "conversation_stage": conversation_stage,
            "urgency_level": urgency_level,
            "recent_conversation": self._compress_messages(messages) if messages else None,
        }

        # ── 4. Strategic Frame ────────────────────────────────────────
        strategic_frame = {
            "objective": "win_high_value_job",
            "avoid": [
                "underpricing",
                "generic_positioning",
                "desperate_tone",
                "overcommitting_on_scope",
            ],
            "prioritize": [
                "authority_and_specificity",
                "differentiation_from_competitors",
                "ROI_framing_for_client",
                "scarcity_positioning",
            ],
        }

        return {
            "freelancer_profile": freelancer_profile,
            "historical_recall": historical_recall,
            "current_context": current_context,
            "strategic_frame": strategic_frame,
            # Keep raw data for backward compat
            "messages": messages,
        }

    # ── Legacy Adapters (called from main.py) ─────────────────────────────

    async def for_job_page(self, title: str, description: str) -> Dict[str, Any]:
        ctx = await self.build(page_type="job", job_title=title, job_description=description)
        # Flatten some keys for backward compat with ai.py
        ctx["title"] = title
        ctx["description"] = description
        ctx["freelancer_profile_flat"] = ctx["freelancer_profile"]
        ctx["similar_winning_proposals"] = [
            {"text": w["proposal_snippet"]} for w in ctx["historical_recall"]["similar_wins"]
        ]
        ctx["similar_losing_proposals"] = [
            {"text": l["proposal_snippet"]} for l in ctx["historical_recall"]["similar_losses"]
        ]
        return ctx

    async def for_conversation(self, room_id: str) -> Dict[str, Any]:
        from database.connection import async_session_maker
        from database.models.conversations import Conversation
        from sqlalchemy import select

        try:
            async with async_session_maker() as session:
                stmt = select(Conversation).where(Conversation.room_id == room_id)
                result = await session.execute(stmt)
                conv = result.scalar_one_or_none()

            if not conv:
                return {}

            title = conv.thread_name or ""
            msgs = conv.messages_json or []
            client_score = conv.analytics.get("client_score") if conv.analytics else None

            ctx = await self.build(
                page_type="conversation",
                job_title=title,
                job_description="Embedded in conversation thread.",
                messages=msgs,
                client_data=client_score,
            )
            ctx["room_id"] = room_id
            ctx["analytics"] = conv.analytics or {}
            ctx["risk_flags"] = conv.risk_flags or []
            return ctx

        except Exception as e:
            print(f"[BrainContext] Conversation error: {e}")
            return {}

    async def for_invitation(self, title: str, description: str) -> Dict[str, Any]:
        ctx = await self.build(page_type="invitation", job_title=title, job_description=description)
        ctx["is_invitation"] = True
        return ctx

    async def for_proposal_writing(self, job_description: str, draft: str = "", job_title: str = "") -> Dict[str, Any]:
        ctx = await self.build(page_type="proposal", job_title=job_title, job_description=job_description)
        ctx["current_draft"] = draft
        ctx["winning_proposals"] = [
            {"text": w["proposal_snippet"]} for w in ctx["historical_recall"]["similar_wins"]
        ]
        return ctx


# Global instance
copilot_context = BrainContext()
