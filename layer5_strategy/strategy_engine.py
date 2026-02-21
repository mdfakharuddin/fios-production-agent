import json
from FIOS.copilot.ai import _call_ai, SYSTEM_PROMPT
from FIOS.database.connection import async_session_maker
from FIOS.database.models.conversations import Conversation
from FIOS.analytics import pricing_engine
from FIOS.memory import retrieval
from sqlalchemy.future import select

async def get_conversation(room_id: str):
    async with async_session_maker() as session:
        result = await session.execute(select(Conversation).where(Conversation.room_id == room_id))
        return result.scalars().first()

async def get_profile():
    # Placeholder for actual profile fetch
    return {"skills": ["System Architecture", "React", "Python", "UX Design"], "price_range": "$50-$100/hr"}

async def handle_reply(request):
    """Strategic reply generation."""
    conversation = await get_conversation(request.room_id)
    if not conversation:
        return {"error": "Conversation not found"}

    summary = conversation.summary or "No summary available"
    similar = await retrieval.search_similar_conversations(summary, top_k=3)
    pricing = await pricing_engine.get_patterns("general")
    profile = await get_profile()
    
    messages = conversation.messages_json
    latest_message = messages[-1] if messages else {}

    context = {
        "profile": profile,
        "summary": summary,
        "similar_wins": similar,
        "pricing_patterns": pricing,
        "latest_message": latest_message,
        "action": "Generate strategic reply"
    }

    prompt = f"Provide a STRATEGIC REPLY for this conversation using the following context:\n\n{json.dumps(context, indent=2)}\n\nFormat your output as the exact JSON required in CONVERSATION INTELLIGENCE MODE."
    raw = await _call_ai(prompt, SYSTEM_PROMPT)
    return {"status": "success", "data": raw}

async def handle_quick_reply(request):
    """Quick reply generation."""
    conversation = await get_conversation(request.room_id)
    if not conversation:
        return {"error": "Conversation not found"}

    summary = conversation.summary or "No summary available"
    messages = conversation.messages_json or []
    latest_message = messages[-1] if messages else {}
    
    context = {"summary": summary, "latest_message": latest_message, "action": "Generate quick reply"}

    prompt = f"Provide a QUICK REPLY using only this context:\n\n{json.dumps(context, indent=2)}\n\nFormat your output as the exact JSON required for QUICK replying."
    raw = await _call_ai(prompt, SYSTEM_PROMPT)
    return {"status": "success", "data": raw}
