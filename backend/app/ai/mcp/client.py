"""
MCP Client Manager: discovers and connects to Model Context Protocol servers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.ai.mcp.security import (
    is_ssrf_safe_url,
)
from app.ai.tools.permissions import ToolPermission
from app.ai.tools.registry import tool_registry

logger = logging.getLogger("ai.mcp.client")


@dataclass
class DiscoveredMCPTool:
    name: str
    description: str
    parameters_schema: dict[str, Any]
    server_name: str
    read_only: bool = True
    requires_approval: bool = False


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
            ctx = stdio_client(params)
            read_stream, write_stream = await ctx.__aenter__()
            session = ClientSession(read_stream, write_stream)
            await session.__aenter__()
            await session.initialize()

            sdk_tools = await session.list_tools()
            for t in sdk_tools.tools:
                schema = t.inputSchema if hasattr(t, "inputSchema") and t.inputSchema else {}
                # Governance: default deny write. Detect sensitive keywords requiring human approval
                is_write = any(
                    w in t.name.lower()
                    for w in [
                        "dispatch",
                        "write",
                        "delete",
                        "refund",
                        "cancel",
                        "create",
                        "ship",
                        "modify",
                        "update",
                    ]
                )
                tools.append(
                    DiscoveredMCPTool(
                        name=t.name,
                        description=t.description or f"MCP tool {t.name}",
                        parameters_schema=schema,
                        server_name=name,
                        read_only=not is_write,
                        requires_approval=is_write,
                    )
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
                    requires_approval=True,  # requires human approval
                ),
            ]
        else:
            tools = []

        # Register discovered tools with ToolRegistry
        for t in tools:
            # Create invocation closure bound to real session if available
            def make_handler(tool_name: str, active_session: Any | None):
                async def handler(**kwargs):
                    if active_session:
                        res = await active_session.call_tool(tool_name, arguments=kwargs)
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
