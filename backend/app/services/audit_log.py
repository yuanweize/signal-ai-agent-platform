"""Audit logging service."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def write_audit_log(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    target: str = "",
    status: str = "success",
    ip_address: str | None = None,
    details: dict | None = None,
) -> None:
    payload = details or {}
    session.add(
        AuditLog(
            actor=actor,
            action=action,
            target=target,
            status=status,
            ip_address=ip_address,
            details=json.dumps(payload, ensure_ascii=False),
        )
    )


async def list_audit_logs(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 50,
    action_prefix: str | None = None,
) -> tuple[list[AuditLog], int]:
    query = select(AuditLog)
    if action_prefix:
        query = query.where(AuditLog.action.like(f"{action_prefix}%"))

    total_query = select(AuditLog)
    if action_prefix:
        total_query = total_query.where(AuditLog.action.like(f"{action_prefix}%"))

    total = len((await session.execute(total_query)).scalars().all())
    items = (
        await session.execute(
            query.order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return items, total
