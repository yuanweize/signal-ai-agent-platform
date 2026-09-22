"""
Integration tests: Message ingestion pipeline.

Tests the full pipeline through MessageHandler against an in-memory DB:
- DM: user created exactly once, conversation exactly once, message exactly once
- Block policy: blocked user triggers no AI reply
- Dedup: same signal_event_id is rejected on second call
- Group attribution: group messages are NOT attributed to a single user
- Manual takeover: AI suppressed when mode == 'manual'
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.conversation import Conversation, ConversationMode, Message
from app.models.user import User
from app.schemas.signal import SignalIncomingMessage


def _make_incoming(
    sender_number: str,
    text: str,
    sender_name: str = "Test User",
    group_id: str | None = None,
    timestamp: int = 1700000000000,
) -> SignalIncomingMessage:
    data_message = {
        "timestamp": timestamp,
        "message": text,
    }
    if group_id:
        data_message["groupInfo"] = {"groupId": group_id, "type": "DELIVER"}

    return SignalIncomingMessage.model_validate(
        {
            "envelope": {
                "sourceNumber": sender_number,
                "sourceName": sender_name,
                "sourceDevice": 1,
                "timestamp": timestamp,
                "dataMessage": data_message,
            },
            "account": "+420000000000",
        }
    )


@pytest.fixture
def mock_signal_client():
    with patch("app.services.message_handler.signal_client") as mock:
        mock.send_reply = AsyncMock(return_value=True)
        mock.send_read_receipt = AsyncMock(return_value=True)
        mock.show_typing = AsyncMock(return_value=True)
        mock.hide_typing = AsyncMock(return_value=True)
        yield mock


@pytest.fixture
def mock_async_session(session):
    """Patch async_session in message_handler to use test session."""
    import contextlib

    @contextlib.asynccontextmanager
    async def fake_session():
        yield session

    with patch("app.services.message_handler.async_session", fake_session):
        yield session


class TestDMPipeline:
    async def test_new_user_created_exactly_once(
        self, mock_async_session, mock_signal_client, session
    ):
        from app.services.message_handler import MessageHandler

        handler = MessageHandler()

        incoming = _make_incoming("+420111000001", "hello", timestamp=1700000001000)
        await handler.handle(incoming)

        result = await session.execute(select(User).where(User.signal_id == "+420111000001"))
        users = result.scalars().all()
        assert len(users) == 1
        assert users[0].display_name == "Test User"

    async def test_conversation_created_exactly_once(
        self, mock_async_session, mock_signal_client, session
    ):
        from app.services.message_handler import MessageHandler

        handler = MessageHandler()

        for ts in [1700000002000, 1700000003000]:
            incoming = _make_incoming("+420111000002", "msg", timestamp=ts)
            await handler.handle(incoming)

        result = await session.execute(
            select(Conversation).where(Conversation.signal_id == "+420111000002")
        )
        convs = result.scalars().all()
        assert len(convs) == 1

    async def test_inbound_message_stored(self, mock_async_session, mock_signal_client, session):
        from app.services.message_handler import MessageHandler

        handler = MessageHandler()

        incoming = _make_incoming("+420111000003", "test message", timestamp=1700000004000)
        await handler.handle(incoming)

        result = await session.execute(select(Message).where(Message.sender_id == "+420111000003"))
        msgs = result.scalars().all()
        assert len(msgs) == 1
        assert msgs[0].content == "test message"
        assert msgs[0].role == "user"
        assert msgs[0].signal_event_id == "+420111000003:1700000004000"


class TestBlockPolicy:
    async def test_blocked_user_no_ai_reply(self, mock_async_session, mock_signal_client, session):
        from app.models.user import User
        from app.services.message_handler import MessageHandler

        # Create blocked user
        user = User(signal_id="+420111000010", display_name="Blocked", is_blocked=True)
        session.add(user)
        await session.commit()

        mock_runtime = MagicMock()
        mock_runtime.run = AsyncMock()
        handler = MessageHandler()
        handler.set_agent_runtime(mock_runtime)

        incoming = _make_incoming("+420111000010", "hello blocked", timestamp=1700000010000)
        await handler.handle(incoming)

        # AgentRuntime should NOT have been called
        mock_runtime.run.assert_not_called()
        mock_signal_client.send_reply.assert_not_called()

    async def test_blocked_user_message_still_recorded(
        self, mock_async_session, mock_signal_client, session
    ):
        from app.models.user import User
        from app.services.message_handler import MessageHandler

        user = User(signal_id="+420111000011", display_name="Blocked2", is_blocked=True)
        session.add(user)
        await session.commit()

        handler = MessageHandler()
        incoming = _make_incoming("+420111000011", "blocked msg", timestamp=1700000011000)
        await handler.handle(incoming)

        result = await session.execute(select(Message).where(Message.sender_id == "+420111000011"))
        msgs = result.scalars().all()
        assert len(msgs) == 1
        assert msgs[0].content == "blocked msg"


class TestDeduplication:
    async def test_duplicate_signal_event_rejected(
        self, mock_async_session, mock_signal_client, session
    ):
        from app.services.message_handler import MessageHandler

        handler = MessageHandler()

        # Same timestamp = same signal_event_id
        incoming = _make_incoming("+420111000020", "dup msg", timestamp=1700000020000)
        await handler.handle(incoming)
        await handler.handle(incoming)  # replay

        result = await session.execute(select(Message).where(Message.sender_id == "+420111000020"))
        msgs = result.scalars().all()
        # Must be exactly 1, not 2
        assert len(msgs) == 1


class TestGroupAttribution:
    async def test_group_conversation_not_attributed_to_single_user(
        self, mock_async_session, mock_signal_client, session
    ):
        from app.services.message_handler import MessageHandler

        handler = MessageHandler()

        # Alice sends to group
        alice_msg = _make_incoming(
            "+420111000030",
            "alice msg",
            sender_name="Alice",
            group_id="grp-test-001",
            timestamp=1700000030000,
        )
        # Bob sends to same group
        bob_msg = _make_incoming(
            "+420111000031",
            "bob msg",
            sender_name="Bob",
            group_id="grp-test-001",
            timestamp=1700000031000,
        )

        await handler.handle(alice_msg)
        await handler.handle(bob_msg)

        result = await session.execute(
            select(Conversation).where(Conversation.group_id == "grp-test-001")
        )
        convs = result.scalars().all()
        # Exactly one group conversation
        assert len(convs) == 1
        # user_id is None for group conversations (P0-5 fix)
        assert convs[0].user_id is None

        # Only user messages — sender attribution is correct
        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == convs[0].id)
            .where(Message.role == "user")
            .order_by(Message.timestamp)
        )
        user_msgs = result.scalars().all()
        assert len(user_msgs) == 2
        assert user_msgs[0].sender_id == "+420111000030"  # Alice
        assert user_msgs[1].sender_id == "+420111000031"  # Bob
        # Sender names captured
        assert user_msgs[0].sender_name == "Alice"
        assert user_msgs[1].sender_name == "Bob"


class TestManualTakeover:
    async def test_ai_suppressed_in_manual_mode(
        self, mock_async_session, mock_signal_client, session
    ):
        from app.models.user import User
        from app.services.message_handler import MessageHandler

        # Create user + conversation in manual mode
        user = User(signal_id="+420111000040", display_name="ManualUser")
        session.add(user)
        await session.flush()
        conv = Conversation(
            user_id=user.id,
            signal_id="+420111000040",
            group_id=None,
            mode=ConversationMode.manual.value,
            is_active=True,
        )
        session.add(conv)
        await session.commit()

        mock_runtime = MagicMock()
        mock_runtime.run = AsyncMock()
        handler = MessageHandler()
        handler.set_agent_runtime(mock_runtime)

        incoming = _make_incoming("+420111000040", "any message", timestamp=1700000040000)
        await handler.handle(incoming)

        # AgentRuntime must NOT have been called
        mock_runtime.run.assert_not_called()
        # No outbound send should have happened
        mock_signal_client.send_reply.assert_not_called()
