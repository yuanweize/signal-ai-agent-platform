"""
Groups API Router — advanced Signal group management.

Includes local DB sync: after create/update operations succeed on the gateway,
the local Group record is immediately upserted so the UI is consistent.
"""

from typing import Optional
from datetime import datetime

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser, get_current_admin
from app.database import get_session
from app.models.group import Group
from app.services.signal_client import signal_client

router = APIRouter(prefix="/groups", tags=["Groups"])


class CreateGroupRequest(BaseModel):
    name: str
    members: list[str]


class UpdateGroupRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class GroupMembersRequest(BaseModel):
    members: list[str]


class GroupResponse(BaseModel):
    id: int
    group_id: str
    name: str | None
    description: str | None
    is_active: bool
    system_prompt_override: str | None = None
    language_override: str | None = None
    notes: str | None = None
    total_messages: int
    created_at: str
    updated_at: str


@router.get("", response_model=list[GroupResponse])
async def list_groups(
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """List all known groups from the local database."""
    result = await session.execute(
        select(Group).order_by(Group.last_activity.desc())
    )
    groups = result.scalars().all()

    return [
        GroupResponse(
            id=g.id,
            group_id=g.group_id,
            name=g.name,
            description=g.description,
            is_active=g.is_active,
            system_prompt_override=g.system_prompt_override,
            language_override=g.language_override,
            notes=g.notes,
            total_messages=g.total_messages,
            created_at=g.created_at.isoformat(),
            updated_at=g.updated_at.isoformat(),
        )
        for g in groups
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
        raise HTTPException(status_code=502, detail="Failed to create group")

    # P1-8 fix: immediately upsert local Group record after gateway success
    gateway_group_id = result.get("id") or result.get("group_id")
    if gateway_group_id:
        existing = (await session.execute(
            select(Group).where(Group.group_id == gateway_group_id)
        )).scalar_one_or_none()

        if existing is None:
            group = Group(
                group_id=gateway_group_id,
                name=request.name,
                is_active=True,
            )
            session.add(group)
        else:
            existing.name = request.name
        await session.commit()

    return result


@router.post("/sync")
async def sync_groups_from_gateway(
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Sync all groups from the Signal gateway into local DB.

    Gateway is the source of truth. Local DB is updated to match.
    App-specific settings (system_prompt_override, language_override, etc.)
    are preserved.
    """
    gateway_groups = await signal_client.list_groups()
    if gateway_groups is None:
        raise HTTPException(status_code=502, detail="Failed to fetch groups from gateway")

    synced = 0
    for gg in gateway_groups:
        gid = gg.get("id") or gg.get("group_id", "")
        if not gid:
            continue
        name = gg.get("name") or f"Group {gid[:8]}..."
        description = gg.get("description")

        existing = (await session.execute(
            select(Group).where(Group.group_id == gid)
        )).scalar_one_or_none()

        if existing is None:
            group = Group(
                group_id=gid,
                name=name,
                description=description,
                is_active=True,
            )
            session.add(group)
        else:
            existing.name = name
            if description is not None:
                existing.description = description
            existing.last_activity = datetime.now()
        synced += 1

    await session.commit()
    return {"ok": True, "synced": synced}


@router.put("/{group_id}")
async def update_group(
    group_id: str,
    request: UpdateGroupRequest,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Update group metadata on gateway and sync to local DB."""
    success = await signal_client.update_group(group_id, name=request.name, description=request.description)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to update group")

    # Sync local DB
    existing = (await session.execute(
        select(Group).where(Group.group_id == group_id)
    )).scalar_one_or_none()
    if existing:
        if request.name is not None:
            existing.name = request.name
        if request.description is not None:
            existing.description = request.description
        await session.commit()

    return {"ok": True}


@router.put("/{group_id}/settings")
async def update_group_settings(
    group_id: str,
    is_active: Optional[bool] = None,
    system_prompt_override: Optional[str] = None,
    language_override: Optional[str] = None,
    notes: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Update app-specific group settings (not synced to gateway)."""
    existing = (await session.execute(
        select(Group).where(Group.group_id == group_id)
    )).scalar_one_or_none()

    if existing is None:
        raise HTTPException(status_code=404, detail="Group not found in local DB")

    if is_active is not None:
        existing.is_active = is_active
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
    admin: AdminUser = Depends(get_current_admin),
):
    """Add members to a group."""
    success = await signal_client.add_group_members(group_id, request.members)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to add members")
    return {"ok": True}


@router.delete("/{group_id}/members")
async def remove_members(
    group_id: str,
    request: GroupMembersRequest,
    admin: AdminUser = Depends(get_current_admin),
):
    """Remove members from a group."""
    success = await signal_client.remove_group_members(group_id, request.members)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to remove members")
    return {"ok": True}


@router.post("/{group_id}/admins")
async def add_admins(
    group_id: str,
    request: GroupMembersRequest,
    admin: AdminUser = Depends(get_current_admin),
):
    """Add admins to a group."""
    success = await signal_client.modify_group_admins(group_id, request.members, action="add")
    if not success:
        raise HTTPException(status_code=502, detail="Failed to add admins")
    return {"ok": True}


@router.delete("/{group_id}/admins")
async def remove_admins(
    group_id: str,
    request: GroupMembersRequest,
    admin: AdminUser = Depends(get_current_admin),
):
    """Remove admins from a group."""
    success = await signal_client.modify_group_admins(group_id, request.members, action="remove")
    if not success:
        raise HTTPException(status_code=502, detail="Failed to remove admins")
    return {"ok": True}


@router.post("/{group_id}/quit")
async def quit_group(
    group_id: str,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Leave a Signal group and mark as inactive in local DB."""
    success = await signal_client.quit_group(group_id)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to quit group")

    existing = (await session.execute(
        select(Group).where(Group.group_id == group_id)
    )).scalar_one_or_none()
    if existing:
        existing.is_active = False
        await session.commit()

    return {"ok": True}
