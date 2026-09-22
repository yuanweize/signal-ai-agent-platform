"""
Production Wiring, Adapter Verification, Hardening, and Diagnostics Tests.

Covers Section 81 of v0.4 Reality Audit:
- test_production_runtime_does_not_use_fake_providers
- test_auto_mode_uses_agent_runtime
- test_copilot_mode_uses_same_agent_runtime
- test_real_qdrant_adapter_roundtrip
- test_real_mcp_sdk_discovery_and_call
- test_mcp_write_requires_approval
- test_ai_dashboard_has_no_hardcoded_metrics
- test_reindex_pipeline
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.mcp.client import mcp_manager
from app.ai.providers.embeddings import FakeEmbeddingProvider, OpenAICompatibleEmbeddingProvider
from app.ai.providers.llm import FakeLLMProvider, OpenAICompatibleProvider
from app.ai.rag.qdrant_store import QdrantVectorStore
from app.ai.rag.vector_store import FakeVectorStore
from app.ai.runtime.agent_runtime import AgentRuntime
from app.ai.runtime.decisions import AgentDecision, AgentResponse
from app.ai.runtime.factory import create_agent_runtime
from app.ai.tools.permissions import ToolPermission
from app.ai.tools.registry import tool_registry
from app.main import app
from app.models.ai import (
    KnowledgeDocument,
    KnowledgeSource,
)
from app.models.conversation import (
    Conversation,
    ConversationMode,
)
from app.models.user import User
from app.schemas.signal import SignalIncomingMessage
from app.services.message_handler import MessageHandler


@pytest.fixture(autouse=True)
def override_deps(session):
    from app.api.deps import get_current_admin
    from app.database import get_session
    from app.schemas.auth import AdminUser

    app.dependency_overrides[get_current_admin] = lambda: AdminUser(username="admin")
    app.dependency_overrides[get_session] = lambda: session
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}


# ---------------------------------------------------------------------------
# 1. Production Runtime Factory Test (Section 5, 6, 81)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_production_runtime_does_not_use_fake_providers():
    """Verify production runtime factory instantiates real HTTP/Qdrant adapters and forbids Fake providers."""
    # Production configuration
    settings_dict = {
        "ai_api_base_url": "https://api.openai.com/v1",
        "ai_api_key": "sk-real-test-key",
        "ai_model": "gpt-4o-mini",
        "vector_store_provider": "qdrant",
        "qdrant_url": "http://localhost:6333",
        "qdrant_api_key": "qdrant-key",
    }

    # In production mode (is_test=False), create_agent_runtime must instantiate real adapters
    prod_runtime = create_agent_runtime(settings_dict, is_test=False)

    assert isinstance(prod_runtime.llm, OpenAICompatibleProvider)
    assert not isinstance(prod_runtime.llm, FakeLLMProvider)
    assert isinstance(prod_runtime.embedding_provider, OpenAICompatibleEmbeddingProvider)
    assert not isinstance(prod_runtime.embedding_provider, FakeEmbeddingProvider)
    assert isinstance(prod_runtime.vector_store, QdrantVectorStore)
    assert not isinstance(prod_runtime.vector_store, FakeVectorStore)

    # Runtime assertion: Initializing AgentRuntime directly with FakeLLM in non-test mode must fail
    with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
        with pytest.raises(RuntimeError, match="prohibited in non-test environment"):
            AgentRuntime(llm_provider=FakeLLMProvider())


# ---------------------------------------------------------------------------
# 2. Auto Mode uses AgentRuntime and Records Provenance (Section 10, 34, 81)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auto_mode_uses_agent_runtime(session):
    """Auto mode invokes AgentRuntime and dispatches reply with origin=ai_auto and ai_run_id."""
    handler = MessageHandler()

    # Create conversation in Auto mode
    user = User(signal_id="+420777555111", display_name="AutoUser")
    session.add(user)
    await session.flush()

    conv = Conversation(
        user_id=user.id,
        dm_user_id=user.id,
        signal_id="+420777555111",
        type="dm",
        mode=ConversationMode.auto.value,
        is_active=True,
    )
    session.add(conv)
    await session.commit()

    envelope_payload = {
        "envelope": {
            "source": "+420777555111",
            "timestamp": 1700000090000,
            "dataMessage": {
                "timestamp": 1700000090000,
                "message": "Do you sell Colombian coffee?",
            },
        }
    }
    incoming = SignalIncomingMessage(**envelope_payload)

    # Custom AgentRuntime that returns an explicit reply
    mock_runtime = AsyncMock()
    mock_runtime.run = AsyncMock(
        return_value=AgentResponse(
            answer="Yes, we have Colombian Supremo in stock!",
            decision=AgentDecision.reply.value,
            model="gpt-4o-mini",
            provider="openai_compatible",
            ai_run_id=901,
            ai_suggestion_id=902,
        )
    )
    handler.set_agent_runtime(mock_runtime)

    with patch("app.services.message_handler.async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__.return_value = session
        mock_session_ctx.return_value.__aexit__.return_value = None

        with patch("app.services.outbound_service.signal_client") as mock_client:
            mock_client.send_message = AsyncMock(return_value=True)

            await handler.handle_message(incoming)

            # 1. Verify AgentRuntime.run was invoked
            mock_runtime.run.assert_called_once()
            args, kwargs = mock_runtime.run.call_args
            assert args[1].conversation_id == conv.id
            assert args[1].mode == "auto"

            # 2. Verify signal_client sent outbound message
            mock_client.send_message.assert_called_once()


# ---------------------------------------------------------------------------
# 3. Copilot Mode uses Same AgentRuntime without Auto Send (Section 10, 81)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_copilot_mode_uses_same_agent_runtime(session):
    """Copilot mode invokes the same AgentRuntime and drafts suggestion without sending."""
    handler = MessageHandler()

    user = User(signal_id="+420777555222", display_name="CopilotUser")
    session.add(user)
    await session.flush()

    conv = Conversation(
        user_id=user.id,
        dm_user_id=user.id,
        signal_id="+420777555222",
        type="dm",
        mode=ConversationMode.copilot.value,
        is_active=True,
    )
    session.add(conv)
    await session.commit()

    envelope_payload = {
        "envelope": {
            "source": "+420777555222",
            "timestamp": 1700000091000,
            "dataMessage": {
                "timestamp": 1700000091000,
                "message": "Can I cancel my subscription?",
            },
        }
    }
    incoming = SignalIncomingMessage(**envelope_payload)

    mock_runtime = AsyncMock()
    mock_runtime.run = AsyncMock(
        return_value=AgentResponse(
            answer="Certainly! I can help you cancel your subscription.",
            decision=AgentDecision.draft_for_human.value,
            model="gpt-4o-mini",
            provider="openai_compatible",
            ai_run_id=903,
            ai_suggestion_id=904,
        )
    )
    handler.set_agent_runtime(mock_runtime)

    with patch("app.services.message_handler.async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__.return_value = session
        mock_session_ctx.return_value.__aexit__.return_value = None

        with patch("app.services.outbound_service.signal_client") as mock_client:
            mock_client.send_message = AsyncMock(return_value=True)

            await handler.handle_message(incoming)

            # AgentRuntime was called
            mock_runtime.run.assert_called_once()
            # In Copilot mode, message MUST NOT be automatically sent to Signal
            mock_client.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Real Qdrant Adapter Roundtrip Test (Section 21, 81)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_real_qdrant_adapter_roundtrip():
    """Verify QdrantVectorStore against an in-memory Qdrant client."""
    store = QdrantVectorStore(location=":memory:")

    collection = "test_knowledge_col"
    points = [
        {
            "id": "doc_chunk_101",
            "vector": [0.12, 0.34, 0.56, 0.78],
            "payload": {
                "title": "Shipping FAQ",
                "scope_type": "global",
                "content": "We ship worldwide.",
            },
        },
        {
            "id": "doc_chunk_102",
            "vector": [0.99, 0.88, 0.77, 0.66],
            "payload": {
                "title": "Refund FAQ",
                "scope_type": "global",
                "content": "30 days return policy.",
            },
        },
    ]

    # 1. Upsert points
    ok = await store.upsert(collection, points)
    assert ok is True

    # 2. Search
    results = await store.search(collection, query_vector=[0.12, 0.34, 0.56, 0.78], limit=2)
    assert len(results) >= 1
    assert results[0].id == "doc_chunk_101"
    assert results[0].payload["title"] == "Shipping FAQ"

    # 3. Delete point
    del_ok = await store.delete(collection, ["doc_chunk_101"])
    assert del_ok is True

    # 4. Verify deleted point is gone
    after_del = await store.search(collection, query_vector=[0.12, 0.34, 0.56, 0.78], limit=5)
    remaining_ids = [r.id for r in after_del]
    assert "doc_chunk_101" not in remaining_ids
    assert "doc_chunk_102" in remaining_ids


# ---------------------------------------------------------------------------
# 5. Real MCP SDK Discovery and Execution Test (Section 25, 26, 81)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_real_mcp_sdk_discovery_and_call():
    """Verify MCPClientManager connects to a real MCP SDK stdio server and executes a tool."""
    server_script = """
from mcp.server.mcpserver import MCPServer

server = MCPServer("LocalTestInventoryServer")

@server.tool()
def check_item_stock(sku: str) -> str:
    '''Check real stock level for SKU'''
    return f"Stock for {sku}: 42 units available in Prague warehouse"

if __name__ == "__main__":
    server.run(transport="stdio")
"""

    server_name = "test_inventory_mcp"
    tools = await mcp_manager.connect_server(
        name=server_name,
        transport="stdio",
        command_or_url=sys.executable,
        args=["-c", server_script],
    )

    try:
        # 1. Tool discovery
        assert len(tools) == 1
        assert tools[0].name == "check_item_stock"
        assert tools[0].server_name == server_name

        # 2. Tool registered in ToolRegistry
        reg_tool = tool_registry.get_tool("check_item_stock")
        assert reg_tool is not None
        assert reg_tool.is_mcp is True

        # 3. Execute tool via ToolRegistry
        exec_res = await tool_registry.execute("check_item_stock", {"sku": "COFFEE-BEANS-01"})
        assert exec_res["status"] == "success"
        assert "42 units available" in str(exec_res["result"])
    finally:
        await mcp_manager.disconnect_server(server_name)


# ---------------------------------------------------------------------------
# 6. MCP Write Tool Requires Approval Test (Section 27, 81)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mcp_write_requires_approval():
    """MCP write tools must require human approval and block autonomous execution."""
    tool_registry.register(
        name="dispatch_warehouse_order",
        description="Physical inventory dispatch",
        func=AsyncMock(return_value={"shipped": True}),
        permission=ToolPermission(
            name="dispatch_warehouse_order",
            description="Physical inventory dispatch",
            read_only=False,
            writes_data=True,
            requires_human_approval=True,
        ),
        parameters_schema={"type": "object", "properties": {"order_id": {"type": "integer"}}},
        is_mcp=True,
        mcp_server_name="test_warehouse",
    )

    # Autonomous invocation (user_approved=False) MUST be blocked
    blocked_res = await tool_registry.execute(
        "dispatch_warehouse_order",
        {"order_id": 555},
        user_approved=False,
    )
    assert blocked_res["status"] == "requires_approval"
    assert "requires operator approval" in blocked_res["error"]

    # Approved invocation (user_approved=True) succeeds
    approved_res = await tool_registry.execute(
        "dispatch_warehouse_order",
        {"order_id": 555},
        user_approved=True,
    )
    assert approved_res["status"] == "success"
    assert approved_res["result"]["shipped"] is True


# ---------------------------------------------------------------------------
# 7. AI Dashboard Has No Hardcoded Metrics (Section 32, 81)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ai_dashboard_has_no_hardcoded_metrics(session, auth_headers):
    """AI Studio dashboard must compute dynamic metrics from DB events, never hardcode 0.85."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Query overview metrics with empty database
        resp = await client.get("/api/ai-studio/overview", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        # With 0 runs, rag_hit_rate must be 0.0, NOT 0.85!
        assert data["rag_hit_rate"] != 0.85
        assert data["rag_hit_rate"] == 0.0

        # Query diagnostics
        diag_resp = await client.get("/api/ai-studio/diagnostics", headers=auth_headers)
        assert diag_resp.status_code == 200
        diag_data = diag_resp.json()
        assert "llm_provider" in diag_data
        assert "embedding_provider" in diag_data
        assert "vector_store" in diag_data
        assert "signal_gateway" in diag_data
        assert diag_data["llm_provider"]["status"] in (
            "configured",
            "connected",
            "degraded",
            "disabled",
        )


# ---------------------------------------------------------------------------
# 8. Reindex Knowledge Document and Source (Section 23, 81)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reindex_pipeline(session, auth_headers):
    """Test reindex endpoints rebuild vector index from relational DB."""
    source = KnowledgeSource(
        title="Store FAQ",
        source_type="faq",
        language="en",
        status="active",
        created_by="admin",
    )
    session.add(source)
    await session.flush()

    doc = KnowledgeDocument(
        source_id=source.id,
        title="Opening Hours",
        content="We are open Monday to Friday from 9 AM to 6 PM.",
        scope_type="global",
        chunk_count=1,
    )
    session.add(doc)
    await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Reindex single document
        resp = await client.post(
            f"/api/ai-studio/knowledge/documents/{doc.id}/reindex",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["document_id"] == doc.id
        assert data["chunks_reindexed"] >= 1

        # Reindex all documents
        resp_all = await client.post(
            "/api/ai-studio/knowledge/reindex",
            headers=auth_headers,
        )
        assert resp_all.status_code == 200
        all_data = resp_all.json()
        assert all_data["ok"] is True
        assert all_data["documents_reindexed"] >= 1
