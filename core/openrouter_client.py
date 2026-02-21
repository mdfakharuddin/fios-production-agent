import os
import httpx


class OpenRouterClient:

    def __init__(self):

        self.api_key = os.getenv("OPENROUTER_API_KEY")

        self.url = "https://openrouter.ai/api/v1/chat/completions"

        self.model = "deepseek/deepseek-chat"

    async def chat(self, messages):

        headers = {

            "Authorization": f"Bearer {self.api_key}",

            "Content-Type": "application/json"
        }

        payload = {

            "model": self.model,

            "messages": messages,

            "temperature": 0.2

        }

        async with httpx.AsyncClient(timeout=120) as client:

            response = await client.post(
                self.url,
                headers=headers,
                json=payload
            )

            result = response.json()

            return result["choices"][0]["message"]["content"]
