"""
Tests for Groups API and GroupMember roster synchronization.

Verifies:
- Authoritative sync from Signal gateway into local Group & GroupMember records
- List group members with roles (admin/member)
- Local group state update on create, update, member changes, and quit
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.group import Group
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
async def test_sync_groups_from_gateway_upserts_roster(session, auth_headers):
    # Pre-seed a known User
    alice = User(signal_id="+420777991122", display_name="Alice Member")
    session.add(alice)
    await session.commit()

    gateway_data = [
        {
            "id": "group.test.123",
            "name": "Alpha Team",
            "description": "Project group",
            "members": ["+420777991122", "+420777993344"],
            "admins": ["+420777991122"],
            "is_blocked": False,
        }
    ]

    with patch("app.api.groups.signal_client") as mock_client:
        mock_client.list_groups = AsyncMock(return_value=gateway_data)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post("/api/groups/sync", headers=auth_headers)
            assert res.status_code == 200
            assert res.json()["synced"] == 1

            # Verify Group in DB
            list_res = await ac.get("/api/groups", headers=auth_headers)
            assert list_res.status_code == 200
            groups = list_res.json()
            assert len(groups) == 1
            assert groups[0]["group_id"] == "group.test.123"
            assert groups[0]["name"] == "Alpha Team"
            assert groups[0]["sync_status"] == "synced"
            assert groups[0]["members_count"] == 2
            assert groups[0]["admins_count"] == 1

            # Verify Members endpoint
            m_res = await ac.get("/api/groups/group.test.123/members", headers=auth_headers)
            assert m_res.status_code == 200
            members = m_res.json()
            assert len(members) == 2

            alice_m = next(m for m in members if m["external_identifier"] == "+420777991122")
            assert alice_m["is_admin"] is True
            assert alice_m["role"] == "admin"
            assert alice_m["display_name"] == "Alice Member"
            assert alice_m["user_id"] == alice.id

            other_m = next(m for m in members if m["external_identifier"] == "+420777993344")
            assert other_m["is_admin"] is False
            assert other_m["role"] == "member"


@pytest.mark.asyncio
async def test_add_and_remove_members_updates_local_roster(session, auth_headers):
    # Setup initial group
    grp = Group(
        group_id="group.test.456",
        name="Beta Team",
        is_active=True,
        sync_status="synced",
    )
    session.add(grp)
    await session.commit()

    with patch("app.api.groups.signal_client") as mock_client:
        mock_client.add_group_members = AsyncMock(return_value=True)
        mock_client.remove_group_members = AsyncMock(return_value=True)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Add member
            add_res = await ac.post(
                "/api/groups/group.test.456/members",
                json={"members": ["+420777999000"]},
                headers=auth_headers,
            )
            assert add_res.status_code == 200

            m_res1 = await ac.get("/api/groups/group.test.456/members", headers=auth_headers)
            assert len(m_res1.json()) == 1
            assert m_res1.json()[0]["external_identifier"] == "+420777999000"

            # Remove member
            del_res = await ac.request(
                "DELETE",
                "/api/groups/group.test.456/members",
                json={"members": ["+420777999000"]},
                headers=auth_headers,
            )
            assert del_res.status_code == 200

            m_res2 = await ac.get("/api/groups/group.test.456/members", headers=auth_headers)
            assert len(m_res2.json()) == 0
