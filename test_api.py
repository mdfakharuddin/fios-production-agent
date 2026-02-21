import httpx
import asyncio

async def run():
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post('http://localhost:8000/api/chat', json={
            'user_id': 'user_123',
            'message': 'Write a proposal for a Webflow SaaS landing page redesign',
            'conversation_id': 'conv_001'
        })
        print(resp.json())

asyncio.run(run())
