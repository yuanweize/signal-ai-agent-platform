"""Chat logs API for dashboard audit and manual takeover."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser, get_current_admin
from app.database import get_session
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.chat import (
    ChatConversationItem,
    ChatConversationListResponse,
    ChatMessageItem,
    ChatMessagesResponse,
    ChatSendRequest,
    ChatSendResponse,
)
from app.services.audit_log import write_audit_log
from app.services.signal_client import signal_client

router = APIRouter(prefix="/chats", tags=["Chats"])


@router.get("", response_model=ChatConversationListResponse)
async def list_chats(
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    result = await session.execute(
        select(Conversation)
        .where(Conversation.is_active == True)  # noqa: E712
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    conversations = result.scalars().all()

    items: list[ChatConversationItem] = []
    for conversation in conversations:
        user_result = await session.execute(
            select(User).where(User.id == conversation.user_id)
        )
        user = user_result.scalar_one_or_none()

        last_result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.timestamp.desc())
            .limit(1)
        )
        last_message = last_result.scalar_one_or_none()

        items.append(
            ChatConversationItem(
                signal_id=conversation.signal_id,
                display_name=user.display_name if user else conversation.signal_id,
                group_id=conversation.group_id,
                last_message=last_message.content if last_message else "",
                last_message_at=last_message.timestamp if last_message else None,
                message_count=conversation.message_count,
            )
        )

    return ChatConversationListResponse(items=items, total=len(items))


@router.get("/{signal_id}/messages", response_model=ChatMessagesResponse)
async def get_chat_messages(
    signal_id: str,
    group_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    query = select(Conversation).where(Conversation.signal_id == signal_id)
    if group_id is None:
        query = query.where(Conversation.group_id == None)  # noqa: E711
    else:
        query = query.where(Conversation.group_id == group_id)

    query = query.order_by(Conversation.updated_at.desc()).limit(1)

    conv_result = await session.execute(query)
    conversation = conv_result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_result = await session.execute(
        select(User).where(User.id == conversation.user_id)
    )
    user = user_result.scalar_one_or_none()

    total_messages = len(
        (
            await session.execute(
                select(Message).where(Message.conversation_id == conversation.id)
            )
        )
        .scalars()
        .all()
    )

    messages_result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.timestamp.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    messages = messages_result.scalars().all()

    return ChatMessagesResponse(
        signal_id=signal_id,
        display_name=user.display_name if user else signal_id,
        group_id=conversation.group_id,
        items=[
            ChatMessageItem(
                id=m.id,
                role=m.role,
                content=m.content,
                timestamp=m.timestamp,
            )
            for m in messages
        ],
        total=total_messages,
        page=page,
        page_size=page_size,
    )


@router.post("/{signal_id}/send", response_model=ChatSendResponse)
async def send_chat_message(
    signal_id: str,
    payload: ChatSendRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    recipient = signal_id
    if payload.group_id:
        recipient = payload.group_id
        if not recipient.startswith("group."):
            recipient = f"group.{recipient}"

    ok = await signal_client.send_reply(text=payload.message, recipient=recipient)
    if not ok:
        await write_audit_log(
            session,
            actor=admin.username,
            action="chat.takeover.send",
            target=signal_id,
            status="failed",
            ip_address=http_request.client.host if http_request.client else None,
            details={"group_id": payload.group_id, "reason": "gateway_send_failed"},
        )
        await session.commit()
        raise HTTPException(status_code=502, detail="Failed to send message")

    conversation_query = select(Conversation).where(Conversation.signal_id == signal_id)
    if payload.group_id is None:
        conversation_query = conversation_query.where(Conversation.group_id == None)  # noqa: E711
    else:
        conversation_query = conversation_query.where(Conversation.group_id == payload.group_id)
    conversation_query = conversation_query.order_by(Conversation.updated_at.desc()).limit(1)

    conv_result = await session.execute(conversation_query)
    conversation = conv_result.scalar_one_or_none()

    if conversation:
        session.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content=payload.message,
                timestamp=datetime.now(),
            )
        )
        conversation.message_count += 1
        conversation.updated_at = datetime.now()
        await session.commit()

    await write_audit_log(
        session,
        actor=admin.username,
        action="chat.takeover.send",
        target=signal_id,
        status="success",
        ip_address=http_request.client.host if http_request.client else None,
        details={"group_id": payload.group_id, "message_length": len(payload.message)},
    )
    await session.commit()

    return ChatSendResponse(success=True)
