"""
Tool Registry: registers, formats, and governs internal and MCP tools.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.ai.tools.permissions import ToolPermission

logger = logging.getLogger("ai.tools")


@dataclass
class RegisteredTool:
    """A tool registered with the Agent Runtime."""

    name: str
    description: str
    func: Callable[..., Any]
    permission: ToolPermission
    parameters_schema: dict[str, Any] = field(default_factory=dict)
    is_mcp: bool = False
    mcp_server_name: str | None = None

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert to standard OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


class ToolRegistry:
    """Central registry of executable tools with permission enforcement."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        name: str,
        description: str,
        func: Callable[..., Any],
        permission: ToolPermission | None = None,
        parameters_schema: dict[str, Any] | None = None,
        is_mcp: bool = False,
        mcp_server_name: str | None = None,
    ) -> None:
        perm = permission or ToolPermission(name=name, description=description, read_only=True)
        schema = parameters_schema or {
            "type": "object",
            "properties": {},
            "required": [],
        }
        self._tools[name] = RegisteredTool(
            name=name,
            description=description,
            func=func,
            permission=perm,
            parameters_schema=schema,
            is_mcp=is_mcp,
            mcp_server_name=mcp_server_name,
        )
        logger.debug(
            f"Registered tool: {name} (read_only={perm.read_only}, approval={perm.requires_human_approval})"
        )

    def get_tool(self, name: str) -> RegisteredTool | None:
        return self._tools.get(name)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def unregister_server_tools(self, mcp_server_name: str) -> int:
        """Remove all registered tools belonging to a disconnected MCP server."""
        to_remove = [
            name
            for name, tool in self._tools.items()
            if tool.is_mcp and tool.mcp_server_name == mcp_server_name
        ]
        for name in to_remove:
            self._tools.pop(name, None)
        return len(to_remove)

    def list_tools(self) -> list[RegisteredTool]:
        return list(self._tools.values())

    def get_openai_tools(self) -> list[dict[str, Any]]:
        return [t.to_openai_tool() for t in self._tools.values()]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        user_approved: bool = False,
        **extra_kwargs: Any,
    ) -> dict[str, Any]:
        """Execute tool with permission checks."""
        tool = self._tools.get(name)
        if not tool:
            return {
                "status": "error",
                "error": f"Tool '{name}' not found.",
            }

        # Policy Enforcement: Check human approval requirement
        if tool.permission.requires_human_approval and not user_approved:
            logger.warning(
                f"Execution of sensitive tool '{name}' blocked: requires human approval."
            )
            return {
                "status": "requires_approval",
                "error": f"Tool '{name}' performs write/sensitive actions and requires operator approval.",
                "tool_name": name,
                "arguments": arguments,
            }

        try:
            from app.ai.tools.context import current_tool_session

            func = tool.func
            sig = inspect.signature(func)
            has_var_keyword = any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            )
            ctx_session = current_tool_session.get()
            if has_var_keyword:
                kwargs = {**arguments, **extra_kwargs}
                if not tool.is_mcp and "session" not in kwargs and ctx_session is not None:
                    kwargs["session"] = ctx_session
            else:
                kwargs = {}
                for param in sig.parameters.values():
                    if param.name in arguments:
                        kwargs[param.name] = arguments[param.name]
                    elif param.name in extra_kwargs:
                        kwargs[param.name] = extra_kwargs[param.name]
                    elif param.name == "session" and ctx_session is not None and not tool.is_mcp:
                        kwargs["session"] = ctx_session

            if inspect.iscoroutinefunction(func):
                result = await func(**kwargs)
            else:
                result = func(**kwargs)

            return {
                "status": "success",
                "result": result,
            }
        except Exception as e:
            logger.error(f"Error executing tool '{name}': {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }


tool_registry = ToolRegistry()
