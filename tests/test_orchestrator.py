import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

import asyncio

from core.orchestrator import orchestrator


async def test_proposal():
    user_id = "test_user"
    user_input = """
    Write a proposal for this job:

    We are looking for a Webflow expert to redesign our SaaS landing page.
    Must improve conversion rate and performance.
    """

    print("Sending proposal request to Orchestrator...")
    result = await orchestrator.process_user_input(
        user_input=user_input,
        user_id=user_id,
        conversation_id="test_convo_1"
    )

    print("\n=== PROPOSAL RESPONSE ===\n")
    print(result["response"])
    print("\nStrategy:", result["strategy"])
    print("\nAgent:", result["agent"])
    print("\nExecution time:", result["execution_time"])


async def test_conversation():
    user_id = "test_user"
    user_input = """
    Client asked: What would be the timeline and cost?
    """

    print("\nSending conversation request to Orchestrator...")
    result = await orchestrator.process_user_input(
        user_input=user_input,
        user_id=user_id,
        conversation_id="test_convo_2"
    )

    print("\n=== CONVERSATION RESPONSE ===\n")
    print(result["response"])
    print("\nStrategy:", result["strategy"])


async def main():
    await test_proposal()
    await test_conversation()


if __name__ == "__main__":
    asyncio.run(main())
