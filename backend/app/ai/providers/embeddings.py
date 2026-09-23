"""
Embedding provider abstractions and implementations.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable

from openai import AsyncOpenAI


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for generating vector embeddings."""

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query text string."""
        ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document text strings."""
        ...


class OpenAICompatibleEmbeddingProvider:
    """Embedding provider using OpenAI or compatible API endpoints."""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "text-embedding-3-small",
        timeout: float = 20.0,
    ) -> None:
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = api_key or "__NO_KEY__"
        self.model = model
        self.timeout = timeout
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            effective_base_url = self.base_url or "https://api.openai.com/v1"
            if effective_base_url and not effective_base_url.endswith("/v1"):
                effective_base_url = f"{effective_base_url}/v1"
            self._client = AsyncOpenAI(
                base_url=effective_base_url,
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=2,
            )
        return self._client

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_documents([text])
        return vectors[0] if vectors else []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        response = await client.embeddings.create(
            model=self.model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    embed = embed_documents


class FakeEmbeddingProvider:
    """Deterministic, lightweight pseudo-embedding provider for testing and CI."""

    def __init__(self, dimension: int = 64) -> None:
        self.dimension = dimension

    def _hash_vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        words = text.lower().split()
        if not words:
            vec[0] = 1.0
            return vec

        for word in words:
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            vec[idx] += 1.0

        # L2 normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    async def embed_query(self, text: str) -> list[float]:
        return self._hash_vector(text)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_vector(t) for t in texts]
