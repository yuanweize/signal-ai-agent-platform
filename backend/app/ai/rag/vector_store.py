"""
Vector store abstraction and in-memory mock store.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class VectorStoreError(RuntimeError):
    """Raised when vector store upsert, search, or deletion fails."""


@dataclass
class VectorSearchResult:
    """Result of a vector similarity search."""

    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class VectorStore(Protocol):
    """Protocol for vector storage and retrieval."""

    async def upsert(
        self,
        collection: str,
        points: list[dict[str, Any]],
    ) -> bool:
        """Upsert points: list of {'id': str, 'vector': list[float], 'payload': dict}."""
        ...

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 5,
        filter_dict: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        """Search points by vector similarity with optional payload metadata filtering."""
        ...

    async def delete(
        self,
        collection: str,
        ids: list[str],
    ) -> bool:
        """Delete points by IDs."""
        ...

    async def delete_collection(self, collection: str) -> bool:
        """Delete an entire collection."""
        ...


class FakeVectorStore:
    """In-memory vector store with cosine similarity and metadata filtering."""

    def __init__(self) -> None:
        self.collections: dict[str, dict[str, dict[str, Any]]] = {}

    def _cosine_similarity(self, v1: list[float], v2: list[float]) -> float:
        if len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 <= 0 or norm2 <= 0:
            return 0.0
        return dot / (norm1 * norm2)

    async def upsert(
        self,
        collection: str,
        points: list[dict[str, Any]],
    ) -> bool:
        if collection not in self.collections:
            self.collections[collection] = {}

        for p in points:
            pid = str(p["id"])
            self.collections[collection][pid] = {
                "vector": p["vector"],
                "payload": p.get("payload", {}),
            }
        return True

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 5,
        filter_dict: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        if collection not in self.collections:
            return []

        scored: list[VectorSearchResult] = []
        for pid, data in self.collections[collection].items():
            payload = data.get("payload", {})

            # Apply metadata filtering
            match = True
            if filter_dict:
                for k, v in filter_dict.items():
                    if isinstance(v, (list, set, tuple)):
                        if payload.get(k) not in v:
                            match = False
                            break
                    elif payload.get(k) != v:
                        match = False
                        break
            if not match:
                continue

            score = self._cosine_similarity(query_vector, data["vector"])
            scored.append(VectorSearchResult(id=pid, score=score, payload=payload))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:limit]

    async def delete(
        self,
        collection: str,
        ids: list[str],
    ) -> bool:
        if collection not in self.collections:
            return True
        for pid in ids:
            self.collections[collection].pop(str(pid), None)
        return True

    async def delete_collection(self, collection: str) -> bool:
        self.collections.pop(collection, None)
        return True
