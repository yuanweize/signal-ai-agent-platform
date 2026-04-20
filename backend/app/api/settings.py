"""Runtime settings API for admin dashboard."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser, get_current_admin
from app.database import get_session
from app.models.audit import AuditLog
from app.schemas.settings import (
    AuditLogListResponse,
    AuditLogResponse,
    CleanupRequest,
    CleanupResponse,
    RuntimeSettingsResponse,
    RuntimeSettingsRollbackRequest,
    RuntimeSettingsUpdateRequest,
)
from app.services.audit_log import list_audit_logs, write_audit_log
from app.services.data_retention import cleanup_expired_data, purge_all_chat_and_audit_data
from app.services.runtime_config import (
    get_runtime_settings,
    get_runtime_settings_snapshot,
    summarize_runtime_settings,
    upsert_runtime_settings,
)

router = APIRouter(prefix="/settings", tags=["Settings"])


def _to_response(data: dict) -> RuntimeSettingsResponse:
    return RuntimeSettingsResponse(
        ai_prompt=data["ai_prompt"],
        is_ai_enabled=data["is_ai_enabled"],
        is_market_enabled=data["is_market_enabled"],
        has_ai_api_key=data["has_ai_api_key"],
        ai_api_key_masked=data["ai_api_key_masked"],
        retention_days=data["retention_days"],
        ad_automation_enabled=data["ad_automation_enabled"],
        ad_min_interval_minutes=data["ad_min_interval_minutes"],
        ad_quiet_hour_start=data["ad_quiet_hour_start"],
        ad_quiet_hour_end=data["ad_quiet_hour_end"],
        ad_group_blacklist=data["ad_group_blacklist"],
        bot_name=data["bot_name"],
    )


@router.get("", response_model=RuntimeSettingsResponse)
async def get_settings(
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    data = await get_runtime_settings(session)
    return _to_response(data)


@router.put("", response_model=RuntimeSettingsResponse)
async def update_settings(
    payload: RuntimeSettingsUpdateRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    before = await get_runtime_settings_snapshot(session)
    data = await upsert_runtime_settings(
        session,
        ai_prompt=payload.ai_prompt,
        is_ai_enabled=payload.is_ai_enabled,
        is_market_enabled=payload.is_market_enabled,
        ai_api_key=payload.ai_api_key,
        retention_days=payload.retention_days,
        ad_automation_enabled=payload.ad_automation_enabled,
        ad_min_interval_minutes=payload.ad_min_interval_minutes,
        ad_quiet_hour_start=payload.ad_quiet_hour_start,
        ad_quiet_hour_end=payload.ad_quiet_hour_end,
        ad_group_blacklist=payload.ad_group_blacklist,
        bot_name=payload.bot_name,
    )
    after = await get_runtime_settings_snapshot(session)
    await write_audit_log(
        session,
        actor=admin.username,
        action="settings.update",
        target="runtime_config",
        status="success",
        ip_address=http_request.client.host if http_request.client else None,
        details={
            "before": before,
            "after": after,
            "summary": summarize_runtime_settings(after),
        },
    )
    await session.commit()
    return _to_response(data)


@router.post("/rollback", response_model=RuntimeSettingsResponse)
async def rollback_settings(
    payload: RuntimeSettingsRollbackRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    query = select(AuditLog).where(AuditLog.action == "settings.update")
    if payload.audit_log_id is not None:
        query = query.where(AuditLog.id == payload.audit_log_id)
    query = query.order_by(AuditLog.created_at.desc()).limit(1)
    result = await session.execute(query)
    log = result.scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=404, detail="No settings update log found")

    details = json.loads(log.details or "{}")
    before = details.get("before")
    if not before:
        raise HTTPException(status_code=400, detail="Rollback data unavailable")

    restored = await upsert_runtime_settings(
        session,
        ai_prompt=before.get("ai_prompt"),
        is_ai_enabled=before.get("is_ai_enabled"),
        is_market_enabled=before.get("is_market_enabled"),
        retention_days=before.get("retention_days"),
        ad_automation_enabled=before.get("ad_automation_enabled"),
        ad_min_interval_minutes=before.get("ad_min_interval_minutes"),
        ad_quiet_hour_start=before.get("ad_quiet_hour_start"),
        ad_quiet_hour_end=before.get("ad_quiet_hour_end"),
        ad_group_blacklist=before.get("ad_group_blacklist"),
        bot_name=before.get("bot_name"),
    )

    await write_audit_log(
        session,
        actor=admin.username,
        action="settings.rollback",
        target=f"audit_log:{log.id}",
        status="success",
        ip_address=http_request.client.host if http_request.client else None,
        details={"restored_before": before, "source_log_id": log.id},
    )
    await session.commit()

    return _to_response(restored)


@router.get("/audit", response_model=AuditLogListResponse)
async def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action_prefix: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    items, total = await list_audit_logs(
        session,
        page=page,
        page_size=page_size,
        action_prefix=action_prefix,
    )
    return AuditLogListResponse(
        items=[
            AuditLogResponse(
                id=item.id,
                actor=item.actor,
                action=item.action,
                target=item.target,
                status=item.status,
                ip_address=item.ip_address,
                details=item.details,
                created_at=item.created_at.isoformat(),
            )
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup_data(
    payload: CleanupRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    if payload.purge_all:
        result = await purge_all_chat_and_audit_data(session)
        retention_days = None
        action = "settings.cleanup.full"
    else:
        current = await get_runtime_settings(session)
        retention_days = current["retention_days"]
        result = await cleanup_expired_data(session, retention_days=retention_days)
        action = "settings.cleanup.retention"

    await write_audit_log(
        session,
        actor=admin.username,
        action=action,
        target="chat_audit_data",
        status="success",
        ip_address=http_request.client.host if http_request.client else None,
        details={"result": result, "purge_all": payload.purge_all},
    )
    await session.commit()

    return CleanupResponse(
        messages_deleted=result.get("messages_deleted", 0),
        conversations_deleted=result.get("conversations_deleted", 0),
        audit_logs_deleted=result.get("audit_logs_deleted", 0),
        campaign_logs_deleted=result.get("campaign_logs_deleted", 0),
        retention_days=retention_days,
    )
