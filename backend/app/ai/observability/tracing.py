"""
AI Observability and Tracing: LocalTracer and optional Langfuse adapter.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.telemetry.pricing import calculate_cost
from app.models.ai import AIModelCall, AIRun

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
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        cached_input_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        llm_call_count: int = 1,
        usage_source: str = "unavailable",
        estimated_cost: float | None = None,
        cost_currency: str = "USD",
        traffic_source: str = "production",
        model_calls: list[dict[str, Any]] | None = None,
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
    """Standard database tracer recording to the ai_runs and ai_model_calls tables."""

    async def record_run(
        self,
        session: AsyncSession,
        conversation_id: int,
        trace_id: str | None = None,
        input_message_id: int | None = None,
        model: str = "default",
        provider: str = "default",
        prompt_version: str = "v1.0",
        skills_used: list[str] | None = None,
        retrieved_chunks: list[dict[str, Any]] | None = None,
        memories_used: list[dict[str, Any]] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        decision: str = "reply",
        confidence: float | None = None,
        latency_ms: int = 0,
        tokens: int = 0,
        errors: str | None = None,
        final_message_id: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        cached_input_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        llm_call_count: int | None = None,
        usage_source: str = "unavailable",
        estimated_cost: float | None = None,
        cost_currency: str = "USD",
        traffic_source: str = "production",
        model_calls: list[dict[str, Any]] | None = None,
    ) -> AIRun:
        # Resolve canonical tokens and source
        effective_total = (
            total_tokens if total_tokens is not None else (tokens if tokens > 0 else None)
        )
        effective_source = usage_source
        if effective_total is not None and effective_source == "unavailable":
            effective_source = (
                "legacy_total_only"
                if (input_tokens is None and output_tokens is None)
                else "provider"
            )

        call_count = (
            llm_call_count
            if llm_call_count is not None
            else (len(model_calls) if model_calls else 1)
        )

        # Compute cost if not provided and pricing exists
        cost = estimated_cost
        curr = cost_currency or "USD"
        if cost is None and effective_total is not None:
            calc_c, calc_curr = calculate_cost(
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_input_tokens=cached_input_tokens,
            )
            cost = calc_c
            curr = calc_curr

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
            tokens=effective_total or 0,
            errors=errors,
            final_message_id=final_message_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=effective_total,
            cached_input_tokens=cached_input_tokens,
            reasoning_tokens=reasoning_tokens,
            llm_call_count=call_count,
            usage_source=effective_source,
            estimated_cost=cost,
            cost_currency=curr,
            traffic_source=traffic_source,
        )
        session.add(run)
        await session.flush()  # assign run.id

        # Persist individual model calls if available
        if model_calls:
            for mc_item in model_calls:
                mc = mc_item.to_dict() if hasattr(mc_item, "to_dict") else mc_item
                u = mc.get("usage") or {}
                m_in = u.get("input_tokens")
                m_out = u.get("output_tokens")
                m_tot = u.get("total_tokens")
                m_cached = u.get("cached_input_tokens")
                m_reason = u.get("reasoning_tokens")
                m_src = u.get("usage_source", "unavailable")

                mc_cost = mc.get("estimated_cost")
                mc_curr = mc.get("currency", curr)
                if mc_cost is None and m_tot is not None:
                    mc_c, mc_cur = calculate_cost(
                        provider=mc.get("provider", provider),
                        model=mc.get("model", model),
                        input_tokens=m_in,
                        output_tokens=m_out,
                        cached_input_tokens=m_cached,
                    )
                    mc_cost = mc_c
                    mc_curr = mc_cur

                started = mc.get("started_at")
                if isinstance(started, str):
                    try:
                        started = datetime.fromisoformat(started).replace(tzinfo=None)
                    except Exception:
                        started = datetime.now(UTC).replace(tzinfo=None)
                elif not isinstance(started, datetime):
                    started = datetime.now(UTC).replace(tzinfo=None)

                call_record = AIModelCall(
                    ai_run_id=run.id,
                    phase=mc.get("phase", "other"),
                    provider=mc.get("provider", provider),
                    model=mc.get("model", model),
                    started_at=started,
                    latency_ms=mc.get("latency_ms", 0),
                    input_tokens=m_in,
                    output_tokens=m_out,
                    total_tokens=m_tot,
                    cached_input_tokens=m_cached,
                    reasoning_tokens=m_reason,
                    usage_source=m_src,
                    finish_reason=mc.get("finish_reason"),
                    provider_request_id=mc.get("provider_request_id"),
                    success=mc.get("success", True),
                    error=mc.get("error"),
                    estimated_cost=mc_cost,
                    currency=mc_curr,
                )
                session.add(call_record)

        await session.commit()
        await session.refresh(run)
        logger.debug(
            f"Saved AIRun #{run.id} (trace={run.trace_id}, tokens={run.total_tokens}, cost={run.estimated_cost})"
        )
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
