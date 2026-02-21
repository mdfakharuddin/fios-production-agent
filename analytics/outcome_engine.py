"""
FIOS Outcome Intelligence Engine

Provides:
  1. Outcome Normalization — standardizes all job outcomes
  2. Cross-Thread Analytics — win rates by niche/budget/score/length/pricing
  3. Win Probability Scoring — deterministic 0-100 score for any job

Design constraints:
  - No ML libraries (pure statistical aggregation + weighted scoring)
  - < 150ms compute time (uses cached aggregates)
  - All scoring logic is explainable
  - Incrementally updatable
"""

import time
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

# ── Outcome normalization map ───────────────────────────────────────────────
OUTCOME_MAP = {
    # Explicit matches
    "won": "WON", "hired": "WON", "active": "WON", "accepted": "WON",
    "lost": "LOST", "rejected": "LOST", "declined": "LOST",
    "cancelled": "WITHDRAWN", "withdrawn": "WITHDRAWN",
    "ghosted": "GHOSTED", "no_response": "GHOSTED",
    "ongoing": "ONGOING", "pending": "ONGOING", "submitted": "ONGOING",
    "interviewing": "ONGOING", "draft": "ONGOING",
}

RESOLVED_OUTCOMES = {"WON", "LOST", "GHOSTED", "WITHDRAWN"}

# ── Budget tiers ────────────────────────────────────────────────────────────
BUDGET_TIERS = [
    ("micro",      0,     50),
    ("small",      50,    200),
    ("medium",     200,   1000),
    ("large",      1000,  5000),
    ("enterprise", 5000,  float("inf")),
]

# ── Client score brackets ──────────────────────────────────────────────────
SCORE_BRACKETS = [
    ("poor",      0,   3),
    ("fair",      3,   5),
    ("good",      5,   7),
    ("excellent",  7,  10.1),
]

# ── Proposal length buckets ─────────────────────────────────────────────────
LENGTH_BUCKETS = [
    ("very_short",  0,   50),
    ("short",       50,  100),
    ("medium",      100, 200),
    ("long",        200, 350),
    ("very_long",   350, float("inf")),
]


def _bucket(value: float, tiers: list) -> str:
    for name, lo, hi in tiers:
        if lo <= value < hi:
            return name
    return tiers[-1][0]


def _rate(wins: int, total: int) -> float:
    return round((wins / total) * 100, 1) if total > 0 else 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 1. OUTCOME NORMALIZATION
# ═══════════════════════════════════════════════════════════════════════════

def normalize_outcome(raw: str) -> str:
    """Normalize any raw outcome string to WON/LOST/GHOSTED/WITHDRAWN/ONGOING."""
    if not raw:
        return "ONGOING"
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return OUTCOME_MAP.get(key, "ONGOING")


async def backfill_outcomes():
    """
    Scan all jobs and proposals, standardize their outcomes.
    Called once on startup or manually.
    """
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.jobs import Job
    from FIOS.database.models.proposals import Proposal
    from sqlalchemy import select

    stats = {"jobs_updated": 0, "proposals_checked": 0}

    try:
        async with async_session_maker() as session:
            result = await session.execute(select(Job))
            jobs = result.scalars().all()

            for job in jobs:
                raw = str(job.outcome) if job.outcome else "pending"
                normalized = normalize_outcome(raw)
                # Check if job should be marked GHOSTED
                # (no response for 14+ days in associated conversations)
                if normalized == "ONGOING" and job.conversations:
                    for conv in job.conversations:
                        last_ts = conv.last_message_timestamp
                        if last_ts:
                            try:
                                from datetime import datetime, timedelta
                                # Try to parse timestamp
                                for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                                    try:
                                        dt = datetime.strptime(last_ts[:19], fmt)
                                        if datetime.now() - dt > timedelta(days=14):
                                            normalized = "GHOSTED"
                                        break
                                    except ValueError:
                                        continue
                            except Exception:
                                pass

                stats["jobs_updated"] += 1
                stats["proposals_checked"] += len(job.proposals or [])

            await session.commit()
    except Exception as e:
        print(f"[OutcomeEngine] Backfill error: {e}")

    print(f"[OutcomeEngine] Backfill complete: {stats}")
    return stats


# ═══════════════════════════════════════════════════════════════════════════
# 2. CROSS-THREAD ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════

async def compute_outcome_analytics() -> Dict[str, Any]:
    """
    Compute all cross-thread win analytics.
    Returns aggregated stats suitable for caching in strategic_metrics.
    """
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.jobs import Job
    from FIOS.database.models.proposals import Proposal
    from FIOS.database.models.conversations import Conversation
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    t0 = time.time()

    async with async_session_maker() as session:
        result = await session.execute(
            select(Job).options(selectinload(Job.proposals), selectinload(Job.conversations))
        )
        jobs = result.scalars().all()

        result = await session.execute(select(Conversation))
        all_convs = result.scalars().all()

    # Build a client_score lookup from conversations
    conv_score_map: Dict[str, float] = {}
    conv_delay_map: Dict[str, float] = {}
    for c in all_convs:
        a = c.analytics or {}
        cs = a.get("client_score", {})
        if cs and cs.get("score") is not None:
            conv_score_map[c.room_id] = cs["score"]
        delay = a.get("response_delay_avg_mins", 0)
        if delay > 0:
            conv_delay_map[c.room_id] = delay

    # ── Build records ───────────────────────────────────────────────────
    records = []
    for job in jobs:
        raw_outcome = str(job.outcome) if job.outcome else "pending"
        outcome = normalize_outcome(raw_outcome)

        if outcome not in RESOLVED_OUTCOMES:
            continue

        is_won = outcome == "WON"
        budget = max(job.budget_min or 0, job.budget_max or 0)
        niche = job.category or "uncategorized"

        # Find associated client score from conversations
        client_score = None
        avg_delay = None
        for conv in (job.conversations or []):
            if conv.room_id in conv_score_map:
                client_score = conv_score_map[conv.room_id]
            if conv.room_id in conv_delay_map:
                avg_delay = conv_delay_map[conv.room_id]

        for prop in (job.proposals or []):
            bid = prop.bid_amount or 0
            text = prop.cover_letter or ""
            length = prop.length_words or len(text.split())

            records.append({
                "niche": niche,
                "budget": budget,
                "budget_tier": _bucket(budget, BUDGET_TIERS),
                "bid": bid,
                "length": length,
                "length_bucket": _bucket(length, LENGTH_BUCKETS),
                "outcome": outcome,
                "is_won": is_won,
                "client_score": client_score,
                "client_score_bracket": _bucket(client_score, SCORE_BRACKETS) if client_score else "unknown",
                "discount_pct": round(((budget - bid) / budget) * 100, 1) if budget > 0 and bid > 0 else 0,
                "avg_delay_mins": avg_delay,
            })

    total = len(records)
    wins = sum(1 for r in records if r["is_won"])

    # ── Win rate by niche ──────────────────────────────────────────────
    niche_stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for r in records:
        niche_stats[r["niche"]]["total"] += 1
        if r["is_won"]:
            niche_stats[r["niche"]]["wins"] += 1
    win_by_niche = {n: {**s, "rate": _rate(s["wins"], s["total"])} for n, s in niche_stats.items()}

    # ── Win rate by budget tier ────────────────────────────────────────
    tier_stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for r in records:
        tier_stats[r["budget_tier"]]["total"] += 1
        if r["is_won"]:
            tier_stats[r["budget_tier"]]["wins"] += 1
    win_by_budget = {t: {**s, "rate": _rate(s["wins"], s["total"])} for t, s in tier_stats.items()}

    # ── Win rate by client score bracket ───────────────────────────────
    score_stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for r in records:
        score_stats[r["client_score_bracket"]]["total"] += 1
        if r["is_won"]:
            score_stats[r["client_score_bracket"]]["wins"] += 1
    win_by_score = {b: {**s, "rate": _rate(s["wins"], s["total"])} for b, s in score_stats.items()}

    # ── Win rate by proposal length bucket ─────────────────────────────
    len_stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for r in records:
        len_stats[r["length_bucket"]]["total"] += 1
        if r["is_won"]:
            len_stats[r["length_bucket"]]["wins"] += 1
    win_by_length = {b: {**s, "rate": _rate(s["wins"], s["total"])} for b, s in len_stats.items()}

    # ── Win rate by pricing percentile ─────────────────────────────────
    bids = sorted([r["bid"] for r in records if r["bid"] > 0])
    pricing_stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for r in records:
        if r["bid"] <= 0 or not bids:
            continue
        rank = sum(1 for b in bids if b <= r["bid"])
        pct_bucket = f"p{((rank * 100 // len(bids)) // 20) * 20}-p{(((rank * 100 // len(bids)) // 20) + 1) * 20}"
        pricing_stats[pct_bucket]["total"] += 1
        if r["is_won"]:
            pricing_stats[pct_bucket]["wins"] += 1
    win_by_pricing = {b: {**s, "rate": _rate(s["wins"], s["total"])} for b, s in pricing_stats.items()}

    # ── Average negotiation discount ───────────────────────────────────
    win_discounts = [r["discount_pct"] for r in records if r["is_won"] and r["discount_pct"] != 0]
    avg_discount = round(sum(win_discounts) / len(win_discounts), 1) if win_discounts else 0.0

    # ── Average response time before hire ──────────────────────────────
    hire_delays = [r["avg_delay_mins"] for r in records if r["is_won"] and r["avg_delay_mins"]]
    avg_hire_delay = round(sum(hire_delays) / len(hire_delays), 1) if hire_delays else 0.0

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "total_resolved": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate_overall": _rate(wins, total),
        "win_by_niche": win_by_niche,
        "win_by_budget_tier": win_by_budget,
        "win_by_client_score_bracket": win_by_score,
        "win_by_length_bucket": win_by_length,
        "win_by_pricing_percentile": win_by_pricing,
        "avg_negotiation_discount_pct": avg_discount,
        "avg_response_time_before_hire_mins": avg_hire_delay,
        "compute_time_ms": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. WIN PROBABILITY SCORING
# ═══════════════════════════════════════════════════════════════════════════

# Weights for each scoring factor (must sum to 1.0)
FACTOR_WEIGHTS = {
    "niche_performance":     0.25,
    "budget_tier_perf":      0.15,
    "client_score_perf":     0.15,
    "proposal_similarity":   0.20,
    "job_similarity":        0.15,
    "pricing_position":      0.10,
}


async def compute_win_probability(
    job_title: str = "",
    job_description: str = "",
    niche: str = "",
    budget: float = 0,
    proposal_text: str = "",
    bid_amount: float = 0,
    client_score: float = None,
) -> Dict[str, Any]:
    """
    Compute deterministic win probability score (0-100) for a job.

    Uses cached aggregates + vector similarity. Explainable via contributing_factors.
    Target: <150ms.
    """
    t0 = time.time()

    # ── Load cached strategy (fast) ─────────────────────────────────────
    from FIOS.copilot.strategy import get_cached_strategy, compute_strategy, save_strategy_to_db

    cached = await get_cached_strategy()
    if not cached:
        # Compute fresh (one-time cost)
        try:
            cached = await compute_strategy()
            await save_strategy_to_db(cached)
        except Exception:
            cached = {}

    # ── Factor scores (each 0-100) ──────────────────────────────────────
    factors = {}
    contributing = []
    risk_flags = []

    # 1. Niche performance
    niche_key = niche or "uncategorized"
    niche_data = (cached.get("win_rate_by_niche") or {}).get(niche_key)
    if niche_data and niche_data.get("total", 0) >= 2:
        niche_score = niche_data["rate"]
        factors["niche_performance"] = niche_score
        if niche_score >= 50:
            contributing.append(f"Strong niche: '{niche_key}' has {niche_score}% win rate")
        elif niche_score < 20:
            risk_flags.append(f"Weak niche: '{niche_key}' has only {niche_score}% win rate")
    else:
        factors["niche_performance"] = cached.get("win_rate_overall", 30)
        contributing.append(f"New niche '{niche_key}' — using overall average as baseline")

    # 2. Budget tier performance
    tier = _bucket(budget, BUDGET_TIERS)
    tier_data = (cached.get("win_rate_by_budget_tier") or {}).get(tier)
    if tier_data and tier_data.get("total", 0) >= 2:
        tier_score = tier_data["rate"]
        factors["budget_tier_perf"] = tier_score
        if tier_score >= 50:
            contributing.append(f"Good budget tier: '{tier}' has {tier_score}% win rate")
    else:
        factors["budget_tier_perf"] = cached.get("win_rate_overall", 30)

    # 3. Client score performance
    if client_score is not None:
        bracket = _bucket(client_score, SCORE_BRACKETS)
        score_data = (cached.get("win_rate_by_budget_tier") or {}).get(bracket)  # Check if exists
        if client_score >= 7:
            factors["client_score_perf"] = 75
            contributing.append(f"High client score ({client_score}/10) — likely serious buyer")
        elif client_score >= 5:
            factors["client_score_perf"] = 55
        elif client_score >= 3:
            factors["client_score_perf"] = 35
            risk_flags.append(f"Below-average client score ({client_score}/10)")
        else:
            factors["client_score_perf"] = 15
            risk_flags.append(f"Low client score ({client_score}/10) — high risk of ghosting")
    else:
        factors["client_score_perf"] = 50  # Neutral if unknown

    # 4. Proposal similarity to winning proposals (vector search)
    try:
        from FIOS.memory.retrieval import memory
        if proposal_text:
            similar = memory.search_similar("winning_proposals", proposal_text, n=3)
            if similar:
                avg_dist = sum(r["distance"] for r in similar) / len(similar)
                # ChromaDB cosine distance: 0 = identical, 2 = opposite
                sim_score = max(0, min(100, (1 - avg_dist) * 100))
                factors["proposal_similarity"] = sim_score
                if sim_score >= 70:
                    contributing.append(f"Proposal style matches winning patterns ({sim_score:.0f}% similarity)")
                elif sim_score < 30:
                    risk_flags.append("Proposal style differs significantly from past winners")
            else:
                factors["proposal_similarity"] = 40
        else:
            factors["proposal_similarity"] = 40
    except Exception:
        factors["proposal_similarity"] = 40

    # 5. Job similarity to past winning jobs
    try:
        from FIOS.memory.retrieval import memory
        query = f"{job_title}\n{job_description[:500]}"
        if query.strip():
            wins = memory.search_similar("winning_proposals", query, n=3)
            if wins:
                avg_dist = sum(r["distance"] for r in wins) / len(wins)
                job_sim = max(0, min(100, (1 - avg_dist) * 100))
                factors["job_similarity"] = job_sim
                if job_sim >= 65:
                    contributing.append(f"Job matches past wins ({job_sim:.0f}% similarity)")
            else:
                factors["job_similarity"] = 35
        else:
            factors["job_similarity"] = 35
    except Exception:
        factors["job_similarity"] = 35

    # 6. Pricing position
    optimal = cached.get("optimal_price_range") or {}
    if bid_amount > 0 and optimal.get("min") and optimal.get("max"):
        opt_min, opt_max = optimal["min"], optimal["max"]
        if opt_min <= bid_amount <= opt_max:
            factors["pricing_position"] = 80
            contributing.append(f"Bid ${bid_amount} is within optimal range (${opt_min}-${opt_max})")
        elif bid_amount < opt_min:
            deviation = (opt_min - bid_amount) / opt_min * 100
            factors["pricing_position"] = max(20, 80 - deviation)
            if deviation > 30:
                risk_flags.append(f"Bid ${bid_amount} is significantly below optimal range")
        else:
            deviation = (bid_amount - opt_max) / opt_max * 100
            factors["pricing_position"] = max(20, 80 - deviation * 0.5)
            if deviation > 50:
                risk_flags.append(f"Bid ${bid_amount} is well above optimal range — may reduce competitiveness")
    else:
        factors["pricing_position"] = 50

    # ── Weighted final score ────────────────────────────────────────────
    final_score = 0
    for factor_name, weight in FACTOR_WEIGHTS.items():
        val = factors.get(factor_name, 50)
        final_score += val * weight

    final_score = round(min(100, max(0, final_score)), 1)

    # ── Confidence level ────────────────────────────────────────────────
    data_points = cached.get("total_proposals", 0)
    known_factors = sum(1 for v in factors.values() if v != 50 and v != 40 and v != 35)

    if data_points >= 20 and known_factors >= 4:
        confidence = "HIGH"
    elif data_points >= 5 and known_factors >= 2:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "win_probability": final_score,
        "confidence_level": confidence,
        "contributing_factors": contributing,
        "risk_flags": risk_flags,
        "factor_scores": factors,
        "factor_weights": FACTOR_WEIGHTS,
        "data_points": data_points,
        "compute_time_ms": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. CACHE UPDATE (after outcome changes)
# ═══════════════════════════════════════════════════════════════════════════

async def refresh_outcome_analytics():
    """Recompute outcome analytics and merge into strategic_metrics."""
    from FIOS.copilot.strategy import compute_strategy, save_strategy_to_db
    try:
        outcome_data = await compute_outcome_analytics()
        strategy = await compute_strategy()

        # Merge outcome-specific fields into strategy
        strategy["win_by_client_score_bracket"] = outcome_data.get("win_by_client_score_bracket", {})
        strategy["avg_response_time_before_hire_mins"] = outcome_data.get("avg_response_time_before_hire_mins", 0)

        await save_strategy_to_db(strategy)
        print(f"[OutcomeEngine] Analytics refreshed in {outcome_data.get('compute_time_ms', 0)}ms")
        return strategy
    except Exception as e:
        print(f"[OutcomeEngine] Refresh error: {e}")
        return {}
