import json
from FIOS.copilot.ai import _call_ai, SYSTEM_PROMPT
from FIOS.memory import retrieval

async def generate_proposal(request):
    """Generate a proposal fully contextually."""
    job_context = request.job_context or {}
    job_desc = job_context.get("description", "")
    
    # Embed description to find top 2 matching wins
    similar_wins = await retrieval.search_similar_proposals(job_desc, outcome="won", top_k=2)
    
    profile = {"skills": ["Full Stack", "AI Strategy", "UI/UX"]}
    
    context = {
        "job_details": job_context,
        "similar_wins": similar_wins,
        "freelancer_profile": profile
    }

    prompt = f"Execute PROPOSAL GENERATION MODE based on this context:\n\n{json.dumps(context, indent=2)}\n\nReturn EXACTLY the JSON structure required for proposals."
    raw = await _call_ai(prompt, SYSTEM_PROMPT)
    return {"status": "success", "data": raw}
