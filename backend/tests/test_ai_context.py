"""
Unit tests: AI context builder.

Verifies:
- Current user message appears exactly once (P0-1)
- Group sender names appear in context (P1-14)
- Messages are excluded by signal_timestamp_ms (dedup exclusion)
- System prompt loaded correctly
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.conversation import Conversation, ConversationMode, Message
from app.models.user import User
from app.services.ai_engine import AIEngine


@pytest.fixture
def ai_engine():
    engine = AIEngine()
    engine._enabled = True
    engine._client = MagicMock()
    engine._runtime_api_key = "test-key"
    engine._runtime_base_url = "http://localhost/v1"
    engine._runtime_effective_base_url = "http://localhost/v1"
    engine._runtime_model_aliases = {}
    return engine


async def _make_conversation(session, *, user_id=None, group_id=None) -> Conversation:
    conv = Conversation(
        user_id=user_id,
        signal_id="test",
        group_id=group_id,
        mode=ConversationMode.auto.value,
        is_active=True,
    )
    session.add(conv)
    await session.flush()
    return conv


async def _add_message(session, conv_id, role, content, sender_name=None, ts_ms=None):
    from datetime import datetime

    msg = Message(
        conversation_id=conv_id,
        role=role,
        content=content,
        sender_name=sender_name,
        signal_timestamp_ms=ts_ms,
        timestamp=datetime.fromtimestamp((ts_ms or 1700000000000) / 1000),
    )
    session.add(msg)
    await session.flush()
    return msg


class TestCurrentMessageNotDuplicated:
    """P0-1: current user message must appear exactly once in the prompt."""

    async def test_current_message_once(self, session, ai_engine):
        conv = await _make_conversation(session, user_id=None, group_id=None)

        # Add a history message
        await _add_message(session, conv.id, "user", "previous message", ts_ms=1700000000000)
        # Add the CURRENT message (already committed, like the real pipeline does)
        await _add_message(session, conv.id, "user", "current message", ts_ms=1700000001000)
        await session.commit()

        with patch.object(ai_engine, "_get_system_prompt", AsyncMock(return_value="sys")):
            with patch.object(ai_engine, "_build_catalog_context", AsyncMock(return_value=None)):
                with patch.object(
                    ai_engine,
                    "_refresh_runtime_client",
                    AsyncMock(
                        return_value={
                            "is_ai_enabled": True,
                            "ai_api_key": "key",
                            "ai_api_base_url": "http://localhost/v1",
                            "ai_model": "gpt-4",
                            "ai_temperature": 0.7,
                            "ai_max_tokens": 1000,
                            "ai_context_messages": 20,
                            "is_market_enabled": False,
                        }
                    ),
                ):
                    messages = await ai_engine._build_messages(
                        session,
                        conv,
                        "current message",
                        group_id=None,
                        runtime={"ai_context_messages": 20, "is_market_enabled": False},
                        sender_name=None,
                        current_signal_timestamp_ms=1700000001000,  # exclude this from history
                    )

        # Count occurrences of "current message"
        count = sum(1 for m in messages if m.get("content") == "current message")
        assert count == 1, (
            f"Expected 'current message' exactly once, got {count}. Messages: {messages}"
        )


class TestGroupSenderIdentity:
    """P1-14: group messages must include sender name in context."""

    async def test_group_history_includes_sender_name(self, session, ai_engine):
        conv = await _make_conversation(session, user_id=None, group_id="grp-001")

        await _add_message(
            session, conv.id, "user", "Alice's message", sender_name="Alice", ts_ms=1700000000000
        )
        await _add_message(
            session, conv.id, "user", "Bob's message", sender_name="Bob", ts_ms=1700000001000
        )
        await session.commit()

        with patch.object(ai_engine, "_get_system_prompt", AsyncMock(return_value="sys")):
            with patch.object(ai_engine, "_build_catalog_context", AsyncMock(return_value=None)):
                messages = await ai_engine._build_messages(
                    session,
                    conv,
                    "Carol's new message",
                    group_id="grp-001",
                    runtime={"ai_context_messages": 20, "is_market_enabled": False},
                    sender_name="Carol",
                    current_signal_timestamp_ms=1700000002000,
                )

        user_messages = [m for m in messages if m["role"] == "user"]
        # History messages should have sender prefix
        alice_msg = next((m for m in user_messages if "Alice" in m["content"]), None)
        bob_msg = next((m for m in user_messages if "Bob" in m["content"]), None)
        carol_msg = next((m for m in user_messages if "Carol" in m["content"]), None)

        assert alice_msg is not None, "Alice's message not found"
        assert "[Alice]:" in alice_msg["content"]
        assert bob_msg is not None, "Bob's message not found"
        assert "[Bob]:" in bob_msg["content"]
        assert carol_msg is not None, "Carol's current message not found"
        assert "[Carol]:" in carol_msg["content"]


class TestOutboundStatusMachine:
    """P0-2: outbound messages go pending → sent or pending → failed."""

    async def test_sent_status_on_success(self, session):
        from unittest.mock import AsyncMock, patch

        from app.services.message_handler import MessageHandler

        user = User(signal_id="+420111000050", display_name="SendTest")
        session.add(user)
        await session.flush()
        conv = Conversation(
            user_id=user.id,
            signal_id="+420111000050",
            group_id=None,
            mode=ConversationMode.auto.value,
            is_active=True,
        )
        session.add(conv)
        await session.commit()

        with patch("app.services.message_handler.signal_client") as mock_client:
            mock_client.send_reply = AsyncMock(return_value=True)
            handler = MessageHandler()
            await handler._send_outbound_reply(session, conv, "hello back", "+420111000050")

        result = await session.execute(
            select(Message).where(
                Message.conversation_id == conv.id,
                Message.role == "assistant",
            )
        )
        msg = result.scalar_one_or_none()
        assert msg is not None
        assert msg.delivery_status == "sent"

    async def test_failed_status_on_gateway_error(self, session):
        from unittest.mock import AsyncMock, patch

        from app.services.message_handler import MessageHandler

        user = User(signal_id="+420111000051", display_name="FailTest")
        session.add(user)
        await session.flush()
        conv = Conversation(
            user_id=user.id,
            signal_id="+420111000051",
            group_id=None,
            mode=ConversationMode.auto.value,
            is_active=True,
        )
        session.add(conv)
        await session.commit()

        with patch("app.services.message_handler.signal_client") as mock_client:
            mock_client.send_reply = AsyncMock(return_value=False)  # gateway fails
            handler = MessageHandler()
            await handler._send_outbound_reply(session, conv, "hello back", "+420111000051")

        result = await session.execute(
            select(Message).where(
                Message.conversation_id == conv.id,
                Message.role == "assistant",
            )
        )
        msg = result.scalar_one_or_none()
        assert msg is not None
        assert msg.delivery_status == "failed"
        assert msg.delivery_error == "gateway_send_failed"
