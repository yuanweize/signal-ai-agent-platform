"""
Regression tests for semantic role normalization and conversation context loading.

Validates:
- OutboundMessageService.send_message(actor="admin") produces semantic role="assistant".
- ContextLoader normalizes legacy rows (direction=outbound, actor=admin, role=user) to role="assistant".
- Group conversation messages preserve sender attribution (e.g. "Human Support (Bob): ...", "Alice: ...")
  while retaining strict OpenAI LLM roles (role="assistant", role="user").
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.ai.runtime.context_loader import ConversationContextLoader
from app.models.conversation import (
    Conversation,
    ConversationType,
    Message,
    MessageActor,
    MessageDeliveryStatus,
    MessageDirection,
    MessageOrigin,
)
from app.models.user import User
from app.services.outbound_service import OutboundMessageService
from app.services.signal_client import signal_client


@pytest.mark.asyncio
async def test_outbound_admin_message_stores_assistant_role_and_loads_correctly(session):
    """Production path: OutboundMessageService.send_message(actor=admin) -> stored Message -> ContextLoader -> role == assistant."""
    user = User(signal_id="+420111999888", display_name="Charlie")
    session.add(user)
    await session.flush()

    conv = Conversation(
        type=ConversationType.dm.value,
        dm_user_id=user.id,
        signal_id=user.signal_id,
        mode="manual",
    )
    session.add(conv)
    await session.commit()

    # 1. Customer inbound message
    inbound_msg = Message(
        conversation_id=conv.id,
        sender_user_id=user.id,
        content="Hello, is this product available?",
        direction=MessageDirection.inbound.value,
        actor=MessageActor.customer.value,
        role="user",
        origin=MessageOrigin.customer.value,
    )
    session.add(inbound_msg)
    await session.commit()

    # 2. OutboundMessageService dispatch by admin
    outbound_service = OutboundMessageService()
    send_mock = AsyncMock(return_value={"timestamp": 1234567800})
    with patch.object(signal_client, "send_message", send_mock):
        msg = await outbound_service.send_message(
            session=session,
            conversation_id=conv.id,
            content="Yes Charlie, we have 5 units in stock.",
            recipient=user.signal_id,
            actor="admin",
            admin_identity="Operator_Bob",
            origin="human_manual",
        )
        assert msg is not None
        assert msg.actor == "admin"
        assert msg.role == "assistant", f"Admin outbound role must be 'assistant', got {msg.role}"
        assert msg.admin_identity == "Operator_Bob"

    # 3. ContextLoader loads conversation
    loader = ConversationContextLoader()
    history = await loader.load_history(
        session=session,
        conversation_id=conv.id,
        max_messages=10,
        is_group=False,
    )

    assert len(history) == 2
    # Inbound message
    assert history[0]["role"] == "user"
    assert "Hello, is this product available?" in history[0]["content"]

    # Outbound admin message
    assert history[1]["role"] == "assistant"
    assert "Human Support:" in history[1]["content"]
    assert "5 units in stock" in history[1]["content"]


@pytest.mark.asyncio
async def test_legacy_admin_outbound_row_normalized_to_assistant(session):
    """Historical legacy rows stored with direction=outbound, actor=admin, but role=user must normalize to role=assistant."""
    conv = Conversation(
        type=ConversationType.dm.value,
        signal_id="+420333222111",
        mode="manual",
    )
    session.add(conv)
    await session.flush()

    # Legacy row with bad role='user'
    legacy_admin_msg = Message(
        conversation_id=conv.id,
        content="Here is your tracking link: https://track.me/123",
        direction=MessageDirection.outbound.value,
        actor=MessageActor.admin.value,
        role="user",  # Stale legacy value
        origin=MessageOrigin.human_manual.value,
        admin_identity="SupportLead",
        delivery_status=MessageDeliveryStatus.delivered.value,
    )
    session.add(legacy_admin_msg)
    await session.commit()

    loader = ConversationContextLoader()
    history = await loader.load_history(
        session=session,
        conversation_id=conv.id,
        max_messages=10,
        is_group=False,
    )

    assert len(history) == 1
    # Role must be normalized to assistant
    assert history[0]["role"] == "assistant"
    assert "Human Support:" in history[0]["content"]


@pytest.mark.asyncio
async def test_group_conversation_history_attribution_and_roles(session):
    """Group conversation preserves member and operator attribution while keeping standard LLM roles."""
    conv = Conversation(
        type=ConversationType.group.value,
        signal_id="group.test.123",
        group_id="group.test.123",
        mode="copilot",
    )
    session.add(conv)
    await session.flush()

    # Customer 1 message
    m1 = Message(
        conversation_id=conv.id,
        sender_id="Alice",
        sender_name="Alice",
        content="When does the auction start?",
        direction=MessageDirection.inbound.value,
        actor=MessageActor.customer.value,
        role="user",
        origin=MessageOrigin.customer.value,
    )
    # Admin message in group
    m2 = Message(
        conversation_id=conv.id,
        content="Auction starts at 18:00 CET.",
        direction=MessageDirection.outbound.value,
        actor=MessageActor.admin.value,
        role="assistant",
        origin=MessageOrigin.human_manual.value,
        admin_identity="AliceModerator",
        delivery_status=MessageDeliveryStatus.sent.value,
    )
    session.add_all([m1, m2])
    await session.commit()

    loader = ConversationContextLoader()
    history = await loader.load_history(
        session=session,
        conversation_id=conv.id,
        max_messages=10,
        is_group=True,
    )

    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert "Alice: When does the auction start?" in history[0]["content"]

    assert history[1]["role"] == "assistant"
    assert "Human Support (AliceModerator): Auction starts at 18:00 CET." in history[1]["content"]
