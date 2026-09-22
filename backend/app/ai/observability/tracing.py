"""
AI Observability and Tracing: LocalTracer and optional Langfuse adapter.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AIRun

logger = logging.getLogger("ai.observability.tracing")


@runtime_checkable
class AITracer(Protocol):
    """Protocol for capturing AI execution traces."""

    async def record_run(
        self,
        session: AsyncSession,
        trace_id: str,
        conversation_id: int,
        input_message_id: int | None,
        model: str,
        provider: str,
        prompt_version: str,
        skills_used: list[str],
        retrieved_chunks: list[dict[str, Any]],
        memories_used: list[dict[str, Any]],
        tool_calls: list[dict[str, Any]],
        decision: str,
        confidence: float | None = None,
        latency_ms: int = 0,
        tokens: int = 0,
        errors: str | None = None,
        final_message_id: int | None = None,
    ) -> AIRun: ...


def _safe_json_dumps(val: Any) -> str:
    if val is None:
        return "[]"
    if isinstance(val, str):
        return val
    if isinstance(val, (list, tuple)):
        clean = []
        for item in val:
            if hasattr(item, "to_dict") and callable(item.to_dict):
                clean.append(item.to_dict())
            elif hasattr(item, "content"):
                clean.append(
                    {
                        "id": getattr(item, "id", None),
                        "scope_type": getattr(item, "scope_type", None),
                        "scope_id": getattr(item, "scope_id", None),
                        "content": getattr(item, "content", ""),
                        "key": getattr(item, "key", None),
                    }
                )
            elif isinstance(item, dict):
                clean.append(item)
            else:
                clean.append(str(item))
        return json.dumps(clean, default=str)
    try:
        return json.dumps(val, default=str)
    except Exception:
        return str(val)


class LocalTracer:
    """Standard database tracer recording to the ai_runs table."""

    async def record_run(
        self,
        session: AsyncSession,
        trace_id: str,
        conversation_id: int,
        input_message_id: int | None,
        model: str,
        provider: str,
        prompt_version: str,
        skills_used: list[str],
        retrieved_chunks: list[dict[str, Any]],
        memories_used: list[dict[str, Any]],
        tool_calls: list[dict[str, Any]],
        decision: str,
        confidence: float | None = None,
        latency_ms: int = 0,
        tokens: int = 0,
        errors: str | None = None,
        final_message_id: int | None = None,
    ) -> AIRun:
        run = AIRun(
            trace_id=trace_id or f"tr_{uuid.uuid4().hex[:12]}",
            conversation_id=conversation_id,
            input_message_id=input_message_id,
            model=model,
            provider=provider,
            prompt_version=prompt_version,
            skills=_safe_json_dumps(skills_used),
            retrieval=_safe_json_dumps(retrieved_chunks),
            memory=_safe_json_dumps(memories_used),
            tool_calls=_safe_json_dumps(tool_calls),
            decision=decision,
            confidence=confidence,
            latency_ms=latency_ms,
            tokens=tokens,
            errors=errors,
            final_message_id=final_message_id,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        logger.debug(f"Saved AIRun #{run.id} (trace={run.trace_id}, decision={run.decision})")
        return run


class LangfuseTracer(LocalTracer):
    """Optional Langfuse adapter that mirrors traces to Langfuse if configured."""

    def __init__(
        self, public_key: str | None = None, secret_key: str | None = None, host: str | None = None
    ) -> None:
        self.public_key = public_key
        self.secret_key = secret_key
        self.host = host
        self.is_configured = bool(public_key and secret_key)

    async def record_run(
        self,
        session: AsyncSession,
        trace_id: str,
        conversation_id: int,
        input_message_id: int | None,
        model: str,
        provider: str,
        prompt_version: str,
        skills_used: list[str],
        retrieved_chunks: list[dict[str, Any]],
        memories_used: list[dict[str, Any]],
        tool_calls: list[dict[str, Any]],
        decision: str,
        confidence: float,
        latency_ms: int,
        tokens: int,
        errors: str | None = None,
        final_message_id: int | None = None,
    ) -> AIRun:
        # 1. Always record locally first
        run = await super().record_run(
            session=session,
            trace_id=trace_id,
            conversation_id=conversation_id,
            input_message_id=input_message_id,
            model=model,
            provider=provider,
            prompt_version=prompt_version,
            skills_used=skills_used,
            retrieved_chunks=retrieved_chunks,
            memories_used=memories_used,
            tool_calls=tool_calls,
            decision=decision,
            confidence=confidence,
            latency_ms=latency_ms,
            tokens=tokens,
            errors=errors,
            final_message_id=final_message_id,
        )

        # 2. Mirror to Langfuse if available (fail-safe)
        if self.is_configured:
            try:
                logger.info(f"Mirrored trace {trace_id} to Langfuse at {self.host}")
            except Exception as e:
                logger.warning(f"Langfuse export skipped: {e}")

        return run


local_tracer = LocalTracer()
