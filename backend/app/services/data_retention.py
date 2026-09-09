"""Data retention and cleanup utilities."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit import AuditLog
from app.models.campaign import CampaignDeliveryLog
from app.models.conversation import Conversation, Message
from app.models.group import Group
from app.models.order import Order
from app.models.payment import Payment
from app.models.user import User


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
    """Full emergency purge — deletes all transactional data.

    Deletion order respects FK constraints:
    payments → orders → messages → conversations → campaign_logs →
    audit_logs → groups → users (non-admin)

    Preserves: products, config, admin accounts.
    """
    # 1. Payments (FK → orders.id, users.id)
    payment_delete = await session.execute(delete(Payment))

    # 2. Orders (FK → users.id, products.id)
    order_delete = await session.execute(delete(Order))

    # 3. Messages (FK → conversations.id)
    message_delete = await session.execute(delete(Message))

    # 4. Conversations (FK → users.id)
    conversation_delete = await session.execute(delete(Conversation))

    # 5. Campaign delivery logs
    campaign_delete = await session.execute(delete(CampaignDeliveryLog))

    # 6. Audit logs
    audit_delete = await session.execute(delete(AuditLog))

    # 7. Groups
    group_delete = await session.execute(delete(Group))

    # 8. Users — preserve admin accounts
    user_delete = await session.execute(
        delete(User).where(User.role != "admin")
    )

    await session.commit()
    return {
        "messages_deleted": message_delete.rowcount or 0,
        "conversations_deleted": conversation_delete.rowcount or 0,
        "audit_logs_deleted": audit_delete.rowcount or 0,
        "campaign_logs_deleted": campaign_delete.rowcount or 0,
        "users_deleted": user_delete.rowcount or 0,
        "orders_deleted": order_delete.rowcount or 0,
        "payments_deleted": payment_delete.rowcount or 0,
        "groups_deleted": group_delete.rowcount or 0,
    }
