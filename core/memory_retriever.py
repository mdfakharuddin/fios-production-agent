import json
import os
from typing import Dict, List, Optional

from database.vector_store import VectorStore
# from database.models import Proposal, Conversation, Client, Job
from core.embedding_client import EmbeddingClient

class MemoryRetriever:

    def __init__(self):
        self.vector_store = VectorStore()
        self.embedding_client = EmbeddingClient()
        self.brain_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "brain", "brain_snapshot.json")

    async def retrieve_relevant_context(
        self,
        user_id: str,
        query: str,
        conversation_id: Optional[str] = None,
        top_k: int = 8
    ) -> Dict:
        
        embedding = await self.embedding_client.embed(query)

        # MOCKED UNTIL VECTOR STORE IS CREATED
        vector_results = await self.vector_store.search(
            embedding=embedding,
            top_k=top_k,
            user_id=user_id
        )
        # vector_results = []

        proposals = await self._retrieve_proposals(user_id, vector_results)

        conversations = await self._retrieve_conversations(
            user_id,
            vector_results,
            conversation_id
        )

        clients = await self._retrieve_clients(user_id, vector_results)

        brain_snapshot = self._load_brain_snapshot()

        return {
            "proposals": proposals,
            "conversations": conversations,
            "clients": clients,
            "brain_snapshot": brain_snapshot,
            "memory_ids": [r["id"] for r in vector_results]
        }

    async def store_interaction(
        self,
        user_id: str,
        user_input: str,
        response: str,
        strategy: Dict,
        conversation_id: Optional[str] = None
    ):

        combined_text = f"""
USER:
{user_input}

ASSISTANT:
{response}
"""

        embedding = await self.embedding_client.embed(combined_text)

        # MOCKED UNTIL VECTOR STORE IS CREATED
        await self.vector_store.store(
            embedding=embedding,
            text=combined_text,
            metadata={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "strategy": strategy["agent"],
                "timestamp": self._timestamp()
            }
        )
        pass

    async def retrieve_recent_interactions(
        self,
        user_id: str,
        limit: int = 50
    ):
        return await self.vector_store.get_recent(user_id, limit)

    async def get_active_conversations(self, user_id: str):
        # return Conversation.get_active(user_id)
        return []

    async def store_insights(self, user_id: str, insights: Dict):
        
        insights_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "brain", "insights")
        os.makedirs(insights_dir, exist_ok=True)
        path = os.path.join(insights_dir, f"{user_id}.json")

        with open(path, "w") as f:
            json.dump(insights, f, indent=2)

    async def _retrieve_proposals(self, user_id, vector_results):
        proposal_ids = [
            r["metadata"].get("proposal_id")
            for r in vector_results
            if r["metadata"].get("proposal_id")
        ]
        # return Proposal.get_by_ids(proposal_ids)
        return []

    async def _retrieve_conversations(
        self,
        user_id,
        vector_results,
        conversation_id
    ):
        ids = [
            r["metadata"].get("conversation_id")
            for r in vector_results
            if r["metadata"].get("conversation_id")
        ]
        if conversation_id:
            ids.append(conversation_id)
        # return Conversation.get_by_ids(ids)
        return []

    async def _retrieve_clients(self, user_id, vector_results):
        client_ids = [
            r["metadata"].get("client_id")
            for r in vector_results
            if r["metadata"].get("client_id")
        ]
        # return Client.get_by_ids(client_ids)
        return []

    def _load_brain_snapshot(self):
        if not os.path.exists(self.brain_path):
            return {}
        with open(self.brain_path, "r") as f:
            return json.load(f)

    def _timestamp(self):
        import datetime
        return datetime.datetime.utcnow().isoformat()
