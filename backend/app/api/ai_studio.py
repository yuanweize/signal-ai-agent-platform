"""
AI Studio API: Management console routes for Knowledge, Memory, Skills, MCP, Learning, Evals, and Traces.
"""

from __future__ import annotations

import json
import math
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import and_, desc, or_, select
from sqlalchemy import func as sa_func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import case as sa_case

from app.ai.evals.runner import eval_runner
from app.ai.learning.curation import CandidateConflictError, learning_service
from app.ai.learning.examples import dataset_exporter
from app.ai.mcp.client import mcp_manager, parse_and_decrypt_env
from app.ai.prompts.manager import prompt_manager
from app.ai.rag.ingestion import KnowledgeIngestionService
from app.ai.runtime.factory import get_production_agent_runtime
from app.ai.skills.registry import skill_registry
from app.api.deps import AdminUser, get_current_admin
from app.database import get_session
from app.models.ai import (
    AIModelCall,
    AIRun,
    AISuggestion,
    EvaluationRun,
    FeedbackEvent,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    LearningCandidate,
    MCPServerConfig,
    MemoryItem,
    PromptVersion,
    ToolInvocation,
    TrainingExample,
)
from app.models.config import BotConfig
from app.schemas.ai import (
    AIOverviewMetricsDTO,
    AIRunDTO,
    CreateDocumentRequest,
    CreateFAQRequest,
    CreateKnowledgeSourceRequest,
    CreateMCPServerRequest,
    CreateMemoryRequest,
    CreatePromptVersionRequest,
    EvaluationRunDTO,
    EvaluationSuiteResultDTO,
    KnowledgeDocumentDTO,
    KnowledgeSearchResultDTO,
    KnowledgeSourceDetailDTO,
    KnowledgeSourceDTO,
    LearningCandidateDTO,
    MCPServerDetailDTO,
    MCPServerDTO,
    MemoryItemDTO,
    ModelUsageItemDTO,
    ModelUsageResponseDTO,
    PromoteCandidateRequest,
    PromptVersionDTO,
    ProviderLiveTestRequest,
    ProviderLiveTestResponse,
    SkillDTO,
    ToggleSkillRequest,
    TrainingStatsDTO,
    UpdateMCPServerRequest,
    UsageSummaryDTO,
    UsageTimeseriesPointDTO,
    UsageTimeseriesResponseDTO,
)
from app.services.audit_log import write_audit_log
from app.services.runtime_config import encrypt_value
from app.services.sandbox import get_or_create_sandbox_conversation

router = APIRouter(prefix="/ai-studio", tags=["AI Studio"])


# ---------------------------------------------------------------------------
# 1. Overview & Traces
# ---------------------------------------------------------------------------


def require_rag_runtime(runtime: Any) -> None:
    """Ensure RAG infrastructure (embedding provider, vector store, retriever) is configured and active."""
    if not getattr(runtime, "vector_store", None) or not getattr(
        runtime, "embedding_provider", None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RAG is disabled or unconfigured. Please configure Embedding and Vector Store in Settings.",
        )


def resolve_time_bounds(
    time_range: str,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
) -> tuple[datetime | None, datetime | None]:
    """Calculate start and end datetime bounds for analytics queries."""
    now = datetime.now(UTC).replace(tzinfo=None)
    if from_time or to_time:
        return from_time, to_time or now
    if time_range == "24h":
        return now - timedelta(hours=24), now
    if time_range == "7d":
        return now - timedelta(days=7), now
    if time_range == "30d":
        return now - timedelta(days=30), now
    if time_range == "all":
        return None, None
    raise HTTPException(
        status_code=422,
        detail=f"Invalid time_range: '{time_range}'. Expected one of: 24h, 7d, 30d, all.",
    )


def compute_percentiles(
    latencies: list[int | float],
) -> tuple[float | None, float | None, float | None]:
    """Calculate exact P50, P95, and P99 latencies without fake targets."""
    if not latencies:
        return None, None, None
    sorted_lats = sorted(latencies)
    n = len(sorted_lats)

    def p(pct: float) -> float:
        k = (n - 1) * pct
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return float(sorted_lats[int(k)])
        return float(sorted_lats[f] * (c - k) + sorted_lats[c] * (k - f))

    return round(p(0.50), 1), round(p(0.95), 1), round(p(0.99), 1)


@router.get("/overview", response_model=AIOverviewMetricsDTO)
async def get_ai_overview_metrics(
    time_range: str = Query("all"),
    from_time: datetime | None = Query(None),
    to_time: datetime | None = Query(None),
    include_eval: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Return aggregated platform metrics across runs, copilot suggestions, and memory within time range."""
    t_start, t_end = resolve_time_bounds(time_range, from_time, to_time)

    # Filter out evaluation and test traffic by default so evaluations never pollute production KPIs
    run_filters = []
    if not include_eval:
        run_filters.append(AIRun.traffic_source == "production")
    if t_start:
        run_filters.append(AIRun.created_at >= t_start)
    if t_end:
        run_filters.append(AIRun.created_at <= t_end)

    total_runs = (
        await session.execute(select(sa_func.count(AIRun.id)).where(*run_filters))
    ).scalar() or 0
    error_runs = (
        await session.execute(
            select(sa_func.count(AIRun.id)).where(
                *run_filters, AIRun.errors.is_not(None), AIRun.errors != ""
            )
        )
    ).scalar() or 0
    successful_runs = total_runs - error_runs
    error_rate = round(error_runs / total_runs, 3) if total_runs > 0 else 0.0

    # Latencies (computed via SQL avg and bounded percentile scan)
    avg_lat_val = (
        await session.execute(
            select(sa_func.avg(AIRun.latency_ms)).where(*run_filters, AIRun.latency_ms.is_not(None))
        )
    ).scalar()
    avg_lat = round(float(avg_lat_val), 1) if avg_lat_val is not None else 0.0

    lat_filters = [*run_filters, AIRun.latency_ms.is_not(None)]
    n_lat = (
        await session.execute(select(sa_func.count(AIRun.id)).where(*lat_filters))
    ).scalar() or 0

    async def _pct(pct: float) -> float | None:
        if n_lat == 0:
            return None
        k = (n_lat - 1) * pct
        f, c = math.floor(k), math.ceil(k)
        vals = (
            (
                await session.execute(
                    select(AIRun.latency_ms)
                    .where(*lat_filters)
                    .order_by(AIRun.latency_ms.asc())
                    .offset(f)
                    .limit(c - f + 1)
                )
            )
            .scalars()
            .all()
        )
        if not vals:
            return None
        if len(vals) == 1 or f == c:
            return round(float(vals[0]), 1)
        return round(float(vals[0] * (c - k) + vals[1] * (k - f)), 1)

    p50, p95, p99 = await _pct(0.50), await _pct(0.95), await _pct(0.99)

    # Token aggregates & cost
    tok_res = (
        await session.execute(
            select(
                sa_func.sum(AIRun.total_tokens),
                sa_func.sum(AIRun.input_tokens),
                sa_func.sum(AIRun.output_tokens),
                sa_func.sum(AIRun.cached_input_tokens),
                sa_func.sum(AIRun.reasoning_tokens),
                sa_func.sum(AIRun.estimated_cost),
            ).where(*run_filters)
        )
    ).one_or_none()

    total_tokens = int(tok_res[0]) if tok_res and tok_res[0] is not None else 0
    input_tokens = int(tok_res[1]) if tok_res and tok_res[1] is not None else None
    output_tokens = int(tok_res[2]) if tok_res and tok_res[2] is not None else None
    cached_input_tokens = int(tok_res[3]) if tok_res and tok_res[3] is not None else None
    reasoning_tokens = int(tok_res[4]) if tok_res and tok_res[4] is not None else None
    estimated_cost = round(float(tok_res[5]), 5) if tok_res and tok_res[5] is not None else None

    # Suggestions within time boundary
    sug_filters = []
    if t_start:
        sug_filters.append(AISuggestion.generated_at >= t_start)
    if t_end:
        sug_filters.append(AISuggestion.generated_at <= t_end)

    total_sugs = (
        await session.execute(select(sa_func.count(AISuggestion.id)).where(*sug_filters))
    ).scalar() or 0
    accepted_sugs = (
        await session.execute(
            select(sa_func.count(AISuggestion.id)).where(
                *sug_filters, AISuggestion.status == "accepted"
            )
        )
    ).scalar() or 0
    edited_sugs = (
        await session.execute(
            select(sa_func.count(AISuggestion.id)).where(
                *sug_filters, AISuggestion.status == "edited"
            )
        )
    ).scalar() or 0
    rejected_sugs = (
        await session.execute(
            select(sa_func.count(AISuggestion.id)).where(
                *sug_filters, AISuggestion.status == "rejected"
            )
        )
    ).scalar() or 0
    auto_sent = (
        await session.execute(
            select(sa_func.count(AISuggestion.id)).where(
                *sug_filters, AISuggestion.status == "auto_sent"
            )
        )
    ).scalar() or 0

    # True average of edit ratio for edited suggestions
    avg_edit_ratio_val = (
        await session.execute(
            select(sa_func.avg(AISuggestion.edit_ratio)).where(
                *sug_filters, AISuggestion.status == "edited"
            )
        )
    ).scalar()
    copilot_avg_edit_ratio = (
        round(float(avg_edit_ratio_val), 3) if avg_edit_ratio_val is not None else 0.0
    )

    fb_filters = [FeedbackEvent.event_type == "human_takeover"]
    if t_start:
        fb_filters.append(FeedbackEvent.created_at >= t_start)
    if t_end:
        fb_filters.append(FeedbackEvent.created_at <= t_end)
    manual_takeovers = (
        await session.execute(select(sa_func.count(FeedbackEvent.id)).where(*fb_filters))
    ).scalar() or 0

    human_reviewed = accepted_sugs + edited_sugs + rejected_sugs
    acc_rate = round(accepted_sugs / human_reviewed, 3) if human_reviewed > 0 else 0.0
    edit_rate = round(edited_sugs / human_reviewed, 3) if human_reviewed > 0 else 0.0
    rej_rate = round(rejected_sugs / human_reviewed, 3) if human_reviewed > 0 else 0.0

    auto_rate = round(auto_sent / total_runs, 3) if total_runs > 0 else 0.0
    copilot_rate = round(total_sugs / total_runs, 3) if total_runs > 0 else 0.0
    takeover_rate = round(manual_takeovers / total_runs, 3) if total_runs > 0 else 0.0

    # RAG hit rate
    runs_with_rag = (
        await session.execute(
            select(sa_func.count(AIRun.id)).where(
                *run_filters,
                AIRun.retrieval.is_not(None),
                AIRun.retrieval != "[]",
                AIRun.retrieval != "",
            )
        )
    ).scalar() or 0
    actual_rag_hit_rate = round(runs_with_rag / total_runs, 3) if total_runs > 0 else 0.0

    # Tool Invocations (exclude evaluation and provider_test traffic from production KPIs)
    tool_filters = []
    if t_start:
        tool_filters.append(ToolInvocation.created_at >= t_start)
    if t_end:
        tool_filters.append(ToolInvocation.created_at <= t_end)

    tool_base = select(ToolInvocation.id)
    if not include_eval:
        tool_base = tool_base.outerjoin(AIRun, ToolInvocation.ai_run_id == AIRun.id).where(
            or_(AIRun.traffic_source == "production", ToolInvocation.ai_run_id.is_(None))
        )
    if tool_filters:
        tool_base = tool_base.where(*tool_filters)

    total_tool_calls = (
        await session.execute(select(sa_func.count()).select_from(tool_base.subquery()))
    ).scalar() or 0
    successful_tool_calls = (
        await session.execute(
            select(sa_func.count()).select_from(
                tool_base.where(ToolInvocation.status == "success").subquery()
            )
        )
    ).scalar() or 0
    approved_tool_calls = (
        await session.execute(
            select(sa_func.count()).select_from(
                tool_base.where(ToolInvocation.is_approved.is_(True)).subquery()
            )
        )
    ).scalar() or 0
    tool_call_success_rate = (
        round(successful_tool_calls / total_tool_calls, 3) if total_tool_calls > 0 else 0.0
    )
    tool_approval_rate = (
        round(approved_tool_calls / total_tool_calls, 3) if total_tool_calls > 0 else 0.0
    )

    # Knowledge & Memory item counts
    docs_count = (await session.execute(select(sa_func.count(KnowledgeDocument.id)))).scalar() or 0
    sources_count = (await session.execute(select(sa_func.count(KnowledgeSource.id)))).scalar() or 0
    chunks_count = (await session.execute(select(sa_func.count(KnowledgeChunk.id)))).scalar() or 0
    memory_count = (await session.execute(select(sa_func.count(MemoryItem.id)))).scalar() or 0

    return AIOverviewMetricsDTO(
        total_ai_runs=total_runs,
        total_runs=total_runs,
        successful_runs=successful_runs,
        error_runs=error_runs,
        error_rate=error_rate,
        automation_rate=auto_rate,
        copilot_rate=copilot_rate,
        human_takeover_rate=takeover_rate,
        suggestion_acceptance_rate=acc_rate,
        copilot_acceptance_rate=acc_rate,
        copilot_suggestions_count=total_sugs,
        suggestion_edit_rate=edit_rate,
        copilot_avg_edit_ratio=copilot_avg_edit_ratio,
        suggestion_rejection_rate=rej_rate,
        rag_hit_rate=actual_rag_hit_rate,
        tool_call_success_rate=tool_call_success_rate,
        tool_approval_rate=tool_approval_rate,
        memory_items_count=memory_count,
        knowledge_documents_count=docs_count,
        knowledge_sources_count=sources_count,
        knowledge_chunks_count=chunks_count,
        average_latency_ms=avg_lat,
        avg_latency_ms=avg_lat,
        p50_latency_ms=p50,
        p95_latency_ms=p95,
        p99_latency_ms=p99,
        total_tokens_used=total_tokens,
        total_tokens=total_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
        reasoning_tokens=reasoning_tokens,
        tokens_source="provider" if total_tokens > 0 else "unavailable",
        estimated_cost=estimated_cost,
        cost_currency="USD",
        time_range=time_range,
        timezone="UTC",
    )


@router.get("/diagnostics")
async def get_ai_diagnostics(
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Observable status of real AI providers: LLM, Embedding, Vector Store, MCP, and Gateway."""
    from app.config import settings
    from app.services.runtime_config import get_runtime_settings
    from app.services.signal_client import signal_client

    runtime_cfg = await get_runtime_settings(session)
    runtime = await get_production_agent_runtime(session)

    # 1. LLM status
    llm_prov = runtime.llm_provider
    if type(llm_prov).__name__ == "DisabledLLMProvider" or not runtime_cfg.get("is_ai_enabled"):
        llm_status = "disabled"
    else:
        llm_configured = bool(
            getattr(llm_prov, "api_key", None) and getattr(llm_prov, "api_key") != "__NO_KEY__"
        )
        if not llm_configured:
            llm_status = (
                "not_validated" if getattr(llm_prov, "api_key_optional", False) else "degraded"
            )
        else:
            current_model = (runtime_cfg.get("ai_model") or "gpt-4o-mini").strip()
            # Ensure verification is bound to current configuration timestamp
            ai_cfg_keys = ["ai_api_key_enc", "ai_model", "ai_api_base_url"]
            last_cfg_update = (
                await session.execute(
                    select(sa_func.max(BotConfig.updated_at)).where(BotConfig.key.in_(ai_cfg_keys))
                )
            ).scalar()

            verify_query = select(AIRun.id).where(
                AIRun.model == getattr(llm_prov, "default_model", current_model),
                (AIRun.traffic_source == "provider_test")
                | AIRun.errors.is_(None)
                | (AIRun.errors == ""),
                AIRun.created_at >= datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24),
            )
            if last_cfg_update is not None:
                verify_query = verify_query.where(AIRun.created_at >= last_cfg_update)

            recent_success = (await session.execute(verify_query.limit(1))).scalar_one_or_none()
            llm_status = "live_verified" if recent_success else "configured"

    # 2. Embedding status
    emb_prov = runtime.embedding_provider
    if not runtime_cfg.get("rag_enabled"):
        emb_status = "disabled"
    else:
        emb_configured = bool(
            getattr(emb_prov, "api_key", None) and getattr(emb_prov, "api_key") != "__NO_KEY__"
        )
        emb_status = "configured" if emb_configured else "not_validated"

    # 3. Vector store status
    vec_store = runtime.vector_store
    if not runtime_cfg.get("rag_enabled") or vec_store is None:
        vec_provider = "none"
        vec_status = "disabled"
    else:
        vec_provider = type(vec_store).__name__
        vec_status = "configured"
        if hasattr(vec_store, "check_health"):
            try:
                is_healthy = await vec_store.check_health()
                vec_status = "connected" if is_healthy else "degraded"
            except Exception:
                vec_status = "degraded"
        elif hasattr(vec_store, "client") and getattr(vec_store, "client") is not None:
            try:
                await vec_store.client.get_collections()
                vec_status = "connected"
            except Exception:
                vec_status = "degraded"
        elif vec_provider == "FakeVectorStore":
            vec_status = "degraded" if settings.environment != "test" else "configured"

    # 4. RAG Index status
    docs_count = (await session.execute(select(sa_func.count(KnowledgeDocument.id)))).scalar() or 0
    chunks_count = (await session.execute(select(sa_func.count(KnowledgeChunk.id)))).scalar() or 0
    if not runtime_cfg.get("rag_enabled"):
        rag_index_status = "disabled"
    elif vec_status == "connected" and emb_status in ("configured", "connected"):
        rag_index_status = "connected"
    elif vec_status == "degraded" or emb_status == "degraded":
        rag_index_status = "degraded"
    elif vec_status == "configured":
        rag_index_status = "configured"
    else:
        rag_index_status = "not_validated"

    # 5. MCP manager status
    active_mcp = mcp_manager.list_servers()
    all_mcp_servers = (
        await session.execute(select(sa_func.count(MCPServerConfig.id)))
    ).scalar() or 0
    if all_mcp_servers == 0:
        mcp_status = "configured"
    elif active_mcp:
        mcp_status = "connected"
    else:
        mcp_status = "degraded"

    # 6. Signal Gateway status using effective runtime config (Section 23, 31)
    effective_sig_url = (
        signal_client._api_url or runtime_cfg.get("signal_api_url") or settings.signal_api_url
    )
    effective_sig_phone = (
        signal_client._phone_number
        or runtime_cfg.get("signal_phone_number")
        or settings.signal_phone_number
    )
    masked_phone = None
    if effective_sig_phone:
        masked_phone = (
            f"{effective_sig_phone[:3]}***{effective_sig_phone[-2:]}"
            if len(effective_sig_phone) > 5
            else "***"
        )

    if not (effective_sig_url and effective_sig_phone):
        gw_status = "unconfigured"
    else:
        try:
            about = await signal_client.get_about()
            gw_status = "connected" if about else "degraded"
        except Exception:
            gw_status = "not_validated"

    llm_dict = {
        "name": getattr(llm_prov, "provider_name", type(llm_prov).__name__),
        "model": getattr(llm_prov, "default_model", "unknown"),
        "status": llm_status,
    }
    emb_dict = {
        "name": type(emb_prov).__name__ if emb_prov else "None",
        "model": getattr(emb_prov, "model", "unknown") if emb_prov else "none",
        "status": emb_status,
    }

    return {
        "llm": llm_dict,
        "llm_provider": llm_dict,
        "embedding": emb_dict,
        "embedding_provider": emb_dict,
        "vector_store": {
            "provider": vec_provider,
            "status": vec_status,
        },
        "rag_index": {
            "documents_count": docs_count,
            "chunks_count": chunks_count,
            "status": rag_index_status,
        },
        "mcp": {
            "active_servers": len(active_mcp),
            "total_servers": all_mcp_servers,
            "status": mcp_status,
        },
        "signal_gateway": {
            "url": effective_sig_url,
            "phone_number": masked_phone,
            "status": gw_status,
        },
    }


@router.post("/diagnostics/test-provider", response_model=ProviderLiveTestResponse)
async def test_live_provider(
    payload: ProviderLiveTestRequest | None = None,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Execute live provider test against configured external LLM using saved DB credentials."""
    from app.ai.providers.embeddings import OpenAICompatibleEmbeddingProvider
    from app.ai.providers.llm import OpenAICompatibleProvider
    from app.services.runtime_config import get_runtime_settings, is_ai_api_key_optional

    settings_dict = await get_runtime_settings(session)
    base_url = (settings_dict.get("ai_api_base_url") or "").strip()
    api_key = (settings_dict.get("ai_api_key") or "").strip()
    model = (settings_dict.get("ai_model") or "gpt-4o-mini").strip()
    enabled = bool(settings_dict.get("is_ai_enabled", True))
    has_auth = bool(api_key) or is_ai_api_key_optional(base_url)

    test_tools = payload.test_tools if payload is not None else True
    test_embeddings = payload.test_embeddings if payload is not None else True

    tested_at = datetime.now(UTC).replace(tzinfo=None)

    if not enabled:
        return ProviderLiveTestResponse(
            connected=False,
            connection_status="not_configured",
            provider="openai_compatible",
            provider_detected="openai_compatible",
            model=model,
            endpoint=base_url or "not configured",
            preview="",
            response_preview="",
            usage_source="unavailable",
            tool_calling_status="not_verified",
            native_tool_calling="not_verified",
            embedding_status="not_configured",
            embeddings="not_configured",
            error="AI is disabled in Settings",
            error_message="AI is disabled in Settings",
            tested_at=tested_at,
        )

    if not has_auth or not base_url:
        return ProviderLiveTestResponse(
            connected=False,
            connection_status="not_configured",
            provider="openai_compatible",
            provider_detected="openai_compatible",
            model=model,
            endpoint=base_url or "not configured",
            preview="",
            response_preview="",
            usage_source="unavailable",
            tool_calling_status="not_verified",
            native_tool_calling="not_verified",
            embedding_status="not_configured",
            embeddings="not_configured",
            error="API credentials not configured in Settings",
            error_message="API credentials not configured in Settings",
            tested_at=tested_at,
        )

    provider = OpenAICompatibleProvider(
        base_url=base_url,
        api_key=api_key,
        default_model=model,
        timeout=15.0,
    )

    lat_ms = 0
    preview = ""
    u_in = None
    u_out = None
    u_tot = None
    u_cached = None
    u_reasoning = None
    u_source = "unavailable"
    finish_reason = None
    err = None
    connected = False

    # 1. Chat Completion Probe
    try:
        t0 = time.perf_counter()
        llm_res = await provider.generate(
            messages=[{"role": "user", "content": "Respond with the word PONG only."}],
            temperature=0.1,
            max_tokens=20,
        )
        lat_ms = int((time.perf_counter() - t0) * 1000)
        connected = True
        preview = llm_res.content[:100]
        finish_reason = llm_res.finish_reason
        u = llm_res.usage
        u_in = u.input_tokens
        u_out = u.output_tokens
        u_tot = u.total_tokens
        u_cached = u.cached_input_tokens
        u_reasoning = u.reasoning_tokens
        u_source = u.usage_source
    except Exception as e:
        err = f"Provider chat probe failed: {e}"

    # 2. Native Tool Calling Probe
    tool_status = "not_verified"
    if connected and test_tools:
        try:
            sample_tool = [
                {
                    "type": "function",
                    "function": {
                        "name": "check_status",
                        "description": "Probe tool calling capability",
                        "parameters": {
                            "type": "object",
                            "properties": {"probe_id": {"type": "string"}},
                            "required": ["probe_id"],
                        },
                    },
                }
            ]
            tool_res = await provider.tool_generate(
                messages=[{"role": "user", "content": "Call check_status with probe_id 123"}],
                tools=sample_tool,
            )
            if tool_res.tool_calls:
                tool_status = "supported"
            else:
                tool_status = "unsupported"
        except Exception:
            tool_status = "unsupported"

    # 3. Embeddings Probe (use embedding_base_url per section 16)
    emb_status = "not_configured"
    if test_embeddings:
        emb_url = (
            settings_dict.get("embedding_base_url")
            or settings_dict.get("embedding_api_base_url")
            or base_url
        ).strip()
        emb_key = (settings_dict.get("embedding_api_key") or api_key).strip()
        emb_model = (settings_dict.get("embedding_model") or "text-embedding-3-small").strip()
        if emb_url and (emb_key or is_ai_api_key_optional(emb_url)):
            try:
                emb_provider = OpenAICompatibleEmbeddingProvider(
                    base_url=emb_url,
                    api_key=emb_key,
                    model=emb_model,
                    timeout=10.0,
                )
                vectors = await emb_provider.embed(["test probe"])
                if vectors and len(vectors) > 0 and len(vectors[0]) > 0:
                    emb_status = "connected"
                else:
                    emb_status = "unsupported"
            except Exception:
                emb_status = "unsupported"

    # Persist an AIRun into dedicated sandbox conversation with traffic_source="provider_test"
    if connected:
        try:
            sandbox_conv_id = await get_or_create_sandbox_conversation(
                session, "__system_provider_probe__"
            )
            test_run = AIRun(
                trace_id=f"tr_test_{uuid.uuid4().hex[:8]}",
                conversation_id=sandbox_conv_id,
                model=model,
                provider="openai_compatible",
                prompt_version="probe",
                decision="provider_test",
                latency_ms=lat_ms,
                tokens=u_tot or 0,
                input_tokens=u_in,
                output_tokens=u_out,
                total_tokens=u_tot,
                cached_input_tokens=u_cached,
                reasoning_tokens=u_reasoning,
                usage_source=u_source,
                traffic_source="provider_test",
            )
            session.add(test_run)
            await session.commit()
        except Exception:
            await session.rollback()

    return ProviderLiveTestResponse(
        connected=connected,
        connection_status="connected" if connected else "failed",
        provider="openai_compatible",
        provider_detected="openai_compatible",
        model=model,
        endpoint=base_url,
        latency_ms=lat_ms,
        preview=preview,
        response_preview=preview,
        input_tokens=u_in,
        output_tokens=u_out,
        total_tokens=u_tot,
        cached_tokens=u_cached,
        reasoning_tokens=u_reasoning,
        usage_source=u_source,
        finish_reason=finish_reason,
        tool_calling_status=tool_status,
        native_tool_calling=tool_status,
        embedding_status=emb_status,
        embeddings=emb_status,
        tested_at=tested_at,
        error=err,
        error_message=err,
    )


# ---------------------------------------------------------------------------
# Usage Telemetry Endpoints
# ---------------------------------------------------------------------------


@router.get("/usage/summary", response_model=UsageSummaryDTO)
async def get_usage_summary(
    time_range: str = Query("all"),
    provider: str | None = None,
    model: str | None = None,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Aggregate token usage and cost metrics for specified time range."""
    t_start, t_end = resolve_time_bounds(time_range)
    filters = [AIRun.traffic_source == "production"]
    if t_start:
        filters.append(AIRun.created_at >= t_start)
    if t_end:
        filters.append(AIRun.created_at <= t_end)
    if provider:
        filters.append(AIRun.provider == provider)
    if model:
        filters.append(AIRun.model == model)

    res = (
        await session.execute(
            select(
                sa_func.count(AIRun.id),
                sa_func.sum(AIRun.total_tokens),
                sa_func.sum(AIRun.input_tokens),
                sa_func.sum(AIRun.output_tokens),
                sa_func.sum(AIRun.cached_input_tokens),
                sa_func.sum(AIRun.reasoning_tokens),
                sa_func.sum(AIRun.estimated_cost),
                sa_func.sum(AIRun.llm_call_count),
                sa_func.avg(AIRun.latency_ms),
                sa_func.sum(
                    sa_case(
                        (and_(AIRun.errors.is_not(None), AIRun.errors != ""), 1),
                        else_=0,
                    )
                ),
            ).where(*filters)
        )
    ).one_or_none()

    total_runs = res[0] if res and res[0] else 0
    tot_tokens = int(res[1]) if res and res[1] is not None else 0
    in_tokens = int(res[2]) if res and res[2] is not None else None
    out_tokens = int(res[3]) if res and res[3] is not None else None
    cached_tokens = int(res[4]) if res and res[4] is not None else None
    reason_tokens = int(res[5]) if res and res[5] is not None else None
    est_cost = round(float(res[6]), 5) if res and res[6] is not None else None
    total_model_calls = int(res[7]) if res and res[7] is not None else 0
    avg_latency_ms = round(float(res[8]), 1) if res and res[8] is not None else 0.0
    err_runs = int(res[9]) if res and res[9] is not None else 0
    err_rate = round(err_runs / total_runs, 3) if total_runs > 0 else 0.0

    return UsageSummaryDTO(
        time_range=time_range,
        total_runs=total_runs,
        total_tokens=tot_tokens,
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        cached_input_tokens=cached_tokens,
        reasoning_tokens=reason_tokens,
        estimated_cost=est_cost,
        currency="USD",
        cost_currency="USD",
        total_model_calls=total_model_calls,
        avg_latency_ms=avg_latency_ms,
        errors=err_runs,
        error_rate=err_rate,
    )


@router.get("/usage/timeseries", response_model=UsageTimeseriesResponseDTO)
async def get_usage_timeseries(
    time_range: str = Query("7d"),
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Return operational time series data for runs, errors, latency, and tokens."""
    t_start, t_end = resolve_time_bounds(time_range)
    filters = [AIRun.traffic_source == "production"]
    if t_start:
        filters.append(AIRun.created_at >= t_start)
    if t_end:
        filters.append(AIRun.created_at <= t_end)

    stmt = (
        select(
            AIRun.created_at,
            AIRun.total_tokens,
            AIRun.input_tokens,
            AIRun.output_tokens,
            AIRun.latency_ms,
            AIRun.errors,
        )
        .where(*filters)
        .order_by(AIRun.created_at)
    )

    rows = (await session.execute(stmt)).all()

    is_hourly = time_range == "24h"
    points_dict: dict[str, dict[str, Any]] = {}

    for row in rows:
        created = row[0]
        if isinstance(created, str):
            dt = datetime.fromisoformat(created)
        else:
            dt = created

        bucket_key = dt.strftime("%Y-%m-%d %H:00" if is_hourly else "%Y-%m-%d")
        if bucket_key not in points_dict:
            points_dict[bucket_key] = {
                "timestamp": bucket_key,
                "runs": 0,
                "errors": 0,
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "latencies": [],
            }
        b = points_dict[bucket_key]
        b["runs"] += 1
        if row[5]:
            b["errors"] += 1
        b["total_tokens"] += row[1] or 0
        b["input_tokens"] += row[2] or 0
        b["output_tokens"] += row[3] or 0
        if row[4] is not None:
            b["latencies"].append(row[4])

    points = []
    for k in sorted(points_dict.keys()):
        item = points_dict[k]
        lats = item.pop("latencies")
        item["avg_latency_ms"] = round(sum(lats) / len(lats), 1) if lats else 0.0
        points.append(UsageTimeseriesPointDTO(**item))

    return UsageTimeseriesResponseDTO(
        points=points,
        time_range=time_range,
        timezone="UTC",
    )


@router.get("/usage/models", response_model=ModelUsageResponseDTO)
async def get_usage_models(
    time_range: str = Query("all"),
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Return model breakdown with token volumes, error rates, and costs."""
    t_start, t_end = resolve_time_bounds(time_range)
    filters = [AIRun.traffic_source == "production"]
    if t_start:
        filters.append(AIRun.created_at >= t_start)
    if t_end:
        filters.append(AIRun.created_at <= t_end)

    error_case = sa_case(
        (and_(AIRun.errors.is_not(None), AIRun.errors != ""), 1),
        else_=0,
    )
    stmt = (
        select(
            AIRun.provider,
            AIRun.model,
            sa_func.count(AIRun.id),
            sa_func.sum(AIRun.total_tokens),
            sa_func.sum(AIRun.input_tokens),
            sa_func.sum(AIRun.output_tokens),
            sa_func.avg(AIRun.latency_ms),
            sa_func.sum(AIRun.estimated_cost),
            sa_func.sum(error_case),
        )
        .where(*filters)
        .group_by(AIRun.provider, AIRun.model)
    )

    res = (await session.execute(stmt)).all()
    items = []
    for r in res:
        raw_prov, raw_mod = r[0], r[1]
        prov = raw_prov or "unknown"
        mod = raw_mod or "default"
        runs_cnt = r[2] or 0
        tot_tok = int(r[3]) if r[3] is not None else 0
        in_tok = int(r[4]) if r[4] is not None else 0
        out_tok = int(r[5]) if r[5] is not None else 0
        avg_lat = round(float(r[6]), 1) if r[6] is not None else 0.0
        est_cost = round(float(r[7]), 5) if r[7] is not None else None
        err_cnt = int(r[8]) if r[8] is not None else 0
        err_rate = round(err_cnt / runs_cnt, 3) if runs_cnt > 0 else 0.0

        items.append(
            ModelUsageItemDTO(
                provider=prov,
                model=mod,
                runs=runs_cnt,
                errors=err_cnt,
                error_rate=err_rate,
                input_tokens=in_tok,
                output_tokens=out_tok,
                total_tokens=tot_tok,
                avg_latency_ms=avg_lat,
                estimated_cost=est_cost,
                currency="USD",
            )
        )

    return ModelUsageResponseDTO(models=items)


# ---------------------------------------------------------------------------
# Runs & Traces Explorer
# ---------------------------------------------------------------------------


@router.get("/runs", response_model=list[AIRunDTO])
async def list_ai_runs(
    response: Response,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    time_range: str | None = None,
    decision: str | None = None,
    mode: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    has_error: bool | None = None,
    has_rag: bool | None = None,
    # deprecated compatibility alias; remove in future major/minor API cleanup
    used_rag: bool | None = None,
    has_tools: bool | None = None,
    # deprecated compatibility alias; remove in future major/minor API cleanup
    used_tools: bool | None = None,
    conversation_id: int | None = None,
    traffic_source: str | None = None,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Query AI execution traces with filtering and pagination."""
    stmt = select(AIRun)
    if traffic_source:
        stmt = stmt.where(AIRun.traffic_source == traffic_source)
    if decision:
        stmt = stmt.where(AIRun.decision == decision)
    if provider:
        stmt = stmt.where(AIRun.provider == provider)
    if model:
        stmt = stmt.where(AIRun.model == model)
    if prompt_version:
        stmt = stmt.where(AIRun.prompt_version == prompt_version)
    if conversation_id is not None:
        stmt = stmt.where(AIRun.conversation_id == conversation_id)
    if has_error is True:
        stmt = stmt.where(AIRun.errors.is_not(None), AIRun.errors != "")
    elif has_error is False:
        stmt = stmt.where((AIRun.errors.is_(None)) | (AIRun.errors == ""))

    effective_rag = has_rag if has_rag is not None else used_rag
    if effective_rag is True:
        stmt = stmt.where(
            AIRun.retrieval.is_not(None), AIRun.retrieval != "[]", AIRun.retrieval != ""
        )
    elif effective_rag is False:
        stmt = stmt.where(
            or_(AIRun.retrieval.is_(None), AIRun.retrieval == "[]", AIRun.retrieval == "")
        )

    effective_tools = has_tools if has_tools is not None else used_tools
    if effective_tools is True:
        stmt = stmt.where(
            AIRun.tool_calls.is_not(None), AIRun.tool_calls != "[]", AIRun.tool_calls != ""
        )
    elif effective_tools is False:
        stmt = stmt.where(
            or_(AIRun.tool_calls.is_(None), AIRun.tool_calls == "[]", AIRun.tool_calls == "")
        )

    if time_range:
        t_start, t_end = resolve_time_bounds(time_range)
        if t_start:
            stmt = stmt.where(AIRun.created_at >= t_start)
        if t_end:
            stmt = stmt.where(AIRun.created_at <= t_end)

    count_stmt = select(sa_func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0
    response.headers["X-Total-Count"] = str(total)

    stmt = stmt.order_by(desc(AIRun.created_at)).limit(limit).offset(offset)
    res = await session.execute(stmt)
    runs = list(res.scalars().all())

    items = []
    for r in runs:
        ret = json.loads(r.retrieval) if r.retrieval else []
        mem = json.loads(r.memory) if r.memory else []
        tc = json.loads(r.tool_calls) if r.tool_calls else []
        items.append(
            AIRunDTO(
                id=r.id,
                trace_id=r.trace_id,
                conversation_id=r.conversation_id,
                input_message_id=r.input_message_id,
                model=r.model,
                provider=r.provider,
                prompt_version=r.prompt_version,
                skills=json.loads(r.skills) if r.skills else [],
                retrieval=ret,
                citations=ret,
                memory=mem,
                memories=mem,
                tool_calls=tc,
                rag_hit_count=len(ret),
                tool_call_count=len(tc),
                decision=r.decision,
                confidence=r.confidence,
                latency_ms=r.latency_ms,
                tokens=r.total_tokens or r.tokens,
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                total_tokens=r.total_tokens or r.tokens,
                cached_input_tokens=r.cached_input_tokens,
                reasoning_tokens=r.reasoning_tokens,
                llm_call_count=r.llm_call_count,
                usage_source=r.usage_source,
                estimated_cost=r.estimated_cost,
                cost_currency=r.cost_currency,
                traffic_source=r.traffic_source,
                errors=r.errors,
                final_message_id=r.final_message_id,
                created_at=r.created_at,
            )
        )
    return items


@router.get("/runs/{run_id}", response_model=AIRunDTO)
async def get_ai_run_detail(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Retrieve full trace detail of a specific AIRun, including model calls."""
    run = await session.get(AIRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="AIRun not found")

    stmt = (
        select(AIModelCall).where(AIModelCall.ai_run_id == run_id).order_by(AIModelCall.started_at)
    )
    res = await session.execute(stmt)
    model_calls = [
        {
            "id": mc.id,
            "phase": mc.phase,
            "provider": mc.provider,
            "model": mc.model,
            "started_at": mc.started_at.isoformat() if mc.started_at else None,
            "latency_ms": mc.latency_ms,
            "input_tokens": mc.input_tokens,
            "output_tokens": mc.output_tokens,
            "total_tokens": mc.total_tokens,
            "cached_input_tokens": mc.cached_input_tokens,
            "reasoning_tokens": mc.reasoning_tokens,
            "usage_source": mc.usage_source,
            "finish_reason": mc.finish_reason,
            "provider_request_id": mc.provider_request_id,
            "success": mc.success,
            "error": mc.error,
            "estimated_cost": mc.estimated_cost,
            "currency": mc.currency,
        }
        for mc in res.scalars().all()
    ]

    ret = json.loads(run.retrieval) if run.retrieval else []
    mem = json.loads(run.memory) if run.memory else []
    tc = json.loads(run.tool_calls) if run.tool_calls else []

    return AIRunDTO(
        id=run.id,
        trace_id=run.trace_id,
        conversation_id=run.conversation_id,
        input_message_id=run.input_message_id,
        model=run.model,
        provider=run.provider,
        prompt_version=run.prompt_version,
        skills=json.loads(run.skills) if run.skills else [],
        retrieval=ret,
        citations=ret,
        memory=mem,
        memories=mem,
        tool_calls=tc,
        rag_hit_count=len(ret),
        tool_call_count=len(tc),
        decision=run.decision,
        confidence=run.confidence,
        latency_ms=run.latency_ms,
        tokens=run.total_tokens or run.tokens,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        total_tokens=run.total_tokens or run.tokens,
        cached_input_tokens=run.cached_input_tokens,
        reasoning_tokens=run.reasoning_tokens,
        llm_call_count=run.llm_call_count,
        usage_source=run.usage_source,
        estimated_cost=run.estimated_cost,
        cost_currency=run.cost_currency,
        traffic_source=run.traffic_source,
        errors=run.errors,
        final_message_id=run.final_message_id,
        created_at=run.created_at,
        model_calls=model_calls,
    )


# ---------------------------------------------------------------------------
# 2. Knowledge Base & RAG
# ---------------------------------------------------------------------------


@router.get("/knowledge/sources", response_model=list[KnowledgeSourceDTO])
async def list_knowledge_sources(
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    stmt = select(KnowledgeSource).order_by(desc(KnowledgeSource.created_at))
    res = await session.execute(stmt)
    sources = list(res.scalars().all())

    dtos = []
    for s in sources:
        doc_count = len(s.documents) if s.documents else 0
        dtos.append(
            KnowledgeSourceDTO(
                id=s.id,
                title=s.title,
                source_type=s.source_type,
                source_uri=s.source_uri,
                language=s.language,
                status=s.status,
                trust_level=s.trust_level,
                version=s.version,
                created_by=s.created_by,
                created_at=s.created_at,
                updated_at=s.updated_at,
                documents_count=doc_count,
            )
        )
    return dtos


@router.get("/knowledge/sources/{source_id}", response_model=KnowledgeSourceDetailDTO)
async def get_knowledge_source_detail(
    source_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Retrieve details for a specific knowledge source and its documents."""
    source = await session.get(KnowledgeSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")

    docs_stmt = (
        select(KnowledgeDocument)
        .where(KnowledgeDocument.source_id == source_id)
        .order_by(desc(KnowledgeDocument.created_at))
    )
    docs_res = await session.execute(docs_stmt)
    docs = list(docs_res.scalars().all())

    doc_dtos = [
        KnowledgeDocumentDTO(
            id=d.id,
            source_id=d.source_id,
            title=d.title,
            content=d.content,
            scope_type=d.scope_type,
            scope_id=d.scope_id,
            chunk_count=d.chunk_count,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in docs
    ]

    source_dto = KnowledgeSourceDTO(
        id=source.id,
        title=source.title,
        source_type=source.source_type,
        source_uri=source.source_uri,
        language=source.language,
        status=source.status,
        trust_level=source.trust_level,
        version=source.version,
        created_by=source.created_by,
        created_at=source.created_at,
        updated_at=source.updated_at,
        documents_count=len(docs),
    )

    return KnowledgeSourceDetailDTO(source=source_dto, documents=doc_dtos)


@router.post("/knowledge/sources/{source_id}/reindex")
async def reindex_knowledge_source(
    source_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Reindex all documents belonging to a knowledge source."""
    source = await session.get(KnowledgeSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")

    runtime = await get_production_agent_runtime(session)
    require_rag_runtime(runtime)
    ingestion = KnowledgeIngestionService(
        embedding_provider=runtime.embedding_provider,
        vector_store=runtime.vector_store,
    )
    docs_stmt = select(KnowledgeDocument).where(KnowledgeDocument.source_id == source_id)
    docs_res = await session.execute(docs_stmt)
    docs = list(docs_res.scalars().all())
    reindexed_count = 0
    for d in docs:
        c = await ingestion.reindex_document(session=session, document_id=d.id)
        reindexed_count += c

    return {
        "ok": True,
        "source_id": source_id,
        "documents_count": len(docs),
        "chunks_reindexed": reindexed_count,
        "indexed_documents": len(docs),
        "indexed_chunks": reindexed_count,
    }


@router.post("/knowledge/sources", response_model=KnowledgeSourceDTO)
async def create_knowledge_source(
    payload: CreateKnowledgeSourceRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    source = KnowledgeSource(
        title=payload.title,
        source_type=payload.source_type,
        source_uri=payload.source_uri,
        language=payload.language,
        trust_level=payload.trust_level,
        created_by=admin.username,
        approved_by=admin.username,
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)

    await write_audit_log(
        session=session,
        action="knowledge.source.add",
        actor=admin.username,
        target=f"knowledge_source:{source.id}",
        details={"title": source.title, "type": source.source_type},
        ip_address=http_request.client.host if http_request.client else None,
    )

    return KnowledgeSourceDTO(
        id=source.id,
        title=source.title,
        source_type=source.source_type,
        source_uri=source.source_uri,
        language=source.language,
        status=source.status,
        trust_level=source.trust_level,
        version=source.version,
        created_by=source.created_by,
        created_at=source.created_at,
        updated_at=source.updated_at,
        documents_count=0,
    )


@router.delete("/knowledge/sources/{source_id}")
async def delete_knowledge_source(
    source_id: int,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    source = await session.get(KnowledgeSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")

    runtime = await get_production_agent_runtime(session)
    ingestion = KnowledgeIngestionService(
        embedding_provider=runtime.embedding_provider,
        vector_store=runtime.vector_store,
    )
    await ingestion.delete_source(session=session, source_id=source_id)

    await write_audit_log(
        session=session,
        action="knowledge.source.delete",
        actor=admin.username,
        target=f"knowledge_source:{source_id}",
        details={"title": source.title},
        ip_address=http_request.client.host if http_request.client else None,
    )
    return {"ok": True, "deleted_source_id": source_id}


@router.delete("/knowledge/documents/{document_id}")
async def delete_knowledge_document(
    document_id: int,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    doc = await session.get(KnowledgeDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Knowledge document not found")

    runtime = await get_production_agent_runtime(session)
    ingestion = KnowledgeIngestionService(
        embedding_provider=runtime.embedding_provider,
        vector_store=runtime.vector_store,
    )
    await ingestion.delete_document(session=session, document_id=document_id)

    await write_audit_log(
        session=session,
        action="knowledge.document.delete",
        actor=admin.username,
        target=f"knowledge_document:{document_id}",
        details={"title": doc.title},
        ip_address=http_request.client.host if http_request.client else None,
    )
    return {"ok": True, "deleted_document_id": document_id}


@router.delete(
    "/knowledge/sources/{source_id}/documents/{document_id}",
    include_in_schema=False,
)
async def delete_knowledge_document_nested(
    source_id: int,
    document_id: int,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    doc = await session.get(KnowledgeDocument, document_id)
    if not doc or doc.source_id != source_id:
        raise HTTPException(status_code=404, detail="Knowledge document not found in source")
    return await delete_knowledge_document(
        document_id=document_id,
        http_request=http_request,
        session=session,
        admin=admin,
    )


@router.post("/knowledge/sources/{source_id}/documents")
async def add_document_to_source(
    source_id: int,
    payload: CreateDocumentRequest,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    source = await session.get(KnowledgeSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")

    runtime = await get_production_agent_runtime(session)
    require_rag_runtime(runtime)
    ingestion = KnowledgeIngestionService(
        embedding_provider=runtime.embedding_provider,
        vector_store=runtime.vector_store,
    )
    doc = await ingestion.ingest_document(
        session=session,
        source_id=source_id,
        title=payload.title,
        content=payload.content,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
    )
    return {
        "ok": True,
        "document_id": doc.id,
        "chunks_created": doc.chunk_count,
        "chunks_count": doc.chunk_count,
    }


@router.post("/knowledge/sources/{source_id}/faqs")
async def add_faq_to_source(
    source_id: int,
    payload: CreateFAQRequest,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    source = await session.get(KnowledgeSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")

    runtime = await get_production_agent_runtime(session)
    require_rag_runtime(runtime)
    ingestion = KnowledgeIngestionService(
        embedding_provider=runtime.embedding_provider,
        vector_store=runtime.vector_store,
    )
    doc = await ingestion.ingest_document(
        session=session,
        source_id=source_id,
        title=f"FAQ: {payload.question}",
        content=payload.answer,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        is_faq=True,
        faq_question=payload.question,
        metadata={"category": payload.category},
    )
    return {
        "ok": True,
        "document_id": doc.id,
        "chunks_created": doc.chunk_count,
        "chunks_count": doc.chunk_count,
    }


@router.post(
    "/knowledge/search",
    response_model=list[KnowledgeSearchResultDTO],
    operation_id="search_knowledge_post",
)
async def test_knowledge_retrieval(
    query: str,
    limit: int = 5,
    is_group: bool = False,
    group_id: str | None = None,
    user_id: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Simulate RAG search with scope isolation testing."""
    if scope_type == "group":
        is_group = True
        if scope_id:
            group_id = scope_id
    elif scope_type == "user":
        is_group = False
        if scope_id:
            user_id = scope_id
    elif scope_type in ("global", "dm", "all"):
        is_group = False
        group_id = None
        user_id = None

    runtime = await get_production_agent_runtime(session)
    require_rag_runtime(runtime)
    if not runtime.retriever:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="RAG retriever is not configured"
        )
    chunks = await runtime.retriever.retrieve(
        query=query,
        limit=limit,
        is_group=is_group,
        group_id=group_id,
        user_id=user_id,
    )
    return [
        KnowledgeSearchResultDTO(
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            source_id=c.source_id,
            title=c.title,
            content=c.content,
            score=round(c.score, 3),
            scope_type=c.scope_type,
            scope_id=c.scope_id,
        )
        for c in chunks
    ]


@router.get(
    "/knowledge/search",
    response_model=list[KnowledgeSearchResultDTO],
    operation_id="search_knowledge_get",
)
async def test_knowledge_retrieval_get(
    query: str,
    limit: int = 5,
    is_group: bool = False,
    group_id: str | None = None,
    user_id: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    return await test_knowledge_retrieval(
        query=query,
        limit=limit,
        is_group=is_group,
        group_id=group_id,
        user_id=user_id,
        scope_type=scope_type,
        scope_id=scope_id,
        session=session,
        _admin=admin,
    )


@router.post("/knowledge/documents/{document_id}/reindex")
async def reindex_document(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Re-chunk, embed, and refresh vector store embeddings for a specific document."""
    runtime = await get_production_agent_runtime(session)
    require_rag_runtime(runtime)
    ingestion = KnowledgeIngestionService(
        embedding_provider=runtime.embedding_provider,
        vector_store=runtime.vector_store,
    )
    try:
        chunks_count = await ingestion.reindex_document(session=session, document_id=document_id)
        return {
            "ok": True,
            "document_id": document_id,
            "chunks_reindexed": chunks_count,
            "indexed_chunks": chunks_count,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/knowledge/reindex")
async def reindex_all_knowledge(
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Rebuild entire vector index from relational database."""
    runtime = await get_production_agent_runtime(session)
    require_rag_runtime(runtime)
    ingestion = KnowledgeIngestionService(
        embedding_provider=runtime.embedding_provider,
        vector_store=runtime.vector_store,
    )
    result = await ingestion.reindex_all(session=session)
    return {
        "ok": True,
        "documents_count": result.get("documents_reindexed", 0),
        "chunks_reindexed": result.get("chunks_reindexed", 0),
        "indexed_documents": result.get("documents_reindexed", 0),
        "indexed_chunks": result.get("chunks_reindexed", 0),
        **result,
    }


# ---------------------------------------------------------------------------
# 3. Scoped Durable Memory
# ---------------------------------------------------------------------------


@router.get("/memory", response_model=list[MemoryItemDTO])
async def list_memories(
    scope_type: str | None = Query(None),
    scope_id: str | None = Query(None),
    limit: int = Query(50),
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """List memory items with optional scope filtering (returns all scopes when scope_type is None or 'all')."""
    stmt = select(MemoryItem)
    if scope_type and scope_type.lower() != "all":
        stmt = stmt.where(MemoryItem.scope_type == scope_type)
    if scope_id:
        stmt = stmt.where(MemoryItem.scope_id == scope_id)
    stmt = stmt.order_by(desc(MemoryItem.created_at)).limit(limit)

    res = await session.execute(stmt)
    items = list(res.scalars().all())

    return [
        MemoryItemDTO(
            id=m.id,
            scope_type=m.scope_type,
            scope_id=m.scope_id,
            memory_type=m.memory_type,
            content=m.content,
            confidence=m.confidence,
            importance=int(round(float(m.importance or 3))),
            sensitivity=m.sensitivity or "standard",
            status=m.status,
            created_by=m.created_by,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
        for m in items
    ]


@router.post("/memory", response_model=MemoryItemDTO)
async def create_memory_item(
    payload: CreateMemoryRequest,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    runtime = await get_production_agent_runtime(session)
    mem = await runtime.memory.add(
        session=session,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        content=payload.content,
        memory_type=payload.memory_type,
        importance=payload.importance,
        created_by=admin.username,
    )
    return MemoryItemDTO(
        id=mem.id,
        scope_type=mem.scope_type,
        scope_id=mem.scope_id,
        memory_type=mem.memory_type,
        content=mem.content,
        confidence=mem.confidence,
        importance=mem.importance,
        sensitivity=mem.sensitivity,
        status=mem.status,
        created_by=mem.created_by,
        created_at=mem.created_at,
        updated_at=mem.updated_at,
    )


@router.delete("/memory/{memory_id}")
async def delete_memory_item(
    memory_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    runtime = await get_production_agent_runtime(session)
    ok = await runtime.memory.delete(session=session, memory_id=memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory item not found")
    return {"ok": True, "deleted_memory_id": memory_id}


@router.get("/memory/items", response_model=list[MemoryItemDTO], include_in_schema=False)
async def list_memories_alias(
    scope_type: str = Query("user"),
    scope_id: str | None = Query(None),
    limit: int = Query(50),
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    return await list_memories(
        scope_type=scope_type, scope_id=scope_id, limit=limit, session=session, _admin=admin
    )


@router.delete("/memory/items/{memory_id}", include_in_schema=False)
async def delete_memory_item_alias(
    memory_id: int,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    return await delete_memory_item(memory_id=memory_id, session=session, _admin=admin)


# ---------------------------------------------------------------------------
# 4. Agent Skills
# ---------------------------------------------------------------------------


@router.get("/skills", response_model=list[SkillDTO])
async def list_agent_skills(
    _admin: AdminUser = Depends(get_current_admin),
):
    skills = skill_registry.list_skills()
    return [
        SkillDTO(
            name=s.name,
            description=s.description,
            version=s.version,
            scope=s.scope,
            is_enabled=s.is_enabled,
            body=s.body,
        )
        for s in skills
    ]


@router.patch("/skills/{skill_name}")
async def toggle_skill(
    skill_name: str,
    payload: ToggleSkillRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    ok = await skill_registry.set_enabled_persisted(session, skill_name, payload.is_enabled)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    await write_audit_log(
        session=session,
        action="skill.toggle",
        actor=admin.username,
        target=f"skill:{skill_name}",
        details={"enabled": payload.is_enabled},
        ip_address=http_request.client.host if http_request.client else None,
    )
    return {"ok": True, "skill_name": skill_name, "is_enabled": payload.is_enabled}


@router.post("/skills/{skill_name}/toggle", include_in_schema=False)
async def toggle_skill_alias(
    skill_name: str,
    payload: ToggleSkillRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    return await toggle_skill(
        skill_name=skill_name,
        payload=payload,
        http_request=http_request,
        session=session,
        admin=admin,
    )


# ---------------------------------------------------------------------------
# 5. MCP Server Governance
# ---------------------------------------------------------------------------


@router.get("/mcp/servers", response_model=list[MCPServerDTO])
async def list_mcp_servers(
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    stmt = select(MCPServerConfig).order_by(MCPServerConfig.name)
    res = await session.execute(stmt)
    servers = list(res.scalars().all())

    active = {s["name"]: s for s in mcp_manager.list_servers()}
    dtos = []
    for s in servers:
        act = active.get(s.name, {})
        t_count = act.get("tools_count", 0)
        dtos.append(
            MCPServerDTO(
                id=s.id,
                name=s.name,
                transport=s.transport,
                transport_type=s.transport,
                command_or_url=s.command_or_url,
                command=s.command_or_url if s.transport == "stdio" else None,
                endpoint_url=s.command_or_url if s.transport in ("http", "sse") else None,
                is_enabled=s.is_enabled,
                status=s.status,
                last_connected_at=s.last_connected_at,
                last_health_check=s.last_connected_at,
                error_message=s.error_message,
                tools_count=t_count,
                tool_count=t_count,
            )
        )
    return dtos


@router.post("/mcp/servers", response_model=MCPServerDTO)
async def register_mcp_server(
    payload: CreateMCPServerRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    env_str = json.dumps(payload.env) if payload.env else None
    encrypted_env = encrypt_value(env_str) if env_str else None

    server = MCPServerConfig(
        name=payload.name,
        transport=payload.transport,
        command_or_url=payload.command_or_url,
        args_json=json.dumps(payload.args),
        env_json=encrypted_env,
        is_enabled=True,
        status="disconnected",
    )
    session.add(server)
    await session.commit()
    await session.refresh(server)

    await write_audit_log(
        session=session,
        action="mcp.server.add",
        actor=admin.username,
        target=f"mcp_server:{server.id}",
        details={"name": server.name, "transport": server.transport},
        ip_address=http_request.client.host if http_request.client else None,
    )

    return MCPServerDTO(
        id=server.id,
        name=server.name,
        transport=server.transport,
        transport_type=server.transport,
        command_or_url=server.command_or_url,
        command=server.command_or_url if server.transport == "stdio" else None,
        endpoint_url=server.command_or_url if server.transport in ("http", "sse") else None,
        is_enabled=server.is_enabled,
        status=server.status,
        tools_count=0,
        tool_count=0,
    )


@router.post("/mcp/servers/{server_id}/connect")
async def connect_mcp_server(
    server_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    server = await session.get(MCPServerConfig, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    try:
        args = json.loads(server.args_json) if server.args_json else []
        env = parse_and_decrypt_env(server.env_json)
        tools = await mcp_manager.connect_server(
            name=server.name,
            transport=server.transport,
            command_or_url=server.command_or_url,
            args=args,
            env=env,
        )
        server.status = "connected"
        server.last_connected_at = datetime.now(UTC).replace(tzinfo=None)
        server.error_message = None
        await session.commit()
        return {"ok": True, "status": "connected", "tools_discovered": len(tools)}
    except Exception as e:
        server.status = "error"
        server.error_message = str(e)
        await session.commit()
        raise HTTPException(status_code=502, detail=f"Failed to connect MCP server: {e}")


@router.post("/mcp/servers/{server_id}/test", include_in_schema=False)
async def connect_mcp_server_alias(
    server_id: int,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    return await connect_mcp_server(server_id=server_id, session=session, _admin=admin)


@router.post("/mcp/servers/{server_id}/disconnect")
async def disconnect_mcp_server(
    server_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    server = await session.get(MCPServerConfig, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    await mcp_manager.disconnect_server(server.name)
    server.status = "disconnected"
    await session.commit()
    return {"ok": True, "status": "disconnected"}


@router.post("/mcp/servers/{server_id}/toggle")
async def toggle_mcp_server(
    server_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    server = await session.get(MCPServerConfig, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    server.is_enabled = not server.is_enabled
    if not server.is_enabled:
        await mcp_manager.disconnect_server(server.name)
        server.status = "disabled"
    await session.commit()
    return {"ok": True, "is_enabled": server.is_enabled, "status": server.status}


@router.patch("/mcp/servers/{server_id}")
async def update_mcp_server(
    server_id: int,
    payload: UpdateMCPServerRequest,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Enable or disable an MCP server configuration via canonical PATCH."""
    server = await session.get(MCPServerConfig, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    if payload.is_enabled is not None:
        new_val = payload.is_enabled
        if server.is_enabled != new_val:
            server.is_enabled = new_val
            if not new_val:
                await mcp_manager.disconnect_server(server.name)
                server.status = "disabled"
            await session.commit()
    return {"ok": True, "is_enabled": server.is_enabled, "status": server.status}


@router.get("/mcp/servers/{server_id}", response_model=MCPServerDetailDTO)
async def get_mcp_server_detail(
    server_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Retrieve detailed MCP server status including discovered tools and input schemas."""
    server = await session.get(MCPServerConfig, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    tools = mcp_manager.get_server_tools(server.name)
    dto = MCPServerDTO(
        id=server.id,
        name=server.name,
        transport=server.transport,
        transport_type=server.transport,
        command_or_url=server.command_or_url,
        command=server.command_or_url if server.transport == "stdio" else None,
        endpoint_url=server.command_or_url if server.transport in ("http", "sse") else None,
        is_enabled=server.is_enabled,
        status=server.status,
        tools_count=len(tools),
        tool_count=len(tools),
        last_connected_at=server.last_connected_at,
        last_health_check=server.last_connected_at,
        error_message=server.error_message,
    )
    return MCPServerDetailDTO(
        server=dto,
        discovered_tools=tools,
        id=server.id,
        name=server.name,
        transport=server.transport,
        transport_type=server.transport,
        endpoint_url=server.command_or_url if server.transport in ("http", "sse") else None,
        command=server.command_or_url if server.transport == "stdio" else None,
        is_enabled=server.is_enabled,
        status=server.status,
        tools=tools,
    )


@router.delete("/mcp/servers/{server_id}")
async def delete_mcp_server(
    server_id: int,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Disconnect and delete an MCP server registration."""
    server = await session.get(MCPServerConfig, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    await mcp_manager.disconnect_server(server.name)
    s_name = server.name
    await session.delete(server)
    await session.commit()

    await write_audit_log(
        session=session,
        action="mcp.server.delete",
        actor=admin.username,
        target=f"mcp_server:{server_id}",
        details={"name": s_name},
        ip_address=http_request.client.host if http_request.client else None,
    )
    return {"ok": True, "deleted_server_id": server_id}


# ---------------------------------------------------------------------------
# 6. Learning Loop & Dataset Export
# ---------------------------------------------------------------------------


@router.get("/learning/candidates", response_model=list[LearningCandidateDTO])
async def list_learning_candidates(
    status: str = Query("pending"),
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    candidates = await learning_service.list_candidates(session=session, status=status)
    return [
        LearningCandidateDTO(
            id=c.id,
            conversation_id=c.conversation_id,
            customer_question=c.customer_question,
            human_answer=c.human_answer,
            suggested_faq_q=c.suggested_faq_q,
            suggested_faq_a=c.suggested_faq_a,
            category=c.category,
            language=c.language,
            source_quality=c.source_quality,
            status=c.status,
            reviewed_by=c.reviewed_by,
            reviewed_at=c.reviewed_at,
            created_at=c.created_at,
        )
        for c in candidates
    ]


@router.post("/learning/candidates/{candidate_id}/promote")
async def promote_candidate(
    candidate_id: int,
    payload: PromoteCandidateRequest,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Promote learning candidate to Knowledge or Training dataset based on requested action with atomic claim semantics."""
    cand = await session.get(LearningCandidate, candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if cand.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Candidate #{candidate_id} has already been {cand.status}.",
        )

    action = (payload.action or "knowledge").strip().lower()

    if action == "training":
        try:
            ok = await learning_service.add_to_training(
                session=session,
                candidate_id=candidate_id,
                reviewer_name=admin.username,
            )
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"Candidate #{candidate_id} has already been promoted to training.",
            )
        except (CandidateConflictError, ValueError) as e:
            err_msg = str(e)
            if "not found" in err_msg:
                raise HTTPException(status_code=404, detail=err_msg)
            raise HTTPException(status_code=409, detail=err_msg)
        if not ok:
            raise HTTPException(status_code=404, detail="Candidate not found")
        return {
            "ok": True,
            "action": "training",
            "status": "approved",
            "promoted_candidate_id": candidate_id,
        }

    if action == "knowledge":
        runtime = await get_production_agent_runtime(session)
        require_rag_runtime(runtime)
        ingestion = KnowledgeIngestionService(
            embedding_provider=runtime.embedding_provider,
            vector_store=runtime.vector_store,
        )
        try:
            ok = await learning_service.promote_to_knowledge(
                session=session,
                candidate_id=candidate_id,
                ingestion_service=ingestion,
                reviewer_name=admin.username,
                faq_question=payload.faq_question,
                faq_answer=payload.faq_answer,
                scope_type=payload.scope_type,
                scope_id=payload.scope_id,
                confirm_global_privacy=payload.confirm_global_privacy,
            )
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"Candidate #{candidate_id} has already been promoted.",
            )
        except (CandidateConflictError, ValueError) as e:
            err_msg = str(e)
            if "privacy confirmation" in err_msg:
                raise HTTPException(status_code=400, detail=err_msg)
            if "not found" in err_msg:
                raise HTTPException(status_code=404, detail=err_msg)
            raise HTTPException(status_code=409, detail=err_msg)

        if not ok:
            raise HTTPException(status_code=404, detail="Candidate not found")
        return {
            "ok": True,
            "action": "knowledge",
            "status": "promoted",
            "promoted_candidate_id": candidate_id,
        }

    raise HTTPException(
        status_code=422,
        detail=f"Invalid action '{payload.action}'. Expected 'knowledge' or 'training'.",
    )


@router.post("/learning/candidates/{candidate_id}/reject")
async def reject_candidate(
    candidate_id: int,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    try:
        ok = await learning_service.reject_candidate(
            session=session,
            candidate_id=candidate_id,
            reviewer_name=admin.username,
        )
    except (CandidateConflictError, ValueError) as e:
        err_msg = str(e)
        if "not found" in err_msg:
            raise HTTPException(status_code=404, detail=err_msg)
        raise HTTPException(status_code=409, detail=err_msg)

    if not ok:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"ok": True, "rejected_candidate_id": candidate_id}


@router.get("/learning/training-stats", response_model=TrainingStatsDTO)
async def get_training_dataset_stats(
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Return count of approved training examples."""
    count = (await session.execute(select(sa_func.count(TrainingExample.id)))).scalar() or 0
    return {"total_approved_examples": count}


@router.get("/learning/training-export")
async def export_training_dataset(
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Download approved human-reviewed examples as a JSONL fine-tuning file."""
    jsonl_content = await dataset_exporter.export_jsonl(session)
    return Response(
        content=jsonl_content,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=training_dataset.jsonl"},
    )


@router.get("/learning/export-jsonl", include_in_schema=False)
async def export_training_dataset_alias(
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    return await export_training_dataset(session=session, _admin=admin)


# ---------------------------------------------------------------------------
# 7. Evaluations
# ---------------------------------------------------------------------------


@router.post("/evals/run", response_model=EvaluationSuiteResultDTO)
async def run_evaluation_suite(
    limit: int = Query(0, ge=0),
    eval_type: str = Query("deterministic"),
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Execute the evaluation benchmark suite and record a persistent run."""
    runtime = await get_production_agent_runtime(session)
    limit_val = limit if limit > 0 else None
    summary = await eval_runner.run_suite(
        session=session,
        runtime=runtime,
        limit=limit_val,
        eval_type=eval_type,
    )
    return EvaluationSuiteResultDTO(**summary)


@router.post("/evaluation/run", response_model=EvaluationSuiteResultDTO, include_in_schema=False)
async def run_evaluation_suite_alias(
    limit: int = Query(0, ge=0),
    eval_type: str = Query("deterministic"),
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    return await run_evaluation_suite(
        limit=limit, eval_type=eval_type, session=session, _admin=admin
    )


@router.get("/evals/runs", response_model=list[EvaluationRunDTO])
async def list_evaluation_runs(
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """List historical evaluation benchmark runs persisted in database."""
    stmt = select(EvaluationRun).order_by(desc(EvaluationRun.started_at)).limit(limit)
    res = await session.execute(stmt)
    runs = list(res.scalars().all())

    items = []
    for r in runs:
        results_data = []
        for cr in r.case_results or []:
            det = {}
            if cr.details:
                try:
                    det = json.loads(cr.details)
                except Exception:
                    det = {}
            results_data.append(
                {
                    "case_id": cr.case_id,
                    "case_name": det.get("case_name") or cr.case_id,
                    "passed": (cr.status == "PASS"),
                    "decision_correct": det.get("decision_correct")
                    if "decision_correct" in det
                    else None,
                    "expected_decision": cr.expected_decision or "",
                    "actual_decision": cr.actual_decision or "",
                    "keyword_score": det.get("keyword_score") if "keyword_score" in det else None,
                    "latency_ms": cr.latency_ms if cr.latency_ms is not None else None,
                    "tokens": cr.tokens,
                }
            )
        items.append(
            EvaluationRunDTO(
                id=r.id,
                eval_type=r.eval_type,
                provider=r.provider,
                model=r.model,
                prompt_version=r.prompt_version,
                dataset_version=r.dataset_version,
                total_cases=r.total_cases,
                passed_cases=r.passed_cases,
                pass_rate=r.pass_rate,
                decision_accuracy=r.decision_accuracy,
                average_latency_ms=r.avg_latency_ms,
                total_tokens=r.total_tokens,
                estimated_cost=r.estimated_cost,
                status=r.status,
                started_at=r.started_at,
                completed_at=r.completed_at,
                results=results_data,
            )
        )
    return items


# ---------------------------------------------------------------------------
# 8. Prompt Versioning
# ---------------------------------------------------------------------------


@router.get("/prompts/versions", response_model=list[PromptVersionDTO])
async def list_prompt_versions(
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """List all system prompt versions."""
    versions = await prompt_manager.list_versions(session)
    return [
        PromptVersionDTO(
            id=v.id,
            version=v.version,
            name=v.name,
            template=v.template,
            is_active=v.is_active,
            created_by=v.created_by,
            created_at=v.created_at,
            activated_at=v.activated_at,
        )
        for v in versions
    ]


@router.post("/prompts/versions", response_model=PromptVersionDTO)
async def create_prompt_version(
    payload: CreatePromptVersionRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Create a new immutable system prompt version."""
    existing = (
        await session.execute(select(PromptVersion).where(PromptVersion.version == payload.version))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Prompt version '{payload.version}' already exists. Versions are immutable.",
        )

    from sqlalchemy.exc import IntegrityError

    try:
        pv = await prompt_manager.create_version(
            session=session,
            version=payload.version,
            name=payload.name,
            template=payload.template,
            created_by=admin.username,
            set_active=payload.set_active,
        )
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Prompt version '{payload.version}' already exists. Versions are immutable.",
        )

    await write_audit_log(
        session=session,
        action="prompt.version.create",
        actor=admin.username,
        target=f"prompt_version:{pv.version}",
        details={"version": pv.version, "is_active": pv.is_active},
        ip_address=http_request.client.host if http_request.client else None,
    )

    return PromptVersionDTO(
        id=pv.id,
        version=pv.version,
        name=pv.name,
        template=pv.template,
        is_active=pv.is_active,
        created_by=pv.created_by,
        created_at=pv.created_at,
        activated_at=pv.activated_at,
    )


@router.post("/prompts/versions/{version}/activate")
async def activate_prompt_version(
    version: str,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Activate a specific prompt version."""
    active = await prompt_manager.activate_version(session, version)
    if not active:
        raise HTTPException(status_code=404, detail=f"Prompt version '{version}' not found")

    await write_audit_log(
        session=session,
        action="prompt.version.activate",
        actor=admin.username,
        target=f"prompt_version:{version}",
        details={"activated_version": version},
        ip_address=http_request.client.host if http_request.client else None,
    )

    return {"ok": True, "activated_version": active.version}
