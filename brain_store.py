"""
FIOS Brain Store — Persistent Freelancer Intelligence

Stores and maintains a continuously-updated JSON snapshot of all
freelancer intelligence. This is the "brain" that:
  1. The extension UI queries for context
  2. External agents (n8n, OpenClaw) query via /api/v1/brain/snapshot
  3. Gets enriched every time new data arrives (proposals, conversations, jobs)

Brain file: FIOS/brain_snapshot.json
"""

import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import Counter


BRAIN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_snapshot.json")

# Default brain skeleton
DEFAULT_BRAIN = {
    "last_updated": None,
    "freelancer": {
        "niches": [],
        "strongest_skills": [],
        "positioning_style": "Professional and solution-focused",
        "average_hourly_rate": None,
        "bid_range": None,
        "total_proposals_sent": 0,
        "total_conversations": 0,
        "total_jobs_seen": 0,
        "win_rate_pct": 0,
        "authority_level": "Building",   # Building → Moderate → Strong → Expert
    },
    "patterns": {
        "winning_tone_keywords": [],
        "common_proposal_openers": [],
        "average_proposal_length": 0,
        "preferred_project_types": [],
        "pricing_history": [],
    },
    "recent_activity": {
        "last_5_proposals": [],
        "last_5_conversations": [],
        "last_5_jobs_viewed": [],
    },
    "strategic_notes": [],
}


def load_brain() -> Dict[str, Any]:
    """Load the brain snapshot from disk."""
    if os.path.exists(BRAIN_PATH):
        try:
            with open(BRAIN_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_BRAIN.copy()


def save_brain(brain: Dict[str, Any]) -> None:
    """Persist the brain snapshot to disk."""
    brain["last_updated"] = datetime.utcnow().isoformat() + "Z"
    with open(BRAIN_PATH, "w") as f:
        json.dump(brain, f, indent=2, default=str)


def rebuild_brain() -> Dict[str, Any]:
    """
    Full brain rebuild from SQLite database.
    Called on startup and after major data changes.
    """
    import sqlite3

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fios_local_db.sqlite3")
    if not os.path.exists(db_path):
        return load_brain()

    brain = DEFAULT_BRAIN.copy()

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # ── Proposals Analysis ─────────────────────────────────────────────
        proposals = cur.execute("SELECT * FROM proposals ORDER BY created_at DESC").fetchall()
        brain["freelancer"]["total_proposals_sent"] = len(proposals)

        bids = [p["bid_amount"] for p in proposals if p["bid_amount"] and p["bid_amount"] > 0]
        if bids:
            brain["freelancer"]["average_hourly_rate"] = round(sum(bids) / len(bids), 2)
            brain["freelancer"]["bid_range"] = f"${min(bids):.0f} - ${max(bids):.0f}/hr"
            brain["patterns"]["pricing_history"] = [
                {"amount": b, "date": None} for b in bids[-10:]
            ]

        # Extract cover letter patterns
        cover_letters = [p["cover_letter"] for p in proposals if p["cover_letter"]]
        if cover_letters:
            # Average length
            lengths = [len(cl.split()) for cl in cover_letters]
            brain["patterns"]["average_proposal_length"] = round(sum(lengths) / len(lengths))

            # Extract clean cover letter text (strip the Upwork UI noise)
            clean_letters = []
            for cl in cover_letters:
                # Find the actual cover letter in the scraped text
                markers = ["Cover letter", "cover letter"]
                for marker in markers:
                    idx = cl.find(marker)
                    if idx != -1:
                        clean = cl[idx + len(marker):].strip()
                        # Cut at common end markers
                        for end_marker in ["Profile highlights", "Messages", "Edit proposal"]:
                            end_idx = clean.find(end_marker)
                            if end_idx != -1:
                                clean = clean[:end_idx].strip()
                        if len(clean) > 50:
                            clean_letters.append(clean[:500])
                            break

            # Common openers
            openers = []
            for cl in clean_letters:
                first_sentence = cl.split(".")[0].strip() if "." in cl else cl[:100]
                if len(first_sentence) > 10:
                    openers.append(first_sentence[:100])
            brain["patterns"]["common_proposal_openers"] = openers[:5]

            # Recent proposals
            brain["recent_activity"]["last_5_proposals"] = [
                {
                    "text_preview": cl[:200],
                    "bid": proposals[i]["bid_amount"] if i < len(proposals) else None,
                    "status": proposals[i]["status"] if i < len(proposals) else "UNKNOWN",
                }
                for i, cl in enumerate(clean_letters[:5])
            ]

        # ── Jobs Analysis ──────────────────────────────────────────────────
        jobs = cur.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        brain["freelancer"]["total_jobs_seen"] = len(jobs)

        # Extract skills
        all_skills = []
        for j in jobs:
            if j["skills_required"]:
                try:
                    skills = json.loads(j["skills_required"]) if isinstance(j["skills_required"], str) else j["skills_required"]
                    if isinstance(skills, list):
                        all_skills.extend(skills)
                except Exception:
                    pass

        skill_counts = Counter(all_skills)
        brain["freelancer"]["strongest_skills"] = [s for s, _ in skill_counts.most_common(10)]

        # Extract job categories/niches
        categories = [j["category"] for j in jobs if j["category"] and j["category"] not in ("Extracted Job", "Stealth Extracted Job", "Raw Extracted Page")]
        if categories:
            brain["freelancer"]["niches"] = list(set(categories))[:5]

        # Infer niches from job titles if categories are generic
        if not brain["freelancer"]["niches"]:
            titles = [j["title"] for j in jobs if j["title"]]
            # Use skill frequency to infer niches
            if brain["freelancer"]["strongest_skills"]:
                brain["freelancer"]["niches"] = brain["freelancer"]["strongest_skills"][:3]

        # Preferred project types
        budget_types = Counter(j["budget_type"] for j in jobs if j["budget_type"])
        brain["patterns"]["preferred_project_types"] = [
            {"type": bt, "count": c} for bt, c in budget_types.most_common(3)
        ]

        # Recent jobs
        brain["recent_activity"]["last_5_jobs_viewed"] = [
            {
                "title": j["title"],
                "budget": f"{j['budget_type']} ${j['budget_min']}-${j['budget_max']}" if j["budget_min"] else j["budget_type"],
                "skills": json.loads(j["skills_required"]) if j["skills_required"] else [],
            }
            for j in jobs[:5]
        ]

        # ── Conversations Analysis ─────────────────────────────────────────
        convos = cur.execute("SELECT * FROM conversations ORDER BY created_at DESC").fetchall()
        brain["freelancer"]["total_conversations"] = len(convos)

        brain["recent_activity"]["last_5_conversations"] = [
            {
                "thread_name": c["thread_name"],
                "sync_status": c["sync_status"],
                "message_count": c["message_count_synced"] or 0,
                "summary": (c["summary"] or "")[:200],
            }
            for c in convos[:5]
        ]

        # ── Authority Level ────────────────────────────────────────────────
        total = brain["freelancer"]["total_proposals_sent"]
        if total >= 50:
            brain["freelancer"]["authority_level"] = "Expert"
        elif total >= 20:
            brain["freelancer"]["authority_level"] = "Strong"
        elif total >= 5:
            brain["freelancer"]["authority_level"] = "Moderate"
        else:
            brain["freelancer"]["authority_level"] = "Building"

        conn.close()

    except Exception as e:
        print(f"[BrainStore] Rebuild error: {e}")
        import traceback
        traceback.print_exc()

    save_brain(brain)
    print(f"[BrainStore] Brain rebuilt: {brain['freelancer']['total_proposals_sent']} proposals, "
          f"{brain['freelancer']['total_jobs_seen']} jobs, "
          f"{brain['freelancer']['total_conversations']} conversations, "
          f"{len(brain['freelancer']['strongest_skills'])} skills")
    return brain


def get_brain_compact() -> str:
    """
    Return a compact text version of the brain for AI prompts.
    Designed to be SHORT — under 400 tokens.
    """
    brain = load_brain()
    f = brain.get("freelancer", {})
    p = brain.get("patterns", {})
    r = brain.get("recent_activity", {})

    lines = [
        f"FREELANCER: {f.get('total_proposals_sent', 0)} proposals sent, "
        f"{f.get('total_conversations', 0)} conversations, "
        f"{f.get('total_jobs_seen', 0)} jobs tracked.",
    ]

    if f.get("strongest_skills"):
        lines.append(f"SKILLS: {', '.join(f['strongest_skills'][:6])}")

    if f.get("average_hourly_rate"):
        lines.append(f"RATE: ${f['average_hourly_rate']}/hr (range: {f.get('bid_range', 'N/A')})")

    if f.get("authority_level"):
        lines.append(f"AUTHORITY: {f['authority_level']}")

    if p.get("common_proposal_openers"):
        lines.append(f"TONE SAMPLES: {p['common_proposal_openers'][0][:100]}")

    if r.get("last_5_jobs_viewed"):
        recent_titles = [j["title"] for j in r["last_5_jobs_viewed"][:3] if j.get("title")]
        if recent_titles:
            lines.append(f"RECENT JOBS: {' | '.join(recent_titles)}")

    return "\n".join(lines)
