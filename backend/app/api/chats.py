"""Chat logs API for dashboard audit and manual takeover."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser, get_current_admin
from app.database import get_session
from app.models.conversation import Conversation, ConversationMode, Message
from app.models.group import Group
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
    """List chat conversations.

    - DMs: one entry per user (signal_id, group_id=None)
    - Groups: one entry per group_id
    """
    result = await session.execute(
        select(Conversation)
        .where(Conversation.is_active == True)  # noqa: E712
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    conversations = result.scalars().all()

    items: list[ChatConversationItem] = []

    for conv in conversations:
        # Get latest message
        last_result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.timestamp.desc())
            .limit(1)
        )
        last_message = last_result.scalar_one_or_none()

        if conv.group_id:
            group_result = await session.execute(
                select(Group).where(Group.group_id == conv.group_id)
            )
            group = group_result.scalar_one_or_none()
            display_name = group.name if group else f"Group {conv.group_id[:12]}..."

            items.append(
                ChatConversationItem(
                    id=conv.id,
                    signal_id=conv.group_id,
                    display_name=display_name,
                    group_id=conv.group_id,
                    mode=conv.mode,
                    last_message=last_message.content if last_message else "",
                    last_message_at=last_message.timestamp if last_message else None,
                    message_count=conv.message_count,
                )
            )
        else:
            user_result = await session.execute(select(User).where(User.id == conv.user_id))
            user = user_result.scalar_one_or_none()

            items.append(
                ChatConversationItem(
                    id=conv.id,
                    signal_id=conv.signal_id,
                    display_name=user.display_name if user else conv.signal_id,
                    group_id=None,
                    mode=conv.mode,
                    last_message=last_message.content if last_message else "",
                    last_message_at=last_message.timestamp if last_message else None,
                    message_count=conv.message_count,
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
    """Get messages for a conversation.

    - DM: fetches messages from the specific user's conversation
    - Group: fetches messages for the group conversation
    """
    if group_id:
        query = select(Conversation).where(Conversation.group_id == group_id)
    else:
        query = (
            select(Conversation)
            .where(Conversation.signal_id == signal_id)
            .where(Conversation.group_id == None)  # noqa: E711
        )

    query = query.order_by(Conversation.updated_at.desc()).limit(1)
    conv_result = await session.execute(query)
    conversation = conv_result.scalar_one_or_none()

    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Get display name
    if group_id:
        group_result = await session.execute(select(Group).where(Group.group_id == group_id))
        group = group_result.scalar_one_or_none()
        display_name = group.name if group else f"Group {group_id[:12]}..."
    else:
        user_result = await session.execute(select(User).where(User.id == conversation.user_id))
        user = user_result.scalar_one_or_none()
        display_name = user.display_name if user else signal_id

    # Messages
    count_result = await session.execute(
        select(sa_func.count(Message.id)).where(Message.conversation_id == conversation.id)
    )
    total_messages = count_result.scalar() or 0

    messages_result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.timestamp.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    messages = messages_result.scalars().all()

    # Pre-fetch users for sender names
    sender_ids = list({m.sender_id for m in messages if m.sender_id and m.sender_id != "bot"})
    sender_map = {}
    if sender_ids:
        users_result = await session.execute(select(User).where(User.signal_id.in_(sender_ids)))
        users = users_result.scalars().all()
        sender_map = {u.signal_id: u.display_name for u in users}

    return ChatMessagesResponse(
        signal_id=signal_id,
        display_name=display_name,
        group_id=group_id,
        conversation_id=conversation.id,
        mode=conversation.mode,
        items=[
            ChatMessageItem(
                id=m.id,
                role=m.role,
                content=m.content,
                timestamp=m.timestamp,
                sender_name=sender_map.get(m.sender_id, m.sender_id)
                if m.role == "user" and m.sender_id
                else None,
                sender_id=m.sender_id,
                signal_timestamp_ms=m.signal_timestamp_ms,
                delivery_status=m.delivery_status,
                delivery_error=m.delivery_error,
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
    """Manual takeover: admin sends a message to a DM or group.

    Uses the same outbound state machine as the AI pipeline:
    pending → sent | failed
    """
    recipient = signal_id
    if payload.group_id:
        recipient = payload.group_id
        if not recipient.startswith("group."):
            recipient = f"group.{recipient}"

    # Find conversation first
    if payload.group_id:
        conversation_query = (
            select(Conversation)
            .where(Conversation.group_id == payload.group_id)
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )
    else:
        conversation_query = (
            select(Conversation)
            .where(Conversation.signal_id == signal_id)
            .where(Conversation.group_id == None)  # noqa: E711
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )

    conv_result = await session.execute(conversation_query)
    conversation = conv_result.scalar_one_or_none()

    # Write pending outbound record before attempting send
    pending_msg = None
    if conversation:
        pending_msg = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=payload.message,
            sender_id="admin",
            sender_name=admin.username,
            delivery_status="pending",
            timestamp=datetime.now(),
        )
        session.add(pending_msg)
        conversation.message_count += 1
        conversation.updated_at = datetime.now()
        await session.commit()

    # Attempt gateway send
    ok = await signal_client.send_reply(text=payload.message, recipient=recipient)

    if not ok:
        # Update status to failed
        if pending_msg:
            pending_msg.delivery_status = "failed"
            pending_msg.delivery_error = "gateway_send_failed"
            await session.commit()

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

    # Mark as sent
    if pending_msg:
        pending_msg.delivery_status = "sent"
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


class ReactionRequest(BaseModel):
    emoji: str
    target_author: str


@router.post("/{signal_id}/messages/{timestamp}/react")
async def send_reaction(
    signal_id: str,
    timestamp: int,
    request: ReactionRequest,
    group_id: str | None = None,
    admin: AdminUser = Depends(get_current_admin),
):
    """Send a reaction to a specific message."""
    recipient = group_id if group_id else signal_id
    if recipient and not recipient.startswith("group.") and group_id:
        recipient = f"group.{recipient}"

    success = await signal_client.send_reaction(
        recipient=recipient,
        target_author=request.target_author,
        timestamp=timestamp,
        emoji=request.emoji,
    )
    if not success:
        raise HTTPException(status_code=502, detail="Failed to send reaction")
    return {"ok": True}


@router.delete("/{signal_id}/messages/{timestamp}/react")
async def remove_reaction(
    signal_id: str,
    timestamp: int,
    target_author: str,
    group_id: str | None = None,
    admin: AdminUser = Depends(get_current_admin),
):
    """Remove a previously sent reaction."""
    recipient = group_id if group_id else signal_id
    if recipient and not recipient.startswith("group.") and group_id:
        recipient = f"group.{recipient}"

    success = await signal_client.remove_reaction(
        recipient=recipient,
        target_author=target_author,
        timestamp=timestamp,
    )
    if not success:
        raise HTTPException(status_code=502, detail="Failed to remove reaction")
    return {"ok": True}


@router.delete("/{signal_id}/messages/{timestamp}")
async def delete_message(
    signal_id: str,
    timestamp: int,
    group_id: str | None = None,
    admin: AdminUser = Depends(get_current_admin),
):
    """Remotely delete a message sent by the bot."""
    recipient = group_id if group_id else signal_id
    if recipient and not recipient.startswith("group.") and group_id:
        recipient = f"group.{recipient}"

    success = await signal_client.delete_message(
        recipient=recipient,
        target_timestamp=timestamp,
    )
    if not success:
        raise HTTPException(status_code=502, detail="Failed to remotely delete message")
    return {"ok": True}


# ---- Conversation Mode (Manual Takeover) ----


class ConversationModeRequest(BaseModel):
    mode: str  # "auto" | "manual" | "paused"


@router.get("/{conversation_id}/mode")
async def get_conversation_mode(
    conversation_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Get the current mode of a conversation (auto/manual/paused)."""
    result = await session.execute(select(Conversation).where(Conversation.id == conversation_id))
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"id": conv.id, "mode": conv.mode}


@router.put("/{conversation_id}/mode")
async def set_conversation_mode(
    conversation_id: int,
    payload: ConversationModeRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Set conversation mode — persisted to DB, survives restart.

    auto:   AI replies automatically (default)
    manual: AI suppressed; admin replies manually (real takeover)
    paused: No auto-reply; messages are still recorded
    """
    valid_modes = {m.value for m in ConversationMode}
    if payload.mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{payload.mode}'. Must be one of: {sorted(valid_modes)}",
        )

    result = await session.execute(select(Conversation).where(Conversation.id == conversation_id))
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    old_mode = conv.mode
    conv.mode = payload.mode

    await write_audit_log(
        session,
        actor=admin.username,
        action="chat.mode.set",
        target=str(conversation_id),
        status="success",
        ip_address=http_request.client.host if http_request.client else None,
        details={"old_mode": old_mode, "new_mode": payload.mode},
    )
    await session.commit()
    return {"id": conv.id, "mode": conv.mode, "previous_mode": old_mode}
