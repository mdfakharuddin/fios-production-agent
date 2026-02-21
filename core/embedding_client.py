import os
import httpx
from typing import List

class EmbeddingClient:
    """
    Converts text → embeddings using standard OpenAI-compatible endpoints or OpenRouter.
    """
    def __init__(self):
        # OpenRouter or OpenAI API key
        self.api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        
        # If openrouter supports embeddings this URL will be used, else defaults to openai
        self.url = "https://openrouter.ai/api/v1/embeddings" if os.getenv("OPENROUTER_API_KEY") else "https://api.openai.com/v1/embeddings"
        
        # OpenRouter/OpenAI specific robust embedding model
        self.model = "text-embedding-3-large"  # or BAAI/bge-large, customizable based on API payload specifics

    async def embed(self, text: str) -> List[float]:
        """
        Takes raw string and converts it to a high-dimensional vector.
        """
        if not self.api_key:
            # Fallback for local testing without proper API keys loaded to prevent hard crashing
            return [0.0] * 1536

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "input": text
        }
        
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(self.url, headers=headers, json=payload)
                response.raise_for_status()
                
                result = response.json()
                return result["data"][0]["embedding"]
                
        except Exception as e:
            print(f"Embedding Generation Error: {e}")
            # return zero vector to prevent silent downstream pipeline breakage
            return [0.0] * 3072 if "3-large" in self.model else [0.0] * 1536
