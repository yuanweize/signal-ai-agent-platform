"""
Execution context for DB-backed tools.
Provides concurrency-safe thread/async-local injection of the current request's AsyncSession.
"""

from __future__ import annotations

import contextvars

from sqlalchemy.ext.asyncio import AsyncSession

current_tool_session: contextvars.ContextVar[AsyncSession | None] = contextvars.ContextVar(
    "current_tool_session", default=None
)
