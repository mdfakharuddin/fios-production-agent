import os
import asyncpg
import json
from typing import List, Dict, Any, Optional

import pgvector.asyncpg

class VectorStore:
    """
    Production pgvector-based semantic memory store
    """

    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        self.pool = None
        self.vector_dimension = int(os.getenv("VECTOR_DIMENSION", "3072"))

    async def initialize(self):
        if self.pool is None:
            async def init_connection(conn):
                await pgvector.asyncpg.register_vector(conn)
            
            self.pool = await asyncpg.create_pool(
                dsn=self.db_url,
                min_size=2,
                max_size=10,
                init=init_connection
            )
            await self._create_table()

    async def _create_table(self):
        async with self.pool.acquire() as conn:
            # Enable the pgvector extension dynamically
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS memory_embeddings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT,
                content TEXT,
                embedding vector({self.vector_dimension}),
                metadata JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """)

            await conn.execute("""
            CREATE INDEX IF NOT EXISTS memory_embeddings_user_idx
            ON memory_embeddings(user_id);
            """)

        # Skipping IVFFLAT index as pgvector limits ivfflat to 2000 dimensions. Exact KNN is fast enough for <100k rows.

    async def store(
        self,
        embedding: List[float],
        text: str,
        metadata: Dict[str, Any]
    ):
        await self.initialize()
        async with self.pool.acquire() as conn:
            await conn.execute("""
            INSERT INTO memory_embeddings
            (user_id, content, embedding, metadata)
            VALUES ($1, $2, $3, $4)
            """,
            metadata.get("user_id"),
            text,
            embedding,
            json.dumps(metadata)
            )

    async def search(
        self,
        embedding: List[float],
        user_id: str,
        top_k: int = 8
    ) -> List[Dict]:
        await self.initialize()

        # Added safety fallback returning empty if embedding array is mismatched
        if len(embedding) != self.vector_dimension:
             return []

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
            SELECT
                id,
                content,
                metadata,
                1 - (embedding <=> $1) as similarity
            FROM memory_embeddings
            WHERE user_id = $2
            ORDER BY embedding <=> $1
            LIMIT $3
            """,
            embedding,
            user_id,
            top_k
            )

        return [
            {
                "id": str(row["id"]),
                "content": row["content"],
                "metadata": json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"],
                "similarity": row["similarity"]
            }
            for row in rows
        ]

    async def get_recent(
        self,
        user_id: str,
        limit: int = 50
    ):
        await self.initialize()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
            SELECT
                id,
                content,
                metadata,
                created_at
            FROM memory_embeddings
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id,
            limit
            )

        return [
            dict(row)
            for row in rows
        ]

    async def delete_user_memory(self, user_id: str):
        await self.initialize()
        async with self.pool.acquire() as conn:
            await conn.execute("""
            DELETE FROM memory_embeddings
            WHERE user_id = $1
            """,
            user_id
            )
