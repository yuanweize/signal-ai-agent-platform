"""
Structured LLM Token Usage, Model Call Records, and Provider-Neutral Results.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

UsageSource = Literal[
    "provider",
    "estimated",
    "unavailable",
    "legacy_total_only",
    "partial",
]


@dataclass
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    usage_source: UsageSource = "unavailable"

    def is_available(self) -> bool:
        return (
            self.usage_source in ("provider", "estimated", "legacy_total_only", "partial")
            and self.total_tokens is not None
        )

    @classmethod
    def combine(cls, usages: Iterable[TokenUsage | None]) -> TokenUsage:
        """Fold real per-call usages without an artificial 'unavailable' seed."""
        result: TokenUsage | None = None
        for u in usages:
            if u is None:
                continue
            result = u if result is None else result.add(u)
        return result if result is not None else cls(usage_source="unavailable")

    def add(self, other: TokenUsage | None) -> TokenUsage:
        """Combine two token usages safely with truthful provenance."""
        if other is None:
            return self

        in_tok = (
            (self.input_tokens or 0) + (other.input_tokens or 0)
            if (self.input_tokens is not None or other.input_tokens is not None)
            else None
        )
        out_tok = (
            (self.output_tokens or 0) + (other.output_tokens or 0)
            if (self.output_tokens is not None or other.output_tokens is not None)
            else None
        )
        tot_tok = (
            (self.total_tokens or 0) + (other.total_tokens or 0)
            if (self.total_tokens is not None or other.total_tokens is not None)
            else None
        )
        cached = (
            (self.cached_input_tokens or 0) + (other.cached_input_tokens or 0)
            if (self.cached_input_tokens is not None or other.cached_input_tokens is not None)
            else None
        )
        reasoning = (
            (self.reasoning_tokens or 0) + (other.reasoning_tokens or 0)
            if (self.reasoning_tokens is not None or other.reasoning_tokens is not None)
            else None
        )

        sources = {self.usage_source, other.usage_source}
        if sources == {"provider"}:
            src: UsageSource = "provider"
        elif "partial" in sources:
            src = "partial"
        elif "provider" in sources and "unavailable" in sources:
            src = "partial"
        elif "provider" in sources and "legacy_total_only" in sources:
            src = "partial"
        elif "legacy_total_only" in sources and "unavailable" in sources:
            src = "partial"
        elif "estimated" in sources:
            src = "estimated"
        elif sources == {"legacy_total_only"}:
            src = "legacy_total_only"
        else:
            src = "unavailable"

        return TokenUsage(
            input_tokens=in_tok,
            output_tokens=out_tok,
            total_tokens=tot_tok,
            cached_input_tokens=cached,
            reasoning_tokens=reasoning,
            usage_source=src,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "usage_source": self.usage_source,
        }


@dataclass
class LLMResult:
    """Standard text generation result with metadata and backward-compatible tuple unpacking."""

    content: str
    usage: TokenUsage
    model: str | None = None
    finish_reason: str | None = None
    provider_request_id: str | None = None
    latency_ms: int = 0

    def __iter__(self):
        # Support legacy `content, tokens = await llm.generate(...)`
        yield self.content
        yield self.usage.total_tokens or 0

    def __getitem__(self, idx: int):
        if idx == 0:
            return self.content
        if idx == 1:
            return self.usage.total_tokens or 0
        raise IndexError(f"LLMResult index out of range: {idx}")


@dataclass
class LLMToolResult:
    """Tool generation result with metadata and backward-compatible tuple unpacking."""

    content: str | None
    tool_calls: list[dict[str, Any]]
    usage: TokenUsage
    model: str | None = None
    finish_reason: str | None = None
    provider_request_id: str | None = None
    latency_ms: int = 0

    def __iter__(self):
        # Support legacy `content, tool_calls, tokens = await llm.tool_generate(...)`
        yield self.content
        yield self.tool_calls
        yield self.usage.total_tokens or 0

    def __getitem__(self, idx: int):
        if idx == 0:
            return self.content
        if idx == 1:
            return self.tool_calls
        if idx == 2:
            return self.usage.total_tokens or 0
        raise IndexError(f"LLMToolResult index out of range: {idx}")


@dataclass
class ModelCallRecord:
    """Record of an individual model invocation during a turn."""

    phase: str  # "tool_planner", "response_generation", "diagnostics", "other"
    provider: str
    model: str
    latency_ms: int
    usage: TokenUsage
    started_at: datetime | None = None
    finish_reason: str | None = None
    provider_request_id: str | None = None
    success: bool = True
    error: str | None = None
    estimated_cost: float | None = None
    currency: str = "USD"

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "usage": self.usage.to_dict(),
            "started_at": (self.started_at or datetime.now(UTC)).isoformat(),
            "finish_reason": self.finish_reason,
            "provider_request_id": self.provider_request_id,
            "success": self.success,
            "error": self.error,
            "estimated_cost": self.estimated_cost,
            "currency": self.currency,
        }
