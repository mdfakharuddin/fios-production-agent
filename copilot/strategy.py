"""
FIOS Win Pattern Intelligence Engine

Deterministic analytics across all historical jobs and proposals.
Computes: win rates, optimal ranges, correlations, and strategic insights.

Called:
  - Incrementally after outcome changes
  - On-demand via /copilot/strategy/overview
"""

import math
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict


# ── Budget tiers ────────────────────────────────────────────────────────────
BUDGET_TIERS = [
    ("micro",    0,     50),
    ("small",    50,    200),
    ("medium",   200,   1000),
    ("large",    1000,  5000),
    ("enterprise", 5000, float("inf")),
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


def _safe_rate(wins: int, total: int) -> float:
    return round((wins / total) * 100, 1) if total > 0 else 0.0


def _pearson(xs: list, ys: list) -> float:
    """Simple Pearson correlation coefficient. Returns 0 if insufficient data."""
    n = len(xs)
    if n < 3:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x * den_y == 0:
        return 0.0
    return round(num / (den_x * den_y), 3)


async def compute_strategy() -> Dict[str, Any]:
    """
    Full cross-thread strategy computation.
    Returns structured dict matching the StrategicMetrics model.
    """
    from database.connection import async_session_maker
    from database.models.jobs import Job, JobOutcome
    from database.models.proposals import Proposal
    from database.models.conversations import Conversation
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async with async_session_maker() as session:
        # Load all jobs with their proposals
        result = await session.execute(
            select(Job).options(selectinload(Job.proposals))
        )
        jobs = result.scalars().all()

        # Load all conversations for correlation data
        result = await session.execute(select(Conversation))
        convs = result.scalars().all()

    # ── Build analysis dataset ──────────────────────────────────────────
    records = []  # [{niche, budget, bid, length, outcome, ...}]
    for job in jobs:
        outcome_str = str(job.outcome).lower() if job.outcome else "pending"
        is_won = "won" in outcome_str
        is_resolved = is_won or "lost" in outcome_str or "cancelled" in outcome_str

        if not is_resolved:
            continue  # Skip pending jobs

        budget = max(job.budget_min or 0, job.budget_max or 0)
        niche = job.category or "uncategorized"
        skills = job.skills_required or []

        for prop in (job.proposals or []):
            bid = prop.bid_amount or 0
            text = prop.cover_letter or ""
            length = prop.length_words or len(text.split())

            records.append({
                "job_id": str(job.id),
                "niche": niche,
                "skills": skills,
                "budget": budget,
                "budget_tier": _bucket(budget, BUDGET_TIERS),
                "bid": bid,
                "length": length,
                "length_bucket": _bucket(length, LENGTH_BUCKETS),
                "outcome": "won" if is_won else "lost",
                "is_won": is_won,
                "discount_pct": round(((budget - bid) / budget) * 100, 1) if budget > 0 and bid > 0 else 0,
            })

    total = len(records)
    wins = sum(1 for r in records if r["is_won"])
    losses = total - wins

    # ── Win rate by niche ───────────────────────────────────────────────
    niche_stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for r in records:
        niche_stats[r["niche"]]["total"] += 1
        if r["is_won"]:
            niche_stats[r["niche"]]["wins"] += 1

    win_rate_by_niche = {}
    for niche, s in niche_stats.items():
        win_rate_by_niche[niche] = {
            "wins": s["wins"],
            "total": s["total"],
            "rate": _safe_rate(s["wins"], s["total"]),
        }

    # ── Win rate by budget tier ─────────────────────────────────────────
    tier_stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for r in records:
        tier_stats[r["budget_tier"]]["total"] += 1
        if r["is_won"]:
            tier_stats[r["budget_tier"]]["wins"] += 1

    win_rate_by_budget = {}
    for tier, s in tier_stats.items():
        win_rate_by_budget[tier] = {
            "wins": s["wins"],
            "total": s["total"],
            "rate": _safe_rate(s["wins"], s["total"]),
        }

    # ── Win rate by proposal length bucket ──────────────────────────────
    len_stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for r in records:
        len_stats[r["length_bucket"]]["total"] += 1
        if r["is_won"]:
            len_stats[r["length_bucket"]]["wins"] += 1

    win_rate_by_length = {}
    for bucket, s in len_stats.items():
        win_rate_by_length[bucket] = {
            "wins": s["wins"],
            "total": s["total"],
            "rate": _safe_rate(s["wins"], s["total"]),
        }

    # ── Win rate by pricing percentile ──────────────────────────────────
    bids = sorted([r["bid"] for r in records if r["bid"] > 0])
    pricing_stats = defaultdict(lambda: {"wins": 0, "total": 0})

    for r in records:
        if r["bid"] <= 0 or not bids:
            continue
        # Calculate percentile rank
        rank = sum(1 for b in bids if b <= r["bid"])
        pct = int((rank / len(bids)) * 100)
        pct_bucket = f"p{(pct // 20) * 20}-p{((pct // 20) + 1) * 20}"  # p0-p20, p20-p40, etc.
        pricing_stats[pct_bucket]["total"] += 1
        if r["is_won"]:
            pricing_stats[pct_bucket]["wins"] += 1

    win_rate_by_pricing = {}
    for bucket, s in pricing_stats.items():
        win_rate_by_pricing[bucket] = {
            "wins": s["wins"],
            "total": s["total"],
            "rate": _safe_rate(s["wins"], s["total"]),
        }

    # ── Top & underperforming niches ────────────────────────────────────
    niche_list = [
        {"niche": n, "win_rate": d["rate"], "count": d["total"]}
        for n, d in win_rate_by_niche.items()
        if d["total"] >= 2  # Minimum sample size
    ]
    niche_list.sort(key=lambda x: x["win_rate"], reverse=True)
    top_niches = niche_list[:5]
    underperforming = [n for n in niche_list if n["win_rate"] < 30][:5]

    # ── Optimal proposal length ─────────────────────────────────────────
    winning_lengths = [r["length"] for r in records if r["is_won"] and r["length"] > 0]
    optimal_length = {}
    if winning_lengths:
        optimal_length = {
            "min": min(winning_lengths),
            "max": max(winning_lengths),
            "avg_winning": round(sum(winning_lengths) / len(winning_lengths), 0),
            "sample_size": len(winning_lengths),
        }

    # ── Optimal pricing band ────────────────────────────────────────────
    winning_bids = [r["bid"] for r in records if r["is_won"] and r["bid"] > 0]
    optimal_price = {}
    if winning_bids:
        winning_bids.sort()
        # Use interquartile range for robustness
        q1_idx = len(winning_bids) // 4
        q3_idx = (3 * len(winning_bids)) // 4
        optimal_price = {
            "min": winning_bids[q1_idx] if q1_idx < len(winning_bids) else 0,
            "max": winning_bids[q3_idx] if q3_idx < len(winning_bids) else 0,
            "avg_winning": round(sum(winning_bids) / len(winning_bids), 2),
            "sample_size": len(winning_bids),
        }

    # ── Negotiation discount ────────────────────────────────────────────
    discounts = [r["discount_pct"] for r in records if r["is_won"] and r["discount_pct"] != 0]
    avg_discount = round(sum(discounts) / len(discounts), 1) if discounts else 0.0

    # ── Correlations ────────────────────────────────────────────────────
    # 1. Client score vs win probability (from conversation analytics)
    conv_map = {}
    for c in convs:
        analytics = c.analytics or {}
        cs = analytics.get("client_score", {})
        if cs and cs.get("score") is not None:
            conv_map[c.room_id] = cs["score"]

    # We can't perfectly map jobs→conversations, so use what we have
    # 2. Proposal length vs outcome
    length_outcome_x = [r["length"] for r in records if r["length"] > 0]
    length_outcome_y = [1.0 if r["is_won"] else 0.0 for r in records if r["length"] > 0]
    length_corr = _pearson(length_outcome_x, length_outcome_y)

    # 3. Bid amount vs outcome
    bid_outcome_x = [r["bid"] for r in records if r["bid"] > 0]
    bid_outcome_y = [1.0 if r["is_won"] else 0.0 for r in records if r["bid"] > 0]
    bid_corr = _pearson(bid_outcome_x, bid_outcome_y)

    # 4. Discount vs outcome
    disc_x = [r["discount_pct"] for r in records]
    disc_y = [1.0 if r["is_won"] else 0.0 for r in records]
    disc_corr = _pearson(disc_x, disc_y)

    correlations = {
        "proposal_length_vs_win": length_corr,
        "bid_amount_vs_win": bid_corr,
        "discount_vs_win": disc_corr,
    }

    # ── Generate insights ───────────────────────────────────────────────
    insights = _generate_insights(
        total, wins, losses,
        top_niches, underperforming,
        optimal_length, optimal_price,
        avg_discount, correlations,
        win_rate_by_length, win_rate_by_budget,
    )

    return {
        "total_proposals": total,
        "total_wins": wins,
        "total_losses": losses,
        "win_rate_overall": _safe_rate(wins, total),
        "win_rate_by_niche": win_rate_by_niche,
        "win_rate_by_budget_tier": win_rate_by_budget,
        "win_rate_by_length_bucket": win_rate_by_length,
        "win_rate_by_pricing_pct": win_rate_by_pricing,
        "top_niches": top_niches,
        "underperforming_niches": underperforming,
        "optimal_length_range": optimal_length,
        "optimal_price_range": optimal_price,
        "avg_negotiation_discount_pct": avg_discount,
        "correlations": correlations,
        "insights": insights,
        "best_niche": top_niches[0]["niche"] if top_niches else "insufficient data",
        "best_price_range": f"${optimal_price.get('min', 0)}-${optimal_price.get('max', 0)}" if optimal_price else "insufficient data",
    }


def _generate_insights(
    total, wins, losses,
    top_niches, underperforming,
    optimal_length, optimal_price,
    avg_discount, correlations,
    win_rate_by_length, win_rate_by_budget,
) -> List[str]:
    """Generate human-readable strategic insights from computed data."""
    insights = []

    if total == 0:
        return ["No resolved proposals yet. Sync your proposal history to unlock strategic intelligence."]

    # Overall win rate insight
    rate = _safe_rate(wins, total)
    if rate >= 40:
        insights.append(f"🏆 Strong overall win rate of {rate}% across {total} proposals.")
    elif rate >= 20:
        insights.append(f"📊 Moderate win rate of {rate}% — room for improvement in targeting.")
    else:
        insights.append(f"⚠ Low win rate of {rate}% — consider refining niche selection and proposal quality.")

    # Best niche
    if top_niches:
        best = top_niches[0]
        insights.append(f"🎯 Your best niche is '{best['niche']}' with {best['win_rate']}% win rate ({best['count']} proposals).")

    # Underperforming
    if underperforming:
        names = ", ".join(n["niche"] for n in underperforming[:3])
        insights.append(f"📉 Underperforming niches: {names}. Consider reducing effort here.")

    # Optimal length
    if optimal_length and optimal_length.get("avg_winning"):
        avg_len = int(optimal_length["avg_winning"])
        insights.append(f"📝 Your winning proposals average {avg_len} words. Stay in the {optimal_length.get('min', 0)}-{optimal_length.get('max', 0)} word range.")

    # Best length bucket
    if win_rate_by_length:
        best_len = max(win_rate_by_length.items(), key=lambda x: x[1].get("rate", 0))
        if best_len[1]["total"] >= 2:
            insights.append(f"✍️ '{best_len[0]}' proposals have the highest win rate at {best_len[1]['rate']}%.")

    # Pricing
    if optimal_price and optimal_price.get("avg_winning"):
        insights.append(f"💰 Your winning bids average ${optimal_price['avg_winning']}. Sweet spot: ${optimal_price.get('min', 0)}-${optimal_price.get('max', 0)}.")

    # Negotiation
    if avg_discount != 0:
        direction = "below" if avg_discount > 0 else "above"
        insights.append(f"🤝 Average negotiation discount: {abs(avg_discount)}% {direction} posted budget.")

    # Correlations
    if correlations.get("proposal_length_vs_win", 0) > 0.2:
        insights.append("📈 Longer proposals correlate with higher win rates — detail pays off.")
    elif correlations.get("proposal_length_vs_win", 0) < -0.2:
        insights.append("📈 Shorter, punchier proposals correlate with higher win rates — keep it concise.")

    if correlations.get("discount_vs_win", 0) > 0.2:
        insights.append("💡 Bidding below budget correlates with winning — competitive pricing works for you.")
    elif correlations.get("discount_vs_win", 0) < -0.2:
        insights.append("💡 Premium pricing correlates with winning — your expertise commands higher rates.")

    # Budget tier
    if win_rate_by_budget:
        best_tier = max(win_rate_by_budget.items(), key=lambda x: x[1].get("rate", 0))
        if best_tier[1]["total"] >= 2:
            insights.append(f"💎 You perform best in the '{best_tier[0]}' budget tier ({best_tier[1]['rate']}% win rate).")

    return insights


async def save_strategy_to_db(metrics: Dict[str, Any]) -> bool:
    """Upsert the computed strategy into strategic_metrics table."""
    from database.connection import async_session_maker
    from database.models.strategic_metrics import StrategicMetrics
    from sqlalchemy import select

    try:
        async with async_session_maker() as session:
            result = await session.execute(select(StrategicMetrics).limit(1))
            existing = result.scalar_one_or_none()

            if existing:
                existing.total_proposals = metrics["total_proposals"]
                existing.total_wins = metrics["total_wins"]
                existing.total_losses = metrics["total_losses"]
                existing.win_rate_overall = metrics["win_rate_overall"]
                existing.win_rate_by_niche = metrics["win_rate_by_niche"]
                existing.win_rate_by_budget_tier = metrics["win_rate_by_budget_tier"]
                existing.win_rate_by_length_bucket = metrics["win_rate_by_length_bucket"]
                existing.win_rate_by_pricing_pct = metrics["win_rate_by_pricing_pct"]
                existing.top_niches = metrics["top_niches"]
                existing.underperforming_niches = metrics["underperforming_niches"]
                existing.optimal_length_range = metrics["optimal_length_range"]
                existing.optimal_price_range = metrics["optimal_price_range"]
                existing.avg_negotiation_discount_pct = metrics["avg_negotiation_discount_pct"]
                existing.correlations = metrics["correlations"]
                existing.insights = metrics["insights"]
                existing.raw_snapshot = metrics
            else:
                new_row = StrategicMetrics(
                    total_proposals=metrics["total_proposals"],
                    total_wins=metrics["total_wins"],
                    total_losses=metrics["total_losses"],
                    win_rate_overall=metrics["win_rate_overall"],
                    win_rate_by_niche=metrics["win_rate_by_niche"],
                    win_rate_by_budget_tier=metrics["win_rate_by_budget_tier"],
                    win_rate_by_length_bucket=metrics["win_rate_by_length_bucket"],
                    win_rate_by_pricing_pct=metrics["win_rate_by_pricing_pct"],
                    top_niches=metrics["top_niches"],
                    underperforming_niches=metrics["underperforming_niches"],
                    optimal_length_range=metrics["optimal_length_range"],
                    optimal_price_range=metrics["optimal_price_range"],
                    avg_negotiation_discount_pct=metrics["avg_negotiation_discount_pct"],
                    correlations=metrics["correlations"],
                    insights=metrics["insights"],
                    raw_snapshot=metrics,
                )
                session.add(new_row)

            await session.commit()
            return True
    except Exception as e:
        print(f"[Strategy] Error saving metrics: {e}")
        import traceback
        traceback.print_exc()
        return False


async def get_cached_strategy() -> Optional[Dict[str, Any]]:
    """Load last computed strategy from DB (fast path)."""
    from database.connection import async_session_maker
    from database.models.strategic_metrics import StrategicMetrics
    from sqlalchemy import select

    try:
        async with async_session_maker() as session:
            result = await session.execute(select(StrategicMetrics).limit(1))
            row = result.scalar_one_or_none()
            if row and row.raw_snapshot:
                return row.raw_snapshot
    except Exception:
        pass
    return None
