"""
Dashboard API — statistics and overview for the admin panel.

Provides aggregated counts and recent activity data.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser, get_current_admin
from app.database import get_session
from app.models.conversation import Conversation, Message
from app.models.group import Group
from app.models.order import Order
from app.models.product import Product
from app.models.user import User
from app.services.metrics import runtime_metrics
from app.services.runtime_config import get_runtime_settings, is_ai_api_key_optional
from app.services.security_bootstrap import get_bootstrap_status
from app.services.signal_client import signal_client

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
    conversations = (await session.execute(select(func.count(Conversation.id)))).scalar() or 0
    messages = (await session.execute(select(func.count(Message.id)))).scalar() or 0
    groups = (
        await session.execute(
            select(func.count(Group.id)).where(Group.is_active == True)  # noqa: E712
        )
    ).scalar() or 0
    orders = (await session.execute(select(func.count(Order.id)))).scalar() or 0
    runtime = await get_runtime_settings(session)
    bootstrap_status = await get_bootstrap_status(session)
    ai_base_url = runtime.get("ai_api_base_url") or ""
    ai_enabled = bool(runtime.get("is_ai_enabled")) and (
        bool(runtime.get("has_ai_api_key")) or is_ai_api_key_optional(ai_base_url)
    )

    return {
        "users": users,
        "products": products,
        "conversations": conversations,
        "messages": messages,
        "groups": groups,
        "orders": orders,
        "features": {
            "signal": signal_client.is_connected,
            "ai": ai_enabled,
            "market": bool(runtime.get("is_market_enabled")),
            "admin_2fa": bootstrap_status.requires_2fa,
        },
    }


@router.get("/metrics")
async def get_metrics(
    _admin: AdminUser = Depends(get_current_admin),
):
    """Runtime metrics and alert snapshot for ops dashboard."""
    return runtime_metrics.snapshot()
