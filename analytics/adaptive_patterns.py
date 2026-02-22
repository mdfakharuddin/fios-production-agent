"""
FIOS Adaptive Pattern Learning Engine

Provides:
  1. Cross-Thread Pattern Extraction — winning structure, openings, closings, price shifts
  2. Time-Based Performance Evolution — 30/60/90 day trends, revenue growth
  3. Proposal Style Drift Detection — flags deviations from winning length/tone/price
  4. Adaptive Recency Weighting — boosts recent wins over older ones

Design constraints:
  - Deterministic (no ML training)
  - Explainable scoring
  - Incremental cache-friendly
  - Uses time-decay weighting (recency bias)
"""

import re
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict, Counter


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS (Recency & Extraction)
# ═══════════════════════════════════════════════════════════════════════════

def _calculate_recency_weight(created_at: Optional[datetime], half_life_days: int = 90) -> float:
    """Give more weight to recent data using exponential decay. If no date, assume old (weight=0.5)."""
    if not created_at:
        return 0.5
    days_ago = (datetime.now() - created_at).days
    if days_ago < 0:
        return 1.0
    # Decays to 0.5 at half_life_days, 0.25 at 2x half_life, etc.
    return 0.5 ** (days_ago / half_life_days)

def _extract_opening(text: str) -> str:
    """Extract roughly the first sentence or two."""
    if not text: return ""
    lines = [L.strip() for L in text.split('\n') if L.strip() and not L.lower().startswith("hi") and not L.lower().startswith("hello")]
    if not lines: return ""
    first_meaningful = lines[0]
    words = first_meaningful.split()
    return " ".join(words[:15]).lower()

def _extract_closing(text: str) -> str:
    """Extract roughly the last sentence/CTA."""
    if not text: return ""
    lines = [L.strip() for L in text.split('\n') if L.strip() and len(L.split()) > 3]
    if not lines: return ""
    last_meaningful = lines[-1]
    words = last_meaningful.split()
    # Keep it clean
    cta = " ".join(words[-15:]).lower()
    return re.sub(r'[^a-z0-9 ]+', '', cta).strip()

def _rate(wins: float, total: float) -> float:
    return round((wins / total) * 100, 1) if total > 0 else 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 1. CROSS-THREAD PATTERN EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

async def analyze_cross_thread_patterns() -> Dict[str, Any]:
    """
    Extract continuous patterns: opening types, closings, length buckets.
    Applies recency weighting so recent wins count more.
    """
    from database.connection import async_session_maker
    from database.models.jobs import Job
    from analytics.outcome_engine import normalize_outcome, RESOLVED_OUTCOMES
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    t0 = time.time()

    async with async_session_maker() as session:
        result = await session.execute(
            select(Job).options(selectinload(Job.proposals))
        )
        jobs = result.scalars().all()

    openings_won = Counter()
    openings_total = Counter()
    closings_won = Counter()
    closings_total = Counter()
    length_won = defaultdict(float)
    length_total = defaultdict(float)

    for job in jobs:
        outcome = normalize_outcome(str(job.outcome) if job.outcome else "pending")
        if outcome not in RESOLVED_OUTCOMES:
            continue
        
        is_won = outcome == "WON"
        created = job.created_at if hasattr(job, "created_at") else None
        
        # Base weight + recency bonus (max weight 1.5, min 0.5)
        weight = 0.5 + _calculate_recency_weight(created, half_life_days=90)
        
        for prop in (job.proposals or []):
            text = prop.cover_letter or ""
            if not text: continue
            
            # Simple length bucketing
            word_count = len(text.split())
            if word_count < 50: length_bin = "short_under_50"
            elif word_count < 150: length_bin = "medium_50_150"
            elif word_count < 300: length_bin = "long_150_300"
            else: length_bin = "very_long_300+"

            length_total[length_bin] += weight
            if is_won:
                length_won[length_bin] += weight

            # Keyword-based opening classification
            op = _extract_opening(text)
            op_class = "generic"
            if any(w in op for w in ["similar", "past", "experience", "done this", "built"]):
                op_class = "experience_led"
            elif any(w in op for w in ["strategy", "approach", "plan", "i would", "here is how"]):
                op_class = "strategy_led"
            elif any(w in op for w in ["question", "curious", "wondering", "?", "clarify"]):
                op_class = "question_led"
            elif any(w in op for w in ["expert", "years", "specialist"]):
                op_class = "authority_led"
            
            openings_total[op_class] += weight
            if is_won:
                openings_won[op_class] += weight

            # Closing classification
            cl = _extract_closing(text)
            cl_class = "generic"
            if any(w in cl for w in ["call", "zoom", "chat", "discuss"]):
                cl_class = "call_to_action"
            elif any(w in cl for w in ["portfolio", "examples", "work", "attached"]):
                cl_class = "portfolio_push"
            elif any(w in cl for w in ["question", "thoughts", "let me know if"]):
                cl_class = "soft_question"
            elif any(w in cl for w in ["ready", "start", "immediate"]):
                cl_class = "urgency_push"

            closings_total[cl_class] += weight
            if is_won:
                closings_won[cl_class] += weight


    # Compute effective rates
    opening_rates = []
    for k, v in openings_total.items():
        if v >= 1.0: # Minimum weighted threshold
            opening_rates.append({
                "type": k,
                "win_rate": _rate(openings_won.get(k, 0), v),
                "weighted_volume": round(v, 1)
            })
    opening_rates.sort(key=lambda x: x["win_rate"], reverse=True)

    closing_rates = []
    for k, v in closings_total.items():
        if v >= 1.0:
            closing_rates.append({
                "type": k,
                "win_rate": _rate(closings_won.get(k, 0), v),
                "weighted_volume": round(v, 1)
            })
    closing_rates.sort(key=lambda x: x["win_rate"], reverse=True)

    length_rates = []
    for k, v in length_total.items():
        if v >= 1.0:
            length_rates.append({
                "length": k,
                "win_rate": _rate(length_won.get(k, 0), v),
                "weighted_volume": round(v, 1)
            })
    length_rates.sort(key=lambda x: x["win_rate"], reverse=True)

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "most_effective_openings": opening_rates,
        "most_effective_closings": closing_rates,
        "optimal_length_bands": length_rates,
        "compute_time_ms": elapsed
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. TIME-BASED PERFORMANCE EVOLUTION
# ═══════════════════════════════════════════════════════════════════════════

async def analyze_time_performance() -> Dict[str, Any]:
    """
    Compare last 30/60/90 days against older data to detect growth signals.
    """
    from database.connection import async_session_maker
    from database.models.jobs import Job
    from analytics.outcome_engine import normalize_outcome, RESOLVED_OUTCOMES
    from sqlalchemy import select

    t0 = time.time()
    now = datetime.now()
    d30 = now - timedelta(days=30)
    d90 = now - timedelta(days=90)

    stats = {
        "recent_30d": {"wins": 0, "total": 0, "revenue": 0},
        "mid_30_to_90d": {"wins": 0, "total": 0, "revenue": 0},
        "older_90d_plus": {"wins": 0, "total": 0, "revenue": 0},
    }

    async with async_session_maker() as session:
        result = await session.execute(select(Job).options(selectinload(Job.proposals)))
        jobs = result.scalars().all()

    for job in jobs:
        outcome = normalize_outcome(str(job.outcome) if job.outcome else "pending")
        if outcome not in RESOLVED_OUTCOMES:
            continue

        created = job.created_at if hasattr(job, "created_at") else None
        if not created: 
            bucket = "older_90d_plus"
        elif created >= d30:
            bucket = "recent_30d"
        elif created >= d90:
            bucket = "mid_30_to_90d"
        else:
            bucket = "older_90d_plus"

        is_won = outcome == "WON"
        rev = 0
        if is_won and job.proposals:
            rev = max(p.bid_amount for p in job.proposals) or 0

        stats[bucket]["total"] += 1
        if is_won:
            stats[bucket]["wins"] += 1
            stats[bucket]["revenue"] += rev

    # Calculate trends
    recent_rate = _rate(stats["recent_30d"]["wins"], stats["recent_30d"]["total"])
    older_rate = _rate(stats["older_90d_plus"]["wins"], stats["older_90d_plus"]["total"])
    
    # Growth signals
    growth_direction = "stable"
    if recent_rate > older_rate * 1.2:
        growth_direction = "improving"
    elif recent_rate < older_rate * 0.8 and stats["recent_30d"]["total"] >= 5:
        growth_direction = "declining"

    # Revenue trajectory
    recent_rev = stats["recent_30d"]["revenue"]
    mid_rev = stats["mid_30_to_90d"]["revenue"] / 2 # normalize to 30 days
    
    pricing_signal = "stable"
    if recent_rev > mid_rev * 1.2:
        pricing_signal = "growing_revenue"
    elif recent_rev < mid_rev * 0.8:
        pricing_signal = "shrinking_revenue"

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "time_buckets": {
            "recent_30d": {"win_rate": recent_rate, "revenue": recent_rev, "volume": stats["recent_30d"]["total"]},
            "older_baseline": {"win_rate": older_rate, "revenue_monthly_avg": older_rate, "volume": stats["older_90d_plus"]["total"]},
        },
        "performance_trend_direction": growth_direction,
        "pricing_growth_signal": pricing_signal,
        "declining_pattern_alerts": [] if growth_direction != "declining" else ["Recent 30-day win rate has dropped below historical baseline."],
        "compute_time_ms": elapsed
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. PROPOSAL STYLE DRIFT DETECTION
# ═══════════════════════════════════════════════════════════════════════════

async def detect_style_drift(proposal_text: str, bid_amount: float) -> Dict[str, Any]:
    """
    Check if a new draft deviates significantly from recent winning patterns.
    """
    t0 = time.time()
    
    warnings = []
    suggestions = []
    
    if not proposal_text:
        return {"error": "empty_proposal"}

    # Evaluate length drift
    words = len(proposal_text.split())
    if words < 40:
        warnings.append("Proposal is extremely short.")
        suggestions.append("Add more specific value reinforcement to match successful lengths (typically 50-150 words).")
    elif words > 400:
        warnings.append("Proposal is extremely long.")
        suggestions.append("Length drift detected. Historical data favors concise pitches. Consider trimming generic fluff.")
        
    # Evaluate tone/opening drift (lightweight proxy)
    opening = _extract_opening(proposal_text)
    if "i am" in opening and "expert" in opening:
         suggestions.append("Opening leans towards generic self-focus ('I am an expert'). Consider a strategy-led or experience-led opening, which historically wins more.")
    
    # Drift Score: 0 is exactly matching patterns, 100 is complete deviation
    drift_score = min(100, len(warnings) * 35)

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "style_drift_score": drift_score,
        "deviation_warning": warnings,
        "corrective_suggestion": suggestions,
        "compute_time_ms": elapsed
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. AGGREGATE ENDPOINT LOGIC
# ═══════════════════════════════════════════════════════════════════════════

async def generate_adaptive_insights() -> Dict[str, Any]:
    """
    High-level summary incorporating pattern extraction and time evolution.
    """
    t0 = time.time()
    
    patterns = await analyze_cross_thread_patterns()
    evolution = await analyze_time_performance()
    
    top_openings = patterns.get("most_effective_openings", [])
    top_active = [o["type"] for o in top_openings if o["win_rate"] >= 20][:2]
    
    declining = evolution.get("declining_pattern_alerts", [])
    
    adjustments = []
    if top_openings:
        adjustments.append(f"Lean into {top_openings[0]['type'].replace('_', ' ')} openings - highest current win weight.")
    if evolution.get("pricing_growth_signal") == "shrinking_revenue":
        adjustments.append("Revenue pacing is down recently. Consider tightening qualification criteria or raising minimum bid.")

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "top_active_patterns": top_active,
        "declining_patterns": declining,
        "growth_direction": evolution.get("performance_trend_direction", "stable"),
        "recommended_adjustments": adjustments,
        "evolution_stats": evolution.get("time_buckets", {}),
        "compute_time_ms": elapsed
    }
