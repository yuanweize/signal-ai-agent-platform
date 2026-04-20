"""
Dashboard API — statistics and overview for the admin panel.

Provides aggregated counts and recent activity data.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser, get_current_admin
from app.config import settings
from app.database import get_session
from app.models.conversation import Conversation, Message
from app.models.group import Group
from app.models.order import Order
from app.models.product import Product
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
async def get_stats(
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Get aggregated dashboard statistics."""
    users = (await session.execute(select(func.count(User.id)))).scalar() or 0
    products = (
        await session.execute(
            select(func.count(Product.id)).where(Product.is_active == True)  # noqa: E712
        )
    ).scalar() or 0
    conversations = (
        await session.execute(select(func.count(Conversation.id)))
    ).scalar() or 0
    messages = (
        await session.execute(select(func.count(Message.id)))
    ).scalar() or 0
    groups = (
        await session.execute(
            select(func.count(Group.id)).where(Group.is_active == True)  # noqa: E712
        )
    ).scalar() or 0
    orders = (
        await session.execute(select(func.count(Order.id)))
    ).scalar() or 0

    return {
        "users": users,
        "products": products,
        "conversations": conversations,
        "messages": messages,
        "groups": groups,
        "orders": orders,
        "features": settings.features_summary,
    }
