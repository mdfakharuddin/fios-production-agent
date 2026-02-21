"""
FIOS Memory Recall Assistant

Fast retrieval layer that quickly grabs relevant past experience, winning proposals,
and portfolio samples to eliminate hesitation when proving expertise to a client.
"""

import time
from typing import Dict, Any, List

async def build_memory_recall(job_title: str, job_description: str, strict_voice_mode: bool = True) -> Dict[str, Any]:
    """
    Retrieve top similar past jobs, winning proposals, and portfolio matches.
    Passes them to the AI to construct a high-confidence experience snapshot.
    """
    from FIOS.memory.retrieval import memory
    from FIOS.copilot.ai import copilot_ai

    t0 = time.time()
    
    query = f"{job_title}\n{job_description[:500]}"
    
    # 1. Retrieve similar jobs (won first, then lost)
    similar_jobs = memory.search_similar("job_descriptions", query, n=10)
    wins = memory.search_similar("winning_proposals", query, n=5)
    portfolio = memory.search_similar("portfolio_samples", query, n=3)
    
    recent_similar_projects = []
    seen = set()
    
    # Prioritize wins
    for w in wins:
        meta = w.get("metadata", {})
        title = meta.get("job_title", "Previous Win")
        if title not in seen and len(recent_similar_projects) < 5:
            recent_similar_projects.append({
                "title": title,
                "niche": meta.get("niche", "General"),
                "price_range": f"${meta.get('bid_amount', 0)}",
                "outcome": "WON",
                "short_summary": w.get("document", "")[:100] + "..."
            })
            seen.add(title)
            
    # Fill from general jobs
    for j in similar_jobs:
        meta = j.get("metadata", {})
        title = meta.get("title", "Past Job")
        if title not in seen and len(recent_similar_projects) < 5:
            recent_similar_projects.append({
                "title": title,
                "niche": meta.get("category", "General"),
                "price_range": "Undisclosed",
                "outcome": meta.get("outcome", "UNKNOWN"),
                "short_summary": j.get("document", "")[:100] + "..."
            })
            seen.add(title)

    # Format portfolio items
    suggested_portfolio = []
    for p in portfolio:
        meta = p.get("metadata", {})
        suggested_portfolio.append({
            "title": meta.get("title", "Portfolio Sample"),
            "category": meta.get("category", ""),
            "snippet": p.get("document", "")[:100] + "..."
        })

    total_count = len(similar_jobs) + len(wins)

    # 2. Call AI to generate summary and relevant reply
    context_for_ai = {
        "job_title": job_title,
        "job_description": job_description[:1000],
        "similar_projects": recent_similar_projects,
        "portfolio_samples": suggested_portfolio
    }
    
    ai_generated = await copilot_ai.generate_recall_summary(context_for_ai, strict_voice_mode=strict_voice_mode)
    
    elapsed = round((time.time() - t0) * 1000, 1)

    return {
        "total_similar_projects_count": total_count,
        "recent_similar_projects": recent_similar_projects,
        "relevant_portfolio_matches": suggested_portfolio,
        "key_strength_patterns": ai_generated.get("key_strength_patterns", []),
        "suggested_experience_reply_short": ai_generated.get("suggested_experience_reply_short", "I have extensive experience here."),
        "suggested_experience_reply_confident": ai_generated.get("suggested_experience_reply_confident", "I've successfully completed multiple similar projects."),
        "suggested_experience_reply_strategic": ai_generated.get("suggested_experience_reply_strategic", "Based on my past wins in this exact niche, here is how I would approach it."),
        "compute_time_ms": elapsed
    }

