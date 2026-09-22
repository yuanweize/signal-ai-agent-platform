"""
Built-in business and context tools.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.context import current_tool_session
from app.ai.tools.permissions import ToolPermission
from app.ai.tools.registry import tool_registry
from app.models.group import Group
from app.models.product import Product
from app.models.user import User


def _resolve_session(session: AsyncSession | None) -> AsyncSession:
    resolved = session or current_tool_session.get()
    if resolved is None:
        raise RuntimeError("No database session provided or active in ToolExecutionContext")
    return resolved


async def search_products(
    query: str, session: AsyncSession | None = None, limit: int = 5
) -> list[dict[str, Any]]:
    """Search products in the catalog by name or description."""
    db_session = _resolve_session(session)
    stmt = select(Product).where(Product.is_active.is_(True)).limit(limit)
    res = await db_session.execute(stmt)
    products = list(res.scalars().all())

    matched = []
    q = query.lower()
    for p in products:
        if q in p.name.lower() or (p.description and q in p.description.lower()):
            matched.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "price": p.price,
                    "stock": p.stock,
                    "description": p.description,
                }
            )
    # If query is empty or broad, return all active up to limit
    if not matched:
        matched = [
            {
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "stock": p.stock,
                "description": p.description,
            }
            for p in products
        ]
    return matched[:limit]


async def get_product(
    product_id: int, session: AsyncSession | None = None
) -> dict[str, Any] | None:
    """Retrieve detailed information about a specific product."""
    db_session = _resolve_session(session)
    product = await db_session.get(Product, product_id)
    if not product:
        return None
    return {
        "id": product.id,
        "name": product.name,
        "price": product.price,
        "stock": product.stock,
        "description": product.description,
        "is_active": product.is_active,
    }


async def get_customer_profile(
    signal_id: str, session: AsyncSession | None = None
) -> dict[str, Any] | None:
    """Get customer profile information for a Signal identifier."""
    db_session = _resolve_session(session)
    stmt = select(User).where(User.signal_id == signal_id)
    res = await db_session.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        return None
    return {
        "id": user.id,
        "signal_id": user.signal_id,
        "name": user.display_name,
        "is_blocked": user.is_blocked,
    }


async def get_group_info(
    group_id: str, session: AsyncSession | None = None
) -> dict[str, Any] | None:
    """Get group title and status."""
    db_session = _resolve_session(session)
    stmt = select(Group).where(Group.group_id == group_id)
    res = await db_session.execute(stmt)
    grp = res.scalar_one_or_none()
    if not grp:
        return None
    return {
        "id": grp.id,
        "group_id": grp.group_id,
        "name": grp.name,
        "member_count": len(grp.members) if grp.members else 0,
    }


async def trigger_sample_refund(order_id: int, amount: float, reason: str) -> dict[str, Any]:
    """Sensitive action: issue a refund (REQUIRES HUMAN OPERATOR APPROVAL)."""
    return {
        "refund_id": 999,
        "order_id": order_id,
        "amount": amount,
        "status": "processed",
        "reason": reason,
    }


# Register tools
def register_builtin_tools() -> None:
    tool_registry.register(
        name="search_products",
        description="Search available products in the catalog by keyword.",
        func=search_products,
        permission=ToolPermission(
            name="search_products", description="Search products", read_only=True
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term, e.g. 'coffee'"},
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    )

    tool_registry.register(
        name="get_product",
        description="Get exact product details by product ID.",
        func=get_product,
        permission=ToolPermission(
            name="get_product", description="Get product details", read_only=True
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "description": "Product numeric ID"},
            },
            "required": ["product_id"],
        },
    )

    tool_registry.register(
        name="get_customer_profile",
        description="Get customer name and verification details.",
        func=get_customer_profile,
        permission=ToolPermission(
            name="get_customer_profile", description="Customer profile", read_only=True
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "signal_id": {"type": "string", "description": "Customer Signal ID"},
            },
            "required": ["signal_id"],
        },
    )

    tool_registry.register(
        name="get_group_info",
        description="Get current group title and details.",
        func=get_group_info,
        permission=ToolPermission(name="get_group_info", description="Group info", read_only=True),
        parameters_schema={
            "type": "object",
            "properties": {
                "group_id": {"type": "string", "description": "Signal group ID"},
            },
            "required": ["group_id"],
        },
    )

    tool_registry.register(
        name="trigger_sample_refund",
        description="Process a financial refund for an order (SENSITIVE: requires human approval).",
        func=trigger_sample_refund,
        permission=ToolPermission(
            name="trigger_sample_refund",
            description="Process refund",
            read_only=False,
            writes_data=True,
            external_side_effect=True,
            requires_human_approval=True,  # STRICT GOVERNANCE
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "integer", "description": "Order numeric ID"},
                "amount": {"type": "number", "description": "Refund amount"},
                "reason": {"type": "string", "description": "Reason for refund"},
            },
            "required": ["order_id", "amount", "reason"],
        },
    )


register_builtin_tools()
