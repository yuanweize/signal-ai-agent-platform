"""
AI Studio API: Management console routes for Knowledge, Memory, Skills, MCP, Learning, Evals, and Traces.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import desc, select
from sqlalchemy import func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.evals.runner import eval_runner
from app.ai.learning.curation import learning_service
from app.ai.learning.examples import dataset_exporter
from app.ai.mcp.client import mcp_manager, parse_and_decrypt_env
from app.ai.prompts.manager import prompt_manager
from app.ai.rag.ingestion import KnowledgeIngestionService
from app.ai.runtime.factory import get_production_agent_runtime
from app.ai.skills.registry import skill_registry
from app.api.deps import AdminUser, get_current_admin
from app.database import get_session
from app.models.ai import (
    AIRun,
    AISuggestion,
    FeedbackEvent,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    MCPServerConfig,
    MemoryItem,
)
from app.schemas.ai import (
    AIOverviewMetricsDTO,
    AIRunDTO,
    CreateDocumentRequest,
    CreateFAQRequest,
    CreateKnowledgeSourceRequest,
    CreateMCPServerRequest,
    CreateMemoryRequest,
    EvaluationSuiteResultDTO,
    KnowledgeSearchResultDTO,
    KnowledgeSourceDTO,
    LearningCandidateDTO,
    MCPServerDTO,
    MemoryItemDTO,
    PromoteCandidateRequest,
    SkillDTO,
    ToggleSkillRequest,
)
from app.services.audit_log import write_audit_log
from app.services.runtime_config import encrypt_value

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


@router.get("/overview", response_model=AIOverviewMetricsDTO)
async def get_ai_overview_metrics(
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Return aggregated platform metrics across runs, copilot suggestions, and memory."""
    total_runs = (await session.execute(select(sa_func.count(AIRun.id)))).scalar() or 0
    total_sugs = (await session.execute(select(sa_func.count(AISuggestion.id)))).scalar() or 0

    accepted_sugs = (
        await session.execute(
            select(sa_func.count(AISuggestion.id)).where(AISuggestion.status == "accepted")
        )
    ).scalar() or 0

    edited_sugs = (
        await session.execute(
            select(sa_func.count(AISuggestion.id)).where(AISuggestion.status == "edited")
        )
    ).scalar() or 0

    rejected_sugs = (
        await session.execute(
            select(sa_func.count(AISuggestion.id)).where(AISuggestion.status == "rejected")
        )
    ).scalar() or 0

    auto_sent = (
        await session.execute(
            select(sa_func.count(AISuggestion.id)).where(AISuggestion.status == "auto_sent")
        )
    ).scalar() or 0

    manual_takeovers = (
        await session.execute(
            select(sa_func.count(FeedbackEvent.id)).where(
                FeedbackEvent.event_type == "human_takeover"
            )
        )
    ).scalar() or 0

    docs_count = (await session.execute(select(sa_func.count(KnowledgeDocument.id)))).scalar() or 0
    sources_count = (await session.execute(select(sa_func.count(KnowledgeSource.id)))).scalar() or 0
    chunks_count = (await session.execute(select(sa_func.count(KnowledgeChunk.id)))).scalar() or 0
    memory_count = (await session.execute(select(sa_func.count(MemoryItem.id)))).scalar() or 0

    avg_lat = (await session.execute(select(sa_func.avg(AIRun.latency_ms)))).scalar() or 0.0
    tokens_sum = (await session.execute(select(sa_func.sum(AIRun.tokens)))).scalar() or 0

    human_reviewed = accepted_sugs + edited_sugs + rejected_sugs
    acc_rate = round(accepted_sugs / human_reviewed, 3) if human_reviewed > 0 else 0.0
    edit_rate = round(edited_sugs / human_reviewed, 3) if human_reviewed > 0 else 0.0
    rej_rate = round(rejected_sugs / human_reviewed, 3) if human_reviewed > 0 else 0.0

    auto_rate = round(auto_sent / total_runs, 3) if total_runs > 0 else 0.0
    copilot_rate = round(total_sugs / total_runs, 3) if total_runs > 0 else 0.0
    takeover_rate = round(manual_takeovers / total_runs, 3) if total_runs > 0 else 0.0
    runs_with_rag = (
        await session.execute(
            select(sa_func.count(AIRun.id)).where(
                AIRun.retrieval.is_not(None),
                AIRun.retrieval != "[]",
                AIRun.retrieval != "",
            )
        )
    ).scalar() or 0
    actual_rag_hit_rate = round(runs_with_rag / total_runs, 3) if total_runs > 0 else 0.0

    return AIOverviewMetricsDTO(
        total_ai_runs=total_runs,
        total_runs=total_runs,
        automation_rate=auto_rate,
        copilot_rate=copilot_rate,
        human_takeover_rate=takeover_rate,
        suggestion_acceptance_rate=acc_rate,
        copilot_acceptance_rate=acc_rate,
        copilot_suggestions_count=total_sugs,
        suggestion_edit_rate=edit_rate,
        copilot_avg_edit_ratio=edit_rate,
        suggestion_rejection_rate=rej_rate,
        rag_hit_rate=actual_rag_hit_rate,
        memory_items_count=memory_count,
        knowledge_documents_count=docs_count,
        knowledge_sources_count=sources_count,
        knowledge_chunks_count=chunks_count,
        average_latency_ms=round(float(avg_lat), 1),
        avg_latency_ms=round(float(avg_lat), 1),
        total_tokens_used=int(tokens_sum),
        total_tokens=int(tokens_sum),
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
        llm_status = (
            "configured"
            if llm_configured
            else ("not_validated" if getattr(llm_prov, "api_key_optional", False) else "degraded")
        )

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
        if hasattr(vec_store, "client") and getattr(vec_store, "client") is not None:
            try:
                await vec_store.client.get_collections()
                vec_status = "connected"
            except Exception:
                vec_status = "degraded"
        elif vec_provider == "FakeVectorStore":
            vec_status = "degraded" if settings.environment != "test" else "configured"

    # 4. RAG Index status based on component health (Section 54)
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

    # 6. Signal Gateway status using effective runtime config (Section 23)
    effective_sig_url = (
        signal_client._api_url or runtime_cfg.get("signal_api_url") or settings.signal_api_url
    )
    effective_sig_phone = (
        signal_client._phone_number
        or runtime_cfg.get("signal_phone_number")
        or settings.signal_phone_number
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
            "url": settings.signal_api_url,
            "status": gw_status,
        },
    }


@router.get("/runs", response_model=list[AIRunDTO])
async def list_ai_runs(
    limit: int = Query(50, ge=1, le=200),
    decision: str | None = None,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Query recent AI execution traces."""
    stmt = select(AIRun).order_by(desc(AIRun.created_at)).limit(limit)
    if decision:
        stmt = stmt.where(AIRun.decision == decision)

    res = await session.execute(stmt)
    runs = list(res.scalars().all())

    items = []
    for r in runs:
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
                retrieval=json.loads(r.retrieval) if r.retrieval else [],
                memory=json.loads(r.memory) if r.memory else [],
                tool_calls=json.loads(r.tool_calls) if r.tool_calls else [],
                decision=r.decision,
                confidence=r.confidence,
                latency_ms=r.latency_ms,
                tokens=r.tokens,
                errors=r.errors,
                final_message_id=r.final_message_id,
                created_at=r.created_at,
            )
        )
    return items


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
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Simulate RAG search with scope isolation testing."""
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
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    return await test_knowledge_retrieval(
        query=query,
        limit=limit,
        is_group=is_group,
        group_id=group_id,
        user_id=user_id,
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
        return {"ok": True, "document_id": document_id, "chunks_reindexed": chunks_count}
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
    return {"ok": True, **result}


# ---------------------------------------------------------------------------
# 3. Scoped Durable Memory
# ---------------------------------------------------------------------------


@router.get("/memory", response_model=list[MemoryItemDTO])
async def list_memories(
    scope_type: str = Query("user"),
    scope_id: str | None = Query(None),
    limit: int = Query(50),
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    stmt = select(MemoryItem).where(MemoryItem.scope_type == scope_type)
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
            importance=m.importance,
            sensitivity=m.sensitivity,
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not ok:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"ok": True, "promoted_candidate_id": candidate_id}


@router.post("/learning/candidates/{candidate_id}/reject")
async def reject_candidate(
    candidate_id: int,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    ok = await learning_service.reject_candidate(
        session=session,
        candidate_id=candidate_id,
        reviewer_name=admin.username,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"ok": True, "rejected_candidate_id": candidate_id}


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
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Execute the golden evaluation benchmark suite."""
    runtime = await get_production_agent_runtime(session)
    summary = await eval_runner.run_suite(session=session, runtime=runtime)
    return EvaluationSuiteResultDTO(**summary)


@router.post("/evaluation/run", response_model=EvaluationSuiteResultDTO, include_in_schema=False)
async def run_evaluation_suite_alias(
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    return await run_evaluation_suite(session=session, _admin=admin)


@router.get("/evals/runs")
async def list_evaluation_runs(
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """List historical evaluation runs."""
    return []


# ---------------------------------------------------------------------------
# 8. Prompt Versioning
# ---------------------------------------------------------------------------


@router.get("/prompts/versions")
async def list_prompt_versions(
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    versions = await prompt_manager.list_versions(session)
    return [
        {
            "id": v.id,
            "version": v.version,
            "name": v.name,
            "template": v.template,
            "is_active": v.is_active,
            "created_by": v.created_by,
            "created_at": v.created_at,
            "activated_at": v.activated_at,
        }
        for v in versions
    ]


@router.post("/prompts/versions/{version}/activate")
async def activate_prompt_version(
    version: str,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    active = await prompt_manager.activate_version(session, version)
    if not active:
        raise HTTPException(status_code=404, detail=f"Prompt version '{version}' not found")
    return {"ok": True, "activated_version": active.version}
