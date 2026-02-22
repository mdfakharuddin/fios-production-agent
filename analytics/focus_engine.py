"""
FIOS Focus Allocation & Opportunity Prioritization Engine

Provides:
  1. Revenue Concentration Analysis — where your money actually comes from
  2. Opportunity Prioritization — score any job 0-100 with expected value
  3. Distraction Detection — flag low-ROI patterns eating your time
  4. Daily Strategic Brief — actionable daily summary

Design constraints:
  - Deterministic weighted scoring
  - Explainable (all outputs include reasoning)
  - Caches heavy aggregates
  - Maximize monthly revenue with minimal cognitive load
"""

import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict


# ── Revenue tier buckets ────────────────────────────────────────────────────
PRICE_TIERS = [
    ("under_100",    0,    100),
    ("100_300",      100,  300),
    ("300_700",      300,  700),
    ("700_1500",     700,  1500),
    ("1500_plus",    1500, float("inf")),
]


def _bucket(value: float, tiers: list) -> str:
    for name, lo, hi in tiers:
        if lo <= value < hi:
            return name
    return tiers[-1][0]


def _rate(wins: int, total: int) -> float:
    return round((wins / total) * 100, 1) if total > 0 else 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 1. REVENUE CONCENTRATION ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

async def analyze_revenue_concentration() -> Dict[str, Any]:
    """
    Where does your money actually come from?
    Revenue-weighted analysis across niches, clients, pricing tiers.
    """
    from database.connection import async_session_maker
    from database.models.jobs import Job
    from database.models.proposals import Proposal
    from database.models.conversations import Conversation
    from analytics.outcome_engine import normalize_outcome
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    t0 = time.time()

    async with async_session_maker() as session:
        result = await session.execute(
            select(Job).options(selectinload(Job.proposals), selectinload(Job.conversations))
        )
        jobs = result.scalars().all()

    total_revenue = 0
    niche_rev = defaultdict(lambda: {"revenue": 0, "wins": 0, "total": 0, "connects": 0})
    tier_rev = defaultdict(lambda: {"revenue": 0, "wins": 0, "total": 0})
    client_rev = defaultdict(lambda: {"revenue": 0, "wins": 0, "jobs": 0})
    job_type_rev = defaultdict(lambda: {"revenue": 0, "wins": 0, "total": 0})  # fixed vs hourly

    for job in jobs:
        outcome = normalize_outcome(str(job.outcome) if job.outcome else "pending")
        is_won = outcome == "WON"
        niche = job.category or "uncategorized"
        budget = max(job.budget_min or 0, job.budget_max or 0)
        jtype = str(job.budget_type) if job.budget_type else "unknown"

        for prop in (job.proposals or []):
            bid = prop.bid_amount or 0
            connects = prop.connects_spent or 0
            revenue = bid if is_won else 0

            total_revenue += revenue

            niche_rev[niche]["total"] += 1
            niche_rev[niche]["connects"] += connects
            tier_rev[_bucket(bid, PRICE_TIERS)]["total"] += 1
            job_type_rev[jtype]["total"] += 1

            if is_won:
                niche_rev[niche]["wins"] += 1
                niche_rev[niche]["revenue"] += revenue
                tier_rev[_bucket(bid, PRICE_TIERS)]["wins"] += 1
                tier_rev[_bucket(bid, PRICE_TIERS)]["revenue"] += revenue
                job_type_rev[jtype]["wins"] += 1
                job_type_rev[jtype]["revenue"] += revenue

                # Client tracking (from conversations)
                for conv in (job.conversations or []):
                    cname = conv.thread_name or "unknown"
                    client_rev[cname]["revenue"] += revenue
                    client_rev[cname]["wins"] += 1
                    client_rev[cname]["jobs"] += 1

    # ── Revenue per niche ───────────────────────────────────────────────
    niche_list = []
    for niche, data in niche_rev.items():
        roi = round(data["revenue"] / data["connects"], 2) if data["connects"] > 0 else 0
        niche_list.append({
            "niche": niche,
            "revenue": round(data["revenue"], 2),
            "wins": data["wins"],
            "total": data["total"],
            "win_rate": _rate(data["wins"], data["total"]),
            "connects_spent": data["connects"],
            "revenue_per_connect": roi,
            "revenue_share_pct": round((data["revenue"] / total_revenue) * 100, 1) if total_revenue > 0 else 0,
        })
    niche_list.sort(key=lambda x: x["revenue"], reverse=True)

    # ── Revenue per pricing tier ────────────────────────────────────────
    tier_list = []
    for tier, data in tier_rev.items():
        tier_list.append({
            "tier": tier,
            "revenue": round(data["revenue"], 2),
            "wins": data["wins"],
            "total": data["total"],
            "win_rate": _rate(data["wins"], data["total"]),
            "avg_revenue_per_win": round(data["revenue"] / data["wins"], 2) if data["wins"] > 0 else 0,
        })
    tier_list.sort(key=lambda x: x["revenue"], reverse=True)

    # ── Revenue per job type ────────────────────────────────────────────
    type_list = []
    for jtype, data in job_type_rev.items():
        type_list.append({
            "type": jtype,
            "revenue": round(data["revenue"], 2),
            "wins": data["wins"],
            "total": data["total"],
            "win_rate": _rate(data["wins"], data["total"]),
        })
    type_list.sort(key=lambda x: x["revenue"], reverse=True)

    # ── Revenue concentration score (Herfindahl index) ──────────────────
    # Higher = more concentrated in fewer niches
    concentration = 0
    if total_revenue > 0:
        for n in niche_list:
            share = n["revenue"] / total_revenue
            concentration += share * share
    concentration_score = round(concentration * 100, 1)

    # ── Top ROI ─────────────────────────────────────────────────────────
    niches_with_roi = [n for n in niche_list if n["connects_spent"] > 0]
    niches_with_roi.sort(key=lambda x: x["revenue_per_connect"], reverse=True)
    highest_roi = niches_with_roi[0]["niche"] if niches_with_roi else "insufficient_data"
    lowest_roi = niches_with_roi[-1]["niche"] if len(niches_with_roi) > 1 else "insufficient_data"

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "total_revenue": round(total_revenue, 2),
        "revenue_per_niche": niche_list,
        "revenue_per_pricing_tier": tier_list,
        "revenue_per_job_type": type_list,
        "top_3_revenue_niches": [n["niche"] for n in niche_list[:3]],
        "most_profitable_price_band": tier_list[0]["tier"] if tier_list else "insufficient_data",
        "highest_roi_job_type": highest_roi,
        "lowest_roi_job_type": lowest_roi,
        "revenue_concentration_score": concentration_score,
        "top_clients": sorted(
            [{"name": k, **v} for k, v in client_rev.items()],
            key=lambda x: x["revenue"], reverse=True
        )[:10],
        "compute_time_ms": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. OPPORTUNITY PRIORITIZATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

OPPORTUNITY_WEIGHTS = {
    "win_probability":     0.25,
    "revenue_potential":   0.25,
    "niche_strength":      0.15,
    "client_quality":      0.15,
    "negotiation_risk":    0.10,
    "time_investment":     0.10,
}


async def score_opportunity(
    job_title: str = "",
    job_description: str = "",
    niche: str = "",
    budget: float = 0,
    client_score: float = None,
    win_probability: float = None,
) -> Dict[str, Any]:
    """
    Score any job opportunity 0-100.
    Combines win probability, revenue potential, niche strength, client quality.
    """
    t0 = time.time()

    factors = {}
    reasoning = []
    risk_flags = []

    # ── Load cached strategy for baselines ──────────────────────────────
    from copilot.strategy import get_cached_strategy
    cached = await get_cached_strategy() or {}

    # 1. Win probability (use provided or compute)
    if win_probability is not None:
        factors["win_probability"] = min(100, max(0, win_probability))
    else:
        try:
            from analytics.outcome_engine import compute_win_probability
            wp = await compute_win_probability(
                job_title=job_title,
                job_description=job_description,
                niche=niche,
                budget=budget,
                client_score=client_score,
            )
            factors["win_probability"] = wp.get("win_probability", 40)
        except Exception:
            factors["win_probability"] = 40

    if factors["win_probability"] >= 60:
        reasoning.append(f"High win probability ({factors['win_probability']:.0f}%)")
    elif factors["win_probability"] < 25:
        risk_flags.append(f"Low win probability ({factors['win_probability']:.0f}%)")

    # 2. Revenue potential (scale budget to 0-100)
    if budget > 0:
        # Score relative to historical median
        optimal = cached.get("optimal_price_range", {})
        avg_win = optimal.get("avg_winning", 300)
        revenue_ratio = budget / avg_win if avg_win > 0 else 1
        factors["revenue_potential"] = min(100, max(10, revenue_ratio * 60))
        if budget >= 1000:
            reasoning.append(f"High-value job (${budget})")
        elif budget < 100:
            risk_flags.append(f"Low-budget job (${budget}) — consider ROI")
    else:
        factors["revenue_potential"] = 50

    # 3. Niche strength
    niche_key = (niche or "uncategorized").lower()
    niche_data = (cached.get("win_rate_by_niche") or {}).get(niche_key)
    if niche_data and niche_data.get("total", 0) >= 2:
        factors["niche_strength"] = min(100, niche_data["rate"] * 1.2)
        if niche_data["rate"] >= 50:
            reasoning.append(f"Strong niche '{niche_key}' ({niche_data['rate']}% win rate)")
        elif niche_data["rate"] < 20:
            risk_flags.append(f"Weak niche '{niche_key}' ({niche_data['rate']}% win rate)")
    else:
        factors["niche_strength"] = 45
        reasoning.append(f"New niche '{niche_key}' — no historical data")

    # 4. Client quality
    if client_score is not None:
        factors["client_quality"] = min(100, max(0, client_score * 10))
        if client_score >= 8:
            reasoning.append(f"High-quality client (score {client_score}/10)")
        elif client_score < 4:
            risk_flags.append(f"Low-quality client (score {client_score}/10)")
    else:
        factors["client_quality"] = 50

    # 5. Negotiation risk (inverse — lower risk = higher score)
    # Budget jobs below $200 have higher negotiation risk
    if budget > 0 and budget < 200:
        factors["negotiation_risk"] = 35
        risk_flags.append("Low budget → higher negotiation probability")
    elif budget >= 1000:
        factors["negotiation_risk"] = 80
        reasoning.append("Premium budget → lower negotiation risk")
    else:
        factors["negotiation_risk"] = 60

    # 6. Time investment (inverse — less time = higher score)
    # Estimate based on budget tier
    if budget > 0:
        if budget < 100:
            factors["time_investment"] = 40  # Low budget, possibly not worth it
        elif budget < 500:
            factors["time_investment"] = 65
        elif budget < 2000:
            factors["time_investment"] = 80
        else:
            factors["time_investment"] = 70  # Very large jobs may take too long
    else:
        factors["time_investment"] = 55

    # ── Weighted score ──────────────────────────────────────────────────
    final_score = sum(
        factors.get(f, 50) * w for f, w in OPPORTUNITY_WEIGHTS.items()
    )
    final_score = round(min(100, max(0, final_score)), 1)

    # Priority level
    if final_score >= 70:
        priority = "HIGH"
    elif final_score >= 45:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    # Expected value estimate (win_probability * budget)
    wp = factors.get("win_probability", 40) / 100
    expected_value = round(budget * wp, 2) if budget > 0 else 0

    # Risk level
    if len(risk_flags) >= 3:
        risk_level = "HIGH"
    elif len(risk_flags) >= 1:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "opportunity_score": final_score,
        "priority_level": priority,
        "expected_value_estimate": expected_value,
        "risk_level": risk_level,
        "reasoning": reasoning,
        "risk_flags": risk_flags,
        "factor_scores": factors,
        "factor_weights": OPPORTUNITY_WEIGHTS,
        "compute_time_ms": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. DISTRACTION DETECTION
# ═══════════════════════════════════════════════════════════════════════════

async def detect_distractions() -> Dict[str, Any]:
    """
    Find patterns where low-value jobs consume disproportionate effort.
    Returns alerts and recommended focus shifts.
    """
    from database.connection import async_session_maker
    from database.models.jobs import Job
    from database.models.conversations import Conversation
    from analytics.outcome_engine import normalize_outcome
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    t0 = time.time()

    async with async_session_maker() as session:
        result = await session.execute(
            select(Job).options(selectinload(Job.proposals), selectinload(Job.conversations))
        )
        jobs = result.scalars().all()

    alerts = []
    focus_shifts = []

    # Track niche-level patterns
    niche_effort = defaultdict(lambda: {
        "revenue": 0, "wins": 0, "total": 0, "messages": 0,
        "connects": 0, "risk_flags_total": 0,
    })

    for job in jobs:
        outcome = normalize_outcome(str(job.outcome) if job.outcome else "pending")
        niche = job.category or "uncategorized"
        budget = max(job.budget_min or 0, job.budget_max or 0)

        for prop in (job.proposals or []):
            bid = prop.bid_amount or 0
            connects = prop.connects_spent or 0
            niche_effort[niche]["total"] += 1
            niche_effort[niche]["connects"] += connects

            if outcome == "WON":
                niche_effort[niche]["wins"] += 1
                niche_effort[niche]["revenue"] += bid

        for conv in (job.conversations or []):
            msg_count = len(conv.messages_json or [])
            risk_count = len(conv.risk_flags or [])
            niche_effort[niche]["messages"] += msg_count
            niche_effort[niche]["risk_flags_total"] += risk_count

            # Alert: High message count + low budget + won = low effective rate
            if outcome == "WON" and msg_count > 30 and budget < 200:
                alerts.append({
                    "type": "low_value_high_effort",
                    "severity": "high",
                    "message": f"Job '{conv.thread_name}' ({niche}): {msg_count} messages for only ${budget}. This pattern reduces effective hourly rate.",
                    "thread": conv.thread_name,
                })

            # Alert: High risk flags
            if risk_count >= 3:
                alerts.append({
                    "type": "high_stress_client",
                    "severity": "medium",
                    "message": f"Thread '{conv.thread_name}' has {risk_count} risk flags. High-stress clients reduce effective revenue.",
                    "thread": conv.thread_name,
                })

    # Detect low-ROI niches consuming lots of connects
    for niche, data in niche_effort.items():
        if data["total"] < 3:
            continue

        win_rate = _rate(data["wins"], data["total"])
        roi = data["revenue"] / data["connects"] if data["connects"] > 0 else 0
        avg_msgs = data["messages"] / data["total"] if data["total"] > 0 else 0

        # Low win rate + high effort
        if win_rate < 20 and data["total"] >= 5:
            alerts.append({
                "type": "low_win_rate_niche",
                "severity": "high",
                "message": f"Niche '{niche}': {win_rate}% win rate across {data['total']} proposals. Consider reducing effort here.",
                "niche": niche,
            })
            focus_shifts.append({
                "action": "reduce",
                "niche": niche,
                "reason": f"Only {win_rate}% win rate with {data['total']} proposals — poor ROI",
            })

        # High message count per job (time sink)
        if avg_msgs > 40 and data["revenue"] / max(1, data["wins"]) < 300:
            alerts.append({
                "type": "time_sink_niche",
                "severity": "medium",
                "message": f"Niche '{niche}': avg {avg_msgs:.0f} messages per job but avg revenue ${data['revenue'] / max(1, data['wins']):.0f}/win. Time-intensive for low revenue.",
                "niche": niche,
            })

        # High ROI niche not getting enough attention
        if roi > 50 and data["total"] < 5:
            focus_shifts.append({
                "action": "increase",
                "niche": niche,
                "reason": f"${roi:.0f} revenue per connect — high ROI but only {data['total']} proposals. Apply more here.",
            })

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "distraction_alerts": alerts[:15],
        "recommended_focus_shift": focus_shifts[:10],
        "total_alerts": len(alerts),
        "compute_time_ms": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. DAILY STRATEGIC BRIEF
# ═══════════════════════════════════════════════════════════════════════════

async def generate_daily_brief() -> Dict[str, Any]:
    """
    Actionable daily strategic summary.
    Combines revenue analysis, active opportunities, distraction alerts.
    """
    from database.connection import async_session_maker
    from database.models.conversations import Conversation
    from database.models.jobs import Job
    from analytics.outcome_engine import normalize_outcome
    from analytics.behavior_engine import suggest_followup
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    t0 = time.time()

    async with async_session_maker() as session:
        result = await session.execute(
            select(Conversation).options(selectinload(Conversation.job))
        )
        convs = result.scalars().all()

    # ── Identify active threads needing attention ───────────────────────
    priority_jobs = []
    jobs_to_ignore = []
    risk_alerts = []

    for conv in convs:
        job = conv.job
        if not job:
            continue

        outcome = normalize_outcome(str(job.outcome) if job.outcome else "pending")
        if outcome not in ("ONGOING",):
            continue

        budget = max(job.budget_min or 0, job.budget_max or 0)
        niche = job.category or "uncategorized"
        analytics = conv.analytics or {}
        risk_flags = conv.risk_flags or []
        msg_count = len(conv.messages_json or [])

        # Parse last message time
        last_ts_str = conv.last_message_timestamp or ""
        hours_inactive = 0
        if last_ts_str:
            from analytics.behavior_engine import _parse_ts
            last_ts = _parse_ts(last_ts_str)
            if last_ts:
                hours_inactive = (datetime.now() - last_ts).total_seconds() / 3600

        # Score each active job
        try:
            opp = await score_opportunity(
                job_title=conv.thread_name,
                niche=niche,
                budget=budget,
            )
            opp_score = opp.get("opportunity_score", 50)
        except Exception:
            opp_score = 50

        entry = {
            "thread_name": conv.thread_name,
            "room_id": conv.room_id,
            "niche": niche,
            "budget": budget,
            "opportunity_score": opp_score,
            "hours_inactive": round(hours_inactive, 1),
            "message_count": msg_count,
            "risk_flag_count": len(risk_flags),
        }

        if opp_score >= 60:
            priority_jobs.append(entry)
        elif opp_score < 30 and budget < 100:
            jobs_to_ignore.append(entry)

        # Risk alerts
        if len(risk_flags) >= 2:
            risk_alerts.append({
                "thread": conv.thread_name,
                "flags": risk_flags[:3],
                "severity": "high" if len(risk_flags) >= 3 else "medium",
            })

        if hours_inactive > 72:
            risk_alerts.append({
                "thread": conv.thread_name,
                "flags": [f"Inactive for {hours_inactive:.0f} hours"],
                "severity": "medium",
            })

    # Sort by opportunity score
    priority_jobs.sort(key=lambda x: x["opportunity_score"], reverse=True)

    # ── Revenue focus recommendation ────────────────────────────────────
    rev_focus = "No enough data for recommendation"
    try:
        rev = await analyze_revenue_concentration()
        top_niches = rev.get("top_3_revenue_niches", [])
        if top_niches:
            rev_focus = f"Focus on {', '.join(top_niches[:2])} — your highest revenue niches"
    except Exception:
        pass

    # ── Pricing hint ────────────────────────────────────────────────────
    pricing_hint = "Maintain current pricing strategy"
    try:
        from copilot.strategy import get_cached_strategy
        cached = await get_cached_strategy() or {}
        opt_price = cached.get("optimal_price_range", {})
        if opt_price.get("avg_winning"):
            pricing_hint = f"Your winning bid average is ${opt_price['avg_winning']}. Target ${opt_price.get('min', 0)}-${opt_price.get('max', 0)} range."
    except Exception:
        pass

    # ── Distraction alerts ──────────────────────────────────────────────
    try:
        distractions = await detect_distractions()
        distraction_alerts = distractions.get("distraction_alerts", [])[:5]
        focus_shifts = distractions.get("recommended_focus_shift", [])[:3]
    except Exception:
        distraction_alerts = []
        focus_shifts = []

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "today_priority_jobs": priority_jobs[:5],
        "jobs_to_ignore": jobs_to_ignore[:5],
        "revenue_focus_recommendation": rev_focus,
        "pricing_adjustment_hint": pricing_hint,
        "risk_alerts": risk_alerts[:5],
        "distraction_alerts": distraction_alerts,
        "recommended_focus_shift": focus_shifts,
        "active_opportunities": len(priority_jobs),
        "low_value_opportunities": len(jobs_to_ignore),
        "compute_time_ms": elapsed,
    }
