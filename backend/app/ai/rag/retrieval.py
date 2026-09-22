"""
Knowledge retrieval engine with strict scope isolation and citations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.ai.providers.embeddings import EmbeddingProvider
from app.ai.rag.ingestion import KNOWLEDGE_COLLECTION
from app.ai.rag.vector_store import VectorStore

logger = logging.getLogger("ai.rag.retrieval")


@dataclass
class RetrievedChunk:
    """A retrieved knowledge chunk with score and provenance."""

    chunk_id: int
    document_id: int
    source_id: int
    title: str
    content: str
    score: float
    scope_type: str
    scope_id: str | None = None

    def to_citation(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "source_id": self.source_id,
            "title": self.title,
            "snippet": self.content[:150] + "..." if len(self.content) > 150 else self.content,
        }


class KnowledgeRetriever:
    """Retrieval service enforcing cross-scope privacy isolation."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        self.embeddings = embedding_provider
        self.vector_store = vector_store

    async def retrieve(
        self,
        query: str,
        limit: int = 4,
        is_group: bool = False,
        group_id: str | None = None,
        user_id: str | int | None = None,
        min_score: float = 0.25,
    ) -> list[RetrievedChunk]:
        """
        Perform vector + lexical search while enforcing scope isolation.

        Scope Rules:
        - 'global' chunks are always accessible.
        - 'group' chunks are ONLY accessible if group_id matches.
        - 'user' chunks are ONLY accessible if user_id matches.
        """
        if not query or not query.strip():
            return []

        query_vec = await self.embeddings.embed_query(query.strip())
        if not query_vec:
            return []

        # Vector search top candidate points
        results = await self.vector_store.search(
            collection=KNOWLEDGE_COLLECTION,
            query_vector=query_vec,
            limit=limit * 3,  # Over-fetch for scope filtering and lexical boosting
        )

        allowed: list[RetrievedChunk] = []
        user_str = str(user_id) if user_id is not None else None

        for r in results:
            payload = r.payload
            scope_type = payload.get("scope_type", "global")
            scope_id = payload.get("scope_id")

            # P0: Strict Scope Isolation
            if scope_type == "global":
                pass  # Permitted
            elif scope_type == "group":
                if not is_group or not group_id or str(scope_id) != str(group_id):
                    continue  # Leakage prevention
            elif scope_type == "user":
                if not user_str or str(scope_id) != user_str:
                    continue  # Leakage prevention
            else:
                continue

            # Hybrid score: vector score + simple keyword bonus
            content = payload.get("content", "")
            title = payload.get("title", "")
            lexical_bonus = 0.0
            query_words = [w.lower() for w in query.split() if len(w) > 2]
            if query_words:
                text_lower = (title + " " + content).lower()
                matches = sum(1 for w in query_words if w in text_lower)
                lexical_bonus = (matches / len(query_words)) * 0.2

            final_score = r.score + lexical_bonus
            if final_score < min_score:
                continue

            allowed.append(
                RetrievedChunk(
                    chunk_id=payload.get("chunk_id", 0),
                    document_id=payload.get("document_id", 0),
                    source_id=payload.get("source_id", 0),
                    title=title,
                    content=content,
                    score=final_score,
                    scope_type=scope_type,
                    scope_id=scope_id,
                )
            )

        allowed.sort(key=lambda x: x.score, reverse=True)
        return allowed[:limit]
