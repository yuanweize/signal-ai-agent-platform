"""Data retention and cleanup utilities."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit import AuditLog
from app.models.campaign import CampaignDeliveryLog
from app.models.conversation import Conversation, Message


async def cleanup_expired_data(session: AsyncSession, retention_days: int | None = None) -> dict:
    days = retention_days if retention_days is not None else settings.data_retention_days
    cutoff = datetime.now() - timedelta(days=days)

    message_delete = await session.execute(
        delete(Message).where(Message.timestamp < cutoff)
    )
    conversation_delete = await session.execute(
        delete(Conversation).where(Conversation.updated_at < cutoff)
    )
    audit_delete = await session.execute(
        delete(AuditLog).where(AuditLog.created_at < cutoff)
    )
    campaign_delete = await session.execute(
        delete(CampaignDeliveryLog).where(CampaignDeliveryLog.created_at < cutoff)
    )
    await session.commit()

    return {
        "retention_days": days,
        "messages_deleted": message_delete.rowcount or 0,
        "conversations_deleted": conversation_delete.rowcount or 0,
        "audit_logs_deleted": audit_delete.rowcount or 0,
        "campaign_logs_deleted": campaign_delete.rowcount or 0,
    }


async def purge_all_chat_and_audit_data(session: AsyncSession) -> dict:
    message_delete = await session.execute(delete(Message))
    conversation_delete = await session.execute(delete(Conversation))
    audit_delete = await session.execute(delete(AuditLog))
    campaign_delete = await session.execute(delete(CampaignDeliveryLog))
    await session.commit()
    return {
        "messages_deleted": message_delete.rowcount or 0,
        "conversations_deleted": conversation_delete.rowcount or 0,
        "audit_logs_deleted": audit_delete.rowcount or 0,
        "campaign_logs_deleted": campaign_delete.rowcount or 0,
    }
