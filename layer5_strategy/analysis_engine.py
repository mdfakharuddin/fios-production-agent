import json
from copilot.ai import _call_ai, SYSTEM_PROMPT
from memory import retrieval
from analytics import pricing_engine

async def handle_job(request):
    """Analyze a new job opportunity."""
    
    # 1. Gather job context
    job_context = request.job_context or {}
    job_desc = job_context.get("description", "")
    
    # 2. Retrieve similar wins/losses
    similar_wins = await retrieval.search_similar_proposals(job_desc, outcome="won", top_k=3)
    similar_losses = await retrieval.search_similar_proposals(job_desc, outcome="lost", top_k=2)
    
    # 3. Get pricing patterns
    pricing = await pricing_engine.get_patterns(job_context.get("title", ""))
    
    context = {
        "job_details": job_context,
        "similar_wins": similar_wins,
        "similar_losses": similar_losses,
        "pricing_patterns": pricing
    }

    prompt = f"Perform JOB ANALYSIS MODE on this context:\n\n{json.dumps(context, indent=2)}\n\nReturn EXACTLY the JSON structure required by JOB ANALYSIS MODE."
    raw = await _call_ai(prompt, SYSTEM_PROMPT)
    return {"status": "success", "data": raw}
