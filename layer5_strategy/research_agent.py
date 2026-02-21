import json
from FIOS.copilot.ai import _call_ai, SYSTEM_PROMPT
from FIOS.memory import retrieval
from FIOS.analytics import pricing_engine
from FIOS.layer5_strategy.strategy_engine import get_conversation

async def handle_chat(request):
    query = request.query or ""
    chat_history = request.context or "[]"
    
    vector_results = await retrieval.search_vector_memory(query, top_k=3)
    pricing = await pricing_engine.get_patterns("general")

    # If the user is inside an active room, grab the actual Upwork thread details:
    active_room_context = "No active room detected."
    if request.room_id:
        conv = await get_conversation(request.room_id)
        if conv:
            active_room_context = {
                "room_title": conv.thread_name or "Unknown Thread",
                "upwork_summary": conv.summary or "",
                "total_messages_in_thread": len(conv.messages_json) if conv.messages_json else 0,
                "latest_messages": conv.messages_json[-50:] if conv.messages_json else []
            }

    # Fallback to live extracted DOM data from frontend if DB is empty
    if active_room_context == "No active room detected." and request.data:
        print("[BrainFreeChat] WARNING: Database empty for room. Proceeding with Live Scraped frontend context.")
        payload = request.data
        if isinstance(payload, dict) and "messages" in payload:
            active_room_context = {
                "room_title": payload.get("thread_name", "Unknown UI Thread"),
                "upwork_summary": "Not yet synced to Database",
                "total_messages_on_screen": len(payload.get("messages", [])),
                "latest_messages": payload.get("messages", [])[-50:] 
            }
            print(f"[BrainFreeChat] Extracted {len(active_room_context['latest_messages'])} live messages from DOM.")
        else:
            print(f"[BrainFreeChat] Payload shape mismatch: {payload.keys() if isinstance(payload, dict) else type(payload)}")
    elif active_room_context == "No active room detected.":
        print("[BrainFreeChat] Warning: No DB Data AND no Live Scraped context passed from frontend.")

    try:
        history_obj = json.loads(chat_history)
    except:
        history_obj = []

    context = {
        "query": query,
        "active_upwork_room": active_room_context,
        "vector_search_results": vector_results if len(query) > 5 else "Omitted due to short query length.",
        "pricing_patterns": pricing if len(query) > 5 else "Omitted",
        "recent_chat_history": history_obj
    }
    
    behavioral_override = ""
    if len(query) <= 10:
        behavioral_override = "\nBehavioral Note: The user query is extremely short (e.g. 'hi'). Be welcoming, do not hallucinate past projects immediately, and ask how you can help them navigate their freelance tasks right now."

    prompt_instructions = (
        f"Execute FREE CHAT INTELLIGENCE MODE based on this context and user query:\n\n{json.dumps(context, indent=2)}\n\n"
        "Important Contextual Note: If the user says 'this' or refers to 'the client' or 'this message', they are explicitly "
        "referring to the `active_upwork_room` data provided in the JSON context. Do not ask for more context about the message, just reply to the latest_messages block.\n\n"
        "Active Memory: You MUST pay attention to the `recent_chat_history`. If the user asks a follow-up question, use the previous messages in that history to maintain continuity.\n\n"
        "Provide concise strategic output."
        f"{behavioral_override}\n\n"
        "IMPORTANT: Do NOT output your internal reasoning or say 'Here is my strategic output:'. "
        "Do NOT use the 5-part STRATEGIC format (Situation Analysis, Strategic Reasoning, Recommended Positioning, Final Draft, Confidence Level). "
        "If asked to write a reply, simply provide the raw text of the reply document, ready to copy-paste. Respond directly to the user in the first person as FIOS."
    )

    raw = await _call_ai(prompt_instructions, SYSTEM_PROMPT)
    return {"status": "success", "data": raw}
