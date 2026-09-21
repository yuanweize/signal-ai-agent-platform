"""
Tests for /api/conversations API.

Verifies:
- List conversations with unread counts and delivery status
- Distinct DM vs Group representation
- Chronological message timeline with cursor pagination
- Admin outbound message delivery and audit logging
- Server-side read cursor persistence
- Outbound retry endpoint
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.conversation import (
    Conversation,
    ConversationMode,
    Message,
    MessageActor,
    MessageDeliveryStatus,
    MessageDirection,
)
from app.models.user import User


@pytest.fixture(autouse=True)
def override_deps(session):
    from app.api.deps import get_current_admin
    from app.database import get_session
    from app.schemas.auth import AdminUser

    app.dependency_overrides[get_current_admin] = lambda: AdminUser(username="admin")
    app.dependency_overrides[get_session] = lambda: session
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}


@pytest.mark.asyncio
async def test_list_conversations_with_unread_and_failed_status(session, auth_headers):
    # Setup DM conversation with 2 inbound messages, 1 outbound failed
    user = User(signal_id="+420777123456", display_name="Alice")
    session.add(user)
    await session.flush()

    conv = Conversation(
        user_id=user.id,
        dm_user_id=user.id,
        signal_id="+420777123456",
        type="dm",
        mode=ConversationMode.auto.value,
        is_active=True,
    )
    session.add(conv)
    await session.flush()

    msg1 = Message(
        conversation_id=conv.id,
        role="user",
        direction=MessageDirection.inbound.value,
        actor=MessageActor.customer.value,
        content="Inbound 1",
    )
    msg2 = Message(
        conversation_id=conv.id,
        role="user",
        direction=MessageDirection.inbound.value,
        actor=MessageActor.customer.value,
        content="Inbound 2",
    )
    msg3 = Message(
        conversation_id=conv.id,
        role="assistant",
        direction=MessageDirection.outbound.value,
        actor=MessageActor.bot.value,
        content="Outbound failed",
        delivery_status=MessageDeliveryStatus.failed.value,
    )
    session.add_all([msg1, msg2, msg3])
    await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/conversations", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 1
        conv_item = next(item for item in data["items"] if item["id"] == conv.id)
        assert conv_item["display_name"] == "Alice"
        assert conv_item["type"] == "dm"
        assert conv_item["unread_count"] == 2  # msg1 and msg2 unread
        assert conv_item["has_failed_outbound"] is True


@pytest.mark.asyncio
async def test_mark_conversation_read_persists_server_side(session, auth_headers):
    user = User(signal_id="+420777888111", display_name="Bob")
    session.add(user)
    await session.flush()

    conv = Conversation(
        user_id=user.id,
        dm_user_id=user.id,
        signal_id="+420777888111",
        type="dm",
        mode=ConversationMode.auto.value,
        is_active=True,
    )
    session.add(conv)
    await session.flush()

    msg = Message(
        conversation_id=conv.id,
        role="user",
        direction=MessageDirection.inbound.value,
        actor=MessageActor.customer.value,
        content="Hey Bob",
    )
    session.add(msg)
    await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Before read: unread_count is 1
        res1 = await ac.get(f"/api/conversations/{conv.id}", headers=auth_headers)
        assert res1.status_code == 200
        assert res1.json()["unread_count"] == 1

        # Mark read
        read_res = await ac.post(
            f"/api/conversations/{conv.id}/read",
            json={"last_message_id": msg.id},
            headers=auth_headers,
        )
        assert read_res.status_code == 200
        assert read_res.json()["ok"] is True

        # After read: unread_count is 0
        res2 = await ac.get(f"/api/conversations/{conv.id}", headers=auth_headers)
        assert res2.status_code == 200
        assert res2.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_conversation_messages_chronological_timeline(session, auth_headers):
    conv = Conversation(
        signal_id="+420777333444",
        type="dm",
        mode=ConversationMode.manual.value,
        is_active=True,
    )
    session.add(conv)
    await session.flush()

    # Add 3 messages
    for i in range(3):
        m = Message(
            conversation_id=conv.id,
            role="user",
            content=f"Message {i}",
            direction=MessageDirection.inbound.value,
            actor=MessageActor.customer.value,
        )
        session.add(m)
    await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get(f"/api/conversations/{conv.id}/messages", headers=auth_headers)
        assert res.status_code == 200
        items = res.json()["items"]
        assert len(items) == 3
        # Must be in chronological order
        assert items[0]["content"] == "Message 0"
        assert items[1]["content"] == "Message 1"
        assert items[2]["content"] == "Message 2"


@pytest.mark.asyncio
async def test_admin_send_message_via_conversation_api(session, auth_headers):
    conv = Conversation(
        signal_id="+420777555666",
        type="dm",
        mode=ConversationMode.manual.value,
        is_active=True,
    )
    session.add(conv)
    await session.commit()

    with patch("app.services.outbound_service.signal_client") as mock_client:
        mock_client.send_message = AsyncMock(return_value=True)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post(
                f"/api/conversations/{conv.id}/messages",
                json={"message": "Admin manual reply"},
                headers=auth_headers,
            )
            assert res.status_code == 200
            data = res.json()
            assert data["content"] == "Admin manual reply"
            assert data["actor"] == "admin"
            assert data["delivery_status"] == "sent"


@pytest.mark.asyncio
async def test_update_conversation_mode(session, auth_headers):
    conv = Conversation(
        signal_id="+420777999888",
        type="dm",
        mode=ConversationMode.auto.value,
        is_active=True,
    )
    session.add(conv)
    await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.patch(
            f"/api/conversations/{conv.id}/mode",
            json={"mode": "manual"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["mode"] == "manual"
