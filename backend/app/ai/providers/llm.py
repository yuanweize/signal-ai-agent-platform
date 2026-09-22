"""
LLM Provider abstractions and implementations.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

from openai import AsyncOpenAI

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
    ) -> tuple[str, int]:
        """Generate text completion from messages. Returns (content, tokens_used)."""
        ...

    async def tool_generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None = None,
    ) -> tuple[str | None, list[dict[str, Any]], int]:
        """Generate response with optional tool calls. Returns (content, tool_calls, tokens_used)."""
        ...


class OpenAICompatibleProvider:
    """OpenAI-compatible LLM provider implementation."""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        default_model: str = "gpt-4o-mini",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = api_key or "__NO_KEY__"
        self.default_model = default_model
        self.timeout = timeout
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=2,
            )
        return self._client

    async def generate(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 800,
    ) -> tuple[str, int]:
        client = self._get_client()
        target_model = model or self.default_model
        response = await client.chat.completions.create(
            model=target_model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else len(content) // 4
        return content, tokens

    async def tool_generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None = None,
    ) -> tuple[str | None, list[dict[str, Any]], int]:
        client = self._get_client()
        target_model = model or self.default_model
        kwargs: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        content = choice.message.content
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

        tokens = response.usage.total_tokens if response.usage else 0
        return content, tool_calls, tokens


class FakeLLMProvider:
    """Deterministic fake LLM provider for unit tests and local evaluation."""

    def __init__(self, fixed_reply: str | None = None) -> None:
        self.fixed_reply = fixed_reply
        self.invocations: list[dict[str, Any]] = []

    async def generate(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 800,
    ) -> tuple[str, int]:
        self.invocations.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
            }
        )
        if self.fixed_reply is not None:
            return self.fixed_reply, 42

        # Inspect last message for deterministic behaviors
        last_msg = messages[-1]["content"] if messages else ""
        if "product" in last_msg.lower():
            return "Here are our current featured products: Organic Arabica Coffee ($15.00).", 35
        if "order" in last_msg.lower():
            return "Your order status is confirmed and scheduled for packaging.", 25
        if "human" in last_msg.lower() or "agent" in last_msg.lower():
            return "I am connecting you with a human representative right now.", 20
        return "Thank you for reaching out! How can I assist you today?", 15

    async def tool_generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None = None,
    ) -> tuple[str | None, list[dict[str, Any]], int]:
        self.invocations.append(
            {
                "messages": messages,
                "tools": tools,
                "model": model,
            }
        )
        last_msg = messages[-1]["content"] if messages else ""
        if "search" in last_msg.lower() or "price" in last_msg.lower():
            return (
                None,
                [{"id": "call_1", "name": "search_products", "arguments": {"query": "coffee"}}],
                30,
            )
        return await self.generate(messages, model=model)
