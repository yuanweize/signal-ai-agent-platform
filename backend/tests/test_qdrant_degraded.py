"""
Tests for Qdrant failure vs empty result semantics.
Verifies Section 14:
- Legitimate 0-result search returns [] without error
- Vector store infrastructure failure raises VectorStoreUnavailableError
- AgentRuntime records degraded retrieval error in AIRun
- Knowledge-sensitive queries safely handoff without leaking internal exceptions to customer
- Diagnostics surfaces degraded status
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.ai.providers.embeddings import FakeEmbeddingProvider
from app.ai.rag.retrieval import KnowledgeRetriever
from app.ai.rag.vector_store import (
    VectorStoreUnavailableError,
)
from app.ai.runtime.agent_runtime import AgentRuntime
from app.ai.runtime.context import AgentContext
from app.api.deps import get_current_admin
from app.database import get_session
from app.main import app
from app.models.ai import AIRun
from app.models.config import BotConfig
from app.models.conversation import Conversation, ConversationType
from app.schemas.auth import AdminUser


@pytest.mark.asyncio
async def test_qdrant_empty_result_vs_infrastructure_failure():
    """Verify clean distinction between legitimate empty search and infrastructure failure."""
    from app.ai.rag.qdrant_store import QdrantVectorStore

    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(return_value=type("Res", (), {"points": []})())
    store = QdrantVectorStore(client=mock_client)

    # 1. Legitimate empty result returns []
    with patch.object(store, "_ensure_collection", new_callable=AsyncMock):
        results = await store.search(collection="test_col", query_vector=[0.1, 0.2], limit=3)
        assert results == []

    # 2. Infrastructure failure raises VectorStoreUnavailableError
    mock_client.query_points = AsyncMock(side_effect=ConnectionError("Connection refused by peer"))
    with patch.object(store, "_ensure_collection", new_callable=AsyncMock):
        with pytest.raises(VectorStoreUnavailableError) as exc_info:
            await store.search(collection="test_col", query_vector=[0.1, 0.2], limit=3)
        assert "Qdrant search failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_agent_runtime_retrieval_failure_marks_degraded_and_records_airun_error(session):
    """When vector store fails, AgentRuntime records degraded error in AIRun and executes safe handoff."""
    conv = Conversation(type=ConversationType.dm.value, signal_id="+200", mode="auto")
    session.add(conv)
    await session.commit()
    await session.refresh(conv)

    try:
        class FailingVectorStore:
            async def search(
                self, collection: str, query_vector: list[float], limit: int = 5, **kwargs
            ):
                raise VectorStoreUnavailableError("Qdrant service unreachable: connection refused")

            async def check_health(self) -> bool:
                return False

        failing_store = FailingVectorStore()
        retriever = KnowledgeRetriever(FakeEmbeddingProvider(), failing_store)

        runtime = AgentRuntime(
            retriever=retriever,
            vector_store=failing_store,
            is_test=True,
        )

        ctx = AgentContext(
            conversation_id=conv.id,
            sender_id="+200",
            text="What is your return policy for damaged items?",
            mode="auto",
        )
        res = await runtime.run(session, ctx)

        # 1. Decision must safely hand off when required knowledge is unreachable
        assert res.decision == "handoff"

        # 2. Never expose technical error messages or stack details to customer
        assert "Qdrant" not in res.answer
        assert "Vector store" not in res.answer
        assert any(w in res.answer.lower() for w in ["agent", "human", "representative", "team"])

        # 3. AIRun record must truthfully record degraded error
        run = (await session.execute(select(AIRun).where(AIRun.id == res.ai_run_id))).scalar_one()
        assert run.errors is not None
        assert "retrieval_degraded" in run.errors or "Vector store" in run.errors
    finally:
        await session.delete(conv)
        await session.commit()


@pytest.mark.asyncio
async def test_diagnostics_surfaces_degraded_when_vector_store_fails(session):
    """Diagnostics endpoint must report degraded status when vector store health check fails."""
    cfg = BotConfig(key="rag_enabled", value="true")
    session.add(cfg)
    await session.commit()

    app.dependency_overrides[get_current_admin] = lambda: AdminUser(username="admin")
    app.dependency_overrides[get_session] = lambda: session

    class FailingHealthStore:
        async def check_health(self) -> bool:
            return False

    class DummyRuntime:
        vector_store = FailingHealthStore()
        embedding_provider = FakeEmbeddingProvider()
        llm_provider = None
        llm = None

    with patch(
        "app.api.ai_studio.get_production_agent_runtime", new_callable=AsyncMock
    ) as mock_get_runtime:
        mock_get_runtime.return_value = DummyRuntime()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                resp = await client.get("/api/ai-studio/diagnostics")
                assert resp.status_code == 200
                data = resp.json()
                vec_info = data.get("vector_store", {})
                assert vec_info.get("status") == "degraded"
                rag_info = data.get("rag_index", {})
                assert rag_info.get("status") == "degraded"
        finally:
            app.dependency_overrides.clear()
            await session.delete(cfg)
            await session.commit()
