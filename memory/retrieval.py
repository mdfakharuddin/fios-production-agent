"""
FIOS Semantic Memory — Hybrid Store (ChromaDB + SQLite Fallback)

When ChromaDB is unavailable (Python 3.14 Pydantic issue), falls back to
direct SQLite queries against the existing FIOS database to provide
historical recall for the Brain Context Protocol.
"""

from FIOS.core.config import settings
from typing import List, Dict, Any, Optional
import uuid
import hashlib
import warnings
import json
import os


COLLECTIONS = [
    "conversations",
    "winning_proposals",
    "losing_proposals",
    "job_descriptions",
    "portfolio_samples",
]


class SemanticMemory:
    """Manages vector store + SQLite fallback for FIOS Brain."""

    def __init__(self):
        self.client = None
        self._collections: Dict[str, Any] = {}
        self._init_error: Optional[str] = None
        self._initialized = False
        self._use_fallback = False

    def _ensure_initialized(self) -> bool:
        """Lazy-init ChromaDB client. Returns True if available."""
        if self._initialized:
            return self.client is not None

        self._initialized = True
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self.client = chromadb.PersistentClient(
                    path=settings.CHROMA_PERSIST_DIRECTORY,
                    settings=ChromaSettings(allow_reset=True, anonymized_telemetry=False),
                )
            for name in COLLECTIONS:
                self._collections[name] = self.client.get_or_create_collection(
                    name=name,
                    metadata={"hnsw:space": "cosine"},
                )
            print("[SemanticMemory] ChromaDB initialized successfully.")
            return True
        except Exception as e:
            self._init_error = str(e)
            self._use_fallback = True
            print(f"[SemanticMemory] ChromaDB unavailable: {e}")
            print("[SemanticMemory] Using SQLite fallback for historical recall.")
            return False

    def collection(self, name: str):
        if not self._ensure_initialized():
            return None
        if name not in self._collections:
            self._collections[name] = self.client.get_or_create_collection(
                name=name, metadata={"hnsw:space": "cosine"}
            )
        return self._collections[name]

    # ── Embed helpers ──────────────────────────────────────────────────────

    def _doc_id(self, prefix: str, text: str) -> str:
        h = hashlib.md5(text.encode()).hexdigest()[:12]
        return f"{prefix}_{h}"

    def embed_texts(self, collection_name: str, texts: List[str],
                    metadatas: Optional[List[dict]] = None, id_prefix: str = "doc") -> int:
        col = self.collection(collection_name)
        if col is None:
            return 0

        ids = [self._doc_id(id_prefix, t) for t in texts]
        existing = set()
        try:
            existing_docs = col.get(ids=ids)
            existing = set(existing_docs["ids"]) if existing_docs["ids"] else set()
        except Exception:
            pass

        new_ids, new_texts, new_metas = [], [], []
        for i, (doc_id, text) in enumerate(zip(ids, texts)):
            if doc_id not in existing and text.strip():
                new_ids.append(doc_id)
                new_texts.append(text)
                new_metas.append(metadatas[i] if metadatas else {})

        if new_texts:
            col.add(documents=new_texts, metadatas=new_metas, ids=new_ids)

        return len(new_texts)

    def embed_conversation(self, room_id: str, messages: List[dict]) -> int:
        if not messages:
            return 0
        chunks, current_chunk, current_len = [], [], 0
        for m in messages:
            sender = m.get("sender", m.get("role", "unknown"))
            text = m.get("text", "")
            line = f"{sender}: {text}"
            current_chunk.append(line)
            current_len += len(line)
            if current_len >= 500:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0
        if current_chunk:
            chunks.append("\n".join(current_chunk))
        metadatas = [{"room_id": room_id, "chunk_index": i} for i in range(len(chunks))]
        return self.embed_texts("conversations", chunks, metadatas, id_prefix=f"conv_{room_id[:8]}")

    def embed_proposal(self, proposal_id: str, text: str, outcome: str = "pending", job_title: str = "") -> int:
        if not text.strip():
            return 0
        collection_name = "winning_proposals" if outcome == "won" else "losing_proposals"
        meta = {"proposal_id": proposal_id, "outcome": outcome, "job_title": job_title}
        return self.embed_texts(collection_name, [text], [meta], id_prefix=f"prop_{proposal_id[:8]}")

    def embed_job(self, job_id: str, title: str, description: str) -> int:
        full_text = f"{title}\n\n{description}"
        meta = {"job_id": job_id, "title": title}
        return self.embed_texts("job_descriptions", [full_text], [meta], id_prefix=f"job_{job_id[:8]}")

    # ── Search ─────────────────────────────────────────────────────────────

    def search_similar(self, collection_name: str, query: str, n: int = 5,
                       where: dict = None, max_distance: float = 1.2) -> List[Dict[str, Any]]:
        """Search by ChromaDB or fall back to SQLite keyword search."""
        # Try ChromaDB first
        if self._ensure_initialized():
            return self._chroma_search(collection_name, query, n, where, max_distance)

        # Fallback: SQLite keyword search
        return self._sqlite_fallback_search(collection_name, query, n)

    def _chroma_search(self, collection_name, query, n, where, max_distance):
        col = self.collection(collection_name)
        if col is None or col.count() == 0:
            return []
        kwargs = {"query_texts": [query], "n_results": min(n, col.count())}
        if where:
            kwargs["where"] = where
        try:
            results = col.query(**kwargs)
        except Exception:
            return []

        items = []
        if results and results["documents"] and results["distances"]:
            for i, doc in enumerate(results["documents"][0]):
                dist = results["distances"][0][i]
                if dist <= max_distance:
                    items.append({
                        "id": results["ids"][0][i] if results["ids"] else "",
                        "text": doc,
                        "document": doc,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": dist,
                    })
        return items

    def _sqlite_fallback_search(self, collection_name: str, query: str, n: int) -> List[Dict[str, Any]]:
        """Keyword-based fallback search against the FIOS SQLite database."""
        import sqlite3

        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fios_local_db.sqlite3")
        if not os.path.exists(db_path):
            return []

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            results = []

            # Extract keywords from query (ignore common words)
            stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "and", "or", "i", "we", "you", "it", "this", "that"}
            keywords = [w.lower().strip() for w in query.split() if len(w) > 2 and w.lower() not in stop_words][:8]

            if collection_name in ("winning_proposals", "losing_proposals"):
                rows = cur.execute("SELECT id, cover_letter, bid_amount, status FROM proposals").fetchall()
                for row in rows:
                    text = row["cover_letter"] or ""
                    score = sum(1 for kw in keywords if kw in text.lower())
                    if score > 0 or not keywords:
                        outcome = "won" if row["status"] in ("HIRED", "WON") else "pending"
                        if collection_name == "winning_proposals" and outcome != "won":
                            continue
                        if collection_name == "losing_proposals" and outcome == "won":
                            continue
                        results.append({
                            "id": str(row["id"]),
                            "text": text[:500],
                            "document": text[:500],
                            "metadata": {
                                "proposal_id": str(row["id"]),
                                "bid_amount": row["bid_amount"],
                                "outcome": outcome,
                                "job_title": "",
                            },
                            "distance": 1.0 - (score / max(len(keywords), 1)),
                            "_score": score,
                        })

                # If no category-specific matches, return all proposals for context
                if not results and collection_name == "winning_proposals":
                    rows = cur.execute("SELECT id, cover_letter, bid_amount, status FROM proposals LIMIT ?", (n,)).fetchall()
                    for row in rows:
                        text = row["cover_letter"] or ""
                        results.append({
                            "id": str(row["id"]),
                            "text": text[:500],
                            "document": text[:500],
                            "metadata": {
                                "proposal_id": str(row["id"]),
                                "bid_amount": row["bid_amount"],
                                "outcome": "reference",
                            },
                            "distance": 0.8,
                            "_score": 0,
                        })

            elif collection_name == "conversations":
                rows = cur.execute("SELECT id, thread_name, messages_json, summary FROM conversations WHERE messages_json IS NOT NULL AND messages_json != '[]'").fetchall()
                for row in rows:
                    text = (row["thread_name"] or "") + " " + (row["summary"] or "")
                    msgs_raw = row["messages_json"] or "[]"
                    try:
                        msgs = json.loads(msgs_raw) if isinstance(msgs_raw, str) else msgs_raw
                        text += " " + " ".join(m.get("text", "") for m in msgs[-5:])
                    except Exception:
                        pass
                    score = sum(1 for kw in keywords if kw in text.lower())
                    if score > 0 or not keywords:
                        results.append({
                            "id": str(row["id"]),
                            "text": text[:400],
                            "document": text[:400],
                            "metadata": {"room_id": str(row["id"])},
                            "distance": 1.0 - (score / max(len(keywords), 1)),
                            "_score": score,
                        })

            elif collection_name == "job_descriptions":
                rows = cur.execute("SELECT id, title, description FROM jobs").fetchall()
                for row in rows:
                    text = (row["title"] or "") + " " + (row["description"] or "")
                    score = sum(1 for kw in keywords if kw in text.lower())
                    if score > 0 or not keywords:
                        results.append({
                            "id": str(row["id"]),
                            "text": text[:400],
                            "document": text[:400],
                            "metadata": {"job_id": str(row["id"]), "title": row["title"]},
                            "distance": 1.0 - (score / max(len(keywords), 1)),
                            "_score": score,
                        })

            conn.close()

            # Sort by relevance score and return top N
            results.sort(key=lambda x: x.get("_score", 0), reverse=True)
            return results[:n]

        except Exception as e:
            print(f"[SemanticMemory] SQLite fallback error: {e}")
            return []

    # ── Stats ──────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, int]:
        if self._ensure_initialized():
            return {name: self.collection(name).count() for name in COLLECTIONS}

        # Fallback: count from SQLite
        import sqlite3
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fios_local_db.sqlite3")
        if not os.path.exists(db_path):
            return {name: 0 for name in COLLECTIONS}
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            proposals = cur.execute("SELECT COUNT(*) FROM proposals").fetchone()[0]
            convos = cur.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            jobs = cur.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            conn.close()
            return {
                "conversations": convos,
                "winning_proposals": proposals,
                "losing_proposals": 0,
                "job_descriptions": jobs,
                "portfolio_samples": 0,
            }
        except Exception:
            return {name: 0 for name in COLLECTIONS}

    def get_freelancer_profile(self) -> Dict[str, Any]:
        """Build freelancer profile from available data."""
        stats = self.get_stats()
        total_proposals = stats.get("winning_proposals", 0) + stats.get("losing_proposals", 0)

        # Try to extract richer profile from SQLite
        profile = {
            "total_conversations": stats.get("conversations", 0),
            "total_proposals": total_proposals,
            "winning_proposals": stats.get("winning_proposals", 0),
            "losing_proposals": stats.get("losing_proposals", 0),
            "win_rate_pct": 0,
            "jobs_indexed": stats.get("job_descriptions", 0),
            "portfolio_samples": stats.get("portfolio_samples", 0),
        }

        # Enrich from SQLite if available
        import sqlite3
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fios_local_db.sqlite3")
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()

                # Extract niches from job categories
                categories = cur.execute("SELECT DISTINCT category FROM jobs WHERE category IS NOT NULL").fetchall()
                profile["niches"] = [c[0] for c in categories if c[0]]

                # Extract skills from jobs
                skills_raw = cur.execute("SELECT skills_required FROM jobs WHERE skills_required IS NOT NULL").fetchall()
                all_skills = []
                for s in skills_raw:
                    try:
                        parsed = json.loads(s[0]) if isinstance(s[0], str) else s[0]
                        if isinstance(parsed, list):
                            all_skills.extend(parsed)
                    except Exception:
                        pass
                # Count frequency
                from collections import Counter
                skill_counts = Counter(all_skills)
                profile["strongest_categories"] = [s for s, _ in skill_counts.most_common(5)]

                # Average bid amount
                bids = cur.execute("SELECT bid_amount FROM proposals WHERE bid_amount > 0").fetchall()
                if bids:
                    amounts = [b[0] for b in bids]
                    profile["average_price_range"] = f"${min(amounts):.0f} - ${max(amounts):.0f}/hr"

                conn.close()
            except Exception as e:
                print(f"[SemanticMemory] Profile enrichment error: {e}")

        return profile


# ── Global singleton ──────────────────────────────────────────────────────
memory = SemanticMemory()

import asyncio

async def search_similar_conversations(query: str, top_k: int = 3):
    return memory.search_similar("conversations", query, n=top_k)

async def search_similar_proposals(query: str, outcome: str = "won", top_k: int = 3):
    collection = "winning_proposals" if outcome == "won" else "losing_proposals"
    return memory.search_similar(collection, query, n=top_k)

async def search_vector_memory(query: str, top_k: int = 3):
    # Search all collections
    res = []
    res.extend(memory.search_similar("conversations", query, n=top_k))
    res.extend(memory.search_similar("winning_proposals", query, n=top_k))
    return res[:top_k]
