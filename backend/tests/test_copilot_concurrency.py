"""
Concurrency regression tests for Copilot suggestion claim and state machine.

Verifies:
- test_double_accept_sends_exactly_once
- test_accept_and_edit_race_sends_exactly_once
- test_reject_and_accept_race_has_single_terminal_state
- test_accept_failed_delivery_not_marked_successful
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.main import app
from app.models.ai import AISuggestion, AISuggestionStatus
from app.models.conversation import Conversation, ConversationType
from app.services.signal_client import signal_client


@pytest.fixture
async def conc_db(tmp_path):
    """File-backed SQLite database to enable real concurrent connections."""
    db_file = tmp_path / "conc_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from app.api.deps import get_current_admin
    from app.database import get_session
    from app.schemas.auth import AdminUser

    app.dependency_overrides[get_current_admin] = lambda: AdminUser(username="admin")

    async def _get_test_session():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _get_test_session

    yield maker

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_double_accept_sends_exactly_once(conc_db):
    """Concurrent accept requests on the same suggestion must only deliver once."""
    async with conc_db() as session:
        conv = Conversation(
            type=ConversationType.dm.value,
            signal_id="+420111222333",
            mode="copilot",
        )
        session.add(conv)
        await session.flush()

        sug = AISuggestion(
            conversation_id=conv.id,
            suggested_text="Special discount available for you today!",
            status=AISuggestionStatus.pending.value,
        )
        session.add(sug)
        await session.commit()
        conv_id = conv.id
        sug_id = sug.id

    send_mock = AsyncMock(return_value={"timestamp": 1234567890})
    with patch.object(signal_client, "send_message", send_mock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res1, res2 = await asyncio.gather(
                client.post(
                    f"/api/conversations/{conv_id}/suggestion/accept?suggestion_id={sug_id}"
                ),
                client.post(
                    f"/api/conversations/{conv_id}/suggestion/accept?suggestion_id={sug_id}"
                ),
            )

        status_codes = [res1.status_code, res2.status_code]
        assert 200 in status_codes, f"At least one request must succeed: {status_codes}"
        assert 409 in status_codes, (
            f"The losing concurrent request must receive 409 Conflict: {status_codes}"
        )
        assert send_mock.call_count == 1

    async with conc_db() as session:
        sug_db = (
            await session.execute(select(AISuggestion).where(AISuggestion.id == sug_id))
        ).scalar_one()
        assert sug_db.status == AISuggestionStatus.accepted.value


@pytest.mark.asyncio
async def test_accept_and_edit_race_sends_exactly_once(conc_db):
    """Concurrent accept vs edit_and_send must only allow the first winner to send."""
    async with conc_db() as session:
        conv = Conversation(
            type=ConversationType.dm.value,
            signal_id="+420222333444",
            mode="copilot",
        )
        session.add(conv)
        await session.flush()

        sug = AISuggestion(
            conversation_id=conv.id,
            suggested_text="Original draft response",
            status=AISuggestionStatus.pending.value,
        )
        session.add(sug)
        await session.commit()
        conv_id = conv.id
        sug_id = sug.id

    send_mock = AsyncMock(return_value={"timestamp": 1234567891})
    with patch.object(signal_client, "send_message", send_mock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res_accept, res_edit = await asyncio.gather(
                client.post(
                    f"/api/conversations/{conv_id}/suggestion/accept?suggestion_id={sug_id}"
                ),
                client.post(
                    f"/api/conversations/{conv_id}/suggestion/edit?suggestion_id={sug_id}",
                    json={"edited_text": "Manually edited response"},
                ),
            )

        codes = [res_accept.status_code, res_edit.status_code]
        assert 200 in codes, f"One must succeed: {codes}"
        assert 409 in codes, f"One must receive 409 conflict: {codes}"
        assert send_mock.call_count == 1


@pytest.mark.asyncio
async def test_reject_and_accept_race_has_single_terminal_state(conc_db):
    """Concurrent reject vs accept must result in exactly one terminal outcome without duplicate execution."""
    async with conc_db() as session:
        conv = Conversation(
            type=ConversationType.dm.value,
            signal_id="+420333444555",
            mode="copilot",
        )
        session.add(conv)
        await session.flush()

        sug = AISuggestion(
            conversation_id=conv.id,
            suggested_text="Pending suggestion for reject test",
            status=AISuggestionStatus.pending.value,
        )
        session.add(sug)
        await session.commit()
        conv_id = conv.id
        sug_id = sug.id

    send_mock = AsyncMock(return_value={"timestamp": 1234567892})
    with patch.object(signal_client, "send_message", send_mock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res_rej, res_acc = await asyncio.gather(
                client.post(
                    f"/api/conversations/{conv_id}/suggestion/reject?suggestion_id={sug_id}"
                ),
                client.post(
                    f"/api/conversations/{conv_id}/suggestion/accept?suggestion_id={sug_id}"
                ),
            )

    async with conc_db() as session:
        sug_db = (
            await session.execute(select(AISuggestion).where(AISuggestion.id == sug_id))
        ).scalar_one()

        assert sug_db.status in (
            AISuggestionStatus.rejected.value,
            AISuggestionStatus.accepted.value,
        )
        if sug_db.status == AISuggestionStatus.rejected.value:
            assert send_mock.call_count == 0
        else:
            assert send_mock.call_count == 1


@pytest.mark.asyncio
async def test_accept_failed_delivery_not_marked_successful(conc_db):
    """If Signal network send fails, suggestion status must transition to send_failed, not accepted."""
    async with conc_db() as session:
        conv = Conversation(
            type=ConversationType.dm.value,
            signal_id="+420444555666",
            mode="copilot",
        )
        session.add(conv)
        await session.flush()

        sug = AISuggestion(
            conversation_id=conv.id,
            suggested_text="Suggestion with network failure",
            status=AISuggestionStatus.pending.value,
        )
        session.add(sug)
        await session.commit()
        conv_id = conv.id
        sug_id = sug.id

    send_mock = AsyncMock(side_effect=RuntimeError("Signal daemon timeout"))
    with patch.object(signal_client, "send_message", send_mock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/conversations/{conv_id}/suggestion/accept?suggestion_id={sug_id}",
            )
        assert resp.status_code == 502

    async with conc_db() as session:
        sug_db = (
            await session.execute(select(AISuggestion).where(AISuggestion.id == sug_id))
        ).scalar_one()
        assert sug_db.status == AISuggestionStatus.send_failed.value
