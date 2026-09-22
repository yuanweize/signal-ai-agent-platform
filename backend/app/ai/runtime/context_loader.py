"""
Conversation context loader for multi-turn conversational memory.
Retrieves recent messages from DB with sender attribution and token budgeting.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Message

logger = logging.getLogger("ai.context_loader")

APPROX_CHARS_PER_TOKEN = 4
DEFAULT_MAX_CONTEXT_TOKENS = 3000


class ConversationContextLoader:
    """Loads and formats recent conversation history for AgentRuntime."""

    async def load_history(
        self,
        session: AsyncSession,
        conversation_id: int,
        max_messages: int = 20,
        *,
        current_message_id: int | None = None,
        is_group: bool = False,
        token_budget: int = DEFAULT_MAX_CONTEXT_TOKENS,
    ) -> list[dict[str, str]]:
        """
        Load recent messages for conversation_id up to max_messages and token_budget.
        Returns messages ordered oldest -> newest.
        Excludes the current inbound message (by current_message_id) so it is not duplicated.
        """
        query = select(Message).where(Message.conversation_id == conversation_id)
        if current_message_id is not None:
            query = query.where(Message.id != current_message_id)

        query = query.order_by(Message.timestamp.desc(), Message.id.desc()).limit(max_messages)
        res = await session.execute(query)
        db_messages = res.scalars().all()

        # Reverse to get chronological order (oldest -> newest)
        db_messages = list(reversed(db_messages))

        # We take from newest to oldest for token budgeting, then reverse back
        budgeted_messages = []
        total_tokens = 0
        for msg in reversed(db_messages):
            content = (msg.content or "").strip()
            if not content:
                continue

            # Robust classification using direction, actor, origin, and admin_identity (Section 19)
            is_outbound = msg.direction == "outbound"
            is_admin = (
                msg.actor in ("admin", "human")
                or msg.origin in ("human_manual", "human_ai_assisted")
                or bool(msg.admin_identity)
                or msg.role in ("admin", "human")
            )
            is_ai = (
                msg.actor in ("bot", "ai")
                or msg.origin == "ai_auto"
                or msg.role in ("assistant", "bot")
            )
            is_system = msg.actor == "system" or msg.role == "system"

            if is_system:
                role = "system"
            elif is_outbound or is_admin or is_ai:
                role = "assistant"
            else:
                role = "user"

            # Sender attribution presentation (Section 19)
            if is_group:
                if is_admin:
                    name = msg.admin_identity or msg.sender_name or msg.sender_id or "Support"
                    attribution = f"Human Support ({name}): "
                elif is_ai:
                    attribution = "AI: "
                else:
                    name = msg.sender_name or msg.sender_id or "User"
                    attribution = f"{name}: "
                final_content = f"{attribution}{content}"
            else:
                if is_admin:
                    final_content = f"Human Support: {content}"
                else:
                    final_content = content

            approx_tokens = max(1, len(final_content) // APPROX_CHARS_PER_TOKEN)
            if total_tokens + approx_tokens > token_budget and budgeted_messages:
                break

            total_tokens += approx_tokens
            budgeted_messages.append({"role": role, "content": final_content})

        formatted = list(reversed(budgeted_messages))
        return formatted

    # Alias for compatibility
    load_context_messages = load_history


context_loader = ConversationContextLoader()
