"""
FIOS Behavioral Revenue Engine

Provides:
  1. Negotiation Pattern Analyzer — cross-thread discount/scope/revision patterns
  2. Real-Time Negotiation Detector — detects live negotiation signals, suggests strategy replies
  3. Follow-Up Timing Optimizer — optimal follow-up window, ghost probability

Design constraints:
  - Deterministic (no ML)
  - Explainable (all outputs include reasoning)
  - Never auto-sends messages
  - Revenue-maximizing priority
"""

import re
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict


# ═══════════════════════════════════════════════════════════════════════════
# NEGOTIATION SIGNAL DETECTION (keyword + pattern based)
# ═══════════════════════════════════════════════════════════════════════════

PRICE_OBJECTION_PATTERNS = [
    r"too\s+expensive", r"over\s*(?:our|my)?\s*budget", r"can\s+you\s+(?:lower|reduce|discount)",
    r"best\s+price", r"lower\s+(?:the\s+)?(?:rate|price|cost|bid)",
    r"(?:is|that'?s)\s+(?:a\s+(?:bit|little)\s+)?(?:high|steep|much)",
    r"budget\s+(?:is|only|around)", r"(?:we|i)\s+(?:can(?:not|'t)?|don'?t)\s+(?:afford|pay)",
    r"any\s+(?:discount|flexibility)", r"(?:negotiate|negotiable)",
    r"cheaper", r"less\s+(?:than|expensive)",
]

SCOPE_CREEP_PATTERNS = [
    r"(?:also|additionally|one\s+more)\s+(?:need|want|can\s+you)",
    r"(?:add|include|throw\s+in)\s+(?:this|that|these|the)",
    r"while\s+(?:you(?:'re)?|we(?:'re)?)\s+at\s+it",
    r"extra\s+(?:feature|page|screen|section|revision)",
    r"(?:another|additional)\s+(?:round|set|batch)",
    r"(?:small|quick|minor)\s+(?:change|tweak|addition|update)",
    r"scope\s+(?:change|expansion|increase)",
]

REVISION_ESCALATION_PATTERNS = [
    r"(?:not|don'?t)\s+(?:quite\s+)?(?:what|how)\s+(?:i|we)\s+(?:wanted|expected|imagined)",
    r"(?:another|one\s+more|additional)\s+(?:round|revision|iteration)",
    r"(?:needs?|require)\s+(?:more\s+)?(?:changes|revisions|adjustments)",
    r"(?:redo|redo\s+this|start\s+over|from\s+scratch)",
    r"(?:completely|totally)\s+(?:different|wrong|off)",
]

PAYMENT_DELAY_PATTERNS = [
    r"(?:pay|payment)\s+(?:later|next\s+week|next\s+month|after|when)",
    r"(?:hold|wait)\s+(?:on\s+)?(?:the\s+)?payment",
    r"(?:escrow|milestone)\s+(?:not\s+)?(?:funded|released)",
    r"(?:haven'?t|didn'?t)\s+(?:(?:been\s+)?paid|receive)",
    r"(?:invoice|billing)\s+(?:issue|problem|delay)",
]


def _detect_signals(text: str) -> Dict[str, bool]:
    """Detect negotiation signals in a message text."""
    text_lower = text.lower()
    return {
        "price_objection": any(re.search(p, text_lower) for p in PRICE_OBJECTION_PATTERNS),
        "scope_creep": any(re.search(p, text_lower) for p in SCOPE_CREEP_PATTERNS),
        "revision_escalation": any(re.search(p, text_lower) for p in REVISION_ESCALATION_PATTERNS),
        "payment_delay": any(re.search(p, text_lower) for p in PAYMENT_DELAY_PATTERNS),
    }


def _has_negotiation(signals: Dict[str, bool]) -> bool:
    return any(signals.values())


def _rate(wins: int, total: int) -> float:
    return round((wins / total) * 100, 1) if total > 0 else 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 1. NEGOTIATION PATTERN ANALYZER (cross-thread)
# ═══════════════════════════════════════════════════════════════════════════

async def analyze_negotiation_patterns() -> Dict[str, Any]:
    """
    Analyze all historical conversations for negotiation patterns.
    Returns: discount stats, strategy effectiveness, revenue impact.
    """
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.jobs import Job
    from FIOS.database.models.conversations import Conversation
    from FIOS.database.models.proposals import Proposal
    from FIOS.analytics.outcome_engine import normalize_outcome, RESOLVED_OUTCOMES
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    t0 = time.time()

    async with async_session_maker() as session:
        result = await session.execute(
            select(Job).options(
                selectinload(Job.proposals),
                selectinload(Job.conversations),
            )
        )
        jobs = result.scalars().all()

    # ── Analyze each job+conversation pair ──────────────────────────────
    total_resolved = 0
    with_negotiation = 0
    without_negotiation = 0
    wins_with_negotiation = 0
    wins_without_negotiation = 0

    negotiation_patterns = []
    all_discounts_won = []
    all_discounts_lost = []
    revenue_with_discount = 0
    revenue_without_discount = 0
    revenue_lost_to_discounts = 0

    # Signal type counters
    signal_counts = defaultdict(lambda: {"total": 0, "wins": 0})

    # Strategy buckets (detected from freelancer replies after negotiation)
    reply_after_negotiation = defaultdict(lambda: {"total": 0, "wins": 0})

    for job in jobs:
        outcome = normalize_outcome(str(job.outcome) if job.outcome else "pending")
        if outcome not in RESOLVED_OUTCOMES:
            continue

        is_won = outcome == "WON"
        total_resolved += 1
        budget = max(job.budget_min or 0, job.budget_max or 0)

        # Scan all conversations for this job
        job_had_negotiation = False
        job_signals = set()

        for conv in (job.conversations or []):
            messages = conv.messages_json or []

            for i, msg in enumerate(messages):
                sender = (msg.get("sender") or "").lower()
                text = msg.get("text") or ""

                # Only detect signals from CLIENT messages
                if "you" in sender or "freelancer" in sender or "me" in sender:
                    continue

                signals = _detect_signals(text)
                if _has_negotiation(signals):
                    job_had_negotiation = True
                    for sig, active in signals.items():
                        if active:
                            job_signals.add(sig)
                            signal_counts[sig]["total"] += 1
                            if is_won:
                                signal_counts[sig]["wins"] += 1

                    # Check the next freelancer reply (if any) to classify strategy
                    for j in range(i + 1, min(i + 3, len(messages))):
                        reply = messages[j]
                        reply_sender = (reply.get("sender") or "").lower()
                        reply_text = (reply.get("text") or "").lower()

                        if "you" in reply_sender or "freelancer" in reply_sender or "me" in reply_sender:
                            # Classify reply strategy
                            if any(w in reply_text for w in ["value", "quality", "experience", "expertise", "worth", "investment"]):
                                strategy = "value_reinforcement"
                            elif any(w in reply_text for w in ["scope", "reduce", "fewer", "simplify", "trim", "cut"]):
                                strategy = "scope_adjustment"
                            elif any(w in reply_text for w in ["discount", "lower", "reduce the", "special", "deal"]):
                                strategy = "structured_discount"
                            else:
                                strategy = "other"

                            reply_after_negotiation[strategy]["total"] += 1
                            if is_won:
                                reply_after_negotiation[strategy]["wins"] += 1
                            break

        # Track negotiation vs no-negotiation outcomes
        if job_had_negotiation:
            with_negotiation += 1
            if is_won:
                wins_with_negotiation += 1
        else:
            without_negotiation += 1
            if is_won:
                wins_without_negotiation += 1

        # Track discount impact
        for prop in (job.proposals or []):
            bid = prop.bid_amount or 0
            if budget > 0 and bid > 0:
                discount_pct = round(((budget - bid) / budget) * 100, 1)
                gave_discount = discount_pct > 5  # More than 5% below budget

                if is_won:
                    if gave_discount:
                        all_discounts_won.append(discount_pct)
                        revenue_with_discount += bid
                        revenue_lost_to_discounts += (budget - bid)
                    else:
                        revenue_without_discount += bid
                else:
                    if gave_discount:
                        all_discounts_lost.append(discount_pct)

        # Build pattern record
        if job_had_negotiation:
            negotiation_patterns.append({
                "job_id": str(job.id),
                "outcome": outcome,
                "signals": list(job_signals),
                "budget": budget,
                "bid": (job.proposals[0].bid_amount if job.proposals else 0),
            })

    # ── Compute aggregates ──────────────────────────────────────────────
    avg_discount = round(
        sum(all_discounts_won) / len(all_discounts_won), 1
    ) if all_discounts_won else 0.0

    # Win rates
    discount_win_rate = _rate(wins_with_negotiation, with_negotiation)
    no_discount_win_rate = _rate(wins_without_negotiation, without_negotiation)

    # Most effective strategy
    strategy_effectiveness = {}
    best_strategy = "insufficient_data"
    best_rate = 0
    for strat, counts in reply_after_negotiation.items():
        rate = _rate(counts["wins"], counts["total"])
        strategy_effectiveness[strat] = {
            "wins": counts["wins"],
            "total": counts["total"],
            "rate": rate,
        }
        if rate > best_rate and counts["total"] >= 2:
            best_rate = rate
            best_strategy = strat

    # Signal effectiveness
    signal_effectiveness = {}
    for sig, counts in signal_counts.items():
        signal_effectiveness[sig] = {
            "occurrences": counts["total"],
            "wins_after": counts["wins"],
            "win_rate": _rate(counts["wins"], counts["total"]),
        }

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "total_resolved": total_resolved,
        "with_negotiation": with_negotiation,
        "without_negotiation": without_negotiation,
        "average_discount_rate": avg_discount,
        "discount_vs_no_discount_win_rate": {
            "with_discount": {"wins": wins_with_negotiation, "total": with_negotiation, "rate": discount_win_rate},
            "without_discount": {"wins": wins_without_negotiation, "total": without_negotiation, "rate": no_discount_win_rate},
        },
        "most_effective_negotiation_strategy": best_strategy,
        "strategy_effectiveness": strategy_effectiveness,
        "scope_reduction_success_rate": strategy_effectiveness.get("scope_adjustment", {}).get("rate", 0),
        "revenue_loss_from_discounting": round(revenue_lost_to_discounts, 2),
        "revenue_with_discount": round(revenue_with_discount, 2),
        "revenue_without_discount": round(revenue_without_discount, 2),
        "signal_effectiveness": signal_effectiveness,
        "negotiation_patterns": negotiation_patterns[:20],
        "compute_time_ms": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. REAL-TIME NEGOTIATION DETECTOR
# ═══════════════════════════════════════════════════════════════════════════

async def detect_negotiation_live(messages: List[dict]) -> Dict[str, Any]:
    """
    Detect live negotiation signals in recent messages and suggest strategy replies.
    Called from conversation_assist for real-time detection.
    """
    t0 = time.time()

    # Check last 5 client messages for negotiation signals
    client_msgs = [m for m in messages[-8:] if not _is_freelancer(m.get("sender", ""))]
    detected = {
        "price_objection": False,
        "scope_creep": False,
        "revision_escalation": False,
        "payment_delay": False,
    }
    trigger_messages = []

    for msg in client_msgs:
        text = msg.get("text", "")
        signals = _detect_signals(text)
        for sig, active in signals.items():
            if active:
                detected[sig] = True
                trigger_messages.append({"signal": sig, "text": text[:120]})

    is_negotiation = _has_negotiation(detected)

    # Load historical effectiveness for reply suggestions
    strategy_probs = {"value_reinforcement": 55, "scope_adjustment": 50, "structured_discount": 45}
    try:
        cached = await _get_cached_negotiation_stats()
        if cached:
            for strat in strategy_probs:
                hist = cached.get("strategy_effectiveness", {}).get(strat, {})
                if hist.get("total", 0) >= 2:
                    strategy_probs[strat] = hist["rate"]
    except Exception:
        pass

    # Build strategy replies
    strategy_replies = []
    if is_negotiation:
        if detected["price_objection"]:
            strategy_replies = [
                {
                    "type": "value_reinforcement",
                    "label": "💎 Reinforce Value",
                    "text": "I understand budget is a concern. What you're getting here is [specific value]. My experience with similar projects ensures fast delivery and fewer revisions, which actually saves money in the long run.",
                    "estimated_success_pct": strategy_probs["value_reinforcement"],
                    "revenue_impact": "preserves_full_rate",
                },
                {
                    "type": "scope_adjustment",
                    "label": "📐 Adjust Scope",
                    "text": "I can work within your budget if we adjust the scope. For example, we could [specific reduction]. This keeps quality high while fitting your investment range.",
                    "estimated_success_pct": strategy_probs["scope_adjustment"],
                    "revenue_impact": "preserves_hourly_rate",
                },
                {
                    "type": "structured_discount",
                    "label": "🤝 Conditional Discount",
                    "text": "I can offer a [X]% adjustment if we agree on [condition: e.g., milestone upfront, long-term engagement, fixed revisions]. This way we both benefit.",
                    "estimated_success_pct": strategy_probs["structured_discount"],
                    "revenue_impact": "reduced_but_secured",
                },
            ]
        elif detected["scope_creep"]:
            strategy_replies = [
                {
                    "type": "value_reinforcement",
                    "label": "📋 Define Boundaries",
                    "text": "Great idea! That would be a separate task from the original scope. I can quote it separately or we can discuss adding it as a follow-up milestone.",
                    "estimated_success_pct": strategy_probs["value_reinforcement"],
                    "revenue_impact": "additional_revenue",
                },
                {
                    "type": "scope_adjustment",
                    "label": "🔄 Trade-Off",
                    "text": "I can include that if we trade it for [existing item]. This keeps us on timeline and budget while getting you what matters most.",
                    "estimated_success_pct": strategy_probs["scope_adjustment"],
                    "revenue_impact": "neutral",
                },
                {
                    "type": "structured_discount",
                    "label": "📈 Upsell",
                    "text": "Happy to add that! It would be an additional [amount/hours]. I can bundle it at a slight discount since we're already working together.",
                    "estimated_success_pct": strategy_probs["structured_discount"],
                    "revenue_impact": "increased_revenue",
                },
            ]
        elif detected["revision_escalation"]:
            strategy_replies = [
                {
                    "type": "value_reinforcement",
                    "label": "✅ Clarify Direction",
                    "text": "I want to make sure we're aligned. Could you share specific examples of what you're looking for? This helps me nail it in the next round.",
                    "estimated_success_pct": 60,
                    "revenue_impact": "preserves_full_rate",
                },
                {
                    "type": "scope_adjustment",
                    "label": "🎯 Focus Feedback",
                    "text": "Let's focus on the top 3 changes that matter most. I'll prioritize those in the next revision to make the best use of our remaining rounds.",
                    "estimated_success_pct": 55,
                    "revenue_impact": "preserves_full_rate",
                },
                {
                    "type": "structured_discount",
                    "label": "📝 Extra Round",
                    "text": "I'm happy to do an additional revision round. Since this goes beyond our original agreement, I can add it for [small amount] to cover the extra time.",
                    "estimated_success_pct": 45,
                    "revenue_impact": "additional_revenue",
                },
            ]

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "is_negotiation": is_negotiation,
        "detected_signals": detected,
        "trigger_messages": trigger_messages[:5],
        "strategy_replies": strategy_replies,
        "compute_time_ms": elapsed,
    }


def _is_freelancer(sender: str) -> bool:
    s = sender.lower()
    return any(w in s for w in ["you", "me", "freelancer", "self"])


async def _get_cached_negotiation_stats() -> Optional[Dict]:
    """Quick cache check for negotiation stats."""
    from FIOS.copilot.strategy import get_cached_strategy
    cached = await get_cached_strategy()
    return cached or {}


# ═══════════════════════════════════════════════════════════════════════════
# 3. FOLLOW-UP TIMING OPTIMIZER
# ═══════════════════════════════════════════════════════════════════════════

async def analyze_followup_timing() -> Dict[str, Any]:
    """
    Cross-thread timing analysis: optimal follow-up windows,
    ghost patterns, time-to-hire metrics.
    """
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.conversations import Conversation
    from FIOS.database.models.jobs import Job
    from FIOS.analytics.outcome_engine import normalize_outcome
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    t0 = time.time()

    async with async_session_maker() as session:
        result = await session.execute(
            select(Conversation).options(selectinload(Conversation.job))
        )
        convs = result.scalars().all()

    # ── Parse message timestamps ────────────────────────────────────────
    timing_records = []

    for conv in convs:
        messages = conv.messages_json or []
        if len(messages) < 2:
            continue

        job = conv.job
        outcome = "ONGOING"
        if job:
            outcome = normalize_outcome(str(job.outcome) if job.outcome else "pending")

        # Calculate reply gaps
        reply_gaps_hours = []
        last_client_msg_time = None
        last_freelancer_msg_time = None
        last_msg_time = None

        for msg in messages:
            ts_str = msg.get("timestamp") or msg.get("time") or ""
            if not ts_str:
                continue

            ts = _parse_ts(ts_str)
            if not ts:
                continue

            sender = (msg.get("sender") or "").lower()
            is_client = not _is_freelancer(sender)

            if is_client:
                last_client_msg_time = ts
                if last_freelancer_msg_time:
                    gap = (ts - last_freelancer_msg_time).total_seconds() / 3600
                    reply_gaps_hours.append({"type": "client_reply", "hours": gap})
            else:
                last_freelancer_msg_time = ts
                if last_client_msg_time:
                    gap = (ts - last_client_msg_time).total_seconds() / 3600
                    reply_gaps_hours.append({"type": "freelancer_reply", "hours": gap})

            last_msg_time = ts

        # Days since last message
        days_inactive = 0
        if last_msg_time:
            days_inactive = (datetime.now() - last_msg_time).days

        # Average client reply time
        client_replies = [g["hours"] for g in reply_gaps_hours if g["type"] == "client_reply" and g["hours"] > 0]
        avg_client_reply_hours = round(sum(client_replies) / len(client_replies), 1) if client_replies else 0

        timing_records.append({
            "room_id": conv.room_id or "",
            "thread_name": conv.thread_name or "",
            "outcome": outcome,
            "is_won": outcome == "WON",
            "is_ghosted": outcome == "GHOSTED",
            "message_count": len(messages),
            "days_inactive": days_inactive,
            "avg_client_reply_hours": avg_client_reply_hours,
            "reply_gaps": reply_gaps_hours,
        })

    # ── Aggregate timing stats ──────────────────────────────────────────
    won_records = [r for r in timing_records if r["is_won"]]
    ghosted_records = [r for r in timing_records if r["is_ghosted"]]
    active_records = [r for r in timing_records if r["outcome"] == "ONGOING"]

    # Average client reply time (across all won threads)
    all_client_times = [r["avg_client_reply_hours"] for r in won_records if r["avg_client_reply_hours"] > 0]
    avg_reply_time = round(sum(all_client_times) / len(all_client_times), 1) if all_client_times else 0

    # Time-to-hire patterns (using gap analysis from won jobs)
    # Ghost patterns
    ghost_inactive_days = [r["days_inactive"] for r in ghosted_records]
    avg_ghost_days = round(sum(ghost_inactive_days) / len(ghost_inactive_days), 1) if ghost_inactive_days else 14

    # Win rate by follow-up timing
    followup_timing_buckets = defaultdict(lambda: {"wins": 0, "total": 0})
    for r in timing_records:
        if r["outcome"] not in ("WON", "LOST", "GHOSTED"):
            continue
        # Use avg freelancer reply time as proxy for follow-up speed
        freelancer_replies = [g["hours"] for g in r["reply_gaps"] if g["type"] == "freelancer_reply" and g["hours"] > 0]
        if freelancer_replies:
            avg_followup = sum(freelancer_replies) / len(freelancer_replies)
            if avg_followup < 2:
                bucket = "under_2h"
            elif avg_followup < 8:
                bucket = "2h_to_8h"
            elif avg_followup < 24:
                bucket = "8h_to_24h"
            elif avg_followup < 72:
                bucket = "1d_to_3d"
            else:
                bucket = "over_3d"

            followup_timing_buckets[bucket]["total"] += 1
            if r["is_won"]:
                followup_timing_buckets[bucket]["wins"] += 1

    win_by_timing = {}
    for bucket, s in followup_timing_buckets.items():
        win_by_timing[bucket] = {
            "wins": s["wins"],
            "total": s["total"],
            "rate": _rate(s["wins"], s["total"]),
        }

    # Optimal follow-up window: timing bucket with highest win rate
    optimal_window = "2h_to_8h"  # Default
    best_rate = 0
    for bucket, data in win_by_timing.items():
        if data["total"] >= 2 and data["rate"] > best_rate:
            best_rate = data["rate"]
            optimal_window = bucket

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "avg_client_reply_time_hours": avg_reply_time,
        "avg_ghost_inactivity_days": avg_ghost_days,
        "win_rate_by_followup_timing": win_by_timing,
        "optimal_follow_up_window": optimal_window,
        "total_active_threads": len(active_records),
        "total_ghosted_threads": len(ghosted_records),
        "compute_time_ms": elapsed,
    }


async def suggest_followup(room_id: str) -> Dict[str, Any]:
    """
    For a specific conversation, compute follow-up recommendation.
    Returns: timing advice, ghost probability, suggested message.
    """
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.conversations import Conversation
    from sqlalchemy import select

    t0 = time.time()

    async with async_session_maker() as session:
        result = await session.execute(
            select(Conversation).where(Conversation.room_id == room_id)
        )
        conv = result.scalar_one_or_none()

    if not conv:
        return {"status": "not_found", "message": "Thread not found"}

    messages = conv.messages_json or []
    if not messages:
        return {"status": "no_messages", "message": "No messages in thread"}

    # Parse last message time
    last_msg = messages[-1]
    last_ts = _parse_ts(last_msg.get("timestamp") or last_msg.get("time") or "")
    last_sender = (last_msg.get("sender") or "").lower()
    is_waiting_for_client = _is_freelancer(last_sender)

    days_inactive = 0
    hours_inactive = 0
    if last_ts:
        delta = datetime.now() - last_ts
        days_inactive = delta.days
        hours_inactive = round(delta.total_seconds() / 3600, 1)

    # Ghost probability scoring
    ghost_score = 0
    risk_factors = []

    if days_inactive >= 14:
        ghost_score = 85
        risk_factors.append(f"No activity for {days_inactive} days")
    elif days_inactive >= 7:
        ghost_score = 60
        risk_factors.append(f"Inactive for {days_inactive} days")
    elif days_inactive >= 3:
        ghost_score = 35
        risk_factors.append(f"Inactive for {days_inactive} days")
    elif hours_inactive >= 48:
        ghost_score = 20
        risk_factors.append(f"No reply in {hours_inactive:.0f} hours")
    else:
        ghost_score = 5

    if is_waiting_for_client:
        ghost_score = min(100, ghost_score + 15)
        risk_factors.append("Waiting for client reply")
    else:
        ghost_score = max(0, ghost_score - 20)
        risk_factors.append("Client is waiting for your reply")

    # Message count factor
    if len(messages) < 3:
        ghost_score = min(100, ghost_score + 10)
        risk_factors.append("Very early in conversation (< 3 messages)")

    # ── Follow-up timing recommendation ─────────────────────────────────
    if is_waiting_for_client:
        if hours_inactive < 12:
            timing = "Wait — too early to follow up"
            urgency = "low"
        elif hours_inactive < 48:
            timing = "Good window — send a friendly check-in"
            urgency = "medium"
        elif hours_inactive < 168:
            timing = "Overdue — follow up now with value add"
            urgency = "high"
        else:
            timing = "Late — last chance follow-up or move on"
            urgency = "critical"
    else:
        timing = "Client is waiting — reply as soon as possible"
        urgency = "high" if hours_inactive > 24 else "medium"

    # ── Suggested follow-up messages ────────────────────────────────────
    follow_up_suggestions = []
    thread_name = conv.thread_name or "this project"

    if is_waiting_for_client and hours_inactive >= 12:
        follow_up_suggestions = [
            {
                "type": "friendly_check",
                "label": "👋 Friendly Check-In",
                "text": f"Hi! Just checking in on {thread_name}. Let me know if you have any questions or if there's anything else you need from my side.",
            },
            {
                "type": "value_add",
                "label": "💡 Value Add",
                "text": f"Hi! While reviewing {thread_name}, I had an idea that could improve the outcome. Would love to share it when you have a moment.",
            },
            {
                "type": "soft_close",
                "label": "🎯 Soft Close",
                "text": f"Hi! I have availability opening up next week. If you'd like to move forward with {thread_name}, now would be a great time to get started. Let me know!",
            },
        ]

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "room_id": room_id,
        "thread_name": conv.thread_name or "",
        "days_inactive": days_inactive,
        "hours_inactive": hours_inactive,
        "is_waiting_for_client": is_waiting_for_client,
        "ghost_probability": ghost_score,
        "ghost_risk_factors": risk_factors,
        "follow_up_timing": timing,
        "urgency": urgency,
        "follow_up_suggestions": follow_up_suggestions,
        "compute_time_ms": elapsed,
    }


def _parse_ts(ts_str: str) -> Optional[datetime]:
    """Try multiple timestamp formats."""
    if not ts_str:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%b %d, %Y, %I:%M %p",
        "%B %d, %Y, %I:%M %p",
        "%b %d, %Y %I:%M %p",
        "%m/%d/%Y %I:%M %p",
        "%d/%m/%Y %H:%M",
    ):
        try:
            return datetime.strptime(ts_str[:26].strip(), fmt)
        except ValueError:
            continue
    return None
