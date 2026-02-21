"""
FIOS Niche Dominance & Market Positioning Engine

Provides:
  1. Niche Strength Analysis — win rate, revenue, stress, repeat rate per niche
  2. Niche Concentration Risk — overexposure alerts + diversification advice
  3. Portfolio Gap Analyzer — missing categories, rising keywords, sample recs
  4. Competitive Density Signal — proposal density trends, emerging/declining niches
  5. Strategic Positioning Summary — primary/secondary niche focus + action items

Design constraints:
  - Deterministic (no ML)
  - Uses historical data + embedded job trend signals
  - Explainable outputs
  - Schedulable as weekly task
"""

import re
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict, Counter


# ═══════════════════════════════════════════════════════════════════════════
# 1. NICHE STRENGTH ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

async def analyze_niche_strength() -> Dict[str, Any]:
    """
    Deep niche-level analysis: win rate, revenue, stress, negotiation,
    repeat rate, LTV per niche.
    """
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.jobs import Job
    from FIOS.database.models.clients import Client
    from FIOS.database.models.conversations import Conversation
    from FIOS.analytics.outcome_engine import normalize_outcome, RESOLVED_OUTCOMES
    from FIOS.analytics.behavior_engine import _detect_signals, _is_freelancer
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    t0 = time.time()

    async with async_session_maker() as session:
        result = await session.execute(
            select(Job).options(
                selectinload(Job.proposals),
                selectinload(Job.conversations),
                selectinload(Job.client),
            )
        )
        jobs = result.scalars().all()

    niche_data = defaultdict(lambda: {
        "wins": 0, "total": 0, "revenue": 0,
        "clients": set(), "repeat_clients": set(),
        "stress_scores": [], "neg_counts": [],
        "project_sizes": [], "msg_counts": [],
        "risk_flags": 0,
    })

    for job in jobs:
        outcome = normalize_outcome(str(job.outcome) if job.outcome else "pending")
        if outcome not in RESOLVED_OUTCOMES:
            continue

        is_won = outcome == "WON"
        niche = (job.category or "uncategorized").lower()
        budget = max(job.budget_min or 0, job.budget_max or 0)
        client_id = str(job.client_id) if job.client_id else None

        nd = niche_data[niche]
        nd["total"] += 1

        if client_id:
            if client_id in nd["clients"]:
                nd["repeat_clients"].add(client_id)
            nd["clients"].add(client_id)

        for prop in (job.proposals or []):
            bid = prop.bid_amount or 0
            if is_won:
                nd["wins"] += 1
                nd["revenue"] += bid
                nd["project_sizes"].append(bid)

        # Conversation-level metrics
        for conv in (job.conversations or []):
            messages = conv.messages_json or []
            nd["msg_counts"].append(len(messages))
            nd["risk_flags"] += len(conv.risk_flags or [])

            neg_count = 0
            for msg in messages:
                sender = (msg.get("sender") or "").lower()
                text = msg.get("text") or ""
                if not _is_freelancer(sender):
                    signals = _detect_signals(text)
                    if any(signals.values()):
                        neg_count += 1
            nd["neg_counts"].append(neg_count)

        # Stress from client
        if job.client:
            nd["stress_scores"].append(job.client.risk_score or 0)

    # ── Build niche profiles ────────────────────────────────────────────
    def _safe_avg(lst):
        return round(sum(lst) / len(lst), 1) if lst else 0

    def _rate(w, t):
        return round((w / t) * 100, 1) if t > 0 else 0

    niche_profiles = []
    for niche, d in niche_data.items():
        win_rate = _rate(d["wins"], d["total"])
        avg_stress = _safe_avg(d["stress_scores"])
        avg_neg = _safe_avg(d["neg_counts"])
        avg_msgs = _safe_avg(d["msg_counts"])
        avg_project = _safe_avg(d["project_sizes"])
        total_clients = len(d["clients"])
        repeat_count = len(d["repeat_clients"])
        repeat_rate = _rate(repeat_count, total_clients)

        # Stability score: consistent wins + low stress + repeat clients
        stability = min(100, round(
            (min(100, win_rate * 1.5) * 0.3) +
            ((100 - min(100, avg_stress * 10)) * 0.25) +
            (min(100, repeat_rate * 1.2) * 0.25) +
            (min(100, d["total"] * 10) * 0.2)  # Data volume factor
        ))

        niche_profiles.append({
            "niche": niche,
            "win_rate": win_rate,
            "wins": d["wins"],
            "total": d["total"],
            "revenue": round(d["revenue"], 2),
            "avg_project_size": avg_project,
            "avg_stress_index": avg_stress,
            "avg_negotiation_per_thread": avg_neg,
            "avg_messages_per_thread": avg_msgs,
            "total_clients": total_clients,
            "repeat_clients": repeat_count,
            "repeat_client_rate": repeat_rate,
            "lifetime_value": round(d["revenue"], 2),
            "risk_flags": d["risk_flags"],
            "stability_score": stability,
        })

    niche_profiles.sort(key=lambda x: x["revenue"], reverse=True)

    # ── Identify key niches ─────────────────────────────────────────────
    valid = [n for n in niche_profiles if n["total"] >= 2]
    dominant = max(valid, key=lambda x: x["win_rate"]) if valid else None
    high_rev = max(valid, key=lambda x: x["revenue"]) if valid else None
    low_stress = min(valid, key=lambda x: x["avg_stress_index"]) if valid else None
    high_risk = max(valid, key=lambda x: x["avg_stress_index"]) if valid else None

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "niche_profiles": niche_profiles,
        "dominant_niche": dominant["niche"] if dominant else "insufficient_data",
        "high_revenue_niche": high_rev["niche"] if high_rev else "insufficient_data",
        "low_stress_niche": low_stress["niche"] if low_stress else "insufficient_data",
        "high_risk_niche": high_risk["niche"] if high_risk else "insufficient_data",
        "niche_stability_score": round(
            sum(n["stability_score"] for n in valid) / len(valid), 1
        ) if valid else 0,
        "total_niches": len(niche_profiles),
        "compute_time_ms": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. NICHE CONCENTRATION RISK
# ═══════════════════════════════════════════════════════════════════════════

async def analyze_concentration_risk() -> Dict[str, Any]:
    """
    Detect overexposure to single niche/client/budget band.
    Uses Herfindahl-Hirschman Index (HHI) for concentration measurement.
    """
    t0 = time.time()

    strength = await analyze_niche_strength()
    profiles = strength["niche_profiles"]

    alerts = []
    recommendations = []

    total_revenue = sum(p["revenue"] for p in profiles)
    total_jobs = sum(p["total"] for p in profiles)

    if total_revenue <= 0 or total_jobs < 3:
        return {
            "overexposure_alerts": [],
            "diversification_recommendation": "Insufficient data for concentration analysis. Continue building history.",
            "compute_time_ms": round((time.time() - t0) * 1000, 1),
        }

    # ── Niche concentration (HHI) ──────────────────────────────────────
    niche_hhi = 0
    for p in profiles:
        share = p["revenue"] / total_revenue if total_revenue > 0 else 0
        niche_hhi += share * share

    if niche_hhi > 0.5:
        top = profiles[0] if profiles else None
        share_pct = round((top["revenue"] / total_revenue) * 100, 1) if top else 0
        alerts.append({
            "type": "niche_overexposure",
            "severity": "high",
            "message": f"Revenue heavily concentrated in '{top['niche']}' ({share_pct}% of total). If this niche slows down, income drops significantly.",
            "hhi_score": round(niche_hhi * 100, 1),
        })
        recommendations.append(f"Diversify into related niches. Current HHI: {round(niche_hhi * 100)}%. Target < 35%.")
    elif niche_hhi > 0.3:
        alerts.append({
            "type": "niche_moderate_concentration",
            "severity": "medium",
            "message": f"Moderate niche concentration (HHI: {round(niche_hhi * 100)}%). Consider expanding to 1-2 adjacent niches.",
            "hhi_score": round(niche_hhi * 100, 1),
        })

    # ── Client concentration ────────────────────────────────────────────
    # Check if any single niche has very few unique clients
    for p in profiles:
        if p["revenue"] > total_revenue * 0.3 and p["total_clients"] <= 2:
            alerts.append({
                "type": "client_concentration",
                "severity": "high",
                "message": f"Niche '{p['niche']}' generates {round(p['revenue'] / total_revenue * 100)}% of revenue but has only {p['total_clients']} client(s). Losing one client = major revenue impact.",
            })

    # ── Budget band concentration ───────────────────────────────────────
    budget_counts = defaultdict(int)
    for p in profiles:
        if p["avg_project_size"] < 100:
            budget_counts["micro"] += p["total"]
        elif p["avg_project_size"] < 300:
            budget_counts["small"] += p["total"]
        elif p["avg_project_size"] < 700:
            budget_counts["medium"] += p["total"]
        else:
            budget_counts["large"] += p["total"]

    dominant_band = max(budget_counts.items(), key=lambda x: x[1]) if budget_counts else None
    if dominant_band and total_jobs > 0:
        share = dominant_band[1] / total_jobs
        if share > 0.7:
            alerts.append({
                "type": "budget_band_overexposure",
                "severity": "medium",
                "message": f"{round(share * 100)}% of jobs are in the '{dominant_band[0]}' budget band. Consider targeting higher-value projects.",
            })
            if dominant_band[0] in ("micro", "small"):
                recommendations.append("Move upmarket: target medium-large projects to increase revenue per proposal.")

    # Overall recommendation
    if not recommendations:
        recommendations.append("Good diversification. Maintain current niche spread.")

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "overexposure_alerts": alerts,
        "diversification_recommendation": " | ".join(recommendations),
        "niche_hhi": round(niche_hhi * 100, 1),
        "budget_band_distribution": dict(budget_counts),
        "compute_time_ms": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. PORTFOLIO GAP ANALYZER
# ═══════════════════════════════════════════════════════════════════════════

async def analyze_portfolio_gaps() -> Dict[str, Any]:
    """
    Detect missing portfolio categories, rising keywords, sample recommendations.
    Uses job_descriptions vector index + historical job data.
    """
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.jobs import Job
    from FIOS.analytics.outcome_engine import normalize_outcome
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    t0 = time.time()

    async with async_session_maker() as session:
        result = await session.execute(
            select(Job).options(selectinload(Job.proposals))
        )
        jobs = result.scalars().all()

    # ── Extract keywords from winning vs all jobs ───────────────────────
    STOP_WORDS = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "i", "we", "you", "he", "she",
        "it", "they", "me", "us", "him", "her", "them", "my", "our", "your",
        "his", "its", "their", "this", "that", "these", "those", "not", "no",
        "so", "if", "as", "up", "out", "about", "into", "through", "during",
        "before", "after", "above", "below", "between", "need", "looking",
        "want", "like", "please", "also", "just", "very", "more", "some",
        "any", "all", "each", "every", "both", "few", "many", "much",
    }

    def extract_keywords(text: str) -> List[str]:
        words = re.findall(r"[a-z]+", text.lower())
        return [w for w in words if len(w) > 2 and w not in STOP_WORDS]

    winning_keywords = Counter()
    all_keywords = Counter()
    winning_categories = Counter()
    all_categories = Counter()
    winning_skills = Counter()

    for job in jobs:
        outcome = normalize_outcome(str(job.outcome) if job.outcome else "pending")
        is_won = outcome == "WON"
        desc = job.description or ""
        title = job.title or ""
        category = (job.category or "").lower()
        skills = job.skills_required or []

        kw = extract_keywords(f"{title} {desc}")
        all_keywords.update(kw)
        if category:
            all_categories[category] += 1

        if is_won:
            winning_keywords.update(kw)
            if category:
                winning_categories[category] += 1
            for skill in skills:
                winning_skills[str(skill).lower()] += 1

    # ── Portfolio samples we have ───────────────────────────────────────
    portfolio_categories = set()
    try:
        from FIOS.memory.retrieval import memory
        stats = memory.get_stats()
        portfolio_count = stats.get("portfolio_samples", {}).get("count", 0)
        if portfolio_count > 0:
            # Sample some portfolio items to see what categories we cover
            sample = memory.search_similar("portfolio_samples", "design branding web app", n=10)
            for item in sample:
                meta = item.get("metadata", {})
                cat = meta.get("category", "")
                if cat:
                    portfolio_categories.add(cat.lower())
    except Exception:
        pass

    # ── Missing categories ──────────────────────────────────────────────
    requested_cats = set(all_categories.keys())
    missing = requested_cats - portfolio_categories
    missing_portfolio = [
        {"category": cat, "jobs_requesting": all_categories.get(cat, 0)}
        for cat in missing if all_categories.get(cat, 0) >= 2
    ]
    missing_portfolio.sort(key=lambda x: x["jobs_requesting"], reverse=True)

    # ── Rising keywords in winning jobs ─────────────────────────────────
    # Keywords that appear disproportionately in wins vs overall
    rising = []
    for kw, win_count in winning_keywords.most_common(50):
        all_count = all_keywords.get(kw, 0)
        if all_count < 3:
            continue
        win_ratio = win_count / all_count
        if win_ratio > 0.6 and win_count >= 2:
            rising.append({
                "keyword": kw,
                "in_wins": win_count,
                "in_total": all_count,
                "win_correlation": round(win_ratio * 100, 1),
            })
    rising.sort(key=lambda x: x["win_correlation"], reverse=True)

    # ── Sample recommendations ──────────────────────────────────────────
    sample_recs = []
    top_win_cats = winning_categories.most_common(5)
    for cat, count in top_win_cats:
        if cat not in portfolio_categories:
            sample_recs.append({
                "category": cat,
                "reason": f"Won {count} jobs in this niche but no portfolio sample exists",
                "priority": "high" if count >= 3 else "medium",
            })

    # Positioning upgrade suggestions
    positioning_suggestions = []
    top_skills = winning_skills.most_common(10)
    if top_skills:
        skill_list = [s[0] for s in top_skills[:5]]
        positioning_suggestions.append({
            "type": "skill_emphasis",
            "action": f"Emphasize these in-demand skills in your profile: {', '.join(skill_list)}",
        })

    if rising[:3]:
        kw_list = [r["keyword"] for r in rising[:3]]
        positioning_suggestions.append({
            "type": "keyword_alignment",
            "action": f"Align portfolio titles/descriptions with rising keywords: {', '.join(kw_list)}",
        })

    if missing_portfolio[:2]:
        cat_list = [m["category"] for m in missing_portfolio[:2]]
        positioning_suggestions.append({
            "type": "portfolio_expansion",
            "action": f"Add portfolio samples for frequently requested categories: {', '.join(cat_list)}",
        })

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "missing_portfolio_categories": missing_portfolio[:10],
        "new_sample_recommendations": sample_recs[:5],
        "rising_win_keywords": rising[:15],
        "positioning_upgrade_suggestions": positioning_suggestions,
        "top_winning_skills": [{"skill": s, "count": c} for s, c in top_skills[:10]],
        "compute_time_ms": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. COMPETITIVE DENSITY SIGNAL
# ═══════════════════════════════════════════════════════════════════════════

async def analyze_competition_signals() -> Dict[str, Any]:
    """
    Lightweight competition density analysis from ingested job data.
    Detects trending, emerging, and declining niches.
    """
    from FIOS.database.connection import async_session_maker
    from FIOS.database.models.jobs import Job
    from FIOS.analytics.outcome_engine import normalize_outcome
    from sqlalchemy import select

    t0 = time.time()

    async with async_session_maker() as session:
        result = await session.execute(select(Job))
        jobs = result.scalars().all()

    # ── Time-bucket jobs by niche ───────────────────────────────────────
    now = datetime.now()
    recent_cutoff = now - timedelta(days=30)
    older_cutoff = now - timedelta(days=90)

    recent_niches = Counter()
    older_niches = Counter()
    recent_win_niches = Counter()

    for job in jobs:
        niche = (job.category or "uncategorized").lower()
        outcome = normalize_outcome(str(job.outcome) if job.outcome else "pending")
        created = job.created_at if hasattr(job, "created_at") else None

        if created:
            if created >= recent_cutoff:
                recent_niches[niche] += 1
                if outcome == "WON":
                    recent_win_niches[niche] += 1
            elif created >= older_cutoff:
                older_niches[niche] += 1
        else:
            # No timestamp — count as older
            older_niches[niche] += 1

    # ── Trend analysis ──────────────────────────────────────────────────
    all_niches = set(recent_niches.keys()) | set(older_niches.keys())
    trends = []

    for niche in all_niches:
        recent = recent_niches.get(niche, 0)
        older = older_niches.get(niche, 0)

        # Normalize older to 30-day equivalent (older covers 60 days)
        older_normalized = older / 2 if older > 0 else 0

        if older_normalized > 0:
            change_pct = round(((recent - older_normalized) / older_normalized) * 100, 1)
        elif recent > 0:
            change_pct = 100  # New niche
        else:
            change_pct = 0

        if recent + older < 2:
            trend = "insufficient_data"
        elif change_pct > 30:
            trend = "rising"
        elif change_pct < -30:
            trend = "declining"
        else:
            trend = "stable"

        trends.append({
            "niche": niche,
            "recent_30d_count": recent,
            "older_30_90d_count": older,
            "change_pct": change_pct,
            "trend": trend,
            "recent_wins": recent_win_niches.get(niche, 0),
        })

    trends.sort(key=lambda x: x["change_pct"], reverse=True)

    # ── Extract signals ─────────────────────────────────────────────────
    emerging = [t for t in trends if t["trend"] == "rising"]
    declining = [t for t in trends if t["trend"] == "declining"]

    emerging_signal = []
    for e in emerging[:3]:
        emerging_signal.append({
            "niche": e["niche"],
            "growth": f"+{e['change_pct']}%",
            "action": f"Rising demand in '{e['niche']}' — consider positioning here early",
        })

    declining_warning = []
    for d in declining[:3]:
        declining_warning.append({
            "niche": d["niche"],
            "decline": f"{d['change_pct']}%",
            "action": f"Activity shrinking in '{d['niche']}' — reduce investment here",
        })

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "niche_competition_trend": trends[:15],
        "emerging_opportunity_signal": emerging_signal,
        "declining_niche_warning": declining_warning,
        "compute_time_ms": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. STRATEGIC POSITIONING SUMMARY
# ═══════════════════════════════════════════════════════════════════════════

async def generate_positioning_summary() -> Dict[str, Any]:
    """
    Executive strategic positioning summary.
    Combines niche strength, concentration risk, portfolio gaps, competition.
    """
    t0 = time.time()

    # Run all analyses
    strength = await analyze_niche_strength()
    concentration = await analyze_concentration_risk()
    portfolio = await analyze_portfolio_gaps()
    competition = await analyze_competition_signals()

    profiles = strength["niche_profiles"]
    valid = [p for p in profiles if p["total"] >= 2]

    # ── Primary focus niche ─────────────────────────────────────────────
    # Best niche = highest stability score (balances win rate + revenue + low stress + repeat clients)
    primary = max(valid, key=lambda x: x["stability_score"]) if valid else None
    primary_niche = primary["niche"] if primary else "insufficient_data"

    # ── Secondary expansion niche ───────────────────────────────────────
    # Find emerging niche with decent historical performance
    emerging = competition.get("emerging_opportunity_signal", [])
    secondary_niche = "insufficient_data"

    if emerging:
        for e in emerging:
            en = e["niche"]
            matching = next((p for p in profiles if p["niche"] == en), None)
            if matching and matching.get("win_rate", 0) >= 20:
                secondary_niche = en
                break

    if secondary_niche == "insufficient_data" and len(valid) >= 2:
        # Fallback: second-best stability
        sorted_by_stability = sorted(valid, key=lambda x: x["stability_score"], reverse=True)
        if len(sorted_by_stability) >= 2:
            secondary_niche = sorted_by_stability[1]["niche"]

    # ── Portfolio action items ──────────────────────────────────────────
    portfolio_actions = []
    for rec in portfolio.get("new_sample_recommendations", [])[:3]:
        portfolio_actions.append(f"Add sample for '{rec['category']}' ({rec['reason']})")
    for sug in portfolio.get("positioning_upgrade_suggestions", [])[:2]:
        portfolio_actions.append(sug["action"])

    # ── Pricing direction ───────────────────────────────────────────────
    pricing_direction = "maintain_current"
    if primary:
        if primary["win_rate"] >= 50 and primary["avg_project_size"] > 0:
            pricing_direction = "increase_gradually"
        elif primary["win_rate"] < 25:
            pricing_direction = "decrease_or_adjust_value_proposition"

    # ── Long-term recommendation ────────────────────────────────────────
    rec_parts = []

    if primary:
        rec_parts.append(f"Double down on '{primary_niche}' (stability: {primary['stability_score']}/100, win rate: {primary['win_rate']}%).")

    if secondary_niche != "insufficient_data":
        rec_parts.append(f"Expand into '{secondary_niche}' as secondary growth area.")

    alerts = concentration.get("overexposure_alerts", [])
    if any(a["severity"] == "high" for a in alerts):
        rec_parts.append("Reduce concentration risk by diversifying revenue sources across 2-3 niches.")

    declining = competition.get("declining_niche_warning", [])
    if declining:
        rec_parts.append(f"Phase out investment in declining niches: {', '.join(d['niche'] for d in declining[:2])}.")

    if not rec_parts:
        rec_parts.append("Continue building history. Focus on winning more proposals to generate actionable intelligence.")

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "primary_focus_niche": primary_niche,
        "primary_niche_stats": {
            "win_rate": primary["win_rate"],
            "revenue": primary["revenue"],
            "stability_score": primary["stability_score"],
            "repeat_rate": primary["repeat_client_rate"],
        } if primary else {},
        "secondary_expansion_niche": secondary_niche,
        "portfolio_action_items": portfolio_actions,
        "pricing_adjustment_direction": pricing_direction,
        "long_term_positioning_recommendation": " ".join(rec_parts),
        "concentration_risk": concentration.get("overexposure_alerts", []),
        "emerging_opportunities": competition.get("emerging_opportunity_signal", []),
        "declining_warnings": competition.get("declining_niche_warning", []),
        "total_niches_tracked": strength["total_niches"],
        "compute_time_ms": elapsed,
    }
