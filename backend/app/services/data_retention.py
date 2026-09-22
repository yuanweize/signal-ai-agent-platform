"""Data retention and cleanup utilities with full AI Platform table support."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag.ingestion import KNOWLEDGE_COLLECTION
from app.ai.rag.vector_store import VectorStore
from app.config import settings
from app.models.ai import (
    AIRun,
    AISuggestion,
    FeedbackEvent,
    KnowledgeChunk,
    KnowledgeDocument,
    LearningCandidate,
    MemoryItem,
    ToolInvocation,
    TrainingExample,
)
from app.models.audit import AuditLog
from app.models.campaign import CampaignDeliveryLog
from app.models.conversation import (
    Conversation,
    ConversationReadState,
    Message,
    MessageAttachment,
    MessageReaction,
)
from app.models.group import Group, GroupMember
from app.models.order import Order
from app.models.payment import Payment
from app.models.user import User, UserIdentity

logger = logging.getLogger("services.data_retention")


async def cleanup_expired_data(
    session: AsyncSession, retention_days: int | None = None
) -> dict[str, Any]:
    """Clean up expired messages, audit logs, and AI audit traces older than retention_days."""
    days = retention_days if retention_days is not None else settings.data_retention_days
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

    # 1. Clean up AI telemetry and traces (FK-safe)
    tool_invocations_del = await session.execute(
        delete(ToolInvocation).where(ToolInvocation.created_at < cutoff)
    )
    feedback_del = await session.execute(
        delete(FeedbackEvent).where(FeedbackEvent.created_at < cutoff)
    )
    ai_suggestions_del = await session.execute(
        delete(AISuggestion).where(AISuggestion.generated_at < cutoff)
    )
    ai_runs_del = await session.execute(delete(AIRun).where(AIRun.created_at < cutoff))

    # 2. Clean up core conversation and audit data
    message_delete = await session.execute(delete(Message).where(Message.timestamp < cutoff))
    conversation_delete = await session.execute(
        delete(Conversation).where(Conversation.updated_at < cutoff)
    )
    audit_delete = await session.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
    campaign_delete = await session.execute(
        delete(CampaignDeliveryLog).where(CampaignDeliveryLog.created_at < cutoff)
    )
    await session.commit()

    return {
        "retention_days": days,
        "tool_invocations_deleted": tool_invocations_del.rowcount or 0,
        "feedback_events_deleted": feedback_del.rowcount or 0,
        "ai_suggestions_deleted": ai_suggestions_del.rowcount or 0,
        "ai_runs_deleted": ai_runs_del.rowcount or 0,
        "messages_deleted": message_delete.rowcount or 0,
        "conversations_deleted": conversation_delete.rowcount or 0,
        "audit_logs_deleted": audit_delete.rowcount or 0,
        "campaign_logs_deleted": campaign_delete.rowcount or 0,
    }


async def purge_user_data(
    session: AsyncSession,
    identifier: str,
    vector_store: VectorStore | None = None,
) -> dict[str, Any]:
    """Purge all private data for a given user.

    Resolves canonical user first via User.id, signal_id, phone_number, signal_uuid,
    or UserIdentity aliases. Cleans up canonical and legacy scope records.
    Strictly fails closed if vector deletion fails (no false success).
    """
    identifier_str = str(identifier).strip()
    user: User | None = None

    if identifier_str.isdigit():
        user = await session.get(User, int(identifier_str))

    if not user:
        stmt = (
            select(User)
            .outerjoin(UserIdentity, UserIdentity.user_id == User.id)
            .where(
                (User.signal_id == identifier_str)
                | (User.phone_number == identifier_str)
                | (User.signal_uuid == identifier_str)
                | (UserIdentity.identity_value == identifier_str)
            )
        )
        user = (await session.execute(stmt)).scalars().first()

    scope_ids: set[str] = {identifier_str}
    user_id: int | None = None

    if user:
        user_id = user.id
        scope_ids.add(str(user.id))
        scope_ids.add(user.signal_id)
        if user.phone_number:
            scope_ids.add(user.phone_number)
        if user.signal_uuid:
            scope_ids.add(user.signal_uuid)
        stmt_idents = select(UserIdentity.identity_value).where(UserIdentity.user_id == user.id)
        ident_vals = (await session.execute(stmt_idents)).scalars().all()
        for iv in ident_vals:
            scope_ids.add(iv)

    # 1. User-scoped knowledge chunks and vectors
    stmt_chunks = select(KnowledgeChunk).where(
        KnowledgeChunk.scope_type == "user",
        KnowledgeChunk.scope_id.in_(scope_ids),
    )
    chunks = list((await session.execute(stmt_chunks)).scalars().all())
    vector_ids = [c.vector_id for c in chunks if c.vector_id]

    vectors_deleted = 0
    if vector_store and vector_ids:
        try:
            await vector_store.delete(KNOWLEDGE_COLLECTION, vector_ids)
            vectors_deleted = len(vector_ids)
        except Exception as e:
            logger.error(f"Vector deletion failed during user purge for {identifier_str}: {e}")
            await session.rollback()
            raise RuntimeError(f"Vector deletion failed during user purge: {e}") from e

    chunks_del = await session.execute(
        delete(KnowledgeChunk).where(
            KnowledgeChunk.scope_type == "user",
            KnowledgeChunk.scope_id.in_(scope_ids),
        )
    )
    docs_del = await session.execute(
        delete(KnowledgeDocument).where(
            KnowledgeDocument.scope_type == "user",
            KnowledgeDocument.scope_id.in_(scope_ids),
        )
    )

    # 2. User memories
    memories_del = await session.execute(
        delete(MemoryItem).where(
            MemoryItem.scope_type == "user",
            MemoryItem.scope_id.in_(scope_ids),
        )
    )

    # 3. User conversations and messages
    conv_query = select(Conversation.id).where(
        (Conversation.signal_id.in_(scope_ids))
        | (Conversation.dm_user_id == user_id if user_id else False)
        | (Conversation.user_id == user_id if user_id else False)
    )
    conv_ids = list((await session.execute(conv_query)).scalars().all())

    ai_runs_del_count = 0
    sugs_del_count = 0
    feedback_del_count = 0
    learning_del_count = 0
    training_del_count = 0
    messages_del_count = 0
    tool_invocations_del_count = 0

    if conv_ids:
        cand_query = select(LearningCandidate.id).where(
            LearningCandidate.conversation_id.in_(conv_ids)
        )
        cand_ids = list((await session.execute(cand_query)).scalars().all())
        if cand_ids:
            training_del = await session.execute(
                delete(TrainingExample).where(TrainingExample.source_candidate_id.in_(cand_ids))
            )
            training_del_count = training_del.rowcount or 0

        learning_del = await session.execute(
            delete(LearningCandidate).where(LearningCandidate.conversation_id.in_(conv_ids))
        )
        learning_del_count = learning_del.rowcount or 0

        feedback_del = await session.execute(
            delete(FeedbackEvent).where(FeedbackEvent.conversation_id.in_(conv_ids))
        )
        feedback_del_count = feedback_del.rowcount or 0

        runs_query = select(AIRun.id).where(AIRun.conversation_id.in_(conv_ids))
        run_ids = list((await session.execute(runs_query)).scalars().all())
        if run_ids:
            ti_del = await session.execute(
                delete(ToolInvocation).where(ToolInvocation.ai_run_id.in_(run_ids))
            )
            tool_invocations_del_count = ti_del.rowcount or 0

        # Break circular foreign keys between messages and ai_runs / ai_suggestions
        await session.execute(
            update(Message)
            .where(Message.conversation_id.in_(conv_ids))
            .values(ai_run_id=None, ai_suggestion_id=None)
        )
        await session.execute(
            update(AIRun)
            .where(AIRun.conversation_id.in_(conv_ids))
            .values(final_message_id=None, input_message_id=None)
        )
        await session.execute(
            update(AISuggestion)
            .where(AISuggestion.conversation_id.in_(conv_ids))
            .values(final_message_id=None, inbound_message_id=None, ai_run_id=None)
        )

        sugs_del = await session.execute(
            delete(AISuggestion).where(AISuggestion.conversation_id.in_(conv_ids))
        )
        sugs_del_count = sugs_del.rowcount or 0

        runs_del = await session.execute(delete(AIRun).where(AIRun.conversation_id.in_(conv_ids)))
        ai_runs_del_count = runs_del.rowcount or 0

        msg_query = select(Message.id).where(Message.conversation_id.in_(conv_ids))
        msg_ids = list((await session.execute(msg_query)).scalars().all())
        if msg_ids:
            await session.execute(
                delete(MessageReaction).where(MessageReaction.message_id.in_(msg_ids))
            )
            await session.execute(
                delete(MessageAttachment).where(MessageAttachment.message_id.in_(msg_ids))
            )
            msg_del = await session.execute(
                delete(Message).where(Message.conversation_id.in_(conv_ids))
            )
            messages_del_count = msg_del.rowcount or 0

        await session.execute(
            delete(ConversationReadState).where(ConversationReadState.conversation_id.in_(conv_ids))
        )
        await session.execute(delete(Conversation).where(Conversation.id.in_(conv_ids)))

    # 4. User record and related metadata cleanup (non-admin)
    users_deleted = 0
    if user and user.role != "admin":
        await session.execute(delete(Payment).where(Payment.user_id == user.id))
        await session.execute(delete(Order).where(Order.user_id == user.id))
        await session.execute(delete(GroupMember).where(GroupMember.user_id == user.id))
        await session.execute(
            delete(MessageReaction).where(MessageReaction.reactor_user_id == user.id)
        )
        await session.execute(delete(UserIdentity).where(UserIdentity.user_id == user.id))
        u_del = await session.execute(delete(User).where(User.id == user.id))
        users_deleted = u_del.rowcount or 0

    await session.commit()
    return {
        "identifier": identifier_str,
        "canonical_scope_id": str(user_id) if user_id else identifier_str,
        "vectors_deleted": vectors_deleted,
        "chunks_deleted": chunks_del.rowcount or 0,
        "documents_deleted": docs_del.rowcount or 0,
        "memories_deleted": memories_del.rowcount or 0,
        "ai_runs_deleted": ai_runs_del_count,
        "ai_suggestions_deleted": sugs_del_count,
        "tool_invocations_deleted": tool_invocations_del_count,
        "learning_candidates_deleted": learning_del_count,
        "training_examples_deleted": training_del_count,
        "feedback_events_deleted": feedback_del_count,
        "messages_deleted": messages_del_count,
        "conversations_deleted": len(conv_ids),
        "users_deleted": users_deleted,
    }


async def purge_all_chat_and_audit_data(
    session: AsyncSession,
    vector_store: VectorStore | None = None,
) -> dict[str, Any]:
    """Full emergency purge — deletes all transactional and AI operational data.

    Deletion order strictly respects FK constraints:
    ToolInvocation → FeedbackEvent → AISuggestion → AIRun → TrainingExample →
    LearningCandidate → MemoryItem → KnowledgeChunk/Doc (user/group scope) →
    Payment → Order → MessageReaction/Attachment → Message →
    ConversationReadState → Conversation → CampaignDeliveryLog → AuditLog →
    GroupMember → Group → User (non-admin)

    Preserves: products, runtime config, admin accounts, global knowledge sources.
    Fails closed if vector deletion fails.
    """
    # 0. User and group scoped vector & knowledge cleanup
    stmt = select(KnowledgeChunk).where(KnowledgeChunk.scope_type.in_(["user", "group"]))
    res = await session.execute(stmt)
    chunks = list(res.scalars().all())
    user_group_vecs = [c.vector_id for c in chunks if c.vector_id]

    vectors_deleted = 0
    if vector_store and user_group_vecs:
        try:
            await vector_store.delete(KNOWLEDGE_COLLECTION, user_group_vecs)
            vectors_deleted = len(user_group_vecs)
        except Exception as e:
            logger.error(f"Vector deletion failed during full purge: {e}")
            await session.rollback()
            raise RuntimeError(f"Vector deletion failed during full purge: {e}") from e

    # Delete relational chunks and documents for non-global scopes
    await session.execute(
        delete(KnowledgeChunk).where(KnowledgeChunk.scope_type.in_(["user", "group"]))
    )
    await session.execute(
        delete(KnowledgeDocument).where(KnowledgeDocument.scope_type.in_(["user", "group"]))
    )

    # 1. AI execution & audit tables
    tool_invocations_del = await session.execute(delete(ToolInvocation))
    feedback_del = await session.execute(delete(FeedbackEvent))

    # Break circular references before deleting runs, suggestions, messages
    await session.execute(update(Message).values(ai_run_id=None, ai_suggestion_id=None))
    await session.execute(update(AIRun).values(final_message_id=None, input_message_id=None))
    await session.execute(
        update(AISuggestion).values(final_message_id=None, inbound_message_id=None, ai_run_id=None)
    )

    suggestion_del = await session.execute(delete(AISuggestion))
    airun_del = await session.execute(delete(AIRun))
    training_del = await session.execute(delete(TrainingExample))
    learning_del = await session.execute(delete(LearningCandidate))
    memory_del = await session.execute(delete(MemoryItem))

    # 2. Payments & orders
    payment_delete = await session.execute(delete(Payment))
    order_delete = await session.execute(delete(Order))

    # 3. Messages & reactions & attachments & conversations
    await session.execute(delete(MessageReaction))
    await session.execute(delete(MessageAttachment))
    message_delete = await session.execute(delete(Message))
    read_state_delete = await session.execute(delete(ConversationReadState))
    conversation_delete = await session.execute(delete(Conversation))

    # 4. Logs
    campaign_delete = await session.execute(delete(CampaignDeliveryLog))
    audit_delete = await session.execute(delete(AuditLog))

    # 5. Groups & non-admin users
    await session.execute(delete(GroupMember))
    group_delete = await session.execute(delete(Group))
    await session.execute(delete(UserIdentity))
    user_delete = await session.execute(delete(User).where(User.role != "admin"))

    await session.commit()
    return {
        "tool_invocations_deleted": tool_invocations_del.rowcount or 0,
        "feedback_events_deleted": feedback_del.rowcount or 0,
        "ai_suggestions_deleted": suggestion_del.rowcount or 0,
        "ai_runs_deleted": airun_del.rowcount or 0,
        "training_examples_deleted": training_del.rowcount or 0,
        "learning_candidates_deleted": learning_del.rowcount or 0,
        "memory_items_deleted": memory_del.rowcount or 0,
        "vectors_deleted": vectors_deleted,
        "messages_deleted": message_delete.rowcount or 0,
        "read_states_deleted": read_state_delete.rowcount or 0,
        "conversations_deleted": conversation_delete.rowcount or 0,
        "audit_logs_deleted": audit_delete.rowcount or 0,
        "campaign_logs_deleted": campaign_delete.rowcount or 0,
        "users_deleted": user_delete.rowcount or 0,
        "orders_deleted": order_delete.rowcount or 0,
        "payments_deleted": payment_delete.rowcount or 0,
        "groups_deleted": group_delete.rowcount or 0,
    }
