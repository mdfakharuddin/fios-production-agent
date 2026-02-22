"""
FIOS Background Embedder

Scans the database for un-embedded conversations, proposals, and jobs,
and embeds them into ChromaDB vector collections.

Called:
  1. On server startup (full scan)
  2. After each new ingest (incremental)
"""

from typing import Set


async def run_full_embed():
    """
    Scan all conversations, proposals, and jobs in the database.
    Embed anything not yet in the vector store.
    """
    from database.connection import async_session_maker
    from database.models.conversations import Conversation
    from database.models.jobs import Job
    from database.models.proposals import Proposal
    from memory.retrieval import memory
    from sqlalchemy import select

    stats = {"conversations": 0, "proposals": 0, "jobs": 0}

    try:
        async with async_session_maker() as session:
            # ── Conversations ───────────────────────────────────────────
            result = await session.execute(select(Conversation))
            convs = result.scalars().all()

            for c in convs:
                messages = c.messages_json or []
                if messages:
                    added = memory.embed_conversation(c.room_id, messages)
                    stats["conversations"] += added

            # ── Jobs ────────────────────────────────────────────────────
            result = await session.execute(select(Job))
            jobs = result.scalars().all()

            for j in jobs:
                added = memory.embed_job(
                    str(j.id),
                    j.title or "",
                    j.description or "",
                )
                stats["jobs"] += added

            # ── Proposals ───────────────────────────────────────────────
            result = await session.execute(select(Proposal))
            proposals = result.scalars().all()

            for p in proposals:
                outcome = "pending"
                if hasattr(p, "status"):
                    status_val = str(p.status).lower()
                    if "hired" in status_val or "won" in status_val or "active" in status_val:
                        outcome = "won"
                    elif "lost" in status_val or "rejected" in status_val or "cancelled" in status_val:
                        outcome = "lost"

                job_title = ""
                if p.job and hasattr(p.job, "title"):
                    job_title = p.job.title

                added = memory.embed_proposal(
                    str(p.id),
                    p.cover_letter or "",
                    outcome=outcome,
                    job_title=job_title,
                )
                stats["proposals"] += added

    except Exception as e:
        print(f"[Embedder] Error during full embed: {e}")
        import traceback
        traceback.print_exc()

    print(f"[Embedder] Full embed complete: {stats}")
    return stats


async def embed_conversation_incremental(room_id: str, messages: list):
    """Embed a single conversation after ingest (called from pipeline)."""
    from memory.retrieval import memory
    try:
        added = memory.embed_conversation(room_id, messages)
        print(f"[Embedder] Incremental embed for {room_id}: {added} chunks")
        return added
    except Exception as e:
        print(f"[Embedder] Error embedding {room_id}: {e}")
        return 0


async def embed_job_incremental(job_id: str, title: str, description: str):
    """Embed a single job after ingest."""
    from memory.retrieval import memory
    try:
        return memory.embed_job(job_id, title, description)
    except Exception:
        return 0


async def embed_proposal_incremental(proposal_id: str, text: str, outcome: str = "pending", job_title: str = ""):
    """Embed a single proposal after ingest."""
    from memory.retrieval import memory
    try:
        return memory.embed_proposal(proposal_id, text, outcome, job_title)
    except Exception:
        return 0
