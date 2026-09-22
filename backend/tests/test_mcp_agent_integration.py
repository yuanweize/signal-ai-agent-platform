"""
Real MCP Agent Integration Tests (Section 10).
Tests MCP stdio tool execution THROUGH AgentRuntime:
Case A: Read-only inventory MCP tool -> Real MCP call -> result in answer -> ToolInvocation persisted
Case B: Write/destructive MCP tool -> Policy blocks execution -> draft_for_human -> external side effect not executed
"""

import os
import sys
import tempfile

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.mcp.client import mcp_manager
from app.ai.providers.llm import LLMProvider
from app.ai.runtime.agent_runtime import AgentRuntime
from app.ai.runtime.context import AgentContext
from app.ai.runtime.decisions import AgentDecision
from app.ai.tools.registry import tool_registry
from app.database import Base
from app.models.ai import ToolInvocation

SERVER_CODE = """
import asyncio
from mcp.server.mcpserver import MCPServer

m = MCPServer("integration-warehouse")

@m.tool()
async def check_inventory(sku: str) -> str:
    '''Check warehouse inventory level for a SKU.'''
    return f"SKU {sku} has 42 units in stock."

@m.tool()
async def dispatch_order(order_id: int) -> str:
    '''Dispatch order to customer.'''
    return f"Order {order_id} dispatched."

if __name__ == "__main__":
    asyncio.run(m.run_stdio_async())
"""


class PassthroughTestLLM(LLMProvider):
    """Test LLM that incorporates tool results into final answer."""

    def __init__(self):
        super().__init__(api_key="__TEST__", default_model="test-model")

    async def generate(self, messages: list[dict[str, str]], **kwargs) -> tuple[str, int]:
        # Search messages for tool output
        for m in messages:
            content = m.get("content", "")
            if "Business Tool Results:" in content and "42 units in stock" in content:
                return "The warehouse reports that SKU-COFFEE-01 has 42 units in stock.", 30
        return "I can assist you with that request.", 15


@pytest.fixture
def mcp_server_script():
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(SERVER_CODE)
        path = f.name
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_mcp_agent_readonly_execution_e2e(tmp_path, mcp_server_script):
    """Case A: Read-only inventory MCP tool executes through AgentRuntime and is persisted."""
    db_file = tmp_path / "mcp_test_a.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 1. Connect real stdio MCP subprocess
    server_name = "real_stdio_warehouse_a"
    try:
        discovered = await mcp_manager.connect_server(
            name=server_name,
            transport="stdio",
            command_or_url=sys.executable,
            args=[mcp_server_script],
        )
        assert len(discovered) == 2
        assert any(t.name == "check_inventory" for t in discovered)

        # 2. Build AgentRuntime
        llm = PassthroughTestLLM()
        runtime = AgentRuntime(
            llm_provider=llm,
            retriever=None,
        )

        ctx = AgentContext(
            conversation_id=1,
            text="Can you check inventory for SKU-COFFEE-01?",
            mode="auto",
        )

        async with session_factory() as session:
            result = await runtime.run(session, ctx)

        # 3. Assert real MCP call executed and incorporated into answer
        assert "42 units in stock" in result.answer
        assert result.decision == AgentDecision.reply.value

        # 4. Verify ToolInvocation row persisted in DB
        async with session_factory() as session:
            invocations = (await session.execute(select(ToolInvocation))).scalars().all()
            assert len(invocations) >= 1
            mcp_inv = next((inv for inv in invocations if inv.tool_name == "check_inventory"), None)
            assert mcp_inv is not None
            assert mcp_inv.tool_type == "mcp"
            assert mcp_inv.status == "success"
            assert "42 units in stock" in str(mcp_inv.result_json)

    finally:
        await mcp_manager.disconnect_server(server_name)
        tool_registry.unregister("check_inventory")
        tool_registry.unregister("dispatch_order")
        await engine.dispose()


@pytest.mark.asyncio
async def test_mcp_agent_write_tool_governed_blocking(tmp_path, mcp_server_script):
    """Case B: Destructive write MCP tool is blocked by policy, draft_for_human emitted."""
    db_file = tmp_path / "mcp_test_b.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    server_name = "real_stdio_warehouse_b"
    try:
        discovered = await mcp_manager.connect_server(
            name=server_name,
            transport="stdio",
            command_or_url=sys.executable,
            args=[mcp_server_script],
        )
        assert any(t.name == "dispatch_order" for t in discovered)
        disp_tool = next(t for t in discovered if t.name == "dispatch_order")
        assert disp_tool.requires_approval is True

        llm = PassthroughTestLLM()
        runtime = AgentRuntime(
            llm_provider=llm,
            retriever=None,
        )

        ctx = AgentContext(
            conversation_id=2,
            text="Please dispatch order 101 now.",
            mode="auto",
        )

        async with session_factory() as session:
            result = await runtime.run(session, ctx)

        # Destructive tool blocked: draft_for_human emitted, approval required
        assert result.decision == AgentDecision.draft_for_human.value

        # Verify AIRun recorded decision and ToolInvocation recorded approval requirement
        async with session_factory() as session:
            from app.models.ai import AIRun

            ai_run = (
                await session.execute(select(AIRun).where(AIRun.id == result.ai_run_id))
            ).scalar_one_or_none()
            assert ai_run is not None
            assert ai_run.decision == AgentDecision.draft_for_human.value

            invocations = (await session.execute(select(ToolInvocation))).scalars().all()
            disp_inv = next((inv for inv in invocations if inv.tool_name == "dispatch_order"), None)
            assert disp_inv is not None
            assert disp_inv.status == "requires_approval"
            assert disp_inv.requires_approval is True

    finally:
        await mcp_manager.disconnect_server(server_name)
        tool_registry.unregister("check_inventory")
        tool_registry.unregister("dispatch_order")
        await engine.dispose()
