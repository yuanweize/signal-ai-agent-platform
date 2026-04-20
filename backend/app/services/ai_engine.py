"""
AI Engine — Optional LLM integration with conversation memory.

Connects to any OpenAI-compatible API (OpenAI, Tailscale AI Gateway,
OpenRouter, Ollama, vLLM, etc.) via configurable base_url.

This module is OPTIONAL — controlled by FEATURE_AI_ENABLED.
When disabled, the bot still receives/logs messages but doesn't reply.
"""

from __future__ import annotations

import logging
from datetime import datetime

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.conversation import Conversation, Message
from app.models.group import Group
from app.models.product import Product

logger = logging.getLogger("ai.engine")


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

    async def initialize(self) -> bool:
        """
        Initialize the AI client.

        Returns True if successfully initialized, False if disabled/misconfigured.
        """
        if not settings.is_ai_available:
            logger.info(
                "🧠 AI engine DISABLED "
                f"(feature_ai_enabled={settings.feature_ai_enabled}, "
                f"api_key={'set' if settings.ai_api_key else 'empty'})"
            )
            self._enabled = False
            return False

        try:
            self._client = AsyncOpenAI(
                api_key=settings.ai_api_key,
                base_url=settings.ai_api_base_url,
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

    async def generate_response(
        self,
        session: AsyncSession,
        conversation: Conversation,
        user_message: str,
        group_id: str | None = None,
    ) -> str | None:
        """
        Generate an AI response given a conversation and new user message.

        Args:
            session: DB session for loading context
            conversation: Current conversation record
            user_message: The new message from the user
            group_id: Group ID for per-group prompt override

        Returns:
            AI response text, or None if generation fails
        """
        if not self.is_enabled:
            return None

        try:
            # Build the message list for the API call
            messages = await self._build_messages(
                session, conversation, user_message, group_id
            )

            # Call the LLM
            response = await self._client.chat.completions.create(
                model=settings.ai_model,
                messages=messages,
                temperature=settings.ai_temperature,
                max_tokens=settings.ai_max_tokens,
            )

            # Extract response
            choice = response.choices[0]
            reply = choice.message.content

            # Track token usage
            tokens_used = None
            if response.usage:
                tokens_used = response.usage.total_tokens
                logger.debug(
                    f"🔢 Tokens: {response.usage.prompt_tokens} prompt + "
                    f"{response.usage.completion_tokens} completion = "
                    f"{tokens_used} total"
                )

            # Store token count on the latest assistant message (will be saved by handler)
            # Return as tuple-like info — handler will use it
            self._last_tokens_used = tokens_used

            if reply:
                preview = reply[:80].replace("\n", " ")
                logger.info(f"🤖 AI reply: {preview}...")
                return reply.strip()
            else:
                logger.warning("⚠️  AI returned empty response")
                return None

        except Exception as e:
            logger.error(f"❌ AI generation error: {e}", exc_info=True)
            return None

    @property
    def last_tokens_used(self) -> int | None:
        """Token count from the last API call (for tracking)."""
        return getattr(self, "_last_tokens_used", None)

    async def _build_messages(
        self,
        session: AsyncSession,
        conversation: Conversation,
        user_message: str,
        group_id: str | None = None,
    ) -> list[dict]:
        """
        Build the messages list for the OpenAI API call.

        Structure:
        1. System prompt (global or per-group override)
        2. Conversation summary (if exists, for long-term memory)
        3. Recent messages from DB (short-term context window)
        4. Current user message
        """
        messages = []

        # 1. System prompt
        system_prompt = await self._get_system_prompt(session, group_id)
        messages.append({"role": "system", "content": system_prompt})

        # 2. Product catalog (only when market module is enabled)
        if settings.is_market_available:
            catalog = await self._build_catalog_context(session)
            if catalog:
                messages.append({"role": "system", "content": catalog})

        # 3. Conversation summary (long-term memory compression)
        if conversation.summary:
            messages.append({
                "role": "system",
                "content": (
                    f"Shrnutí předchozí konverzace s tímto uživatelem:\n"
                    f"{conversation.summary}"
                ),
            })

        # 4. Load recent messages from DB (short-term context)
        history = await self._load_context_messages(session, conversation.id)
        messages.extend(history)

        # 5. Current user message
        messages.append({"role": "user", "content": user_message})

        return messages

    async def _get_system_prompt(
        self,
        session: AsyncSession,
        group_id: str | None = None,
    ) -> str:
        """
        Get the system prompt — check for per-group override first.
        """
        if group_id:
            result = await session.execute(
                select(Group).where(Group.group_id == group_id)
            )
            group = result.scalar_one_or_none()
            if group and group.system_prompt_override:
                return group.system_prompt_override

        # Fall back to global system prompt
        return settings.bot_system_prompt

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
            lines.append(
                f"  • {p.name} — {p.price:.0f} {p.currency} ({stock_info})"
            )
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
    ) -> list[dict]:
        """
        Load the last N messages from the conversation for context.

        Only loads 'user' and 'assistant' roles (not system messages).
        """
        max_messages = settings.ai_context_messages

        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .where(Message.role.in_(["user", "assistant"]))
            .order_by(Message.timestamp.desc())
            .limit(max_messages)
        )
        db_messages = result.scalars().all()

        # Reverse to get chronological order (we queried desc for limit)
        db_messages = list(reversed(db_messages))

        return [
            {"role": msg.role, "content": msg.content}
            for msg in db_messages
        ]


# ---- Singleton instance ----
ai_engine = AIEngine()
