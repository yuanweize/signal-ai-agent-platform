"""
Internal System and Sandbox Conversation Utilities.
Ensures non-customer evaluation and probe traffic is fully isolated into dedicated system conversations.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, ConversationMode, ConversationType

logger = logging.getLogger("services.sandbox")


async def get_or_create_sandbox_conversation(
    session: AsyncSession,
    signal_id: str = "__system_eval_sandbox__",
) -> int:
    """
    Ensure a dedicated internal system sandbox conversation exists and return its database ID.
    Never creates synthetic fake IDs or contaminates real customer conversation threads.
    """
    stmt = (
        select(Conversation.id)
        .where(Conversation.signal_id == signal_id)
        .order_by(Conversation.id)
        .limit(1)
    )
    conv_id = (await session.execute(stmt)).scalars().first()
    if conv_id is not None:
        return conv_id

    conv = Conversation(
        signal_id=signal_id,
        type=ConversationType.dm.value,
        mode=ConversationMode.auto.value,
        is_active=False,
    )
    try:
        async with session.begin_nested():
            session.add(conv)
            await session.flush()
    except Exception:
        conv_id = (await session.execute(stmt)).scalars().first()
        if conv_id is None:
            raise
        return conv_id

    logger.info(f"Created dedicated system sandbox conversation #{conv.id} (signal_id={signal_id})")
    return conv.id
