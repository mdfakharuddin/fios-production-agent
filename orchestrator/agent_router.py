from typing import Dict, Any

from FIOS.layer5_strategy import strategy_engine, analysis_engine, execution_engine, research_agent
from FIOS.analytics import pricing_engine

async def route(request) -> Dict[str, Any]:
    """Single-Entry Intelligence Router."""
    event_type = request.event_type

    try:
        if event_type == "strategic_reply" or event_type == "agent_strategic_reply":
            return await strategy_engine.handle_reply(request)

        elif event_type == "quick_reply" or event_type == "agent_quick_reply":
            return await strategy_engine.handle_quick_reply(request)

        elif event_type == "job_analysis":
            return await analysis_engine.handle_job(request)

        elif event_type == "generate_proposal" or event_type == "proposal_generation":
            return await execution_engine.generate_proposal(request)

        elif event_type == "free_chat" or event_type == "agent_free_chat":
            return await research_agent.handle_chat(request)
            
        elif event_type == "analyze_conversation":
            # Temporary bridge using strategy engine
            res = await strategy_engine.handle_reply(request)
            return {"status": "success", "data": {"stage": "Negotiation", "tone": "Professional", "risk": "Low", "full_analysis": res}}
            
        elif event_type == "agent_pricing_advice":
            pricing = await pricing_engine.get_patterns(request.query or "")
            return {"status": "success", "data": {"pricing_analysis": "Based on history", "suggested_price": pricing.get("avg_price", 0)}}
            
        else:
            return {"status": "error", "message": f"Unknown event type: {event_type}"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}
