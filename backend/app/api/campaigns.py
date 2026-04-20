"""Campaign APIs for group advertising and controlled broadcast operations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser, get_current_admin
from app.database import get_session
from app.models.campaign import CampaignDeliveryLog
from app.models.group import Group
from app.schemas.settings import (
    CampaignBroadcastGroupResult,
    CampaignBroadcastRequest,
    CampaignBroadcastResponse,
)
from app.services.audit_log import write_audit_log
from app.services.runtime_config import get_runtime_settings
from app.services.signal_client import signal_client

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


def _normalize_group_id(group_id: str) -> str:
    if group_id.startswith("group."):
        return group_id[6:]
    return group_id


def _build_group_recipient(group_id: str) -> str:
    normalized = _normalize_group_id(group_id)
    return f"group.{normalized}"


def _is_in_quiet_hours(current_hour: int, start_hour: int, end_hour: int) -> bool:
    if start_hour == end_hour:
        return False
    if start_hour < end_hour:
        return start_hour <= current_hour < end_hour
    return current_hour >= start_hour or current_hour < end_hour


@router.post("/broadcast", response_model=CampaignBroadcastResponse)
async def run_broadcast(
    payload: CampaignBroadcastRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    settings_data = await get_runtime_settings(session)
    if not settings_data["ad_automation_enabled"]:
        raise HTTPException(status_code=400, detail="Ad automation is disabled in settings")

    targets_result = await session.execute(
        select(Group.group_id).where(Group.is_active == True)  # noqa: E712
    )
    active_group_ids = [_normalize_group_id(group_id) for group_id in targets_result.scalars().all()]
    if payload.target_group_ids:
        requested = {_normalize_group_id(group_id) for group_id in payload.target_group_ids}
        target_group_ids = [group_id for group_id in active_group_ids if group_id in requested]
    else:
        target_group_ids = active_group_ids

    if not target_group_ids:
        raise HTTPException(status_code=400, detail="No active target groups available")

    now = datetime.now()
    current_hour = now.hour
    quiet_start = settings_data["ad_quiet_hour_start"]
    quiet_end = settings_data["ad_quiet_hour_end"]
    in_quiet_hours = _is_in_quiet_hours(current_hour, quiet_start, quiet_end)
    blacklist = {entry.strip() for entry in settings_data["ad_group_blacklist"]}
    message_hash = hashlib.sha256(payload.message.strip().encode("utf-8")).hexdigest()
    min_interval_delta = timedelta(minutes=settings_data["ad_min_interval_minutes"])
    min_allowed_time = now - min_interval_delta

    items: list[CampaignBroadcastGroupResult] = []
    sent = 0
    skipped = 0
    failed = 0

    for group_id in target_group_ids:
        if group_id in blacklist:
            skipped += 1
            items.append(
                CampaignBroadcastGroupResult(
                    group_id=group_id,
                    status="skipped",
                    reason="blacklisted",
                )
            )
            session.add(
                CampaignDeliveryLog(
                    campaign_name=payload.campaign_name,
                    group_id=group_id,
                    message_hash=message_hash,
                    status="skipped",
                    reason="blacklisted",
                    details=None,
                )
            )
            continue

        if in_quiet_hours:
            skipped += 1
            items.append(
                CampaignBroadcastGroupResult(
                    group_id=group_id,
                    status="skipped",
                    reason="quiet_hours",
                )
            )
            session.add(
                CampaignDeliveryLog(
                    campaign_name=payload.campaign_name,
                    group_id=group_id,
                    message_hash=message_hash,
                    status="skipped",
                    reason="quiet_hours",
                    details=f"hour={current_hour}, quiet={quiet_start}-{quiet_end}",
                )
            )
            continue

        latest_success_result = await session.execute(
            select(CampaignDeliveryLog.created_at)
            .where(
                CampaignDeliveryLog.group_id == group_id,
                CampaignDeliveryLog.status == "sent",
            )
            .order_by(CampaignDeliveryLog.created_at.desc())
            .limit(1)
        )
        latest_success_at = latest_success_result.scalar_one_or_none()
        if latest_success_at and latest_success_at > min_allowed_time:
            skipped += 1
            items.append(
                CampaignBroadcastGroupResult(
                    group_id=group_id,
                    status="skipped",
                    reason="min_interval",
                )
            )
            session.add(
                CampaignDeliveryLog(
                    campaign_name=payload.campaign_name,
                    group_id=group_id,
                    message_hash=message_hash,
                    status="skipped",
                    reason="min_interval",
                    details=f"latest_success_at={latest_success_at.isoformat()}",
                )
            )
            continue

        if payload.dry_run:
            skipped += 1
            items.append(
                CampaignBroadcastGroupResult(
                    group_id=group_id,
                    status="dry_run",
                    reason="dry_run",
                )
            )
            session.add(
                CampaignDeliveryLog(
                    campaign_name=payload.campaign_name,
                    group_id=group_id,
                    message_hash=message_hash,
                    status="dry_run",
                    reason="dry_run",
                    details=None,
                )
            )
            continue

        recipient = _build_group_recipient(group_id)
        ok = await signal_client.send_reply(text=payload.message, recipient=recipient)
        if ok:
            sent += 1
            items.append(
                CampaignBroadcastGroupResult(
                    group_id=group_id,
                    status="sent",
                    reason=None,
                )
            )
            session.add(
                CampaignDeliveryLog(
                    campaign_name=payload.campaign_name,
                    group_id=group_id,
                    message_hash=message_hash,
                    status="sent",
                    reason=None,
                    details=None,
                )
            )
        else:
            failed += 1
            items.append(
                CampaignBroadcastGroupResult(
                    group_id=group_id,
                    status="failed",
                    reason="gateway_send_failed",
                )
            )
            session.add(
                CampaignDeliveryLog(
                    campaign_name=payload.campaign_name,
                    group_id=group_id,
                    message_hash=message_hash,
                    status="failed",
                    reason="gateway_send_failed",
                    details=None,
                )
            )

    attempted = len(target_group_ids)
    audit_status = "success" if failed == 0 else "partial"
    await write_audit_log(
        session,
        actor=admin.username,
        action="campaign.broadcast",
        target=payload.campaign_name,
        status=audit_status,
        ip_address=http_request.client.host if http_request.client else None,
        details={
            "campaign_name": payload.campaign_name,
            "attempted": attempted,
            "sent": sent,
            "skipped": skipped,
            "failed": failed,
            "dry_run": payload.dry_run,
            "message_length": len(payload.message),
            "targets": target_group_ids,
            "results": [item.model_dump() for item in items],
            "policy": {
                "quiet_start": quiet_start,
                "quiet_end": quiet_end,
                "min_interval_minutes": settings_data["ad_min_interval_minutes"],
                "blacklist_size": len(blacklist),
            },
        },
    )
    await session.commit()

    return CampaignBroadcastResponse(
        campaign_name=payload.campaign_name,
        attempted=attempted,
        sent=sent,
        skipped=skipped,
        failed=failed,
        dry_run=payload.dry_run,
        items=items,
    )


@router.get("/summary")
async def get_campaign_summary(
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    total_result = await session.execute(select(func.count(CampaignDeliveryLog.id)))
    sent_result = await session.execute(
        select(func.count(CampaignDeliveryLog.id)).where(CampaignDeliveryLog.status == "sent")
    )
    failed_result = await session.execute(
        select(func.count(CampaignDeliveryLog.id)).where(CampaignDeliveryLog.status == "failed")
    )
    recent_result = await session.execute(
        select(CampaignDeliveryLog)
        .order_by(CampaignDeliveryLog.created_at.desc())
        .limit(20)
    )
    recent_rows = recent_result.scalars().all()

    return {
        "total_attempts": total_result.scalar_one(),
        "total_sent": sent_result.scalar_one(),
        "total_failed": failed_result.scalar_one(),
        "recent": [
            {
                "id": row.id,
                "campaign_name": row.campaign_name,
                "group_id": row.group_id,
                "status": row.status,
                "reason": row.reason,
                "created_at": row.created_at.isoformat(),
                "details": json.loads(row.details) if row.details and row.details.startswith("{") else row.details,
            }
            for row in recent_rows
        ],
    }
