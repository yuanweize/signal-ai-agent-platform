"""
Tests for MCP cancellation propagation.
Verifies Section 16:
- asyncio.CancelledError must propagate during MCP server startup
- Cancellation-containing BaseExceptionGroup must propagate
- Operational exceptions (e.g., connection refused, timeout) are caught and degraded safely
"""

import asyncio
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.ai.mcp.client import MCPClientManager
from app.models.ai import MCPServerConfig


@pytest.mark.asyncio
async def test_mcp_connect_enabled_servers_propagates_cancellation(session):
    """connect_enabled_servers must re-raise asyncio.CancelledError, not swallow it."""
    srv = MCPServerConfig(
        name="test_cancel_server",
        transport="stdio",
        command_or_url="echo",
        is_enabled=True,
    )
    session.add(srv)
    await session.commit()

    manager = MCPClientManager()

    try:
        with patch.object(manager, "connect_server", side_effect=asyncio.CancelledError()):
            with pytest.raises(asyncio.CancelledError):
                await manager.connect_enabled_servers(session)
    finally:
        await session.delete(srv)
        await session.commit()


@pytest.mark.asyncio
async def test_mcp_connect_enabled_servers_propagates_exception_group_cancellation(session):
    """connect_enabled_servers must re-raise BaseExceptionGroup containing CancelledError."""
    srv = MCPServerConfig(
        name="test_cancel_group_server",
        transport="stdio",
        command_or_url="echo",
        is_enabled=True,
    )
    session.add(srv)
    await session.commit()

    manager = MCPClientManager()

    eg = BaseExceptionGroup("mcp_cancel", [asyncio.CancelledError()])

    try:
        with patch.object(manager, "connect_server", side_effect=eg):
            with pytest.raises(BaseExceptionGroup):
                await manager.connect_enabled_servers(session)
    finally:
        await session.delete(srv)
        await session.commit()


@pytest.mark.asyncio
async def test_mcp_connect_enabled_servers_degrades_operational_failure(session):
    """Operational failures (e.g. ConnectionRefusedError) are caught and degraded without crashing."""
    srv = MCPServerConfig(
        name="test_operational_err_server",
        transport="stdio",
        command_or_url="echo",
        is_enabled=True,
    )
    session.add(srv)
    await session.commit()

    manager = MCPClientManager()

    try:
        with patch.object(
            manager, "connect_server", side_effect=ConnectionRefusedError("Port closed")
        ):
            results = await manager.connect_enabled_servers(session)
            assert results.get("test_operational_err_server") == 0

        # Verify server status in DB is marked as error
        updated = (
            await session.execute(
                select(MCPServerConfig).where(
                    MCPServerConfig.name == "test_operational_err_server"
                )
            )
        ).scalar_one()
        assert updated.status == "error"
        assert "Port closed" in updated.error_message
    finally:
        await session.delete(srv)
        await session.commit()
