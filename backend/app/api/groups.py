"""
Groups API Router — advanced Signal group management.
"""

from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

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
    created_at: str
    updated_at: str


@router.get("", response_model=list[GroupResponse])
async def list_groups(
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """List all known groups from the local database."""
    result = await session.execute(
        select(Group).order_by(Group.updated_at.desc())
    )
    groups = result.scalars().all()
    
    return [
        GroupResponse(
            id=g.id,
            group_id=g.group_id,
            name=g.name,
            description=g.description,
            created_at=g.created_at.isoformat(),
            updated_at=g.updated_at.isoformat(),
        )
        for g in groups
    ]


@router.post("")
async def create_group(
    request: CreateGroupRequest,
    admin: AdminUser = Depends(get_current_admin),
):
    """Create a new Signal group."""
    result = await signal_client.create_group(request.name, request.members)
    if not result:
        raise HTTPException(status_code=502, detail="Failed to create group")
    return result


@router.put("/{group_id}")
async def update_group(
    group_id: str,
    request: UpdateGroupRequest,
    admin: AdminUser = Depends(get_current_admin),
):
    """Update group metadata."""
    success = await signal_client.update_group(group_id, name=request.name, description=request.description)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to update group")
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
