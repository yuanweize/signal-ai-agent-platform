"""
LLM Provider abstractions and implementations.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Protocol, runtime_checkable

from openai import AsyncOpenAI

from app.ai.types.usage import LLMResult, LLMToolResult, TokenUsage

logger = logging.getLogger("ai.providers.llm")


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM interactions."""

    async def generate(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 800,
    ) -> LLMResult | tuple[str, int]:
        """Generate text completion from messages. Returns LLMResult (or unpackable tuple)."""
        ...

    async def tool_generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None = None,
    ) -> LLMToolResult | tuple[str | None, list[dict[str, Any]], int]:
        """Generate response with optional tool calls. Returns LLMToolResult (or unpackable tuple)."""
        ...


def parse_openai_usage(usage_obj: Any) -> TokenUsage:
    """Parse real OpenAI-compatible usage object safely using getattr."""
    if not usage_obj:
        return TokenUsage(usage_source="unavailable")

    in_tok = getattr(usage_obj, "prompt_tokens", None)
    out_tok = getattr(usage_obj, "completion_tokens", None)
    tot_tok = getattr(usage_obj, "total_tokens", None)
    if tot_tok is None and (in_tok is not None or out_tok is not None):
        tot_tok = (in_tok or 0) + (out_tok or 0)

    cached_tok = None
    prompt_details = getattr(usage_obj, "prompt_tokens_details", None)
    if prompt_details:
        cached_tok = getattr(prompt_details, "cached_tokens", None)

    reasoning_tok = None
    comp_details = getattr(usage_obj, "completion_tokens_details", None)
    if comp_details:
        reasoning_tok = getattr(comp_details, "reasoning_tokens", None)

    src = (
        "provider"
        if (tot_tok is not None or in_tok is not None or out_tok is not None)
        else "unavailable"
    )
    return TokenUsage(
        input_tokens=in_tok,
        output_tokens=out_tok,
        total_tokens=tot_tok,
        cached_input_tokens=cached_tok,
        reasoning_tokens=reasoning_tok,
        usage_source=src,
    )


class OpenAICompatibleProvider:
    """OpenAI-compatible LLM provider implementation."""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        default_model: str = "gpt-4o-mini",
        model: str | None = None,
        timeout: float = 30.0,
        temperature: float = 0.7,
        max_tokens: int = 800,
    ) -> None:
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = api_key or "__NO_KEY__"
        self.default_model = model or default_model
        self.provider_name = "openai_compatible"
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            effective_base_url = self.base_url or "https://api.openai.com/v1"
            if effective_base_url and not effective_base_url.endswith("/v1"):
                effective_base_url = f"{effective_base_url}/v1"
            self._client = AsyncOpenAI(
                base_url=effective_base_url,
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=2,
            )
        return self._client

    async def generate(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult:
        client = self._get_client()
        target_model = model or self.default_model
        temp = temperature if temperature is not None else self.temperature
        tokens_limit = max_tokens if max_tokens is not None else self.max_tokens

        t0 = time.perf_counter()
        response = await client.chat.completions.create(
            model=target_model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temp,
            max_tokens=tokens_limit,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        choice = response.choices[0]
        content = choice.message.content or ""
        finish_reason = getattr(choice, "finish_reason", None)
        req_id = getattr(response, "id", None)
        usage = parse_openai_usage(getattr(response, "usage", None))

        return LLMResult(
            content=content,
            usage=usage,
            model=target_model,
            finish_reason=finish_reason,
            provider_request_id=req_id,
            latency_ms=latency_ms,
        )

    async def tool_generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None = None,
    ) -> LLMToolResult:
        client = self._get_client()
        target_model = model or self.default_model
        kwargs: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        t0 = time.perf_counter()
        response = await client.chat.completions.create(**kwargs)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        choice = response.choices[0]
        content = choice.message.content
        finish_reason = getattr(choice, "finish_reason", None)
        req_id = getattr(response, "id", None)
        usage = parse_openai_usage(getattr(response, "usage", None))

        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                args = {}
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {"raw": tc.function.arguments}
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": args,
                    }
                )

        return LLMToolResult(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            model=target_model,
            finish_reason=finish_reason,
            provider_request_id=req_id,
            latency_ms=latency_ms,
        )


class FakeLLMProvider:
    """Deterministic fake LLM provider for unit tests and local evaluation."""

    def __init__(self, fixed_reply: str | None = None) -> None:
        self.fixed_reply = fixed_reply
        self.default_model = "fake-eval-v1"
        self.provider_name = "fake"
        self.invocations: list[dict[str, Any]] = []

    async def generate(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 800,
    ) -> LLMResult:
        self.invocations.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
            }
        )
        target_model = model or self.default_model

        if self.fixed_reply is not None:
            return LLMResult(
                content=self.fixed_reply,
                usage=TokenUsage(
                    input_tokens=10, output_tokens=32, total_tokens=42, usage_source="estimated"
                ),
                model=target_model,
                latency_ms=15,
            )

        # Inspect messages for tool results
        for m in messages:
            content_str = m.get("content", "")
            if "Business Tool Results:" in content_str:
                tool_data = content_str.replace("Business Tool Results:", "").strip()
                if (
                    "search_products" in tool_data.lower()
                    or "organic arabica coffee" in tool_data.lower()
                ):
                    return LLMResult(
                        content="Here are our current featured products: Organic Arabica Coffee ($15.00).",
                        usage=TokenUsage(
                            input_tokens=15,
                            output_tokens=20,
                            total_tokens=35,
                            usage_source="estimated",
                        ),
                        model=target_model,
                        latency_ms=15,
                    )
                return LLMResult(
                    content=f"According to warehouse and inventory records: {tool_data}",
                    usage=TokenUsage(
                        input_tokens=15, output_tokens=20, total_tokens=35, usage_source="estimated"
                    ),
                    model=target_model,
                    latency_ms=15,
                )

        # Inspect last message for deterministic behaviors
        last_msg = messages[-1]["content"] if messages else ""
        lower = last_msg.lower()
        if "coffee" in lower or "product" in lower:
            reply = "Here are our current featured products: Organic Arabica Coffee ($15.00)."
            out_tok = 35
        elif "return" in lower or "policy" in lower or "damage" in lower:
            reply = (
                "Our customer service policy allows item return within 30 days for damaged goods."
            )
            out_tok = 30
        elif "delivery" in lower or "hour" in lower:
            reply = "Our customer support and delivery hours run Monday through Friday from 09:00 to 18:00."
            out_tok = 25
        elif "refund" in lower:
            reply = "Your refund request has been logged for supervisor approval."
            out_tok = 20
        elif "order" in lower:
            reply = "Your order status is confirmed and scheduled for packaging."
            out_tok = 25
        elif "human" in lower or "agent" in lower:
            reply = "I am connecting you with a human representative right now."
            out_tok = 20
        else:
            reply = "Thank you for reaching out! How can I assist you today?"
            out_tok = 15

        in_tok = max(5, len(last_msg) // 4)
        return LLMResult(
            content=reply,
            usage=TokenUsage(
                input_tokens=in_tok,
                output_tokens=out_tok,
                total_tokens=in_tok + out_tok,
                usage_source="estimated",
            ),
            model=target_model,
            latency_ms=15,
        )

    async def tool_generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None = None,
    ) -> LLMToolResult:
        self.invocations.append(
            {
                "messages": messages,
                "tools": tools,
                "model": model,
            }
        )
        target_model = model or self.default_model
        last_msg = messages[-1]["content"] if messages else ""
        lower = last_msg.lower()
        if "inventory" in lower or "sku" in lower:
            tool_name = "warehouse_check_inventory"
            if tools:
                matched = next(
                    (
                        t["function"]["name"]
                        for t in tools
                        if "inventory" in t["function"]["name"].lower()
                    ),
                    None,
                )
                if matched:
                    tool_name = matched
            return LLMToolResult(
                content=None,
                tool_calls=[
                    {"id": "call_inv_1", "name": tool_name, "arguments": {"sku": "SKU-COFFEE-01"}}
                ],
                usage=TokenUsage(
                    input_tokens=15, output_tokens=15, total_tokens=30, usage_source="estimated"
                ),
                model=target_model,
                latency_ms=20,
            )
        if "dispatch" in lower or "ship order" in lower or "ship it" in lower:
            tool_name = "warehouse_dispatch_order"
            if tools:
                matched = next(
                    (
                        t["function"]["name"]
                        for t in tools
                        if "dispatch" in t["function"]["name"].lower()
                    ),
                    None,
                )
                if matched:
                    tool_name = matched
            return LLMToolResult(
                content=None,
                tool_calls=[
                    {"id": "call_disp_1", "name": tool_name, "arguments": {"order_id": 101}}
                ],
                usage=TokenUsage(
                    input_tokens=15, output_tokens=15, total_tokens=30, usage_source="estimated"
                ),
                model=target_model,
                latency_ms=20,
            )
        if "search" in lower or "price" in lower:
            return LLMToolResult(
                content=None,
                tool_calls=[
                    {"id": "call_1", "name": "search_products", "arguments": {"query": "coffee"}}
                ],
                usage=TokenUsage(
                    input_tokens=15, output_tokens=15, total_tokens=30, usage_source="estimated"
                ),
                model=target_model,
                latency_ms=20,
            )
        gen_res = await self.generate(messages, model=model)
        return LLMToolResult(
            content=gen_res.content,
            tool_calls=[],
            usage=gen_res.usage,
            model=gen_res.model,
            latency_ms=gen_res.latency_ms,
        )


class DisabledLLMProvider:
    """Explicit provider when AI is disabled or unconfigured in Settings."""

    def __init__(self, reason: str = "AI is disabled") -> None:
        self.provider_name = "disabled"
        self.default_model = "disabled"
        self.reason = reason

    async def generate(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 800,
    ) -> tuple[str, int]:
        raise RuntimeError(f"AI provider call prohibited: {self.reason}")

    async def tool_generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None = None,
    ) -> tuple[str | None, list[dict[str, Any]], int]:
        raise RuntimeError(f"AI provider call prohibited: {self.reason}")
