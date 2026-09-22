"""
Inbox Conversations API — primary backend interface for admin inbox.

Provides:
- List conversations with unread counts, failed outbound flags, and search/filtering
- Detailed conversation inspect with DM user info and Group member info
- Chronological message timeline with cursor-based pagination
- Admin outbound message delivery via OutboundMessageService
- Server-side read cursor persistence
- Outbound retry endpoint
"""

from __future__ import annotations

import difflib
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, select
from sqlalchemy import func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.learning.curation import learning_service
from app.ai.learning.feedback import feedback_service
from app.ai.runtime.context import AgentContext
from app.ai.runtime.factory import get_production_agent_runtime
from app.api.deps import AdminUser, get_current_admin
from app.database import get_session
from app.models.ai import AIRun, AISuggestion, AISuggestionStatus
from app.models.conversation import (
    Conversation,
    ConversationReadState,
    ConversationType,
    Message,
    MessageActor,
    MessageAttachment,
    MessageDeliveryStatus,
    MessageDirection,
    MessageReaction,
)
from app.models.group import Group, GroupMember
from app.models.user import User
from app.schemas.ai import (
    AIRunDTO,
    AISuggestionDTO,
    EditSuggestionRequest,
    RejectSuggestionRequest,
)
from app.schemas.conversation import (
    AttachmentDTO,
    ConversationDetailDTO,
    ConversationDTO,
    ConversationListResponse,
    ConversationMessagesResponse,
    MarkReadRequest,
    MessageDTO,
    ReactionDTO,
    SendMessageRequest,
    UpdateModeRequest,
)
from app.services.audit_log import write_audit_log
from app.services.outbound_service import outbound_service

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    search: str | None = Query(None, description="Search by name, phone, or group ID"),
    type: str | None = Query(None, description="Filter by type: dm or group"),
    mode: str | None = Query(None, description="Filter by mode: auto, manual, paused"),
    unread_only: bool = Query(False, description="Only show conversations with unread messages"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """List inbox conversations with computed unread counts and delivery status."""
    query = select(Conversation).where(Conversation.is_active == True)  # noqa: E712

    if type:
        query = query.where(Conversation.type == type)
    if mode:
        query = query.where(Conversation.mode == mode)

    query = query.order_by(Conversation.updated_at.desc())
    res = await session.execute(query)
    all_convs = res.scalars().all()

    items: list[ConversationDTO] = []
    total_unread_all = 0

    for conv in all_convs:
        # 1. Resolve Display Name and Blocked Status
        display_name = conv.signal_id
        is_blocked = False
        if conv.type == ConversationType.group.value and conv.group_id:
            g_res = await session.execute(select(Group).where(Group.group_id == conv.group_id))
            grp = g_res.scalar_one_or_none()
            display_name = grp.name if grp and grp.name else f"Group {conv.group_id[:12]}..."
        else:
            uid = conv.dm_user_id or conv.user_id
            if uid:
                u_res = await session.execute(select(User).where(User.id == uid))
                usr = u_res.scalar_one_or_none()
                if usr:
                    display_name = usr.display_name or usr.phone_number or conv.signal_id
                    is_blocked = usr.is_blocked

        # Search filter
        if search and search.strip():
            s = search.strip().lower()
            if s not in display_name.lower() and s not in (conv.signal_id or "").lower():
                continue

        # 2. Get latest message
        last_m_res = await session.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.id.desc())
            .limit(1)
        )
        last_msg = last_m_res.scalar_one_or_none()

        # 3. Calculate unread count based on server read state
        read_state_res = await session.execute(
            select(ConversationReadState).where(
                ConversationReadState.conversation_id == conv.id,
                ConversationReadState.admin_identity == admin.username,
            )
        )
        read_state = read_state_res.scalar_one_or_none()
        last_read_id = read_state.last_read_message_id if read_state else 0

        unread_q = select(sa_func.count(Message.id)).where(
            Message.conversation_id == conv.id,
            Message.direction == MessageDirection.inbound.value,
            Message.id > last_read_id,
        )
        unread_res = await session.execute(unread_q)
        unread_count = unread_res.scalar() or 0
        total_unread_all += unread_count

        if unread_only and unread_count == 0:
            continue

        # 4. Check for failed outbound messages
        failed_res = await session.execute(
            select(sa_func.count(Message.id)).where(
                Message.conversation_id == conv.id,
                Message.delivery_status == MessageDeliveryStatus.failed.value,
            )
        )
        has_failed = (failed_res.scalar() or 0) > 0

        items.append(
            ConversationDTO(
                id=conv.id,
                type=conv.type or ("group" if conv.group_id else "dm"),
                signal_id=conv.signal_id,
                group_id=conv.group_id,
                display_name=display_name,
                mode=conv.mode,
                is_blocked=is_blocked,
                is_active=conv.is_active,
                summary=conv.summary,
                message_count=conv.message_count or 0,
                unread_count=unread_count,
                has_failed_outbound=has_failed,
                last_message=last_msg.content if last_msg else "",
                last_message_at=last_msg.timestamp if last_msg else conv.last_message_at,
                last_message_actor=last_msg.actor if last_msg else None,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )
        )

    # Paginate slice
    total = len(items)
    paginated_items = items[offset : offset + limit]

    return ConversationListResponse(
        items=paginated_items,
        total=total,
        total_unread=total_unread_all,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailDTO)
async def get_conversation(
    conversation_id: int,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Get full details of a conversation."""
    conv = await session.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    display_name = conv.signal_id
    is_blocked = False
    phone_number = None
    signal_uuid = None
    notes = None
    members_count = 0
    admins_count = 0
    sync_status = None

    if conv.type == ConversationType.group.value and conv.group_id:
        g_res = await session.execute(select(Group).where(Group.group_id == conv.group_id))
        grp = g_res.scalar_one_or_none()
        if grp:
            display_name = grp.name or f"Group {conv.group_id[:12]}..."
            notes = grp.notes
            sync_status = grp.sync_status
            m_res = await session.execute(
                select(sa_func.count(GroupMember.id)).where(GroupMember.group_id == grp.id)
            )
            members_count = m_res.scalar() or 0
            adm_res = await session.execute(
                select(sa_func.count(GroupMember.id)).where(
                    GroupMember.group_id == grp.id,
                    GroupMember.is_admin == True,  # noqa: E712
                )
            )
            admins_count = adm_res.scalar() or 0
    else:
        uid = conv.dm_user_id or conv.user_id
        if uid:
            u_res = await session.execute(select(User).where(User.id == uid))
            usr = u_res.scalar_one_or_none()
            if usr:
                display_name = usr.display_name or usr.phone_number or conv.signal_id
                is_blocked = usr.is_blocked
                phone_number = usr.phone_number
                signal_uuid = usr.signal_uuid
                notes = usr.notes

    # Latest message
    last_m_res = await session.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.id.desc())
        .limit(1)
    )
    last_msg = last_m_res.scalar_one_or_none()

    # Unread
    read_state_res = await session.execute(
        select(ConversationReadState).where(
            ConversationReadState.conversation_id == conv.id,
            ConversationReadState.admin_identity == admin.username,
        )
    )
    read_state = read_state_res.scalar_one_or_none()
    last_read_id = read_state.last_read_message_id if read_state else 0

    unread_res = await session.execute(
        select(sa_func.count(Message.id)).where(
            Message.conversation_id == conv.id,
            Message.direction == MessageDirection.inbound.value,
            Message.id > last_read_id,
        )
    )
    unread_count = unread_res.scalar() or 0

    failed_res = await session.execute(
        select(sa_func.count(Message.id)).where(
            Message.conversation_id == conv.id,
            Message.delivery_status == MessageDeliveryStatus.failed.value,
        )
    )
    has_failed = (failed_res.scalar() or 0) > 0

    return ConversationDetailDTO(
        id=conv.id,
        type=conv.type or ("group" if conv.group_id else "dm"),
        signal_id=conv.signal_id,
        group_id=conv.group_id,
        display_name=display_name,
        mode=conv.mode,
        is_blocked=is_blocked,
        is_active=conv.is_active,
        summary=conv.summary,
        message_count=conv.message_count or 0,
        unread_count=unread_count,
        has_failed_outbound=has_failed,
        last_message=last_msg.content if last_msg else "",
        last_message_at=last_msg.timestamp if last_msg else conv.last_message_at,
        last_message_actor=last_msg.actor if last_msg else None,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        notes=notes,
        dm_user_id=conv.dm_user_id or conv.user_id,
        phone_number=phone_number,
        signal_uuid=signal_uuid,
        members_count=members_count,
        admins_count=admins_count,
        sync_status=sync_status,
    )


@router.get("/{conversation_id}/messages", response_model=ConversationMessagesResponse)
async def get_conversation_messages(
    conversation_id: int,
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = Query(None, description="Fetch messages older than this ID"),
    after_id: int | None = Query(None, description="Fetch messages newer than this ID"),
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """
    Get messages for a conversation timeline with cursor pagination.
    Returns messages in chronological order (oldest -> newest).
    """
    conv = await session.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    query = select(Message).where(Message.conversation_id == conversation_id)

    if before_id is not None:
        query = query.where(Message.id < before_id).order_by(Message.id.desc()).limit(limit)
        res = await session.execute(query)
        messages = list(reversed(res.scalars().all()))
    elif after_id is not None:
        query = query.where(Message.id > after_id).order_by(Message.id.asc()).limit(limit)
        res = await session.execute(query)
        messages = res.scalars().all()
    else:
        # Default: latest N messages, returned in chronological order
        query = query.order_by(Message.id.desc()).limit(limit)
        res = await session.execute(query)
        messages = list(reversed(res.scalars().all()))

    msg_ids = [m.id for m in messages]

    # Pre-fetch attachments and reactions
    attachments_map: dict[int, list[AttachmentDTO]] = {m_id: [] for m_id in msg_ids}
    reactions_map: dict[int, list[ReactionDTO]] = {m_id: [] for m_id in msg_ids}

    if msg_ids:
        att_res = await session.execute(
            select(MessageAttachment).where(MessageAttachment.message_id.in_(msg_ids))
        )
        for att in att_res.scalars().all():
            attachments_map[att.message_id].append(
                AttachmentDTO(
                    id=att.id,
                    filename=att.filename,
                    mime_type=att.mime_type,
                    size=att.size,
                    external_attachment_id=att.external_attachment_id,
                )
            )

        rx_res = await session.execute(
            select(MessageReaction).where(
                MessageReaction.message_id.in_(msg_ids),
                MessageReaction.is_removed == False,  # noqa: E712
            )
        )
        for rx in rx_res.scalars().all():
            reactions_map[rx.message_id].append(
                ReactionDTO(
                    id=rx.id,
                    emoji=rx.emoji,
                    reactor_identity=rx.reactor_identity,
                    target_timestamp=rx.target_timestamp,
                    is_removed=rx.is_removed,
                    occurred_at=rx.occurred_at,
                )
            )

    items = [
        MessageDTO(
            id=m.id,
            conversation_id=m.conversation_id,
            direction=m.direction or ("outbound" if m.role == "assistant" else "inbound"),
            actor=m.actor or ("bot" if m.role == "assistant" else "customer"),
            role=m.role,
            sender_id=m.sender_id,
            sender_name=m.sender_name or m.sender_id,
            content=m.content,
            tokens_used=m.tokens_used,
            reply_to_id=m.reply_to_id,
            delivery_status=m.delivery_status
            or ("sent" if m.direction == "outbound" else "received"),
            delivery_error=m.delivery_error,
            signal_timestamp_ms=m.signal_timestamp_ms,
            occurred_at=m.occurred_at,
            origin=m.origin
            or (
                "customer"
                if m.direction == "inbound"
                else "ai_auto"
                if m.actor == "bot"
                else "human_manual"
            ),
            ai_run_id=m.ai_run_id,
            ai_suggestion_id=m.ai_suggestion_id,
            admin_identity=m.admin_identity,
            model=m.model,
            prompt_version=m.prompt_version,
            timestamp=m.timestamp,
            attachments=attachments_map.get(m.id, []),
            reactions=reactions_map.get(m.id, []),
        )
        for m in messages
    ]

    oldest_id = items[0].id if items else None
    newest_id = items[-1].id if items else None

    has_more_before = False
    has_more_after = False
    if oldest_id is not None:
        more_before_res = await session.execute(
            select(Message.id)
            .where(Message.conversation_id == conversation_id, Message.id < oldest_id)
            .limit(1)
        )
        has_more_before = more_before_res.scalar_one_or_none() is not None

    if newest_id is not None:
        more_after_res = await session.execute(
            select(Message.id)
            .where(Message.conversation_id == conversation_id, Message.id > newest_id)
            .limit(1)
        )
        has_more_after = more_after_res.scalar_one_or_none() is not None

    return ConversationMessagesResponse(
        conversation_id=conversation_id,
        items=items,
        has_more_before=has_more_before,
        has_more_after=has_more_after,
        oldest_id=oldest_id,
        newest_id=newest_id,
    )


@router.post("/{conversation_id}/messages", response_model=MessageDTO)
async def send_conversation_message(
    conversation_id: int,
    payload: SendMessageRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """
    Admin sends a manual message into a conversation.
    Uses OutboundMessageService state machine: pending -> sent | failed.
    """
    conv = await session.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    recipient = conv.signal_id
    if conv.type == ConversationType.group.value or conv.group_id:
        gid = conv.group_id or conv.signal_id
        recipient = gid if gid.startswith("group.") else f"group.{gid}"

    msg = await outbound_service.send_message(
        session=session,
        conversation_id=conv.id,
        content=payload.message,
        recipient=recipient,
        actor=MessageActor.admin.value,
        sender_id=admin.username,
        reply_to_id=payload.reply_to_id,
        origin="human_manual",
        admin_identity=admin.username,
    )

    # Human manual reply learning & feedback loop
    last_inbound_res = await session.execute(
        select(Message)
        .where(
            Message.conversation_id == conv.id, Message.direction == MessageDirection.inbound.value
        )
        .order_by(desc(Message.id))
        .limit(1)
    )
    last_inbound = last_inbound_res.scalar_one_or_none()
    if last_inbound:
        # Expire any pending AI suggestions since admin took manual action
        pending_sugs = await session.execute(
            select(AISuggestion).where(
                AISuggestion.conversation_id == conv.id,
                AISuggestion.status == AISuggestionStatus.pending.value,
            )
        )
        for ps in pending_sugs.scalars().all():
            ps.status = AISuggestionStatus.expired.value

        await feedback_service.record_event(
            session=session,
            event_type="human_manual_reply",
            conversation_id=conv.id,
            message_id=msg.id,
            actor=admin.username,
        )

        await learning_service.create_candidate(
            session=session,
            conversation_id=conv.id,
            customer_question=last_inbound.content,
            human_answer=payload.message,
            inbound_message_id=last_inbound.id,
            outbound_message_id=msg.id,
            category="support",
        )

    await write_audit_log(
        session=session,
        action="conversation.send_message",
        actor=admin.username,
        target=f"conversation:{conv.id}",
        details={
            "message_id": msg.id,
            "recipient": recipient,
            "delivery_status": msg.delivery_status,
            "length": len(payload.message),
            "origin": msg.origin,
        },
        ip_address=http_request.client.host if http_request.client else None,
    )

    return MessageDTO(
        id=msg.id,
        conversation_id=msg.conversation_id,
        direction=msg.direction,
        actor=msg.actor,
        role=msg.role,
        sender_id=msg.sender_id,
        sender_name=admin.username,
        content=msg.content,
        tokens_used=msg.tokens_used,
        reply_to_id=msg.reply_to_id,
        delivery_status=msg.delivery_status,
        delivery_error=msg.delivery_error,
        signal_timestamp_ms=msg.signal_timestamp_ms,
        occurred_at=msg.occurred_at,
        origin=msg.origin,
        ai_run_id=msg.ai_run_id,
        ai_suggestion_id=msg.ai_suggestion_id,
        admin_identity=msg.admin_identity,
        model=msg.model,
        prompt_version=msg.prompt_version,
        timestamp=msg.timestamp,
        attachments=[],
        reactions=[],
    )


@router.patch("/{conversation_id}/mode", response_model=ConversationDTO)
async def update_conversation_mode(
    conversation_id: int,
    payload: UpdateModeRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Switch conversation mode: auto | manual | paused."""
    conv = await session.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    old_mode = conv.mode
    conv.mode = payload.mode
    conv.updated_at = datetime.utcnow()
    await session.commit()

    await write_audit_log(
        session=session,
        action="conversation.mode_change",
        actor=admin.username,
        target=f"conversation:{conv.id}",
        details={"old_mode": old_mode, "new_mode": payload.mode},
        ip_address=http_request.client.host if http_request.client else None,
    )

    # Return refreshed DTO
    return await get_conversation(conversation_id, session, admin)


@router.post("/{conversation_id}/read")
async def mark_conversation_read(
    conversation_id: int,
    payload: MarkReadRequest,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Mark conversation read up to last_message_id (persisted server-side)."""
    conv = await session.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    target_id = payload.last_message_id
    if target_id is None:
        last_m_res = await session.execute(
            select(Message.id)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc())
            .limit(1)
        )
        target_id = last_m_res.scalar_one_or_none() or 0

    read_state_res = await session.execute(
        select(ConversationReadState).where(
            ConversationReadState.conversation_id == conversation_id,
            ConversationReadState.admin_identity == admin.username,
        )
    )
    read_state = read_state_res.scalar_one_or_none()

    if read_state:
        read_state.last_read_message_id = max(read_state.last_read_message_id, target_id)
        read_state.last_read_at = datetime.utcnow()
    else:
        read_state = ConversationReadState(
            conversation_id=conversation_id,
            admin_identity=admin.username,
            last_read_message_id=target_id,
            last_read_at=datetime.utcnow(),
        )
        session.add(read_state)

    await session.commit()
    return {
        "ok": True,
        "conversation_id": conversation_id,
        "last_read_message_id": read_state.last_read_message_id,
    }


@router.post("/{conversation_id}/messages/{message_id}/retry", response_model=MessageDTO)
async def retry_outbound_message(
    conversation_id: int,
    message_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Explicit retry for a failed outbound message."""
    conv = await session.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg = await session.get(Message, message_id)
    if not msg or msg.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail="Message not found in this conversation")

    retried = await outbound_service.retry_message(session=session, message_id=message_id)

    return MessageDTO(
        id=retried.id,
        conversation_id=retried.conversation_id,
        direction=retried.direction,
        actor=retried.actor,
        role=retried.role,
        sender_id=retried.sender_id,
        sender_name=retried.sender_name,
        content=retried.content,
        tokens_used=retried.tokens_used,
        reply_to_id=retried.reply_to_id,
        delivery_status=retried.delivery_status,
        delivery_error=retried.delivery_error,
        signal_timestamp_ms=retried.signal_timestamp_ms,
        occurred_at=retried.occurred_at,
        origin=retried.origin,
        ai_run_id=retried.ai_run_id,
        ai_suggestion_id=retried.ai_suggestion_id,
        admin_identity=retried.admin_identity,
        model=retried.model,
        prompt_version=retried.prompt_version,
        timestamp=retried.timestamp,
        attachments=[],
        reactions=[],
    )


# --- AI Copilot Endpoints ---


@router.get("/{conversation_id}/suggestion", response_model=AISuggestionDTO | None)
async def get_pending_suggestion(
    conversation_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Fetch the active pending Copilot draft for this conversation."""
    stmt = (
        select(AISuggestion)
        .where(
            AISuggestion.conversation_id == conversation_id,
            AISuggestion.status == AISuggestionStatus.pending.value,
        )
        .order_by(desc(AISuggestion.generated_at))
        .limit(1)
    )
    res = await session.execute(stmt)
    sug = res.scalar_one_or_none()
    if not sug:
        return None

    meta = json.loads(sug.metadata_json) if sug.metadata_json else {}
    return AISuggestionDTO(
        id=sug.id,
        conversation_id=sug.conversation_id,
        inbound_message_id=sug.inbound_message_id,
        ai_run_id=sug.ai_run_id,
        suggested_text=sug.suggested_text,
        status=sug.status,
        generated_at=sug.generated_at,
        reviewed_at=sug.reviewed_at,
        reviewed_by=sug.reviewed_by,
        final_message_id=sug.final_message_id,
        edit_distance=sug.edit_distance,
        edit_ratio=sug.edit_ratio,
        metadata=meta,
    )


@router.post("/{conversation_id}/suggestion/generate", response_model=AISuggestionDTO)
async def generate_suggestion_manually(
    conversation_id: int,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Manually generate an AI draft suggestion on-demand (e.g. in manual mode)."""
    conv = await session.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    stmt = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.direction == MessageDirection.inbound.value,
        )
        .order_by(desc(Message.id))
        .limit(1)
    )
    res = await session.execute(stmt)
    last_inbound = res.scalar_one_or_none()
    if not last_inbound:
        raise HTTPException(
            status_code=400, detail="No inbound customer message found to respond to"
        )

    context = AgentContext(
        conversation_id=conv.id,
        message_id=last_inbound.id,
        sender_id=last_inbound.sender_id or conv.signal_id,
        text=last_inbound.content,
        is_group=conv.type == ConversationType.group.value or bool(conv.group_id),
        group_id=conv.group_id,
        mode="copilot",
    )
    runtime = await get_production_agent_runtime(session)
    await runtime.run(session=session, context=context)

    sug_res = await session.execute(
        select(AISuggestion)
        .where(
            AISuggestion.conversation_id == conversation_id,
            AISuggestion.status == AISuggestionStatus.pending.value,
        )
        .order_by(desc(AISuggestion.generated_at))
        .limit(1)
    )
    sug = sug_res.scalar_one_or_none()
    if not sug:
        raise HTTPException(status_code=500, detail="Failed to generate suggestion")

    meta = json.loads(sug.metadata_json) if sug.metadata_json else {}
    return AISuggestionDTO(
        id=sug.id,
        conversation_id=sug.conversation_id,
        inbound_message_id=sug.inbound_message_id,
        ai_run_id=sug.ai_run_id,
        suggested_text=sug.suggested_text,
        status=sug.status,
        generated_at=sug.generated_at,
        reviewed_at=sug.reviewed_at,
        reviewed_by=sug.reviewed_by,
        final_message_id=sug.final_message_id,
        edit_distance=sug.edit_distance,
        edit_ratio=sug.edit_ratio,
        metadata=meta,
    )


@router.post("/{conversation_id}/suggestion/accept", response_model=MessageDTO)
async def accept_suggestion(
    conversation_id: int,
    http_request: Request,
    suggestion_id: int | None = Query(None),
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Accept the Copilot AI draft and deliver to customer via Signal."""
    conv = await session.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if suggestion_id:
        sug = await session.get(AISuggestion, suggestion_id)
    else:
        stmt = (
            select(AISuggestion)
            .where(
                AISuggestion.conversation_id == conversation_id,
                AISuggestion.status == AISuggestionStatus.pending.value,
            )
            .order_by(desc(AISuggestion.generated_at))
            .limit(1)
        )
        res = await session.execute(stmt)
        sug = res.scalar_one_or_none()

    if not sug or sug.status != AISuggestionStatus.pending.value:
        raise HTTPException(status_code=404, detail="No pending suggestion found")

    recipient = conv.signal_id
    if conv.type == ConversationType.group.value or conv.group_id:
        gid = conv.group_id or conv.signal_id
        recipient = gid if gid.startswith("group.") else f"group.{gid}"

    msg = await outbound_service.send_message(
        session=session,
        conversation_id=conv.id,
        content=sug.suggested_text,
        recipient=recipient,
        actor=MessageActor.admin.value,
        sender_id=admin.username,
        origin="human_ai_assisted",
        ai_suggestion_id=sug.id,
        ai_run_id=sug.ai_run_id,
        admin_identity=admin.username,
    )

    sug.status = AISuggestionStatus.accepted.value
    sug.reviewed_at = datetime.utcnow()
    sug.reviewed_by = admin.username
    sug.final_message_id = msg.id
    sug.edit_distance = 0
    sug.edit_ratio = 0.0
    await session.commit()

    await feedback_service.record_event(
        session=session,
        event_type="suggestion_accepted",
        conversation_id=conv.id,
        message_id=msg.id,
        ai_suggestion_id=sug.id,
        ai_run_id=sug.ai_run_id,
        actor=admin.username,
    )

    await write_audit_log(
        session=session,
        action="copilot.accept_suggestion",
        actor=admin.username,
        target=f"suggestion:{sug.id}",
        details={"conversation_id": conv.id, "message_id": msg.id},
        ip_address=http_request.client.host if http_request.client else None,
    )

    return MessageDTO(
        id=msg.id,
        conversation_id=msg.conversation_id,
        direction=msg.direction,
        actor=msg.actor,
        role=msg.role,
        sender_id=msg.sender_id,
        sender_name=admin.username,
        content=msg.content,
        tokens_used=msg.tokens_used,
        reply_to_id=msg.reply_to_id,
        delivery_status=msg.delivery_status,
        delivery_error=msg.delivery_error,
        signal_timestamp_ms=msg.signal_timestamp_ms,
        occurred_at=msg.occurred_at,
        origin=msg.origin,
        ai_run_id=msg.ai_run_id,
        ai_suggestion_id=msg.ai_suggestion_id,
        admin_identity=msg.admin_identity,
        model=msg.model,
        prompt_version=msg.prompt_version,
        timestamp=msg.timestamp,
        attachments=[],
        reactions=[],
    )


@router.post("/{conversation_id}/suggestion/edit", response_model=MessageDTO)
async def edit_and_send_suggestion(
    conversation_id: int,
    payload: EditSuggestionRequest,
    http_request: Request,
    suggestion_id: int | None = Query(None),
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Edit the AI draft and dispatch the finalized response."""
    conv = await session.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if suggestion_id:
        sug = await session.get(AISuggestion, suggestion_id)
    else:
        stmt = (
            select(AISuggestion)
            .where(
                AISuggestion.conversation_id == conversation_id,
                AISuggestion.status == AISuggestionStatus.pending.value,
            )
            .order_by(desc(AISuggestion.generated_at))
            .limit(1)
        )
        res = await session.execute(stmt)
        sug = res.scalar_one_or_none()

    if not sug or sug.status != AISuggestionStatus.pending.value:
        raise HTTPException(status_code=404, detail="No pending suggestion found")

    # Calculate edit distance & ratio
    ratio = difflib.SequenceMatcher(None, sug.suggested_text, payload.edited_text).ratio()
    edit_ratio = round(1.0 - ratio, 3)
    edit_distance = round((1.0 - ratio) * max(len(sug.suggested_text), len(payload.edited_text)))

    recipient = conv.signal_id
    if conv.type == ConversationType.group.value or conv.group_id:
        gid = conv.group_id or conv.signal_id
        recipient = gid if gid.startswith("group.") else f"group.{gid}"

    msg = await outbound_service.send_message(
        session=session,
        conversation_id=conv.id,
        content=payload.edited_text,
        recipient=recipient,
        actor=MessageActor.admin.value,
        sender_id=admin.username,
        origin="human_ai_assisted",
        ai_suggestion_id=sug.id,
        ai_run_id=sug.ai_run_id,
        admin_identity=admin.username,
    )

    sug.status = AISuggestionStatus.edited.value
    sug.reviewed_at = datetime.utcnow()
    sug.reviewed_by = admin.username
    sug.final_message_id = msg.id
    sug.edit_distance = edit_distance
    sug.edit_ratio = edit_ratio
    await session.commit()

    await feedback_service.record_event(
        session=session,
        event_type="suggestion_edited",
        conversation_id=conv.id,
        message_id=msg.id,
        ai_suggestion_id=sug.id,
        ai_run_id=sug.ai_run_id,
        notes=f"edit_ratio={edit_ratio}",
        actor=admin.username,
    )

    # Distill human-edited Q&A into learning candidate
    if sug.inbound_message_id:
        inbound_msg = await session.get(Message, sug.inbound_message_id)
        if inbound_msg:
            await learning_service.create_candidate(
                session=session,
                conversation_id=conv.id,
                customer_question=inbound_msg.content,
                human_answer=payload.edited_text,
                inbound_message_id=inbound_msg.id,
                outbound_message_id=msg.id,
                source_quality="high",
            )

    await write_audit_log(
        session=session,
        action="copilot.edit_suggestion",
        actor=admin.username,
        target=f"suggestion:{sug.id}",
        details={"conversation_id": conv.id, "message_id": msg.id, "edit_ratio": edit_ratio},
        ip_address=http_request.client.host if http_request.client else None,
    )

    return MessageDTO(
        id=msg.id,
        conversation_id=msg.conversation_id,
        direction=msg.direction,
        actor=msg.actor,
        role=msg.role,
        sender_id=msg.sender_id,
        sender_name=admin.username,
        content=msg.content,
        tokens_used=msg.tokens_used,
        reply_to_id=msg.reply_to_id,
        delivery_status=msg.delivery_status,
        delivery_error=msg.delivery_error,
        signal_timestamp_ms=msg.signal_timestamp_ms,
        occurred_at=msg.occurred_at,
        origin=msg.origin,
        ai_run_id=msg.ai_run_id,
        ai_suggestion_id=msg.ai_suggestion_id,
        admin_identity=msg.admin_identity,
        model=msg.model,
        prompt_version=msg.prompt_version,
        timestamp=msg.timestamp,
        attachments=[],
        reactions=[],
    )


@router.post("/{conversation_id}/suggestion/reject")
async def reject_suggestion(
    conversation_id: int,
    payload: RejectSuggestionRequest | None = None,
    suggestion_id: int | None = Query(None),
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Discard an AI suggestion draft."""
    if suggestion_id:
        sug = await session.get(AISuggestion, suggestion_id)
    else:
        stmt = (
            select(AISuggestion)
            .where(
                AISuggestion.conversation_id == conversation_id,
                AISuggestion.status == AISuggestionStatus.pending.value,
            )
            .order_by(desc(AISuggestion.generated_at))
            .limit(1)
        )
        res = await session.execute(stmt)
        sug = res.scalar_one_or_none()

    if not sug:
        raise HTTPException(status_code=404, detail="No pending suggestion found")

    sug.status = AISuggestionStatus.rejected.value
    sug.reviewed_at = datetime.utcnow()
    sug.reviewed_by = admin.username
    await session.commit()

    await feedback_service.record_event(
        session=session,
        event_type="suggestion_rejected",
        conversation_id=conversation_id,
        ai_suggestion_id=sug.id,
        ai_run_id=sug.ai_run_id,
        notes=payload.reason if payload else None,
        actor=admin.username,
    )

    return {"ok": True, "suggestion_id": sug.id, "status": "rejected"}


@router.get("/{conversation_id}/ai-run/{ai_run_id}", response_model=AIRunDTO)
async def get_ai_run_explainability(
    conversation_id: int,
    ai_run_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Return transparent AI decision explainability metadata (citations, tools, latency)."""
    run = await session.get(AIRun, ai_run_id)
    if not run or run.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail="AI run not found for this conversation")

    skills = json.loads(run.skills) if run.skills else []
    retrieval = json.loads(run.retrieval) if run.retrieval else []
    mem = json.loads(run.memory) if run.memory else []
    tools = json.loads(run.tool_calls) if run.tool_calls else []

    return AIRunDTO(
        id=run.id,
        trace_id=run.trace_id,
        conversation_id=run.conversation_id,
        input_message_id=run.input_message_id,
        model=run.model,
        provider=run.provider,
        prompt_version=run.prompt_version,
        skills=skills,
        retrieval=retrieval,
        memory=mem,
        tool_calls=tools,
        decision=run.decision,
        confidence=run.confidence,
        latency_ms=run.latency_ms,
        tokens=run.tokens,
        errors=run.errors,
        final_message_id=run.final_message_id,
        created_at=run.created_at,
    )
