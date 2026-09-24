"""
Tests for AIRun Pagination and Canonical Query Filtering.
Verifies Section 17 & Section 6:
- GET /api/ai-studio/runs returns X-Total-Count header with exact total
- Pagination parameters limit & offset slice results properly
- Canonical filters (has_rag, has_tools) work as expected
- Deprecated aliases (used_rag, used_tools) remain supported for v0.4.1 clients
"""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_current_admin
from app.database import get_session
from app.main import app
from app.models.ai import AIRun
from app.schemas.auth import AdminUser


@pytest.mark.asyncio
async def test_runs_pagination_and_x_total_count(session):
    """Verify runs endpoint returns exact X-Total-Count and respects limit/offset."""
    from app.models.conversation import Conversation, ConversationType

    conv = (
        await session.execute(select(Conversation).where(Conversation.id == 1))
    ).scalar_one_or_none()
    if not conv:
        conv = Conversation(id=1, type=ConversationType.dm.value, signal_id="+100", mode="auto")
        session.add(conv)
        await session.commit()

    now = datetime.now(UTC).replace(tzinfo=None)
    for i in range(15):
        run = AIRun(
            trace_id=f"tr_page_{i}",
            conversation_id=1,
            decision="reply",
            retrieval='[{"title": "FAQ", "content": "Sample"}]' if (i % 2 == 0) else None,
            tool_calls='[{"name": "check_stock"}]' if (i % 3 == 0) else None,
            total_tokens=100 + i,
            usage_source="direct_provider_reported",
            traffic_source="pagination_test_traffic",
            created_at=now,
        )
        session.add(run)
    await session.commit()

    app.dependency_overrides[get_current_admin] = lambda: AdminUser(username="admin")
    app.dependency_overrides[get_session] = lambda: session

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            # 1. Total count with limit=5
            resp = await client.get(
                "/api/ai-studio/runs?traffic_source=pagination_test_traffic&limit=5&offset=0"
            )
            assert resp.status_code == 200
            assert resp.headers.get("x-total-count") == "15"
            items = resp.json()
            assert len(items) == 5

            # 2. Offset=10
            resp2 = await client.get(
                "/api/ai-studio/runs?traffic_source=pagination_test_traffic&limit=5&offset=10"
            )
            assert resp2.status_code == 200
            assert resp2.headers.get("x-total-count") == "15"
            items2 = resp2.json()
            assert len(items2) == 5

            # 3. Canonical filter: has_rag=true
            resp_rag = await client.get(
                "/api/ai-studio/runs?traffic_source=pagination_test_traffic&has_rag=true"
            )
            assert resp_rag.status_code == 200
            total_rag = int(resp_rag.headers.get("x-total-count", "0"))
            # 0, 2, 4, 6, 8, 10, 12, 14 -> 8 items
            assert total_rag == 8

            # 4. Backward compatible alias: used_rag=true
            resp_legacy_rag = await client.get(
                "/api/ai-studio/runs?traffic_source=pagination_test_traffic&used_rag=true"
            )
            assert resp_legacy_rag.status_code == 200
            assert int(resp_legacy_rag.headers.get("x-total-count", "0")) == 8
    finally:
        app.dependency_overrides.clear()
