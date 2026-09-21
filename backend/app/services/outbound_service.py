"""
Outbound Message Delivery Service.

Centralizes outbound message creation, state transitions (pending -> sent | failed),
delivery metadata, idempotency, and explicit retries across AI, admin manual takeover,
and campaign broadcasts.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import (
    Conversation,
    Message,
    MessageActor,
    MessageDeliveryStatus,
    MessageDirection,
)
from app.services.signal_client import signal_client

logger = logging.getLogger("outbound.service")


class OutboundMessageService:
    """Unified service for delivering and tracking outbound Signal messages."""

    async def send_message(
        self,
        session: AsyncSession,
        conversation_id: int,
        content: str,
        recipient: str,
        actor: str = MessageActor.bot.value,
        sender_id: str | None = None,
        reply_to_id: int | None = None,
        tokens_used: int | None = None,
        client=None,
    ) -> Message:
        """
        Create a pending outbound message, attempt Signal send, and update status.
        """
        cli = client or signal_client

        # 1. Create message in pending status
        msg = Message(
            conversation_id=conversation_id,
            role="assistant"
            if actor == MessageActor.bot.value
            else "system"
            if actor == MessageActor.system.value
            else "user",
            direction=MessageDirection.outbound.value,
            actor=actor,
            sender_id=sender_id,
            content=content,
            tokens_used=tokens_used,
            reply_to_id=reply_to_id,
            delivery_status=MessageDeliveryStatus.pending.value,
            delivery_error=None,
        )
        session.add(msg)
        await session.flush()

        # Update conversation message count and last_message_at
        conv = await session.get(Conversation, conversation_id)
        if conv:
            conv.message_count = (conv.message_count or 0) + 1
            conv.last_message_at = datetime.utcnow()

        # 2. Attempt delivery through Signal Gateway
        success = False
        err_msg: str | None = None
        try:
            success = await cli.send_message(
                text=content,
                recipients=[recipient],
            )
            if not success:
                err_msg = "Gateway returned failure status"
        except Exception as e:
            logger.error(f"❌ Error sending outbound message {msg.id}: {e}", exc_info=True)
            err_msg = str(e)
            success = False

        # 3. Update delivery status
        if success:
            msg.delivery_status = MessageDeliveryStatus.sent.value
            msg.delivery_error = None
            msg.occurred_at = datetime.utcnow()
            logger.info(f"✅ Outbound message {msg.id} sent successfully to {recipient}")
        else:
            msg.delivery_status = MessageDeliveryStatus.failed.value
            msg.delivery_error = (err_msg or "Unknown delivery error")[:500]
            logger.warning(f"⚠️ Outbound message {msg.id} failed: {msg.delivery_error}")

        await session.commit()
        return msg

    async def retry_message(
        self,
        session: AsyncSession,
        message_id: int,
        client=None,
    ) -> Message:
        """Retry delivery of a previously failed outbound message."""
        cli = client or signal_client

        result = await session.execute(select(Message).where(Message.id == message_id))
        msg = result.scalar_one_or_none()
        if not msg:
            raise ValueError(f"Message {message_id} not found")

        if msg.delivery_status != MessageDeliveryStatus.failed.value:
            raise ValueError(
                f"Message {message_id} is not in failed status (current: {msg.delivery_status})"
            )

        # Resolve recipient
        conv = await session.get(Conversation, msg.conversation_id)
        if not conv:
            raise ValueError(f"Conversation {msg.conversation_id} not found")

        recipient = conv.group_id if (conv.type == "group" or conv.group_id) else conv.signal_id
        if conv.type == "group" and not recipient.startswith("group."):
            recipient = f"group.{recipient}"

        msg.delivery_status = MessageDeliveryStatus.pending.value
        msg.delivery_error = None
        await session.flush()

        success = False
        err_msg: str | None = None
        try:
            success = await cli.send_message(
                text=msg.content,
                recipients=[recipient],
            )
            if not success:
                err_msg = "Gateway returned failure status"
        except Exception as e:
            logger.error(f"❌ Error retrying message {msg.id}: {e}", exc_info=True)
            err_msg = str(e)
            success = False

        if success:
            msg.delivery_status = MessageDeliveryStatus.sent.value
            msg.delivery_error = None
            msg.occurred_at = datetime.utcnow()
        else:
            msg.delivery_status = MessageDeliveryStatus.failed.value
            msg.delivery_error = (err_msg or "Unknown delivery error")[:500]

        await session.commit()
        return msg


outbound_service = OutboundMessageService()
