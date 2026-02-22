import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator.pipelines import pipeline
from database.connection import async_session_maker
from database.models.conversations import Conversation
from sqlalchemy.future import select
import uuid

async def run():
    async with async_session_maker() as session:
        # Fetch the specific row we modified (using UUID formatting)
        target_id = uuid.UUID("5260d754-fecb-44b7-a83b-ddf4bff6e30d")
        res = await session.execute(select(Conversation).where(Conversation.id == target_id))
        conv = res.scalars().first()
        print(f"Conversation found: {conv is not None}")
        if conv:
            print(f"Room ID: {conv.room_id}")
            print(f"Messages count: {len(conv.messages_json)}")
            await pipeline.trigger_ai_summary(conv.id, conv.messages_json)
            print("Successfully triggered AI summary regen.")
            
        # Re-fetch thread status to verify
        status = await pipeline.get_thread_status("4a0cfabc23e9102e886332596b92c28e")
        print(f"Thread Status after regen: {status}")

asyncio.run(run())
