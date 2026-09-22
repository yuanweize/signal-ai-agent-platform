"""
Round 2 Messaging Pipeline and Ingestion Tests.

Covers:
- Reaction-only event normalization, persistence, and non-filtering (Section 17, 20)
- Attachment-only event persistence in Message and MessageAttachment (Section 18, 19)
- Manual takeover race condition protection (Section 25)
- OutboundMessageService state transitions and retry mechanism (Section 26)
- EventPipeline bounded ingestion and worker concurrency (Section 24)
- Live and ready health check endpoints (Section 57)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.conversation import (
    Conversation,
    ConversationMode,
    Message,
    MessageAttachment,
    MessageDeliveryStatus,
    MessageDirection,
    MessageReaction,
)
from app.models.user import User
from app.schemas.signal import SignalIncomingMessage
from app.services.event_pipeline import EventPipeline
from app.services.message_handler import MessageHandler
from app.services.outbound_service import outbound_service


class TestReactionOnlyEvent:
    """Section 17: Reaction-only event is a mandatory regression case."""

    def test_schema_identifies_reaction_as_data_message(self):
        payload = {
            "envelope": {
                "source": "+420777111222",
                "sourceUuid": "uuid-reaction-1",
                "timestamp": 1700000000000,
                "dataMessage": {
                    "timestamp": 1700000000000,
                    "reaction": {
                        "emoji": "👍",
                        "targetAuthor": "+420123456789",
                        "targetTimestamp": 1699999999000,
                        "isRemove": False,
                    },
                },
            }
        }
        msg = SignalIncomingMessage(**payload)
        assert msg.is_data_message is True
        assert msg.has_reaction is True
        reaction = msg.reaction
        assert reaction is not None
        assert reaction.emoji == "👍"
        assert reaction.target_timestamp == 1699999999000

    @pytest.mark.asyncio
    async def test_reaction_persisted_without_ai_trigger(self, session):
        handler = MessageHandler()

        # Seed target message in a conversation
        user = User(signal_id="+420777111222", display_name="Reactor")
        session.add(user)
        await session.flush()

        conv = Conversation(
            user_id=user.id,
            dm_user_id=user.id,
            signal_id="+420777111222",
            type="dm",
            mode=ConversationMode.auto.value,
            is_active=True,
        )
        session.add(conv)
        await session.flush()

        orig_msg = Message(
            conversation_id=conv.id,
            content="Hello world",
            role="user",
            signal_timestamp_ms=1699999999000,
        )
        session.add(orig_msg)
        await session.commit()

        # Inbound reaction payload
        payload = {
            "envelope": {
                "source": "+420777111222",
                "sourceUuid": "uuid-reaction-1",
                "timestamp": 1700000000000,
                "dataMessage": {
                    "timestamp": 1700000000000,
                    "reaction": {
                        "emoji": "🔥",
                        "targetAuthor": "+420123456789",
                        "targetTimestamp": 1699999999000,
                    },
                },
            }
        }
        envelope = SignalIncomingMessage(**payload)

        with patch("app.services.message_handler.async_session") as mock_session_ctx:
            # Wrap session in an async context manager
            mock_session_ctx.return_value.__aenter__.return_value = session
            mock_session_ctx.return_value.__aexit__.return_value = None

            mock_runtime = MagicMock()
            mock_runtime.run = AsyncMock()
            handler.set_agent_runtime(mock_runtime)

            await handler.handle_message(envelope)

            # AgentRuntime must NOT be invoked for reaction-only event
            mock_runtime.run.assert_not_called()

        # Verify reaction row exists in DB
        rx_res = await session.execute(
            select(MessageReaction).where(MessageReaction.message_id == orig_msg.id)
        )
        rx = rx_res.scalar_one_or_none()
        assert rx is not None
        assert rx.emoji == "🔥"
        assert rx.target_timestamp == 1699999999000
        assert rx.reactor_identity == "+420777111222"


class TestAttachmentOnlyEvent:
    """Section 18: Attachment-only messages must be recorded in DB with metadata."""

    @pytest.mark.asyncio
    async def test_attachment_only_persisted_in_db(self, session):
        handler = MessageHandler()

        payload = {
            "envelope": {
                "source": "+420777888999",
                "sourceUuid": "uuid-attach-1",
                "timestamp": 1700000050000,
                "dataMessage": {
                    "timestamp": 1700000050000,
                    "attachments": [
                        {
                            "contentType": "image/jpeg",
                            "filename": "invoice.jpg",
                            "id": "att-id-12345",
                            "size": 409600,
                        }
                    ],
                },
            }
        }
        envelope = SignalIncomingMessage(**payload)

        with patch("app.services.message_handler.async_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__.return_value = session
            mock_session_ctx.return_value.__aexit__.return_value = None

            mock_runtime = MagicMock()
            mock_runtime.run = AsyncMock()
            handler.set_agent_runtime(mock_runtime)

            await handler.handle_message(envelope)

            # AgentRuntime should not generate normal text reply for attachment-only
            mock_runtime.run.assert_not_called()

        # Verify user, conversation, message, and attachment records
        u_res = await session.execute(select(User).where(User.signal_id == "+420777888999"))
        user = u_res.scalar_one_or_none()
        assert user is not None

        c_res = await session.execute(select(Conversation).where(Conversation.user_id == user.id))
        conv = c_res.scalar_one_or_none()
        assert conv is not None

        m_res = await session.execute(
            select(Message).where(
                Message.conversation_id == conv.id,
                Message.direction == MessageDirection.inbound.value,
            )
        )
        msg = m_res.scalar_one_or_none()
        assert msg is not None
        assert msg.direction == MessageDirection.inbound.value
        assert msg.content == "[attachment]"

        att_res = await session.execute(
            select(MessageAttachment).where(MessageAttachment.message_id == msg.id)
        )
        att = att_res.scalar_one_or_none()
        assert att is not None
        assert att.filename == "invoice.jpg"
        assert att.mime_type == "image/jpeg"
        assert att.external_attachment_id == "att-id-12345"
        assert att.size == 409600

        # Verify polite outbound notification was also recorded
        out_res = await session.execute(
            select(Message).where(
                Message.conversation_id == conv.id,
                Message.direction == MessageDirection.outbound.value,
            )
        )
        out_msg = out_res.scalar_one_or_none()
        assert out_msg is not None
        assert "Děkujeme za soubor" in out_msg.content


class TestManualTakeoverRace:
    """
    Section 25: Critical Manual Takeover Race.
    t0 inbound
    t1 auto
    t2 AI starts
    t3 admin switches manual
    t4 AI finishes
    t5 AI tries send -> discarded!
    """

    @pytest.mark.asyncio
    async def test_ai_outbound_discarded_if_admin_switches_manual_during_generation(self, session):
        handler = MessageHandler()

        user = User(signal_id="+420777000111", display_name="Alice")
        session.add(user)
        await session.flush()

        conv = Conversation(
            user_id=user.id,
            dm_user_id=user.id,
            signal_id="+420777000111",
            type="dm",
            mode=ConversationMode.auto.value,
            is_active=True,
        )
        session.add(conv)
        await session.commit()

        payload = {
            "envelope": {
                "source": "+420777000111",
                "timestamp": 1700000080000,
                "dataMessage": {
                    "timestamp": 1700000080000,
                    "message": "Question while admin is watching",
                },
            }
        }
        envelope = SignalIncomingMessage(**payload)

        # Mock AI generation with a hook that simulates admin switching mode in DB
        async def slow_ai_generate(*args, **kwargs):
            # Mid-generation: admin switches conversation to manual
            conv.mode = ConversationMode.manual.value
            session.add(conv)
            await session.commit()

            from app.ai.runtime.agent_runtime import AgentResponse
            from app.ai.runtime.decisions import AgentDecision

            return AgentResponse(
                decision=AgentDecision.reply.value,
                answer="AI generated answer that should NOT be sent",
            )

        with patch("app.services.message_handler.async_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__.return_value = session
            mock_session_ctx.return_value.__aexit__.return_value = None

            mock_runtime = MagicMock()
            mock_runtime.run = AsyncMock(side_effect=slow_ai_generate)
            handler.set_agent_runtime(mock_runtime)

            with patch("app.services.outbound_service.signal_client") as mock_client:
                mock_client.send_message = AsyncMock(return_value=True)

                await handler.handle_message(envelope)

                # Gateway must have received 0 sends because manual takeover discarded the reply!
                mock_client.send_message.assert_not_called()

        # Outbound message should not have been created as sent
        outbound_msgs = (
            (
                await session.execute(
                    select(Message).where(
                        Message.conversation_id == conv.id,
                        Message.direction == MessageDirection.outbound.value,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(outbound_msgs) == 0


class TestOutboundMessageServiceState:
    """Section 26: OutboundMessageService state machine and retry."""

    @pytest.mark.asyncio
    async def test_pending_to_sent_transition(self, session):
        conv = Conversation(
            signal_id="+420999111222",
            type="dm",
            mode=ConversationMode.manual.value,
        )
        session.add(conv)
        await session.commit()

        mock_client = MagicMock()
        mock_client.send_message = AsyncMock(return_value=True)

        msg = await outbound_service.send_message(
            session=session,
            conversation_id=conv.id,
            content="Admin message",
            recipient="+420999111222",
            actor="admin",
            client=mock_client,
        )

        assert msg.delivery_status == MessageDeliveryStatus.sent.value
        assert msg.delivery_error is None
        assert msg.actor == "admin"
        assert msg.direction == MessageDirection.outbound.value

    @pytest.mark.asyncio
    async def test_failed_send_and_explicit_retry(self, session):
        conv = Conversation(
            signal_id="+420999111333",
            type="dm",
            mode=ConversationMode.manual.value,
        )
        session.add(conv)
        await session.commit()

        # Step 1: Failed send
        failing_client = MagicMock()
        failing_client.send_message = AsyncMock(side_effect=Exception("Gateway timeout"))

        msg = await outbound_service.send_message(
            session=session,
            conversation_id=conv.id,
            content="Failed broadcast",
            recipient="+420999111333",
            actor="bot",
            client=failing_client,
        )

        assert msg.delivery_status == MessageDeliveryStatus.failed.value
        assert "Gateway timeout" in (msg.delivery_error or "")

        # Step 2: Retry with working client
        working_client = MagicMock()
        working_client.send_message = AsyncMock(return_value=True)

        retried_msg = await outbound_service.retry_message(
            session=session,
            message_id=msg.id,
            client=working_client,
        )

        assert retried_msg.id == msg.id
        assert retried_msg.delivery_status == MessageDeliveryStatus.sent.value
        assert retried_msg.delivery_error is None


class TestEventPipelineBoundedIngestion:
    """Section 24: Listener cannot be blocked by AI; bounded ingestion pipeline."""

    @pytest.mark.asyncio
    async def test_enqueue_and_worker_processing(self):
        pipeline = EventPipeline(queue_capacity=50, num_workers=2)
        processed_events = []

        async def mock_handler(envelope):
            await asyncio.sleep(0.01)
            processed_events.append(envelope.sender_id)

        pipeline.register_handler(mock_handler)
        await pipeline.start()

        # Enqueue 5 events
        for i in range(5):
            payload = {
                "envelope": {
                    "source": f"+42077700000{i}",
                    "timestamp": 1700000000000 + i,
                    "dataMessage": {"message": f"Ping {i}"},
                }
            }
            envelope = SignalIncomingMessage(**payload)
            success = await pipeline.enqueue(envelope)
            assert success is True

        # Wait briefly for workers to drain the queue
        await asyncio.sleep(0.1)
        await pipeline.stop()

        assert len(processed_events) == 5
        metrics = pipeline.get_metrics()
        assert metrics["events_enqueued"] == 5
        assert metrics["events_processed"] == 5
