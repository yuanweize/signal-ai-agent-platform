"""Data retention and cleanup utilities with full AI Platform table support."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
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
from app.models.conversation import Conversation, ConversationReadState, Message
from app.models.group import Group
from app.models.order import Order
from app.models.payment import Payment
from app.models.user import User

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
    signal_id: str,
    vector_store: VectorStore | None = None,
) -> dict[str, Any]:
    """Purge all private data for a given user, including memories, user-scoped knowledge, and vectors."""
    # 1. User-scoped knowledge chunks and vectors
    stmt = select(KnowledgeChunk).where(
        KnowledgeChunk.scope_type == "user",
        KnowledgeChunk.scope_id == signal_id,
    )
    res = await session.execute(stmt)
    chunks = list(res.scalars().all())
    vector_ids = [c.vector_id for c in chunks if c.vector_id]

    if vector_store and vector_ids:
        try:
            await vector_store.delete(KNOWLEDGE_COLLECTION, vector_ids)
        except Exception as e:
            logger.warning(f"Error purging user vectors for {signal_id}: {e}")

    chunks_del = await session.execute(
        delete(KnowledgeChunk).where(
            KnowledgeChunk.scope_type == "user",
            KnowledgeChunk.scope_id == signal_id,
        )
    )
    docs_del = await session.execute(
        delete(KnowledgeDocument).where(
            KnowledgeDocument.scope_type == "user",
            KnowledgeDocument.scope_id == signal_id,
        )
    )

    # 2. User memories
    memories_del = await session.execute(
        delete(MemoryItem).where(
            MemoryItem.scope_type == "user",
            MemoryItem.scope_id == signal_id,
        )
    )

    # 3. User conversations and messages
    conv_stmt = select(Conversation.id).where(Conversation.signal_id == signal_id)
    conv_ids = list((await session.execute(conv_stmt)).scalars().all())

    ai_runs_del_count = 0
    sugs_del_count = 0
    feedback_del_count = 0
    learning_del_count = 0

    if conv_ids:
        feedback_del = await session.execute(
            delete(FeedbackEvent).where(FeedbackEvent.conversation_id.in_(conv_ids))
        )
        feedback_del_count = feedback_del.rowcount or 0

        sugs_del = await session.execute(
            delete(AISuggestion).where(AISuggestion.conversation_id.in_(conv_ids))
        )
        sugs_del_count = sugs_del.rowcount or 0

        learning_del = await session.execute(
            delete(LearningCandidate).where(LearningCandidate.conversation_id.in_(conv_ids))
        )
        learning_del_count = learning_del.rowcount or 0

        runs_del = await session.execute(delete(AIRun).where(AIRun.conversation_id.in_(conv_ids)))
        ai_runs_del_count = runs_del.rowcount or 0

        await session.execute(delete(Message).where(Message.conversation_id.in_(conv_ids)))
        await session.execute(
            delete(ConversationReadState).where(ConversationReadState.conversation_id.in_(conv_ids))
        )
        await session.execute(delete(Conversation).where(Conversation.id.in_(conv_ids)))

    await session.commit()
    return {
        "signal_id": signal_id,
        "vectors_deleted": len(vector_ids),
        "chunks_deleted": chunks_del.rowcount or 0,
        "documents_deleted": docs_del.rowcount or 0,
        "memories_deleted": memories_del.rowcount or 0,
        "ai_runs_deleted": ai_runs_del_count,
        "ai_suggestions_deleted": sugs_del_count,
        "learning_candidates_deleted": learning_del_count,
        "feedback_events_deleted": feedback_del_count,
        "conversations_deleted": len(conv_ids),
    }


async def purge_all_chat_and_audit_data(
    session: AsyncSession,
    vector_store: VectorStore | None = None,
) -> dict[str, Any]:
    """Full emergency purge — deletes all transactional and AI operational data.

    Deletion order strictly respects FK constraints:
    ToolInvocation → FeedbackEvent → AISuggestion → AIRun → TrainingExample →
    LearningCandidate → MemoryItem → Payment → Order → Message →
    ConversationReadState → Conversation → CampaignDeliveryLog → AuditLog →
    Group → User (non-admin)

    Preserves: products, config, admin accounts, global knowledge sources.
    """
    # 1. AI execution & audit tables
    tool_invocations_del = await session.execute(delete(ToolInvocation))
    feedback_del = await session.execute(delete(FeedbackEvent))
    suggestion_del = await session.execute(delete(AISuggestion))
    airun_del = await session.execute(delete(AIRun))
    training_del = await session.execute(delete(TrainingExample))
    learning_del = await session.execute(delete(LearningCandidate))
    memory_del = await session.execute(delete(MemoryItem))

    # 2. Payments & orders
    payment_delete = await session.execute(delete(Payment))
    order_delete = await session.execute(delete(Order))

    # 3. Messages & conversations
    message_delete = await session.execute(delete(Message))
    read_state_delete = await session.execute(delete(ConversationReadState))
    conversation_delete = await session.execute(delete(Conversation))

    # 4. Logs
    campaign_delete = await session.execute(delete(CampaignDeliveryLog))
    audit_delete = await session.execute(delete(AuditLog))

    # 5. Groups & non-admin users
    group_delete = await session.execute(delete(Group))
    user_delete = await session.execute(delete(User).where(User.role != "admin"))

    # 6. Purge user-scoped vector chunks if store provided
    if vector_store:
        try:
            stmt = select(KnowledgeChunk.vector_id).where(KnowledgeChunk.scope_type == "user")
            res = await session.execute(stmt)
            user_vecs = [v for v in res.scalars().all() if v]
            if user_vecs:
                await vector_store.delete(KNOWLEDGE_COLLECTION, user_vecs)
        except Exception as e:
            logger.warning(f"Error purging user vectors during full purge: {e}")

    await session.commit()
    return {
        "tool_invocations_deleted": tool_invocations_del.rowcount or 0,
        "feedback_events_deleted": feedback_del.rowcount or 0,
        "ai_suggestions_deleted": suggestion_del.rowcount or 0,
        "ai_runs_deleted": airun_del.rowcount or 0,
        "training_examples_deleted": training_del.rowcount or 0,
        "learning_candidates_deleted": learning_del.rowcount or 0,
        "memory_items_deleted": memory_del.rowcount or 0,
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
