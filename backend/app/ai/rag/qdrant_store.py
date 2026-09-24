"""
Qdrant Vector Store implementation.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from app.ai.rag.vector_store import (
    VectorSearchResult,
    VectorStoreError,
    VectorStoreUnavailableError,
)

logger = logging.getLogger("ai.rag.qdrant")


def to_qdrant_id(raw_id: str | int) -> str | int:
    """Convert any string or integer ID to a valid Qdrant point ID (UUID or int)."""
    if isinstance(raw_id, int):
        return raw_id
    try:
        return str(uuid.UUID(str(raw_id)))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(raw_id)))


class QdrantVectorStore:
    """Qdrant-backed vector store implementation."""

    def __init__(
        self,
        url: str = "http://localhost:6333",
        api_key: str | None = None,
        dimension: int = 1536,
        timeout: float = 10.0,
        location: str | None = None,
        client: AsyncQdrantClient | None = None,
    ) -> None:
        self.url = url
        self.api_key = api_key
        self.dimension = dimension
        self.timeout = timeout
        self.location = location
        self._client: AsyncQdrantClient | None = client
        self._initialized_collections: set[str] = set()

    def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            if self.location:
                self._client = AsyncQdrantClient(location=self.location)
            else:
                self._client = AsyncQdrantClient(
                    url=self.url,
                    api_key=self.api_key,
                    timeout=self.timeout,
                )
        return self._client

    async def _ensure_collection(self, collection: str, vector_size: int) -> None:
        if collection in self._initialized_collections:
            return
        client = self._get_client()
        try:
            collections_resp = await client.get_collections()
            names = {c.name for c in collections_resp.collections}
            if collection not in names:
                await client.create_collection(
                    collection_name=collection,
                    vectors_config=qmodels.VectorParams(
                        size=vector_size,
                        distance=qmodels.Distance.COSINE,
                    ),
                )
                logger.info(f"Created Qdrant collection: {collection} (dim={vector_size})")
            self._initialized_collections.add(collection)
        except Exception as e:
            logger.warning(f"Could not verify/create Qdrant collection '{collection}': {e}")

    async def upsert(
        self,
        collection: str,
        points: list[dict[str, Any]],
    ) -> bool:
        if not points:
            return True
        vector_size = len(points[0]["vector"])
        await self._ensure_collection(collection, vector_size)
        client = self._get_client()

        q_points = [
            qmodels.PointStruct(
                id=to_qdrant_id(p["id"]),
                vector=p["vector"],
                payload={**p.get("payload", {}), "original_id": str(p["id"])},
            )
            for p in points
        ]
        try:
            await client.upsert(
                collection_name=collection,
                points=q_points,
            )
            return True
        except Exception as e:
            logger.error(f"Qdrant upsert failed: {e}")
            raise VectorStoreUnavailableError(f"Qdrant upsert failed: {e}") from e

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 5,
        filter_dict: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        client = self._get_client()
        await self._ensure_collection(collection, len(query_vector))

        q_filter = None
        if filter_dict:
            must_conditions = []
            for k, v in filter_dict.items():
                if isinstance(v, (list, set, tuple)):
                    must_conditions.append(
                        qmodels.FieldCondition(
                            key=k,
                            match=qmodels.MatchAny(any=list(v)),
                        )
                    )
                else:
                    must_conditions.append(
                        qmodels.FieldCondition(
                            key=k,
                            match=qmodels.MatchValue(value=v),
                        )
                    )
            if must_conditions:
                q_filter = qmodels.Filter(must=must_conditions)

        try:
            response = await client.query_points(
                collection_name=collection,
                query=query_vector,
                limit=limit,
                query_filter=q_filter,
                with_payload=True,
            )
            return [
                VectorSearchResult(
                    id=str(r.payload.get("original_id", r.id)),
                    score=float(r.score),
                    payload=r.payload or {},
                )
                for r in response.points
            ]
        except Exception as e:
            logger.error(f"Qdrant search error: {e}")
            raise VectorStoreUnavailableError(f"Qdrant search failed: {e}") from e

    async def check_health(self) -> bool:
        """Check if Qdrant instance is reachable and healthy."""
        try:
            client = self._get_client()
            await client.get_collections()
            return True
        except Exception as e:
            logger.debug(f"Qdrant health check failed: {e}")
            return False

    async def delete(
        self,
        collection: str,
        ids: list[str],
    ) -> bool:
        client = self._get_client()
        q_ids = [to_qdrant_id(i) for i in ids]
        try:
            await client.delete(
                collection_name=collection,
                points_selector=qmodels.PointIdsList(points=q_ids),
            )
            return True
        except Exception as e:
            logger.error(f"Qdrant delete error: {e}")
            raise VectorStoreError(f"Qdrant delete failed: {e}") from e

    async def delete_collection(self, collection: str) -> bool:
        client = self._get_client()
        try:
            await client.delete_collection(collection_name=collection)
            self._initialized_collections.discard(collection)
            return True
        except Exception as e:
            logger.error(f"Qdrant delete collection error: {e}")
            raise VectorStoreError(f"Qdrant delete collection error: {e}") from e
