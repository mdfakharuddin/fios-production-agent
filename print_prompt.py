import asyncio
from FIOS.layer5_strategy.research_agent import handle_chat
from FIOS.main import BrainRequest

async def main():
    req = BrainRequest(
        event_type="free_chat",
        query="write a reply for this message",
        context="[]",
        data={
            "type": "conversation",
            "payload": {
                "thread_name": "Test Client",
                "messages": [
                    {"role": "client", "sender": "Client", "text": "Can you handle the API integration by tomorrow?"}
                ]
            }
        }
    )
    # Mock _call_ai
    import FIOS.layer5_strategy.research_agent
    async def mock_call(prompt, system):
        print(prompt)
        return "MOCK"
    FIOS.layer5_strategy.research_agent._call_ai = mock_call

    await handle_chat(req)

asyncio.run(main())
