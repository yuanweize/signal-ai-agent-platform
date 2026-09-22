"""
Production AgentRuntime Factory & Dependency Injection.

Strictly distinguishes production runtime from testing/mock runtime:
- In production, instantiates OpenAICompatibleProvider, OpenAICompatibleEmbeddingProvider,
  and QdrantVectorStore (or graceful degraded mode if unconfigured).
- Fake providers are ONLY allowed when explicitly requested for testing/CI.
- Silent fallback to FakeLLMProvider in production is strictly prohibited.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory.providers import NativeMemoryProvider
from app.ai.providers.embeddings import (
    EmbeddingProvider,
    FakeEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from app.ai.providers.llm import (
    DisabledLLMProvider,
    FakeLLMProvider,
    LLMProvider,
    OpenAICompatibleProvider,
)
from app.ai.rag.qdrant_store import QdrantVectorStore
from app.ai.rag.retrieval import KnowledgeRetriever
from app.ai.rag.vector_store import FakeVectorStore, VectorStore
from app.ai.runtime.agent_runtime import AgentRuntime
from app.services.runtime_config import get_runtime_settings, is_ai_api_key_optional

logger = logging.getLogger("ai.runtime.factory")


def is_test_environment() -> bool:
    """Check if execution is under pytest or explicit test environment."""
    if os.getenv("ENVIRONMENT", "").lower() in ("production", "prod"):
        return False
    return (
        os.getenv("TESTING", "").lower() in ("1", "true", "yes")
        or os.getenv("ENVIRONMENT", "").lower() in ("test", "testing")
        or bool(os.getenv("PYTEST_CURRENT_TEST"))
    )


def create_agent_runtime(
    settings: dict[str, Any] | None = None,
    is_test: bool | None = None,
    fake_llm_reply: str | None = None,
) -> AgentRuntime:
    """
    Factory constructing an AgentRuntime instance according to execution environment and configuration.

    Rules:
    - If is_test=True, allows Fake providers.
    - If in production (is_test=False), strictly requires real providers or disabled state.
      Silent fallback to FakeLLMProvider or FakeVectorStore is strictly forbidden.
    - If is_test=None, auto-detects test environment.
    """
    settings = settings or {}
    test_mode = is_test if is_test is not None else is_test_environment()

    # 1. LLM Provider instantiation
    llm: LLMProvider
    if test_mode:
        llm = FakeLLMProvider(fixed_reply=fake_llm_reply)
    else:
        ai_base_url = (settings.get("ai_api_base_url") or "").strip()
        ai_api_key = (settings.get("ai_api_key") or "").strip()
        ai_model = (settings.get("ai_model") or "gpt-4o-mini").strip()
        ai_enabled = bool(settings.get("is_ai_enabled", True))
        has_valid_auth = bool(ai_api_key) or is_ai_api_key_optional(ai_base_url)

        if not ai_enabled:
            logger.info("Production AI is disabled in Settings. Initializing DisabledLLMProvider.")
            llm = DisabledLLMProvider(reason="AI is disabled in Settings")
        elif not has_valid_auth:
            logger.warning(
                "Production AI has no valid credentials. Initializing DisabledLLMProvider."
            )
            llm = DisabledLLMProvider(reason="Missing API key for AI provider")
        else:
            llm = OpenAICompatibleProvider(
                base_url=ai_base_url,
                api_key=ai_api_key,
                default_model=ai_model,
                temperature=float(settings.get("ai_temperature", 0.7)),
                max_tokens=int(settings.get("ai_max_tokens", 800)),
            )

    # 2. Embedding Provider & Vector Store instantiation
    embed_provider: EmbeddingProvider | None = None
    vector_store: VectorStore | None = None

    rag_enabled = bool(settings.get("rag_enabled", True))
    if not rag_enabled:
        embed_provider = None
        vector_store = None
    elif test_mode:
        embed_provider = FakeEmbeddingProvider()
        vector_store = FakeVectorStore()
    else:
        vector_backend = (
            settings.get("vector_store_provider")
            or os.getenv("AI_VECTOR_STORE_BACKEND")
            or "qdrant"
        ).lower()

        if vector_backend == "qdrant":
            embed_base_url = (
                settings.get("embedding_base_url") or settings.get("ai_api_base_url") or ""
            ).strip()
            embed_api_key = (
                settings.get("embedding_api_key") or settings.get("ai_api_key") or ""
            ).strip()
            embed_model = (settings.get("embedding_model") or "text-embedding-3-small").strip()

            if embed_api_key or is_ai_api_key_optional(embed_base_url):
                embed_provider = OpenAICompatibleEmbeddingProvider(
                    base_url=embed_base_url or "https://api.openai.com/v1",
                    api_key=embed_api_key or "__NO_KEY__",
                    model=embed_model,
                )
            else:
                embed_provider = None

            qdrant_url = (
                settings.get("qdrant_url") or os.getenv("QDRANT_URL") or "http://localhost:6333"
            )
            qdrant_key = settings.get("qdrant_api_key") or os.getenv("QDRANT_API_KEY")
            vector_store = QdrantVectorStore(url=qdrant_url, api_key=qdrant_key)
        else:
            raise RuntimeError(
                f"Production runtime requires 'qdrant' vector store or explicit rag_enabled=False. "
                f"Unknown or test-only provider '{vector_backend}' is prohibited in production."
            )

    retriever = (
        KnowledgeRetriever(embed_provider, vector_store)
        if (embed_provider is not None and vector_store is not None)
        else None
    )
    memory_provider = NativeMemoryProvider()

    runtime = AgentRuntime(
        llm_provider=llm,
        retriever=retriever,
        memory_provider=memory_provider,
        vector_store=vector_store,
        embedding_provider=embed_provider,
        is_test=test_mode,
        rag_enabled=rag_enabled,
    )
    return runtime


async def get_production_agent_runtime(session: AsyncSession) -> AgentRuntime:
    """Read DB runtime configuration and build live AgentRuntime for current turn."""
    settings = await get_runtime_settings(session)
    return create_agent_runtime(settings=settings, is_test=None)
