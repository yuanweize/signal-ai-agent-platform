"""
Groups API Router — advanced Signal group management with authoritative roster sync.

Features:
- Bidirectional gateway synchronization with status tracking ('synced' | 'failed' | 'not_synced')
- GroupMember roster management (members, admins, roles, display names)
- App-specific overrides (system prompt, language, campaign eligibility, notes)
- Immediate local DB upsert on creation, update, member changes, and exit
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser, get_current_admin
from app.database import get_session
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.audit_log import write_audit_log
from app.services.signal_client import signal_client

router = APIRouter(prefix="/groups", tags=["Groups"])


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    members: list[str] = Field(default_factory=list)


class UpdateGroupRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class GroupMembersRequest(BaseModel):
    members: list[str]


class GroupMemberDTO(BaseModel):
    id: int
    group_id: int
    user_id: int | None = None
    external_identifier: str
    display_name: str | None = None
    is_admin: bool = False
    role: str = "member"
    first_seen_at: str
    last_seen_at: str


class GroupResponse(BaseModel):
    id: int
    group_id: str
    name: str | None
    description: str | None
    is_active: bool
    sync_status: str = "not_synced"
    last_synced_at: str | None = None
    campaign_eligible: bool = True
    members_count: int = 0
    admins_count: int = 0
    system_prompt_override: str | None = None
    language_override: str | None = None
    notes: str | None = None
    total_messages: int = 0
    created_at: str
    updated_at: str


@router.get("", response_model=list[GroupResponse])
async def list_groups(
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """List all known groups from the local database with member counts."""
    result = await session.execute(select(Group).order_by(Group.last_activity.desc()))
    groups = result.scalars().all()

    items: list[GroupResponse] = []
    for g in groups:
        # Count members and admins
        m_res = await session.execute(
            select(sa_func.count(GroupMember.id)).where(GroupMember.group_id == g.id)
        )
        members_count = m_res.scalar() or 0

        adm_res = await session.execute(
            select(sa_func.count(GroupMember.id)).where(
                GroupMember.group_id == g.id,
                GroupMember.is_admin == True,  # noqa: E712
            )
        )
        admins_count = adm_res.scalar() or 0

        items.append(
            GroupResponse(
                id=g.id,
                group_id=g.group_id,
                name=g.name,
                description=g.description,
                is_active=g.is_active,
                sync_status=g.sync_status,
                last_synced_at=g.last_synced_at.isoformat() if g.last_synced_at else None,
                campaign_eligible=g.campaign_eligible,
                members_count=members_count,
                admins_count=admins_count,
                system_prompt_override=g.system_prompt_override,
                language_override=g.language_override,
                notes=g.notes,
                total_messages=g.total_messages,
                created_at=g.created_at.isoformat(),
                updated_at=g.updated_at.isoformat(),
            )
        )
    return items


@router.get("/{group_id}/members", response_model=list[GroupMemberDTO])
async def list_group_members(
    group_id: str,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """List members of a group with roles and user mappings."""
    g_res = await session.execute(select(Group).where(Group.group_id == group_id))
    group = g_res.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    m_res = await session.execute(
        select(GroupMember)
        .where(GroupMember.group_id == group.id)
        .order_by(GroupMember.is_admin.desc(), GroupMember.last_seen_at.desc())
    )
    members = m_res.scalars().all()

    # Pre-fetch user display names
    u_ids = [m.user_id for m in members if m.user_id]
    u_map: dict[int, str] = {}
    if u_ids:
        users = (await session.execute(select(User).where(User.id.in_(u_ids)))).scalars().all()
        u_map = {u.id: u.display_name or u.phone_number or u.signal_id for u in users}

    return [
        GroupMemberDTO(
            id=m.id,
            group_id=m.group_id,
            user_id=m.user_id,
            external_identifier=m.external_identifier,
            display_name=u_map.get(m.user_id) if m.user_id else m.external_identifier,
            is_admin=m.is_admin,
            role=m.role,
            first_seen_at=m.first_seen_at.isoformat(),
            last_seen_at=m.last_seen_at.isoformat(),
        )
        for m in members
    ]


@router.post("")
async def create_group(
    request: CreateGroupRequest,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Create a new Signal group and immediately sync to local DB."""
    result = await signal_client.create_group(request.name, request.members)
    if not result:
        raise HTTPException(status_code=502, detail="Failed to create group on Signal Gateway")

    gateway_group_id = result.get("id") or result.get("group_id")
    if gateway_group_id:
        existing = (
            await session.execute(select(Group).where(Group.group_id == gateway_group_id))
        ).scalar_one_or_none()

        if existing is None:
            group = Group(
                group_id=gateway_group_id,
                name=request.name,
                is_active=True,
                sync_status="synced",
                last_synced_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(group)
            await session.flush()
        else:
            group = existing
            group.name = request.name
            group.is_active = True
            group.sync_status = "synced"
            group.last_synced_at = datetime.now(UTC).replace(tzinfo=None)

        # Seed initial members
        for member_id in request.members:
            if not member_id:
                continue
            u_res = await session.execute(select(User).where(User.signal_id == member_id))
            usr = u_res.scalar_one_or_none()
            gm = GroupMember(
                group_id=group.id,
                user_id=usr.id if usr else None,
                external_identifier=member_id,
                is_admin=False,
                role="member",
            )
            session.add(gm)

        await session.commit()

        await write_audit_log(
            session=session,
            action="group.create",
            actor=admin.username,
            target=f"group:{gateway_group_id}",
            details={"name": request.name, "members_count": len(request.members)},
        )

    return result


@router.post("/sync")
async def sync_groups_from_gateway(
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """
    Authoritative sync of groups and rosters from the Signal gateway into local DB.
    Gateway is external truth; local DB preserves application metadata.
    """
    gateway_groups = await signal_client.list_groups()
    if gateway_groups is None:
        raise HTTPException(status_code=502, detail="Failed to fetch groups from gateway")

    synced = 0
    now = datetime.now(UTC).replace(tzinfo=None)

    for gg in gateway_groups:
        gid = gg.get("id") or gg.get("group_id", "")
        if not gid:
            continue
        name = gg.get("name") or f"Group {gid[:8]}..."
        description = gg.get("description")
        is_blocked = gg.get("is_blocked", False)

        existing = (
            await session.execute(select(Group).where(Group.group_id == gid))
        ).scalar_one_or_none()

        if existing is None:
            group = Group(
                group_id=gid,
                name=name,
                description=description,
                is_active=not is_blocked,
                sync_status="synced",
                last_synced_at=now,
            )
            session.add(group)
            await session.flush()
        else:
            group = existing
            group.name = name
            if description is not None:
                group.description = description
            group.sync_status = "synced"
            group.last_synced_at = now
            group.last_activity = now

        # Synchronize Members & Admins
        gw_members = gg.get("members", []) or []
        gw_admins = set(gg.get("admins", []) or [])

        # Fetch existing members for this group
        existing_m_res = await session.execute(
            select(GroupMember).where(GroupMember.group_id == group.id)
        )
        existing_members = {m.external_identifier: m for m in existing_m_res.scalars().all()}

        for m_ident in gw_members:
            if not m_ident:
                continue
            is_adm = m_ident in gw_admins
            if m_ident in existing_members:
                em = existing_members[m_ident]
                em.is_admin = is_adm
                em.role = "admin" if is_adm else "member"
                em.last_seen_at = now
            else:
                # Resolve User if known
                u_res = await session.execute(select(User).where(User.signal_id == m_ident))
                usr = u_res.scalar_one_or_none()
                new_m = GroupMember(
                    group_id=group.id,
                    user_id=usr.id if usr else None,
                    external_identifier=m_ident,
                    is_admin=is_adm,
                    role="admin" if is_adm else "member",
                )
                session.add(new_m)

        synced += 1

    await session.commit()

    await write_audit_log(
        session=session,
        action="group.sync",
        actor=admin.username,
        target="groups",
        details={"synced_count": synced},
    )

    return {"ok": True, "synced": synced}


@router.put("/{group_id}")
async def update_group(
    group_id: str,
    request: UpdateGroupRequest,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Update group metadata on gateway and sync to local DB."""
    success = await signal_client.update_group(
        group_id, name=request.name, description=request.description
    )
    if not success:
        raise HTTPException(status_code=502, detail="Failed to update group on Signal Gateway")

    # Sync local DB
    existing = (
        await session.execute(select(Group).where(Group.group_id == group_id))
    ).scalar_one_or_none()
    if existing:
        if request.name is not None:
            existing.name = request.name
        if request.description is not None:
            existing.description = request.description
        existing.last_activity = datetime.now(UTC).replace(tzinfo=None)
        await session.commit()

    return {"ok": True}


@router.put("/{group_id}/settings")
async def update_group_settings(
    group_id: str,
    is_active: bool | None = None,
    campaign_eligible: bool | None = None,
    system_prompt_override: str | None = None,
    language_override: str | None = None,
    notes: str | None = None,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Update app-specific group settings (not synced to gateway)."""
    existing = (
        await session.execute(select(Group).where(Group.group_id == group_id))
    ).scalar_one_or_none()

    if existing is None:
        raise HTTPException(status_code=404, detail="Group not found in local DB")

    if is_active is not None:
        existing.is_active = is_active
    if campaign_eligible is not None:
        existing.campaign_eligible = campaign_eligible
    if system_prompt_override is not None:
        existing.system_prompt_override = system_prompt_override or None
    if language_override is not None:
        existing.language_override = language_override or None
    if notes is not None:
        existing.notes = notes or None

    await session.commit()
    return {"ok": True}


@router.post("/{group_id}/members")
async def add_members(
    group_id: str,
    request: GroupMembersRequest,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Add members to a group and update local roster."""
    success = await signal_client.add_group_members(group_id, request.members)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to add members")

    # Update local GroupMember roster
    g_res = await session.execute(select(Group).where(Group.group_id == group_id))
    grp = g_res.scalar_one_or_none()
    if grp:
        for m_ident in request.members:
            if not m_ident:
                continue
            existing_m = (
                await session.execute(
                    select(GroupMember).where(
                        GroupMember.group_id == grp.id,
                        GroupMember.external_identifier == m_ident,
                    )
                )
            ).scalar_one_or_none()
            if not existing_m:
                u_res = await session.execute(select(User).where(User.signal_id == m_ident))
                usr = u_res.scalar_one_or_none()
                session.add(
                    GroupMember(
                        group_id=grp.id,
                        user_id=usr.id if usr else None,
                        external_identifier=m_ident,
                        is_admin=False,
                        role="member",
                    )
                )
        await session.commit()

    return {"ok": True}


@router.delete("/{group_id}/members")
async def remove_members(
    group_id: str,
    request: GroupMembersRequest,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Remove members from a group and update local roster."""
    success = await signal_client.remove_group_members(group_id, request.members)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to remove members")

    g_res = await session.execute(select(Group).where(Group.group_id == group_id))
    grp = g_res.scalar_one_or_none()
    if grp:
        for m_ident in request.members:
            existing_m = (
                await session.execute(
                    select(GroupMember).where(
                        GroupMember.group_id == grp.id,
                        GroupMember.external_identifier == m_ident,
                    )
                )
            ).scalar_one_or_none()
            if existing_m:
                await session.delete(existing_m)
        await session.commit()

    return {"ok": True}


@router.post("/{group_id}/admins")
async def add_admins(
    group_id: str,
    request: GroupMembersRequest,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Add admins to a group."""
    success = await signal_client.modify_group_admins(group_id, request.members, action="add")
    if not success:
        raise HTTPException(status_code=502, detail="Failed to add admins")

    g_res = await session.execute(select(Group).where(Group.group_id == group_id))
    grp = g_res.scalar_one_or_none()
    if grp:
        for m_ident in request.members:
            existing_m = (
                await session.execute(
                    select(GroupMember).where(
                        GroupMember.group_id == grp.id,
                        GroupMember.external_identifier == m_ident,
                    )
                )
            ).scalar_one_or_none()
            if existing_m:
                existing_m.is_admin = True
                existing_m.role = "admin"
        await session.commit()

    return {"ok": True}


@router.delete("/{group_id}/admins")
async def remove_admins(
    group_id: str,
    request: GroupMembersRequest,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Remove admins from a group."""
    success = await signal_client.modify_group_admins(group_id, request.members, action="remove")
    if not success:
        raise HTTPException(status_code=502, detail="Failed to remove admins")

    g_res = await session.execute(select(Group).where(Group.group_id == group_id))
    grp = g_res.scalar_one_or_none()
    if grp:
        for m_ident in request.members:
            existing_m = (
                await session.execute(
                    select(GroupMember).where(
                        GroupMember.group_id == grp.id,
                        GroupMember.external_identifier == m_ident,
                    )
                )
            ).scalar_one_or_none()
            if existing_m:
                existing_m.is_admin = False
                existing_m.role = "member"
        await session.commit()

    return {"ok": True}


@router.post("/{group_id}/quit")
async def quit_group(
    group_id: str,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Leave a Signal group and mark as inactive in local DB."""
    success = await signal_client.quit_group(group_id)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to quit group")

    existing = (
        await session.execute(select(Group).where(Group.group_id == group_id))
    ).scalar_one_or_none()
    if existing:
        existing.is_active = False
        await session.commit()

    return {"ok": True}
