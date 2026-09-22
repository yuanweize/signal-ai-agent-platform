"""
MCP Client Manager: discovers, governs, and connects to Model Context Protocol servers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.mcp.security import (
    is_ssrf_safe_url,
)
from app.ai.tools.permissions import ToolPermission
from app.ai.tools.registry import tool_registry
from app.services.runtime_config import decrypt_value

logger = logging.getLogger("ai.mcp.client")

DEFAULT_MCP_CONNECT_TIMEOUT = 10.0
DEFAULT_MCP_EXEC_TIMEOUT = 15.0


def parse_and_decrypt_env(env_raw: str | None) -> dict[str, str]:
    """Parse environment variables, decrypting if encrypted with Fernet."""
    if not env_raw:
        return {}
    try:
        decrypted = decrypt_value(env_raw)
        data = json.loads(decrypted)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    try:
        data = json.loads(env_raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


@dataclass
class DiscoveredMCPTool:
    name: str
    description: str
    parameters_schema: dict[str, Any]
    server_name: str
    read_only: bool = False
    requires_approval: bool = True


class MCPClientManager:
    """Manages connections to governed MCP servers and registers their tools."""

    def __init__(self) -> None:
        self._active_servers: dict[str, dict[str, Any]] = {}

    async def connect_server(
        self,
        name: str,
        transport: str,
        command_or_url: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        allow_localhost: bool = True,
    ) -> list[DiscoveredMCPTool]:
        """Connect to an MCP server, discover its tools, and register them."""
        # 1. SSRF check for HTTP transports
        if transport in ("http", "sse"):
            safe, err = is_ssrf_safe_url(command_or_url, allow_localhost=allow_localhost)
            if not safe:
                raise ValueError(f"MCP server rejected by security policy: {err}")
            raise NotImplementedError(
                "MCP Streamable HTTP / SSE transport is planned/experimental in v0.4. "
                "Use 'stdio' transport for production MCP integration."
            )

        logger.info(f"Connecting to MCP server '{name}' via {transport}...")

        ctx = None
        session = None
        tools: list[DiscoveredMCPTool] = []

        # 2. Real MCP SDK connection for stdio transport
        if transport == "stdio" and name != "mock_warehouse_mcp":
            from mcp import ClientSession
            from mcp.client.stdio import StdioServerParameters, stdio_client

            params = StdioServerParameters(
                command=command_or_url,
                args=args or [],
                env=env or None,
            )

            async def _init_stdio():
                nonlocal ctx, session, tools
                ctx = stdio_client(params)
                read_stream, write_stream = await ctx.__aenter__()
                session = ClientSession(read_stream, write_stream)
                await session.__aenter__()
                await session.initialize()

                sdk_tools = await session.list_tools()
                for t in sdk_tools.tools:
                    schema = t.inputSchema if hasattr(t, "inputSchema") and t.inputSchema else {}
                    t_name_lower = t.name.lower()

                    # Safe governance: Default to approval required.
                    # Only explicitly classified safe queries qualify for autonomous read_only.
                    safe_query_prefixes = (
                        "get_",
                        "list_",
                        "read_",
                        "check_",
                        "search_",
                        "query_",
                        "fetch_",
                    )
                    dangerous_keywords = (
                        "write",
                        "delete",
                        "remove",
                        "refund",
                        "cancel",
                        "create",
                        "ship",
                        "dispatch",
                        "modify",
                        "update",
                        "exec",
                        "run",
                    )

                    is_safe_query = any(
                        t_name_lower.startswith(p) for p in safe_query_prefixes
                    ) and not any(k in t_name_lower for k in dangerous_keywords)
                    read_only = is_safe_query
                    requires_approval = not is_safe_query

                    tools.append(
                        DiscoveredMCPTool(
                            name=t.name,
                            description=t.description or f"MCP tool {t.name}",
                            parameters_schema=schema,
                            server_name=name,
                            read_only=read_only,
                            requires_approval=requires_approval,
                        )
                    )

            try:
                await asyncio.wait_for(_init_stdio(), timeout=DEFAULT_MCP_CONNECT_TIMEOUT)
            except TimeoutError:
                if session:
                    try:
                        await session.__aexit__(None, None, None)
                    except Exception:
                        pass
                if ctx:
                    try:
                        await ctx.__aexit__(None, None, None)
                    except Exception:
                        pass
                raise TimeoutError(
                    f"Connection to MCP server '{name}' timed out after {DEFAULT_MCP_CONNECT_TIMEOUT}s"
                )

        # In testing or mock scenarios, provide known mock tools
        elif name == "mock_warehouse_mcp":
            tools = [
                DiscoveredMCPTool(
                    name="warehouse_check_inventory",
                    description="Check warehouse inventory level for a SKU",
                    parameters_schema={
                        "type": "object",
                        "properties": {"sku": {"type": "string"}},
                        "required": ["sku"],
                    },
                    server_name=name,
                    read_only=True,
                    requires_approval=False,
                ),
                DiscoveredMCPTool(
                    name="warehouse_dispatch_order",
                    description="Trigger physical shipment dispatch (WRITE/SENSITIVE)",
                    parameters_schema={
                        "type": "object",
                        "properties": {"order_id": {"type": "integer"}},
                        "required": ["order_id"],
                    },
                    server_name=name,
                    read_only=False,
                    requires_approval=True,
                ),
            ]
        else:
            tools = []

        # Register discovered tools with ToolRegistry
        for t in tools:

            def make_handler(tool_name: str, active_session: Any | None):
                async def handler(**kwargs):
                    kwargs.pop("session", None)
                    if active_session:
                        res = await asyncio.wait_for(
                            active_session.call_tool(tool_name, arguments=kwargs),
                            timeout=DEFAULT_MCP_EXEC_TIMEOUT,
                        )
                        text_blocks = [c.text for c in (res.content or []) if hasattr(c, "text")]
                        result_str = text_blocks[0] if len(text_blocks) == 1 else text_blocks
                        return {
                            "mcp_server": name,
                            "tool": tool_name,
                            "result": result_str,
                            "status": "success",
                        }
                    return {
                        "mcp_server": name,
                        "tool": tool_name,
                        "executed_with": kwargs,
                        "status": "success",
                    }

                return handler

            tool_registry.register(
                name=t.name,
                description=t.description,
                func=make_handler(t.name, session),
                permission=ToolPermission(
                    name=t.name,
                    description=t.description,
                    read_only=t.read_only,
                    writes_data=not t.read_only,
                    requires_human_approval=t.requires_approval,
                ),
                parameters_schema=t.parameters_schema,
                is_mcp=True,
                mcp_server_name=name,
            )

        self._active_servers[name] = {
            "name": name,
            "transport": transport,
            "command_or_url": command_or_url,
            "tools_count": len(tools),
            "session": session,
            "ctx": ctx,
        }
        return tools

    async def disconnect_server(self, name: str) -> bool:
        if name in self._active_servers:
            server_info = self._active_servers.pop(name)
            session = server_info.get("session")
            ctx = server_info.get("ctx")
            try:
                if session:
                    await session.__aexit__(None, None, None)
                if ctx:
                    await ctx.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error cleanly closing MCP server {name}: {e}")
            logger.info(f"Disconnected MCP server: {name}")
            return True
        return False

    async def connect_enabled_servers(self, session: AsyncSession) -> dict[str, int]:
        """Connect all enabled MCP servers during app startup. One failure must not crash startup."""
        from app.models.ai import MCPServerConfig

        stmt = select(MCPServerConfig).where(MCPServerConfig.is_enabled.is_(True))
        res = await session.execute(stmt)
        servers = list(res.scalars().all())
        results: dict[str, int] = {}

        for server in servers:
            try:
                args = json.loads(server.args_json) if server.args_json else []
                env = parse_and_decrypt_env(server.env_json)
                tools = await self.connect_server(
                    name=server.name,
                    transport=server.transport,
                    command_or_url=server.command_or_url,
                    args=args,
                    env=env,
                )
                server.status = "connected"
                server.last_connected_at = datetime.now(UTC).replace(tzinfo=None)
                server.error_message = None
                results[server.name] = len(tools)
                logger.info(
                    f"Auto-connected enabled MCP server '{server.name}' ({len(tools)} tools)"
                )
            except Exception as e:
                server.status = "error"
                server.error_message = str(e)
                results[server.name] = 0
                logger.warning(f"Failed to auto-connect enabled MCP server '{server.name}': {e}")

        await session.commit()
        return results

    async def disconnect_all(self) -> None:
        """Disconnect all active MCP servers cleanly during application shutdown."""
        active_names = list(self._active_servers.keys())
        for name in active_names:
            await self.disconnect_server(name)

    def list_servers(self) -> list[dict[str, Any]]:
        return [
            {
                "name": s["name"],
                "transport": s["transport"],
                "command_or_url": s["command_or_url"],
                "tools_count": s["tools_count"],
            }
            for s in self._active_servers.values()
        ]


mcp_manager = MCPClientManager()
