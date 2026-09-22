"""Runtime settings API for admin dashboard."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser, get_current_admin
from app.config import settings
from app.database import get_session
from app.models.audit import AuditLog
from app.schemas.settings import (
    AiModelVerifyRequest,
    AiModelVerifyResponse,
    AiProbeRequest,
    AiProbeResponse,
    AuditLogListResponse,
    AuditLogResponse,
    CleanupRequest,
    CleanupResponse,
    ComponentTestResponse,
    EmbeddingTestRequest,
    RuntimeSettingsResponse,
    RuntimeSettingsRollbackRequest,
    RuntimeSettingsUpdateRequest,
    SignalProbeRequest,
    SignalProbeResponse,
    VectorStoreTestRequest,
)
from app.services.ai_engine import probe_ai_compatibility, verify_ai_model_availability
from app.services.audit_log import list_audit_logs, write_audit_log
from app.services.data_retention import cleanup_expired_data, purge_all_chat_and_audit_data
from app.services.runtime_config import (
    cache_ai_probe_models,
    detect_ai_provider,
    get_runtime_settings,
    get_runtime_settings_snapshot,
    is_ai_api_key_optional,
    summarize_runtime_settings,
    upsert_runtime_settings,
)
from app.services.signal_client import signal_client

router = APIRouter(prefix="/settings", tags=["Settings"])


async def _apply_runtime_to_process(data: dict, *, restart_signal: bool) -> None:
    settings.bot_default_language = (
        str(data.get("bot_default_language") or settings.bot_default_language).strip()
        or settings.bot_default_language
    )
    await signal_client.apply_runtime_config(
        signal_api_url=str(data.get("signal_api_url") or ""),
        signal_api_token=str(data.get("signal_api_token") or ""),
        signal_phone_number=str(data.get("signal_phone_number") or ""),
        restart_listener=restart_signal,
    )


def _to_response(data: dict) -> RuntimeSettingsResponse:
    return RuntimeSettingsResponse(
        signal_api_url=data["signal_api_url"],
        signal_phone_number=data["signal_phone_number"],
        has_signal_api_token=data["has_signal_api_token"],
        signal_api_token_masked=data["signal_api_token_masked"],
        ai_prompt=data["ai_prompt"],
        is_ai_enabled=data["is_ai_enabled"],
        is_market_enabled=data["is_market_enabled"],
        has_ai_api_key=data["has_ai_api_key"],
        ai_api_key_masked=data["ai_api_key_masked"],
        ai_api_key_source=data["ai_api_key_source"],
        ai_api_base_url=data["ai_api_base_url"],
        ai_provider_detected=data["ai_provider_detected"],
        ai_model=data["ai_model"],
        ai_temperature=data["ai_temperature"],
        ai_max_tokens=data["ai_max_tokens"],
        ai_context_messages=data["ai_context_messages"],
        ai_models_cached=data.get("ai_models_cached", []),
        ai_models_cached_invalid=data.get("ai_models_cached_invalid", []),
        ai_models_listed_total=data.get("ai_models_listed_total", 0),
        ai_models_cached_at=data.get("ai_models_cached_at"),
        embedding_base_url=data.get("embedding_base_url", ""),
        embedding_model=data.get("embedding_model", "text-embedding-3-small"),
        has_embedding_api_key=data.get("has_embedding_api_key", False),
        embedding_api_key_masked=data.get("embedding_api_key_masked", ""),
        vector_store_provider=data.get("vector_store_provider", "qdrant"),
        qdrant_url=data.get("qdrant_url", "http://localhost:6333"),
        has_qdrant_api_key=data.get("has_qdrant_api_key", False),
        qdrant_api_key_masked=data.get("qdrant_api_key_masked", ""),
        rag_enabled=data.get("rag_enabled", True),
        retention_days=data["retention_days"],
        ad_automation_enabled=data["ad_automation_enabled"],
        ad_min_interval_minutes=data["ad_min_interval_minutes"],
        ad_quiet_hour_start=data["ad_quiet_hour_start"],
        ad_quiet_hour_end=data["ad_quiet_hour_end"],
        ad_group_blacklist=data["ad_group_blacklist"],
        bot_name=data["bot_name"],
        bot_default_language=data["bot_default_language"],
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
    current = await get_runtime_settings(session)
    signal_config_changed = any(
        value is not None
        for value in (
            payload.signal_api_url,
            payload.signal_api_token,
            payload.signal_phone_number,
        )
    )

    target_base_url = (payload.ai_api_base_url or "").strip()
    if not target_base_url:
        target_base_url = (current.get("ai_api_base_url") or "").strip()

    if payload.ai_api_key is not None and not payload.ai_api_key.strip():
        if not is_ai_api_key_optional(target_base_url):
            raise HTTPException(
                status_code=400,
                detail="Please provide an API key.",
            )

    before = await get_runtime_settings_snapshot(session)
    data = await upsert_runtime_settings(
        session,
        signal_api_url=payload.signal_api_url,
        signal_api_token=payload.signal_api_token,
        signal_phone_number=payload.signal_phone_number,
        ai_prompt=payload.ai_prompt,
        is_ai_enabled=payload.is_ai_enabled,
        is_market_enabled=payload.is_market_enabled,
        ai_api_key=payload.ai_api_key,
        ai_api_base_url=payload.ai_api_base_url,
        ai_model=payload.ai_model,
        ai_temperature=payload.ai_temperature,
        ai_max_tokens=payload.ai_max_tokens,
        ai_context_messages=payload.ai_context_messages,
        embedding_base_url=payload.embedding_base_url,
        embedding_api_key=payload.embedding_api_key,
        embedding_model=payload.embedding_model,
        vector_store_provider=payload.vector_store_provider,
        qdrant_url=payload.qdrant_url,
        qdrant_api_key=payload.qdrant_api_key,
        rag_enabled=payload.rag_enabled,
        retention_days=payload.retention_days,
        ad_automation_enabled=payload.ad_automation_enabled,
        ad_min_interval_minutes=payload.ad_min_interval_minutes,
        ad_quiet_hour_start=payload.ad_quiet_hour_start,
        ad_quiet_hour_end=payload.ad_quiet_hour_end,
        ad_group_blacklist=payload.ad_group_blacklist,
        bot_name=payload.bot_name,
        bot_default_language=payload.bot_default_language,
    )
    await _apply_runtime_to_process(data, restart_signal=signal_config_changed)
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


@router.post("/signal/test", response_model=SignalProbeResponse)
async def test_signal_connection(
    payload: SignalProbeRequest,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    runtime = await get_runtime_settings(session)
    stored_url = (runtime.get("signal_api_url") or "").strip()
    signal_api_url = (payload.signal_api_url or stored_url).strip()
    signal_phone_number = (
        payload.signal_phone_number or runtime.get("signal_phone_number") or ""
    ).strip()

    # SECURITY: Prevent SSRF / token leakage.
    # If the user provides a custom URL that differs from the stored config,
    # do NOT fall back to the stored token — only use the explicitly provided one.
    # This prevents an attacker from pointing the test at their own server
    # and capturing the real API token via the Authorization header.
    custom_url_provided = (
        payload.signal_api_url is not None
        and payload.signal_api_url.strip()
        and payload.signal_api_url.strip() != stored_url
    )

    if custom_url_provided:
        # Only use explicitly provided token for non-stored URLs
        signal_api_token = (payload.signal_api_token or "").strip()
    else:
        # Standard test against known URL — allow stored token fallback
        signal_api_token = (
            payload.signal_api_token.strip()
            if payload.signal_api_token is not None and payload.signal_api_token.strip()
            else (runtime.get("signal_api_token") or "")
        )

    result = await signal_client.test_connection(
        signal_api_url=signal_api_url,
        signal_api_token=signal_api_token,
        signal_phone_number=signal_phone_number,
    )

    return SignalProbeResponse(
        ok=bool(result.get("ok")),
        message=str(result.get("message") or "Signal test completed"),
        status_code=result.get("status_code"),
        latency_ms=int(result.get("latency_ms") or 0),
        listener_running=signal_client.is_running,
        listener_connected=signal_client.is_connected,
    )


@router.post("/embedding/test", response_model=ComponentTestResponse)
async def test_embedding_connection(
    payload: EmbeddingTestRequest,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    current = await get_runtime_settings(session)
    base_url = (payload.embedding_base_url or current.get("embedding_base_url") or "").strip()
    model = (
        payload.embedding_model or current.get("embedding_model") or "text-embedding-3-small"
    ).strip()
    api_key = (
        payload.embedding_api_key
        if payload.embedding_api_key is not None
        else current.get("embedding_api_key", "")
    )

    if not base_url and not current.get("embedding_base_url"):
        base_url = current.get("ai_api_base_url", "")
    if not api_key:
        api_key = current.get("ai_api_key", "")

    if not base_url:
        return ComponentTestResponse(
            ok=False,
            configured=False,
            connected=False,
            message="Embedding endpoint not configured (base URL is empty)",
        )

    start = time.perf_counter()
    try:
        from app.ai.providers.embeddings import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider(
            api_key=api_key or "sk-dummy",
            base_url=base_url,
            model=model,
        )
        res = await provider.embed_query("ping")
        latency = int((time.perf_counter() - start) * 1000)
        if len(res) > 0:
            return ComponentTestResponse(
                ok=True,
                configured=True,
                connected=True,
                latency_ms=latency,
                message=f"Embedding provider connected ({model}, dim={len(res)})",
            )
        return ComponentTestResponse(
            ok=False,
            configured=True,
            connected=False,
            latency_ms=latency,
            message="Embedding provider returned empty vector",
        )
    except Exception as e:
        latency = int((time.perf_counter() - start) * 1000)
        return ComponentTestResponse(
            ok=False,
            configured=True,
            connected=False,
            error=str(e)[:300],
            latency_ms=latency,
            message=f"Embedding connection failed: {str(e)[:150]}",
        )


@router.post("/vector-store/test", response_model=ComponentTestResponse)
async def test_vector_store_connection(
    payload: VectorStoreTestRequest,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    current = await get_runtime_settings(session)
    provider = (
        payload.vector_store_provider or current.get("vector_store_provider") or "qdrant"
    ).strip()
    url = (payload.qdrant_url or current.get("qdrant_url") or "http://localhost:6333").strip()
    api_key = (
        payload.qdrant_api_key
        if payload.qdrant_api_key is not None
        else current.get("qdrant_api_key", "")
    )

    if not url:
        return ComponentTestResponse(
            ok=False,
            configured=False,
            connected=False,
            message="Vector store URL not configured",
        )

    start = time.perf_counter()
    try:
        from app.ai.rag.qdrant_store import QdrantStore

        store = QdrantStore(url=url, api_key=api_key or None)
        collections = await store.client.get_collections()
        latency = int((time.perf_counter() - start) * 1000)
        count = len(collections.collections) if hasattr(collections, "collections") else 0
        return ComponentTestResponse(
            ok=True,
            configured=True,
            connected=True,
            latency_ms=latency,
            message=f"Vector store connected successfully ({provider}, {count} collections)",
        )
    except Exception as e:
        latency = int((time.perf_counter() - start) * 1000)
        return ComponentTestResponse(
            ok=False,
            configured=True,
            connected=False,
            error=str(e)[:300],
            latency_ms=latency,
            message=f"Vector store connection failed: {str(e)[:150]}",
        )


@router.post("/ai/probe", response_model=AiProbeResponse)
async def probe_ai_settings(
    payload: AiProbeRequest,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    runtime = await get_runtime_settings(session)

    base_url = (payload.ai_api_base_url or runtime.get("ai_api_base_url") or "").strip()
    model = (payload.ai_model or runtime.get("ai_model") or "").strip()

    if payload.ai_api_key and payload.ai_api_key.strip():
        api_key = payload.ai_api_key.strip()
    else:
        api_key = runtime.get("ai_api_key") or ""

    if not base_url:
        raise HTTPException(status_code=400, detail="AI base URL is required for probe")
    if not api_key and not is_ai_api_key_optional(base_url):
        raise HTTPException(status_code=400, detail="API key is required for probe")

    result = await probe_ai_compatibility(
        base_url=base_url,
        api_key=api_key,
        model=model,
    )

    provider_detected = detect_ai_provider(base_url)
    await cache_ai_probe_models(
        session,
        listed_models=result.get("listed_models", []),
        valid_models=result.get("valid_models", []),
        invalid_models=result.get("invalid_models", []),
        listed_total=int(result.get("listed_total") or 0),
        verified_total=int(result.get("verified_total") or 0),
        provider_detected=provider_detected,
        requested_base_url=base_url,
        effective_base_url=result.get("base_url"),
        message=result.get("message", "Probe completed"),
        probe_ok=bool(result.get("ok")),
    )

    latest_runtime = await get_runtime_settings(session)
    cached_models = latest_runtime.get("ai_models_cached", []) or []
    cached_invalid = latest_runtime.get("ai_models_cached_invalid", []) or []
    listed_total = int(latest_runtime.get("ai_models_listed_total") or 0)
    response_models = cached_models if cached_models else result.get("valid_models", [])

    return AiProbeResponse(
        ok=result["ok"],
        provider_detected=provider_detected,
        requested_base_url=base_url,
        candidate_base_urls=result.get("base_candidates", []),
        verification_base_candidates=result.get("verification_base_candidates", []),
        effective_base_url=result.get("base_url"),
        effective_model=result.get("model"),
        models=response_models,
        invalid_models=[{"model": model, "reason": "unavailable"} for model in cached_invalid],
        listed_total=listed_total,
        models_count=len(response_models),
        verified_total=int(result.get("verified_total") or 0),
        probed_at=datetime.now(UTC).isoformat(),
        cached_at=latest_runtime.get("ai_models_cached_at"),
        message=result.get("message", "Probe completed"),
        preview=result.get("preview") or None,
        attempts=result.get("attempts", []),
    )


@router.post("/ai/verify-model", response_model=AiModelVerifyResponse)
async def verify_ai_model(
    payload: AiModelVerifyRequest,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    runtime = await get_runtime_settings(session)

    base_url = (payload.ai_api_base_url or runtime.get("ai_api_base_url") or "").strip()
    model = (payload.ai_model or "").strip()

    if payload.ai_api_key and payload.ai_api_key.strip():
        api_key = payload.ai_api_key.strip()
    else:
        api_key = runtime.get("ai_api_key") or ""

    if not base_url:
        raise HTTPException(
            status_code=400, detail="AI base URL is required for model verification"
        )
    if not model:
        raise HTTPException(status_code=400, detail="AI model is required for model verification")
    if not api_key and not is_ai_api_key_optional(base_url):
        raise HTTPException(status_code=400, detail="API key is required for model verification")

    result = await verify_ai_model_availability(
        base_url=base_url,
        api_key=api_key,
        model=model,
    )

    return AiModelVerifyResponse(
        ok=bool(result.get("ok")),
        model=str(result.get("model") or model),
        effective_model=result.get("effective_model"),
        effective_base_url=result.get("effective_base_url"),
        checked_at=str(result.get("checked_at")),
        message=str(result.get("message") or "Model verification completed"),
        preview=result.get("preview"),
        attempts=result.get("attempts", []),
    )


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
        signal_api_url=before.get("signal_api_url"),
        signal_phone_number=before.get("signal_phone_number"),
        ai_prompt=before.get("ai_prompt"),
        is_ai_enabled=before.get("is_ai_enabled"),
        is_market_enabled=before.get("is_market_enabled"),
        ai_api_base_url=before.get("ai_api_base_url"),
        ai_model=before.get("ai_model"),
        ai_temperature=before.get("ai_temperature"),
        ai_max_tokens=before.get("ai_max_tokens"),
        ai_context_messages=before.get("ai_context_messages"),
        retention_days=before.get("retention_days"),
        ad_automation_enabled=before.get("ad_automation_enabled"),
        ad_min_interval_minutes=before.get("ad_min_interval_minutes"),
        ad_quiet_hour_start=before.get("ad_quiet_hour_start"),
        ad_quiet_hour_end=before.get("ad_quiet_hour_end"),
        ad_group_blacklist=before.get("ad_group_blacklist"),
        bot_name=before.get("bot_name"),
        bot_default_language=before.get("bot_default_language"),
    )
    await _apply_runtime_to_process(restored, restart_signal=True)

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
        users_deleted=result.get("users_deleted", 0),
        orders_deleted=result.get("orders_deleted", 0),
        payments_deleted=result.get("payments_deleted", 0),
        groups_deleted=result.get("groups_deleted", 0),
        retention_days=retention_days,
    )
