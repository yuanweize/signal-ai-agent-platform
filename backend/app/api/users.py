"""Admin user management APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser, get_current_admin
from app.database import get_session
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.user import (
    ManagedUserActivityResponse,
    ManagedUserItem,
    ManagedUserListResponse,
    ManagedUsersBatchRequest,
    ManagedUsersBatchResponse,
    ManagedUserUpdateRequest,
    UserConversationSummary,
    UserRecentMessage,
)
from app.services.audit_log import write_audit_log

router = APIRouter(prefix="/users", tags=["Users"])


def _to_user_item(user: User) -> ManagedUserItem:
    return ManagedUserItem(
        id=user.id,
        signal_id=user.signal_id,
        display_name=user.display_name,
        role=user.role,
        language=user.language,
        is_blocked=user.is_blocked,
        notes=user.notes,
        first_seen=user.first_seen,
        last_seen=user.last_seen,
    )


@router.get("", response_model=ManagedUserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str | None = Query(None),
    blocked: bool | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    query = select(User)

    if search:
        keyword = f"%{search.strip()}%"
        query = query.where(
            or_(
                User.signal_id.like(keyword),
                User.display_name.like(keyword),
                User.notes.like(keyword),
            )
        )

    if blocked is not None:
        query = query.where(User.is_blocked == blocked)

    total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()

    rows = (
        (
            await session.execute(
                query.order_by(User.last_seen.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return ManagedUserListResponse(
        items=[_to_user_item(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/batch", response_model=ManagedUsersBatchResponse)
async def batch_users_action(
    payload: ManagedUsersBatchRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    normalized_ids = sorted(set(payload.user_ids))
    rows = (await session.execute(select(User).where(User.id.in_(normalized_ids)))).scalars().all()

    should_block = payload.action == "block"
    updated_count = 0
    for row in rows:
        if row.is_blocked != should_block:
            row.is_blocked = should_block
            updated_count += 1

    await write_audit_log(
        session,
        actor=admin.username,
        action=f"user.batch.{payload.action}",
        target=",".join(str(user_id) for user_id in normalized_ids),
        status="success",
        ip_address=http_request.client.host if http_request.client else None,
        details={
            "requested_user_ids": normalized_ids,
            "matched_users": [row.id for row in rows],
            "updated_count": updated_count,
            "blocked_after": should_block,
        },
    )
    await session.commit()

    return ManagedUsersBatchResponse(updated_count=updated_count, action=payload.action)


@router.get("/{user_id}/activity", response_model=ManagedUserActivityResponse)
async def get_user_activity(
    user_id: int,
    message_limit: int = Query(20, ge=1, le=100),
    conversation_limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    conversation_rows = (
        (
            await session.execute(
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.updated_at.desc())
                .limit(conversation_limit)
            )
        )
        .scalars()
        .all()
    )

    conversation_count = (
        await session.execute(
            select(func.count(Conversation.id)).where(Conversation.user_id == user_id)
        )
    ).scalar_one()

    message_count = (
        await session.execute(
            select(func.count(Message.id))
            .select_from(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.user_id == user_id)
        )
    ).scalar_one()

    recent_messages = (
        await session.execute(
            select(Message, Conversation.group_id)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.user_id == user_id)
            .order_by(Message.timestamp.desc())
            .limit(message_limit)
        )
    ).all()

    recent_conversations: list[UserConversationSummary] = []
    for conversation in conversation_rows:
        last_message_row = (
            await session.execute(
                select(Message.content)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        recent_conversations.append(
            UserConversationSummary(
                conversation_id=conversation.id,
                group_id=conversation.group_id,
                message_count=conversation.message_count,
                updated_at=conversation.updated_at,
                last_message=last_message_row,
            )
        )

    return ManagedUserActivityResponse(
        user=_to_user_item(user),
        conversation_count=conversation_count,
        message_count=message_count,
        recent_conversations=recent_conversations,
        recent_messages=[
            UserRecentMessage(
                id=row[0].id,
                role=row[0].role,
                content=row[0].content,
                timestamp=row[0].timestamp,
                group_id=row[1],
            )
            for row in recent_messages
        ],
    )


@router.put("/{user_id}", response_model=ManagedUserItem)
async def update_user(
    user_id: int,
    payload: ManagedUserUpdateRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    before = {
        "display_name": user.display_name,
        "role": user.role,
        "language": user.language,
        "is_blocked": user.is_blocked,
        "notes": user.notes,
    }

    if payload.display_name is not None:
        user.display_name = payload.display_name.strip() or None
    if payload.role is not None:
        user.role = payload.role.strip()[:20] or user.role
    if payload.language is not None:
        user.language = payload.language.strip()[:10] or user.language
    if payload.is_blocked is not None:
        user.is_blocked = payload.is_blocked
    if payload.notes is not None:
        user.notes = payload.notes.strip()[:1000] or None

    await write_audit_log(
        session,
        actor=admin.username,
        action="user.update",
        target=str(user.id),
        status="success",
        ip_address=http_request.client.host if http_request.client else None,
        details={
            "signal_id": user.signal_id,
            "before": before,
            "after": {
                "display_name": user.display_name,
                "role": user.role,
                "language": user.language,
                "is_blocked": user.is_blocked,
                "notes": user.notes,
            },
        },
    )

    await session.commit()
    await session.refresh(user)

    return _to_user_item(user)
