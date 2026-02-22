"""
FIOS Client Lifetime Value & Growth Intelligence Engine

Provides:
  1. CLV Modeling — lifetime value, projected value, stress index, ideal score
  2. Repeat Client Predictor — repeat probability, upsell score, retention risk
  3. Upsell & Expansion Detector — conversation signal scanning
  4. Client Quality Segmentation — automatic tier classification
  5. Executive Growth Dashboard — top clients, nurture list, expansion pipeline

Design constraints:
  - Deterministic modeling (no ML)
  - Explainable scoring
  - Incrementally updatable
  - Must not impact Copilot latency
"""

import re
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict


# ── Upsell signal patterns ──────────────────────────────────────────────────
SCOPE_GROWTH_PATTERNS = [
    r"(?:phase\s*2|next\s+phase|second\s+part)", r"(?:more\s+pages|more\s+screens|more\s+features)",
    r"(?:expand|extending|scale|grow)\s+(?:the|this|our)", r"(?:full\s+(?:site|app|project|brand))",
]

BRAND_GROWTH_PATTERNS = [
    r"(?:rebrand|redesign|brand\s+guideline|brand\s+identity|logo\s+refresh)",
    r"(?:marketing\s+materials|social\s+media\s+(?:kit|assets|package))",
    r"(?:business\s+card|letterhead|stationery|merch)",
]

MULTI_PROJECT_PATTERNS = [
    r"(?:another\s+project|next\s+project|future\s+(?:project|work))",
    r"(?:ongoing|long[\s-]*term|retainer|monthly|recurring)",
    r"(?:i\s+have\s+(?:another|more|a\s+few))", r"(?:keep\s+(?:you|working))",
]

ONGOING_NEED_PATTERNS = [
    r"(?:maintenance|updates?\s+(?:regularly|monthly|weekly))",
    r"(?:support\s+(?:contract|plan|agreement))", r"(?:manage|managing|management)\s+(?:our|the)",
    r"(?:hosting|ongoing\s+(?:work|support|development))",
]


def _detect_upsell_signals(text: str) -> Dict[str, bool]:
    text_lower = text.lower()
    return {
        "scope_growth": any(re.search(p, text_lower) for p in SCOPE_GROWTH_PATTERNS),
        "brand_growth": any(re.search(p, text_lower) for p in BRAND_GROWTH_PATTERNS),
        "multi_project": any(re.search(p, text_lower) for p in MULTI_PROJECT_PATTERNS),
        "ongoing_needs": any(re.search(p, text_lower) for p in ONGOING_NEED_PATTERNS),
    }


def _rate(wins: int, total: int) -> float:
    return round((wins / total) * 100, 1) if total > 0 else 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 1. CLIENT LIFETIME VALUE MODELING
# ═══════════════════════════════════════════════════════════════════════════

async def compute_client_profiles() -> List[Dict[str, Any]]:
    """
    Compute detailed CLV profile for every client.
    Returns list of client profiles sorted by lifetime_value descending.
    """
    from database.connection import async_session_maker
    from database.models.clients import Client
    from database.models.jobs import Job
    from database.models.conversations import Conversation
    from analytics.outcome_engine import normalize_outcome
    from analytics.behavior_engine import _detect_signals, _is_freelancer, _parse_ts
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async with async_session_maker() as session:
        result = await session.execute(
            select(Client).options(
                selectinload(Client.jobs).selectinload(Job.proposals),
                selectinload(Client.jobs).selectinload(Job.conversations),
            )
        )
        clients = result.scalars().all()

    profiles = []

    for client in clients:
        total_revenue = 0
        project_count = 0
        won_count = 0
        project_sizes = []
        total_messages = 0
        negotiation_messages = 0
        risk_flag_count = 0
        revision_signals = 0
        hire_dates = []

        # Upsell signals from conversations
        upsell_signals_found = set()

        for job in (client.jobs or []):
            outcome = normalize_outcome(str(job.outcome) if job.outcome else "pending")
            project_count += 1

            for prop in (job.proposals or []):
                bid = prop.bid_amount or 0
                if outcome == "WON":
                    total_revenue += bid
                    won_count += 1
                    project_sizes.append(bid)

            for conv in (job.conversations or []):
                messages = conv.messages_json or []
                total_messages += len(messages)
                risk_flag_count += len(conv.risk_flags or [])

                for msg in messages:
                    sender = (msg.get("sender") or "").lower()
                    text = msg.get("text") or ""
                    ts_str = msg.get("timestamp") or msg.get("time") or ""

                    # Track negotiation signals from client
                    if not _is_freelancer(sender):
                        signals = _detect_signals(text)
                        if any(signals.values()):
                            negotiation_messages += 1
                        if signals.get("revision_escalation"):
                            revision_signals += 1

                        # Track upsell signals
                        upsell = _detect_upsell_signals(text)
                        for sig, active in upsell.items():
                            if active:
                                upsell_signals_found.add(sig)

                    # Track hire dates
                    if outcome == "WON" and ts_str and _is_freelancer(sender):
                        ts = _parse_ts(ts_str)
                        if ts:
                            hire_dates.append(ts)

        # ── Calculate metrics ───────────────────────────────────────────
        avg_project_size = round(sum(project_sizes) / len(project_sizes), 2) if project_sizes else 0
        msg_per_project = round(total_messages / project_count, 1) if project_count > 0 else 0

        # Revision intensity (0-100)
        revision_intensity = min(100, round(revision_signals / max(1, won_count) * 50))

        # Negotiation frequency (0-100)
        neg_freq = min(100, round(negotiation_messages / max(1, total_messages) * 200))

        # Payment reliability (inverse of risk + negotiation, combined with Upwork spend)
        upwork_spend = client.total_spent_on_upwork or 0
        payment_score = 50  # Baseline
        if upwork_spend > 10000:
            payment_score += 30
        elif upwork_spend > 1000:
            payment_score += 15
        if client.risk_score and client.risk_score > 5:
            payment_score -= 20
        payment_score = max(0, min(100, payment_score))

        # Time between repeat hires
        avg_rehire_days = 0
        if len(hire_dates) >= 2:
            hire_dates.sort()
            gaps = [(hire_dates[i + 1] - hire_dates[i]).days for i in range(len(hire_dates) - 1)]
            avg_rehire_days = round(sum(gaps) / len(gaps), 1) if gaps else 0

        # Stress index (0-100: higher = more stressful)
        stress = min(100, round(
            (revision_intensity * 0.3) +
            (neg_freq * 0.3) +
            (min(100, risk_flag_count * 15) * 0.2) +
            ((1 if client.is_micromanager else 0) * 20 * 0.2)
        ))

        # Ideal client score (0-100: higher = better)
        ideal_score = max(0, min(100, round(
            (min(100, total_revenue / 10) * 0.3) +  # Revenue contribution
            (payment_score * 0.2) +
            ((100 - stress) * 0.25) +  # Low stress = good
            (min(100, won_count * 25) * 0.15) +  # Repeat business
            (min(100, avg_project_size / 5) * 0.10)  # Project size
        )))

        # Projected lifetime value (simple: current rate * predicted future projects)
        repeat_rate = won_count / max(1, project_count)
        projected_future = avg_project_size * repeat_rate * 2  # 2x future estimate
        projected_ltv = round(total_revenue + projected_future, 2)

        # Repeat probability score (0-100)
        repeat_prob = min(100, round(
            (min(100, won_count * 30) * 0.4) +
            (ideal_score * 0.3) +
            ((100 - stress) * 0.2) +
            (len(upsell_signals_found) * 15 * 0.1)
        ))

        profiles.append({
            "client_id": str(client.id),
            "name": client.name,
            "company": client.company or "",
            "lifetime_value": round(total_revenue, 2),
            "projected_lifetime_value": projected_ltv,
            "project_count": project_count,
            "won_count": won_count,
            "avg_project_size": avg_project_size,
            "total_messages": total_messages,
            "msg_per_project": msg_per_project,
            "revision_intensity": revision_intensity,
            "negotiation_frequency": neg_freq,
            "payment_reliability_score": payment_score,
            "avg_rehire_days": avg_rehire_days,
            "stress_index": stress,
            "ideal_client_score": ideal_score,
            "repeat_probability_score": repeat_prob,
            "upsell_signals": list(upsell_signals_found),
            "upwork_total_spend": upwork_spend,
            "risk_score": client.risk_score or 0,
            "is_micromanager": client.is_micromanager,
        })

    profiles.sort(key=lambda x: x["lifetime_value"], reverse=True)
    return profiles


# ═══════════════════════════════════════════════════════════════════════════
# 2. REPEAT CLIENT PREDICTOR
# ═══════════════════════════════════════════════════════════════════════════

async def predict_repeat(client_name: str) -> Dict[str, Any]:
    """
    For a specific client, predict repeat probability and upsell potential.
    """
    t0 = time.time()

    profiles = await compute_client_profiles()
    client = next((p for p in profiles if p["name"].lower() == client_name.lower()), None)

    if not client:
        return {"status": "not_found", "message": f"Client '{client_name}' not found"}

    # Upsell opportunity score (0-100)
    upsell_score = min(100, round(
        (len(client["upsell_signals"]) * 20) +
        (client["ideal_client_score"] * 0.3) +
        (min(50, client["lifetime_value"] / 20))
    ))

    # Expansion potential
    if client["won_count"] >= 3 and client["stress_index"] < 40:
        expansion = "HIGH"
    elif client["won_count"] >= 1 and client["stress_index"] < 60:
        expansion = "MEDIUM"
    else:
        expansion = "LOW"

    # Retention risk
    if client["stress_index"] > 70 or client["negotiation_frequency"] > 60:
        retention_risk = "HIGH"
    elif client["stress_index"] > 40 or client["payment_reliability_score"] < 40:
        retention_risk = "MEDIUM"
    else:
        retention_risk = "LOW"

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "client_name": client["name"],
        "repeat_probability": client["repeat_probability_score"],
        "upsell_opportunity_score": upsell_score,
        "expansion_potential": expansion,
        "retention_risk": retention_risk,
        "lifetime_value": client["lifetime_value"],
        "project_count": client["won_count"],
        "stress_index": client["stress_index"],
        "ideal_score": client["ideal_client_score"],
        "upsell_signals_detected": client["upsell_signals"],
        "compute_time_ms": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. UPSELL & EXPANSION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

async def detect_upsell_opportunities() -> Dict[str, Any]:
    """
    Scan all active conversations for upsell signals.
    Returns actionable suggestions.
    """
    from database.connection import async_session_maker
    from database.models.conversations import Conversation
    from analytics.outcome_engine import normalize_outcome
    from analytics.behavior_engine import _is_freelancer
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    t0 = time.time()

    async with async_session_maker() as session:
        result = await session.execute(
            select(Conversation).options(selectinload(Conversation.job))
        )
        convs = result.scalars().all()

    opportunities = []

    for conv in convs:
        job = conv.job
        if not job:
            continue

        outcome = normalize_outcome(str(job.outcome) if job.outcome else "pending")
        if outcome not in ("WON", "ONGOING"):
            continue

        messages = conv.messages_json or []
        signals_found = defaultdict(list)

        for msg in messages[-20:]:  # Check recent messages
            sender = (msg.get("sender") or "").lower()
            text = msg.get("text") or ""

            if not _is_freelancer(sender):
                upsell = _detect_upsell_signals(text)
                for sig, active in upsell.items():
                    if active:
                        signals_found[sig].append(text[:100])

        if signals_found:
            suggestions = []

            if "scope_growth" in signals_found:
                suggestions.append({
                    "type": "milestone_expansion",
                    "label": "📈 Milestone Expansion",
                    "action": "Propose a Phase 2 milestone for the expanded scope. Quote the additional work separately to protect your rate.",
                })

            if "brand_growth" in signals_found:
                suggestions.append({
                    "type": "brand_package",
                    "label": "🎨 Brand Package Upsell",
                    "action": "Offer a comprehensive brand package (logo + guidelines + social media kit). Bundle pricing is 15-20% more revenue than individual items.",
                })

            if "multi_project" in signals_found:
                suggestions.append({
                    "type": "retainer_offer",
                    "label": "🔄 Retainer Offer",
                    "action": "Propose a monthly retainer for ongoing work. This secures recurring revenue and reduces the time spent on cold proposals.",
                })

            if "ongoing_needs" in signals_found:
                suggestions.append({
                    "type": "support_plan",
                    "label": "🛠 Support Plan",
                    "action": "Offer a support/maintenance plan with set hours per month. Predictable revenue with minimal acquisition cost.",
                })

            opportunities.append({
                "thread_name": conv.thread_name,
                "room_id": conv.room_id,
                "outcome": outcome,
                "signals": dict(signals_found),
                "suggestions": suggestions,
                "signal_count": sum(len(v) for v in signals_found.values()),
            })

    opportunities.sort(key=lambda x: x["signal_count"], reverse=True)
    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "total_opportunities": len(opportunities),
        "opportunities": opportunities[:15],
        "compute_time_ms": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. CLIENT QUALITY SEGMENTATION
# ═══════════════════════════════════════════════════════════════════════════

def segment_client(profile: Dict[str, Any]) -> str:
    """
    Classify a client into one of five segments:
    - ideal_long_term_partner
    - high_value_repeater
    - high_value_onetime
    - negotiation_heavy
    - low_margin_high_stress
    """
    ltv = profile.get("lifetime_value", 0)
    wins = profile.get("won_count", 0)
    stress = profile.get("stress_index", 50)
    neg_freq = profile.get("negotiation_frequency", 0)
    ideal = profile.get("ideal_client_score", 50)

    if ideal >= 70 and wins >= 2 and stress < 30:
        return "ideal_long_term_partner"
    elif wins >= 2 and ltv > 500:
        return "high_value_repeater"
    elif wins == 1 and ltv > 500:
        return "high_value_onetime"
    elif neg_freq > 50:
        return "negotiation_heavy"
    elif stress > 60 and ltv < 300:
        return "low_margin_high_stress"
    else:
        return "standard"


async def get_segmented_clients() -> Dict[str, List[Dict]]:
    """Return all clients organized by segment."""
    profiles = await compute_client_profiles()

    segments = defaultdict(list)
    for profile in profiles:
        seg = segment_client(profile)
        profile["segment"] = seg
        segments[seg].append({
            "name": profile["name"],
            "company": profile["company"],
            "lifetime_value": profile["lifetime_value"],
            "ideal_score": profile["ideal_client_score"],
            "stress_index": profile["stress_index"],
            "won_count": profile["won_count"],
            "repeat_probability": profile["repeat_probability_score"],
        })

    return dict(segments)


# ═══════════════════════════════════════════════════════════════════════════
# 5. EXECUTIVE GROWTH DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════

async def generate_growth_dashboard() -> Dict[str, Any]:
    """
    Executive-level growth summary.
    Top clients, nurture targets, limits, expansion pipeline, projected revenue.
    """
    t0 = time.time()

    profiles = await compute_client_profiles()
    segments = defaultdict(list)
    for p in profiles:
        p["segment"] = segment_client(p)
        segments[p["segment"]].append(p)

    # ── Top ideal clients ───────────────────────────────────────────────
    ideal = sorted(profiles, key=lambda x: x["ideal_client_score"], reverse=True)
    top_ideal = [{
        "name": c["name"],
        "company": c["company"],
        "ideal_score": c["ideal_client_score"],
        "lifetime_value": c["lifetime_value"],
        "repeat_probability": c["repeat_probability_score"],
        "segment": c["segment"],
    } for c in ideal[:5]]

    # ── Clients to nurture (high potential, need attention) ─────────────
    nurture = [p for p in profiles
               if p["repeat_probability_score"] >= 40
               and p["ideal_client_score"] >= 50
               and p["stress_index"] < 50
               and p["won_count"] >= 1]
    nurture.sort(key=lambda x: x["repeat_probability_score"], reverse=True)
    clients_to_nurture = [{
        "name": c["name"],
        "company": c["company"],
        "repeat_probability": c["repeat_probability_score"],
        "upsell_signals": c["upsell_signals"],
        "lifetime_value": c["lifetime_value"],
    } for c in nurture[:5]]

    # ── Clients to limit (high stress, low margin) ──────────────────────
    limit = [p for p in profiles
             if p["stress_index"] > 60
             or (p["negotiation_frequency"] > 50 and p["lifetime_value"] < 300)]
    limit.sort(key=lambda x: x["stress_index"], reverse=True)
    clients_to_limit = [{
        "name": c["name"],
        "company": c["company"],
        "stress_index": c["stress_index"],
        "negotiation_frequency": c["negotiation_frequency"],
        "lifetime_value": c["lifetime_value"],
        "segment": c["segment"],
    } for c in limit[:5]]

    # ── Expansion opportunities ─────────────────────────────────────────
    try:
        upsell_data = await detect_upsell_opportunities()
        expansion_opps = upsell_data.get("opportunities", [])[:5]
    except Exception:
        expansion_opps = []

    # ── Projected revenue from existing clients ─────────────────────────
    projected_total = sum(p["projected_lifetime_value"] for p in profiles)
    current_total = sum(p["lifetime_value"] for p in profiles)
    projected_growth = round(projected_total - current_total, 2)

    # ── Segment summary ─────────────────────────────────────────────────
    segment_summary = {}
    for seg, members in segments.items():
        segment_summary[seg] = {
            "count": len(members),
            "total_ltv": round(sum(m["lifetime_value"] for m in members), 2),
            "avg_ideal_score": round(sum(m["ideal_client_score"] for m in members) / len(members), 1) if members else 0,
        }

    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "total_clients": len(profiles),
        "total_current_revenue": round(current_total, 2),
        "projected_revenue_from_existing_clients": round(projected_total, 2),
        "projected_growth": projected_growth,
        "top_ideal_clients": top_ideal,
        "clients_to_nurture": clients_to_nurture,
        "clients_to_limit": clients_to_limit,
        "expansion_opportunities": expansion_opps,
        "segment_summary": segment_summary,
        "compute_time_ms": elapsed,
    }
