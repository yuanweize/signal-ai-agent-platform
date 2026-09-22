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

        # In testing or mock scenarios, provide known mock tools
        if name == "mock_warehouse_mcp":
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
            # Placeholder for standard MCP discovery (SDK client integration)
            tools = []

        # Register discovered tools with ToolRegistry
        for t in tools:
            # Create invocation closure
            def make_handler(tool_name: str, is_approval_req: bool):
                async def handler(**kwargs):
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
                func=make_handler(t.name, t.requires_approval),
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
        }
        return tools

    def disconnect_server(self, name: str) -> bool:
        if name in self._active_servers:
            del self._active_servers[name]
            logger.info(f"Disconnected MCP server: {name}")
            return True
        return False

    def list_servers(self) -> list[dict[str, Any]]:
        return list(self._active_servers.values())


mcp_manager = MCPClientManager()
