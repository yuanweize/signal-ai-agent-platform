"""
AI Engine — Optional LLM integration with conversation memory.

Connects to any OpenAI-compatible API (OpenAI, Tailscale AI Gateway,
OpenRouter, Ollama, vLLM, etc.) via configurable base_url.

This module is OPTIONAL — controlled by FEATURE_AI_ENABLED.
When disabled, the bot still receives/logs messages but doesn't reply.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse, urlunparse

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.conversation import Conversation, Message
from app.models.group import Group
from app.models.product import Product
from app.services.runtime_config import get_runtime_settings, is_ai_api_key_optional

logger = logging.getLogger("ai.engine")

DEFAULT_AI_TIMEOUT_SECONDS = 30.0
DEFAULT_AI_MAX_RETRIES = 2


def build_base_url_candidates(base_url: str) -> list[str]:
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        return []

    parsed = urlparse(normalized)
    path = parsed.path.rstrip("/")

    candidates: list[str] = [normalized]
    if path.endswith("/v1"):
        alt_path = path[:-3] or ""
        candidates.append(urlunparse(parsed._replace(path=alt_path)).rstrip("/"))
    else:
        alt_path = f"{path}/v1" if path else "/v1"
        candidates.append(urlunparse(parsed._replace(path=alt_path)).rstrip("/"))

    unique: list[str] = []
    for item in candidates:
        if item and item not in unique:
            unique.append(item)
    return unique


def build_model_candidates(model: str, preferred: str | None = None) -> list[str]:
    candidates: list[str] = []
    if preferred and preferred.strip():
        candidates.append(preferred.strip())

    normalized = (model or "").strip()
    if normalized:
        candidates.append(normalized)
        if "/" not in normalized:
            candidates.append(f"openai/{normalized}")
        if normalized.startswith("openai/") and len(normalized) > len("openai/"):
            candidates.append(normalized.split("/", 1)[1])

    unique: list[str] = []
    for item in candidates:
        if item and item not in unique:
            unique.append(item)
    return unique


def is_model_route_error(status_code: int, message: str) -> bool:
    msg = (message or "").lower()
    return status_code in {400, 404} and any(
        snippet in msg
        for snippet in [
            "no route found for model",
            "model not found",
            "unsupported model",
            "unknown model",
        ]
    )


async def probe_ai_compatibility(
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> dict:
    attempts: list[dict] = []
    last_error: str | None = None
    base_candidates = build_base_url_candidates(base_url)
    model_candidates = build_model_candidates(model) if model else []

    for candidate_base in base_candidates:
        effective_api_key = api_key or "__NO_KEY__"
        client = AsyncOpenAI(
            api_key=effective_api_key,
            base_url=candidate_base,
            timeout=DEFAULT_AI_TIMEOUT_SECONDS,
            max_retries=1,
        )

        listed_models_all: list[str] = []
        try:
            model_list = await client.models.list()
            listed_models_all = sorted(
                {
                    str(item.id).strip()
                    for item in getattr(model_list, "data", [])
                    if getattr(item, "id", None)
                },
                key=lambda v: v.lower(),
            )
            listed_total = len(listed_models_all)
            listed_models = listed_models_all[:500]

            return {
                "ok": True,
                "base_url": candidate_base,
                "model": None,
                "listed_models": listed_models,
                "valid_models": listed_models,
                "invalid_models": [],
                "models": listed_models,
                "listed_total": listed_total,
                "verified_total": 0,
                "base_candidates": base_candidates,
                "verification_base_candidates": [],
                "message": (
                    f"Base URL reachable. models listed={listed_total}. No bulk model verification performed."
                    if listed_total
                    else "Base URL is reachable but model list is empty"
                ),
                "preview": "",
                "attempts": attempts,
            }
        except Exception as e:
            detail = str(e)
            attempts.append(
                {
                    "base_url": candidate_base,
                    "model": "<models.list>",
                    "status": None,
                    "message": detail[:200],
                }
            )
            last_error = detail

        if not model_candidates:
            continue

        for candidate_model in model_candidates:
            try:
                response = await client.chat.completions.create(
                    model=candidate_model,
                    messages=[{"role": "user", "content": "Reply with OK only"}],
                    temperature=0,
                    max_tokens=8,
                )
                preview = (response.choices[0].message.content or "").strip()[:120]
                return {
                    "ok": True,
                    "base_url": candidate_base,
                    "model": candidate_model,
                    "listed_models": [],
                    "valid_models": [candidate_model],
                    "invalid_models": [],
                    "models": [candidate_model],
                    "listed_total": 1,
                    "verified_total": 1,
                    "base_candidates": base_candidates,
                    "message": "Compatibility probe succeeded",
                    "preview": preview,
                    "attempts": attempts,
                }
            except APIStatusError as e:
                detail = str(getattr(e, "body", e))
                attempts.append(
                    {
                        "base_url": candidate_base,
                        "model": candidate_model,
                        "status": e.status_code,
                        "message": detail[:200],
                    }
                )
                last_error = detail
                if is_model_route_error(e.status_code, detail):
                    continue
            except (APITimeoutError, APIConnectionError) as e:
                detail = str(e)
                attempts.append(
                    {
                        "base_url": candidate_base,
                        "model": candidate_model,
                        "status": None,
                        "message": detail[:200],
                    }
                )
                last_error = detail
                continue
            except Exception as e:
                detail = str(e)
                attempts.append(
                    {
                        "base_url": candidate_base,
                        "model": candidate_model,
                        "status": None,
                        "message": detail[:200],
                    }
                )
                last_error = detail

    return {
        "ok": False,
        "base_url": None,
        "model": None,
        "listed_models": [],
        "valid_models": [],
        "invalid_models": [],
        "models": [],
        "listed_total": 0,
        "verified_total": 0,
        "base_candidates": base_candidates,
        "message": (last_error or "Compatibility probe failed")[:200],
        "preview": "",
        "attempts": attempts,
    }


async def verify_ai_model_availability(
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> dict:
    if not model.strip():
        return {
            "ok": False,
            "model": model,
            "effective_model": None,
            "effective_base_url": None,
            "message": "Model is required",
            "checked_at": datetime.now(UTC).isoformat(),
            "attempts": [],
        }

    attempts: list[dict] = []
    for candidate_base in build_base_url_candidates(base_url):
        client = AsyncOpenAI(
            api_key=api_key or "__NO_KEY__",
            base_url=candidate_base,
            timeout=DEFAULT_AI_TIMEOUT_SECONDS,
            max_retries=1,
        )
        for candidate_model in build_model_candidates(model):
            try:
                response = await client.chat.completions.create(
                    model=candidate_model,
                    messages=[{"role": "user", "content": "Reply with OK only"}],
                    temperature=0,
                    max_tokens=8,
                )
                preview = (response.choices[0].message.content or "").strip()[:120]
                return {
                    "ok": True,
                    "model": model,
                    "effective_model": candidate_model,
                    "effective_base_url": candidate_base,
                    "message": "Model is available",
                    "preview": preview,
                    "checked_at": datetime.now(UTC).isoformat(),
                    "attempts": attempts,
                }
            except APIStatusError as e:
                detail = str(getattr(e, "body", e))
                attempts.append(
                    {
                        "base_url": candidate_base,
                        "model": candidate_model,
                        "status": e.status_code,
                        "message": detail[:200],
                    }
                )
                if is_model_route_error(e.status_code, detail):
                    continue
            except (APITimeoutError, APIConnectionError) as e:
                attempts.append(
                    {
                        "base_url": candidate_base,
                        "model": candidate_model,
                        "status": None,
                        "message": str(e)[:200],
                    }
                )
            except Exception as e:
                attempts.append(
                    {
                        "base_url": candidate_base,
                        "model": candidate_model,
                        "status": None,
                        "message": str(e)[:200],
                    }
                )

    return {
        "ok": False,
        "model": model,
        "effective_model": None,
        "effective_base_url": None,
        "message": "Model verification failed",
        "checked_at": datetime.now(UTC).isoformat(),
        "attempts": attempts,
    }


@dataclass
class AIResponse:
    """Structured response from the AI generation call."""

    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    model: str = ""
    provider: str = "openai-compatible"
    effective_base_url: str = ""
    latency_ms: int = 0
    finish_reason: str | None = None


class AIEngine:
    """
    LLM-powered response generator with conversation memory.

    Features:
    - Configurable system prompt (global + per-group override)
    - Product catalog injection (when FEATURE_MARKET_ENABLED)
    - Conversation context window (last N messages from DB)
    - Token usage tracking
    - Graceful degradation (errors logged, never crash the bot)
    """

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None
        self._enabled = False
        self._runtime_api_key: str = ""
        self._runtime_base_url: str = ""
        self._runtime_effective_base_url: str = ""
        self._runtime_model_aliases: dict[str, str] = {}

    async def initialize(self) -> bool:
        """
        Initialize the AI client.

        Returns True if successfully initialized, False if disabled/misconfigured.
        """
        if not settings.feature_ai_enabled:
            logger.info(
                "🧠 AI engine DISABLED "
                f"(feature_ai_enabled={settings.feature_ai_enabled}, "
                f"api_key={'set' if settings.ai_api_key else 'empty'})"
            )
            self._enabled = False
            return False

        if not settings.ai_api_key and not is_ai_api_key_optional(settings.ai_api_base_url):
            logger.info("🧠 AI engine DISABLED (missing API key for current provider)")
            self._enabled = False
            return False

        try:
            self._client = AsyncOpenAI(
                api_key=settings.ai_api_key or "__NO_KEY__",
                base_url=settings.ai_api_base_url,
                timeout=DEFAULT_AI_TIMEOUT_SECONDS,
                max_retries=DEFAULT_AI_MAX_RETRIES,
            )
            self._enabled = True
            logger.info(
                f"🧠 AI engine ENABLED — "
                f"provider: {settings.ai_api_base_url}, "
                f"model: {settings.ai_model}"
            )
            return True

        except Exception as e:
            logger.error(f"❌ AI engine init failed: {e}")
            self._enabled = False
            return False

    @property
    def is_enabled(self) -> bool:
        """Check if AI engine is active and ready."""
        return self._enabled and self._client is not None

    async def generate_ai_response(
        self,
        session: AsyncSession,
        conversation: Conversation,
        user_message: str,
        group_id: str | None = None,
        sender_name: str | None = None,
        current_signal_timestamp_ms: int | None = None,
    ) -> AIResponse | None:
        """
        Generate a structured AI response given a conversation and new user message.
        """
        runtime = await self._refresh_runtime_client(session)
        if not self.is_enabled:
            return None

        start_time = time.perf_counter()
        try:
            # Build the message list for the API call
            messages = await self._build_messages(
                session,
                conversation,
                user_message,
                group_id,
                runtime,
                sender_name=sender_name,
                current_signal_timestamp_ms=current_signal_timestamp_ms,
            )

            # Call the LLM
            response = await self._create_completion_with_adaptation(runtime, messages)
            latency_ms = int((time.perf_counter() - start_time) * 1000)

            choice = response.choices[0]
            reply = choice.message.content
            finish_reason = getattr(choice, "finish_reason", None)

            prompt_tokens = response.usage.prompt_tokens if response.usage else None
            completion_tokens = response.usage.completion_tokens if response.usage else None
            total_tokens = response.usage.total_tokens if response.usage else None

            if total_tokens:
                logger.debug(
                    f"🔢 Tokens: {prompt_tokens} prompt + "
                    f"{completion_tokens} completion = {total_tokens} total"
                )

            if reply:
                preview = reply[:80].replace("\n", " ")
                logger.info(f"🤖 AI reply ({latency_ms}ms): {preview}...")
                return AIResponse(
                    text=reply.strip(),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    model=runtime.get("ai_model", ""),
                    effective_base_url=runtime.get("ai_api_base_url", ""),
                    latency_ms=latency_ms,
                    finish_reason=finish_reason,
                )
            else:
                logger.warning("⚠️  AI returned empty response")
                return None

        except AuthenticationError:
            logger.error("❌ AI auth failed: invalid API key or gateway auth")
            return None
        except RateLimitError:
            logger.warning("⏳ AI rate limited by provider")
            return None
        except APITimeoutError:
            logger.warning("⏱️  AI request timed out")
            return None
        except APIConnectionError:
            logger.error("🌐 AI provider connection failed")
            return None
        except APIStatusError as e:
            logger.error(f"❌ AI provider status error: {e.status_code}")
            return None
        except Exception as e:
            logger.error(f"❌ AI generation error: {e}", exc_info=True)
            return None

    async def generate_response(
        self,
        session: AsyncSession,
        conversation: Conversation,
        user_message: str,
        group_id: str | None = None,
        sender_name: str | None = None,
        current_signal_timestamp_ms: int | None = None,
    ) -> str | None:
        """Backward-compatible helper returning raw text."""
        res = await self.generate_ai_response(
            session=session,
            conversation=conversation,
            user_message=user_message,
            group_id=group_id,
            sender_name=sender_name,
            current_signal_timestamp_ms=current_signal_timestamp_ms,
        )
        return res.text if res else None

    @property
    def last_tokens_used(self) -> int | None:
        """Token count from the last API call — deprecated, use return value instead."""
        return getattr(self, "_last_tokens_used", None)

    async def _refresh_runtime_client(self, session: AsyncSession) -> dict:
        runtime = await get_runtime_settings(session)
        runtime_enabled = runtime["is_ai_enabled"]
        runtime_key = runtime["ai_api_key"]
        runtime_base_url = runtime["ai_api_base_url"]

        if not runtime_enabled:
            self._enabled = False
            return runtime

        if not runtime_key and not is_ai_api_key_optional(runtime_base_url):
            self._enabled = False
            return runtime

        if (
            self._client is None
            or runtime_key != self._runtime_api_key
            or runtime_base_url != self._runtime_base_url
        ):
            self._client = AsyncOpenAI(
                api_key=runtime_key or "__NO_KEY__",
                base_url=runtime_base_url,
                timeout=DEFAULT_AI_TIMEOUT_SECONDS,
                max_retries=DEFAULT_AI_MAX_RETRIES,
            )
            self._runtime_api_key = runtime_key
            self._runtime_base_url = runtime_base_url
            self._runtime_effective_base_url = runtime_base_url
            self._runtime_model_aliases = {}
            logger.info(
                "🔄 AI client refreshed "
                f"(provider={runtime.get('ai_provider_detected', 'unknown')}, "
                f"base_url={runtime_base_url}, model={runtime.get('ai_model', settings.ai_model)})"
            )

        self._enabled = True
        return runtime

    async def _create_completion_with_adaptation(self, runtime: dict, messages: list[dict]):
        requested_base_url = runtime["ai_api_base_url"]
        requested_model = (runtime.get("ai_model") or "").strip()

        base_candidates = build_base_url_candidates(requested_base_url)
        if self._runtime_effective_base_url in base_candidates:
            base_candidates = [
                self._runtime_effective_base_url,
                *[
                    candidate
                    for candidate in base_candidates
                    if candidate != self._runtime_effective_base_url
                ],
            ]

        model_candidates = build_model_candidates(
            requested_model,
            preferred=self._runtime_model_aliases.get(requested_model),
        )

        last_error: Exception | None = None
        for candidate_base in base_candidates:
            client = self._client
            if candidate_base != self._runtime_effective_base_url or client is None:
                client = AsyncOpenAI(
                    api_key=self._runtime_api_key or "__NO_KEY__",
                    base_url=candidate_base,
                    timeout=DEFAULT_AI_TIMEOUT_SECONDS,
                    max_retries=DEFAULT_AI_MAX_RETRIES,
                )

            for candidate_model in model_candidates:
                try:
                    response = await client.chat.completions.create(
                        model=candidate_model,
                        messages=messages,
                        temperature=runtime["ai_temperature"],
                        max_tokens=runtime["ai_max_tokens"],
                    )

                    if candidate_base != self._runtime_effective_base_url:
                        self._client = client
                        self._runtime_effective_base_url = candidate_base
                        logger.info(
                            "🔁 AI endpoint adapted "
                            f"(requested={requested_base_url}, effective={candidate_base})"
                        )

                    if candidate_model != requested_model:
                        self._runtime_model_aliases[requested_model] = candidate_model
                        logger.info(
                            "🔁 AI model adapted "
                            f"(requested={requested_model}, effective={candidate_model})"
                        )

                    return response
                except APIStatusError as e:
                    last_error = e
                    detail = str(getattr(e, "body", e))
                    if e.status_code == 404 or is_model_route_error(e.status_code, detail):
                        continue
                    raise
                except (APITimeoutError, APIConnectionError) as e:
                    last_error = e
                    continue

        if last_error:
            raise last_error
        raise RuntimeError("No compatible endpoint/model combination was found")

    async def _build_messages(
        self,
        session: AsyncSession,
        conversation: Conversation,
        user_message: str,
        group_id: str | None = None,
        runtime: dict | None = None,
        *,
        sender_name: str | None = None,
        current_signal_timestamp_ms: int | None = None,
    ) -> list[dict]:
        """
        Build the messages list for the OpenAI API call.

        Structure:
        1. System prompt (global or per-group override)
        2. Conversation summary (if exists, for long-term memory)
        3. Recent messages from DB (short-term context, excluding current turn)
        4. Current user message (exactly once — P0-1 fix)

        P0-1 fix: The inbound message is already committed to DB before this
        call. We exclude it from context history using current_signal_timestamp_ms
        so it is NOT appended twice.

        P1-14 fix: For group conversations, messages include sender name prefix
        so the model knows who said what.
        """
        messages = []
        runtime = runtime or {}
        is_group = bool(group_id)

        # 1. System prompt
        system_prompt = await self._get_system_prompt(
            session,
            group_id,
            runtime_prompt=runtime.get("ai_prompt"),
        )
        messages.append({"role": "system", "content": system_prompt})

        # 2. Product catalog (only when market module is enabled)
        if runtime.get("is_market_enabled", settings.is_market_available):
            catalog = await self._build_catalog_context(session)
            if catalog:
                messages.append({"role": "system", "content": catalog})

        # 3. Conversation summary (long-term memory compression)
        if conversation.summary:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"Shrnutí předchozí konverzace s tímto uživatelem:\n{conversation.summary}"
                    ),
                }
            )

        # 4. Load recent messages from DB (short-term context)
        # Exclude the current message (already committed) to prevent duplication.
        history = await self._load_context_messages(
            session,
            conversation.id,
            runtime.get("ai_context_messages", settings.ai_context_messages),
            exclude_signal_timestamp_ms=current_signal_timestamp_ms,
            is_group=is_group,
        )
        messages.extend(history)

        # 5. Current user message (exactly once — P0-1)
        if is_group and sender_name:
            # P1-14: prefix group messages with sender name so model knows who spoke
            current_content = f"[{sender_name}]: {user_message}"
        else:
            current_content = user_message
        messages.append({"role": "user", "content": current_content})

        return messages

    async def _get_system_prompt(
        self,
        session: AsyncSession,
        group_id: str | None = None,
        runtime_prompt: str | None = None,
    ) -> str:
        """
        Get the system prompt — check for per-group override first.
        """
        if group_id:
            result = await session.execute(select(Group).where(Group.group_id == group_id))
            group = result.scalar_one_or_none()
            if group and group.system_prompt_override:
                return group.system_prompt_override

        # Fall back to global system prompt
        return runtime_prompt or settings.bot_system_prompt

    async def _build_catalog_context(
        self,
        session: AsyncSession,
    ) -> str | None:
        """
        Build a product catalog string for AI context injection.

        Only includes active, in-stock products.
        Returns None if no products are available.
        """
        result = await session.execute(
            select(Product)
            .where(Product.is_active == True)  # noqa: E712
            .where(Product.stock > 0)
            .order_by(Product.category, Product.name)
        )
        products = result.scalars().all()

        if not products:
            return None

        lines = ["Aktuální nabídka produktů (ceník):"]
        current_category = None

        for p in products:
            if p.category and p.category != current_category:
                current_category = p.category
                lines.append(f"\n📦 {current_category}:")

            stock_info = f"skladem {p.stock} ks" if p.stock < 50 else "skladem"
            lines.append(f"  • {p.name} — {p.price:.0f} {p.currency} ({stock_info})")
            if p.description:
                lines.append(f"    {p.description}")

        lines.append(
            "\nPokud se zákazník ptá na produkty, odpovídej na základě tohoto ceníku. "
            "Pokud se ptá na něco, co nemáme, řekni to přirozeně."
        )

        return "\n".join(lines)

    async def _load_context_messages(
        self,
        session: AsyncSession,
        conversation_id: int,
        max_messages: int,
        *,
        exclude_signal_timestamp_ms: int | None = None,
        is_group: bool = False,
    ) -> list[dict]:
        """
        Load the last N messages from the conversation for context.

        P0-1 fix: exclude the current inbound message by signal_timestamp_ms
        so it does not appear twice in the prompt.

        P1-14 fix: for group conversations, prefix user messages with sender name.
        Only loads 'user' and 'assistant' roles (not system messages).
        """
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .where(Message.role.in_(["user", "assistant"]))
        )

        # Exclude the current message to prevent P0-1 duplication
        if exclude_signal_timestamp_ms is not None:
            query = query.where(Message.signal_timestamp_ms != exclude_signal_timestamp_ms)

        query = query.order_by(Message.timestamp.desc()).limit(max_messages)
        result = await session.execute(query)
        db_messages = result.scalars().all()

        # Reverse to get chronological order (we queried desc for limit)
        db_messages = list(reversed(db_messages))

        context = []
        for msg in db_messages:
            if msg.role == "user" and is_group and msg.sender_name:
                # P1-14: include sender name so model knows who said what in group
                content = f"[{msg.sender_name}]: {msg.content}"
            else:
                content = msg.content
            context.append({"role": msg.role, "content": content})

        return context


# ---- Singleton instance ----
ai_engine = AIEngine()
