"""
Outbound Message Delivery Service.

Centralizes outbound message creation, state transitions (pending -> sent | failed),
delivery metadata, idempotency, and explicit retries across AI, admin manual takeover,
and campaign broadcasts.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

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
        origin: str | None = None,
        ai_run_id: int | None = None,
        ai_suggestion_id: int | None = None,
        admin_identity: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        client=None,
    ) -> Message:
        """
        Create a pending outbound message, attempt Signal send, and update status.
        """
        cli = client or signal_client

        # Default origin based on actor if not explicitly passed
        resolved_origin = origin
        if resolved_origin is None:
            if actor == MessageActor.bot.value:
                resolved_origin = "ai_auto"
            elif actor == MessageActor.admin.value:
                resolved_origin = "human_manual"
            elif actor == MessageActor.system.value:
                resolved_origin = "system"
            else:
                resolved_origin = "customer"

        # 1. Create message in pending status
        msg = Message(
            conversation_id=conversation_id,
            role="assistant"
            if actor in (MessageActor.bot.value, MessageActor.admin.value)
            else "system"
            if actor == MessageActor.system.value
            else "user",
            direction=MessageDirection.outbound.value,
            actor=actor,
            sender_id=sender_id,
            content=content,
            tokens_used=tokens_used,
            reply_to_id=reply_to_id,
            origin=resolved_origin,
            ai_run_id=ai_run_id,
            ai_suggestion_id=ai_suggestion_id,
            admin_identity=admin_identity,
            model=model,
            prompt_version=prompt_version,
            delivery_status=MessageDeliveryStatus.pending.value,
            delivery_error=None,
        )
        session.add(msg)
        await session.flush()

        # Update conversation message count and last_message_at
        conv = await session.get(Conversation, conversation_id)
        if conv:
            conv.message_count = (conv.message_count or 0) + 1
            conv.last_message_at = datetime.now(UTC).replace(tzinfo=None)

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
            msg.occurred_at = datetime.now(UTC).replace(tzinfo=None)
            logger.info(f"✅ Outbound message {msg.id} sent successfully to {recipient}")
        else:
            msg.delivery_status = MessageDeliveryStatus.failed.value
            msg.delivery_error = (err_msg or "Unknown delivery error")[:500]
            logger.warning(f"⚠️ Outbound message {msg.id} failed: {msg.delivery_error}")

        await session.commit()

        # Publish realtime events
        try:
            from app.realtime.broker import event_broker
            from app.realtime.events import RealtimeEvent, RealtimeEventType

            ev_type = (
                RealtimeEventType.MESSAGE_SENT if success else RealtimeEventType.MESSAGE_UPDATED
            )
            await event_broker.publish(
                RealtimeEvent(
                    type=ev_type,
                    conversation_id=conversation_id,
                    payload={
                        "message_id": msg.id,
                        "conversation_id": conversation_id,
                        "role": msg.role,
                        "content": msg.content,
                        "delivery_status": msg.delivery_status,
                        "actor": msg.actor,
                        "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    },
                )
            )
            if conv:
                await event_broker.publish(
                    RealtimeEvent(
                        type=RealtimeEventType.CONVERSATION_UPDATED,
                        conversation_id=conversation_id,
                        payload={
                            "conversation_id": conversation_id,
                            "last_message_at": conv.last_message_at.isoformat()
                            if conv.last_message_at
                            else None,
                            "message_count": conv.message_count,
                        },
                    )
                )
        except Exception as eb_err:
            logger.warning(f"Failed to publish realtime outbound event: {eb_err}")

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
            msg.occurred_at = datetime.now(UTC).replace(tzinfo=None)
        else:
            msg.delivery_status = MessageDeliveryStatus.failed.value
            msg.delivery_error = (err_msg or "Unknown delivery error")[:500]

        await session.commit()
        return msg


outbound_service = OutboundMessageService()
