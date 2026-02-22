import json
from copilot.ai import _call_ai, SYSTEM_PROMPT
from memory import retrieval

async def generate_proposal(request):
    """Generate a proposal fully contextually."""
    from brain_store import load_brain
    
    job_context = request.job_context or {}
    job_desc = job_context.get("description", "")
    job_title = job_context.get("title", "this project")
    
    # Embed description to find top matching wins
    similar_wins = await retrieval.search_similar_proposals(job_desc, outcome="won", top_k=2)
    
    # Load real profile from brain
    brain = load_brain()
    profile = brain.get("freelancer", {
        "strongest_skills": ["Full Stack Development", "Python", "React", "AI Integration"],
        "authority_level": "Professional"
    })
    
    context = {
        "job_details": {
            "title": job_title,
            "description": job_desc[:2000] # Limit to avoid token blowup
        },
        "similar_wins": similar_wins if similar_wins else "No specific matches in local memory yet.",
        "freelancer_profile": profile,
        "action": "Generate high-conversion proposal"
    }

    # Enhanced prompt to prevent generic hallucinations
    prompt = f"""Execute PROPOSAL GENERATION MODE for a job titled '{job_title}'.
    
    USE THIS CONTEXT TO INFORM YOUR TONE AND SPECIFICS:
    {json.dumps(context, indent=2)}
    
    If 'similar_wins' are missing, rely on the 'freelancer_profile' skills to craft a relevant pitch.
    DO NOT hallucinate specific project IDs or past clients that are not in the context.
    Return EXACTLY the JSON structure required for proposals."""
    
    raw = await _call_ai(prompt, SYSTEM_PROMPT)
    return {"status": "success", "data": raw}
