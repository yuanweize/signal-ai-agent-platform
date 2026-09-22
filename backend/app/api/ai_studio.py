"""
AI Studio API: Management console routes for Knowledge, Memory, Skills, MCP, Learning, Evals, and Traces.
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import desc, select
from sqlalchemy import func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.evals.runner import eval_runner
from app.ai.learning.curation import learning_service
from app.ai.learning.examples import dataset_exporter
from app.ai.mcp.client import mcp_manager
from app.ai.prompts.manager import prompt_manager
from app.ai.rag.ingestion import KnowledgeIngestionService
from app.ai.runtime.agent_runtime import agent_runtime
from app.ai.skills.registry import skill_registry
from app.api.deps import AdminUser, get_current_admin
from app.database import get_session
from app.models.ai import (
    AIRun,
    AISuggestion,
    FeedbackEvent,
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

router = APIRouter(prefix="/ai-studio", tags=["AI Studio"])


# ---------------------------------------------------------------------------
# 1. Overview & Traces
# ---------------------------------------------------------------------------


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

    return AIOverviewMetricsDTO(
        total_ai_runs=total_runs,
        automation_rate=auto_rate,
        copilot_rate=copilot_rate,
        human_takeover_rate=takeover_rate,
        suggestion_acceptance_rate=acc_rate,
        suggestion_edit_rate=edit_rate,
        suggestion_rejection_rate=rej_rate,
        rag_hit_rate=0.85,
        memory_items_count=memory_count,
        knowledge_documents_count=docs_count,
        average_latency_ms=round(float(avg_lat), 1),
        total_tokens_used=int(tokens_sum),
    )


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

    ingestion = KnowledgeIngestionService(
        embedding_provider=agent_runtime.embedding_provider,
        vector_store=agent_runtime.vector_store,
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

    ingestion = KnowledgeIngestionService(
        embedding_provider=agent_runtime.embedding_provider,
        vector_store=agent_runtime.vector_store,
    )
    doc = await ingestion.ingest_document(
        session=session,
        source_id=source_id,
        title=payload.title,
        content=payload.content,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
    )
    return {"ok": True, "document_id": doc.id, "chunks_created": doc.chunk_count}


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

    ingestion = KnowledgeIngestionService(
        embedding_provider=agent_runtime.embedding_provider,
        vector_store=agent_runtime.vector_store,
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
    return {"ok": True, "document_id": doc.id, "chunks_created": doc.chunk_count}


@router.post("/knowledge/search", response_model=list[KnowledgeSearchResultDTO])
async def test_knowledge_retrieval(
    query: str,
    limit: int = 5,
    is_group: bool = False,
    group_id: str | None = None,
    user_id: str | None = None,
    _admin: AdminUser = Depends(get_current_admin),
):
    """Simulate RAG search with scope isolation testing."""
    chunks = await agent_runtime.retriever.retrieve(
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
    mem = await agent_runtime.memory.add(
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
    ok = await agent_runtime.memory.delete(session=session, memory_id=memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory item not found")
    return {"ok": True, "deleted_memory_id": memory_id}


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
    ok = skill_registry.set_enabled(skill_name, payload.is_enabled)
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
        dtos.append(
            MCPServerDTO(
                id=s.id,
                name=s.name,
                transport=s.transport,
                command_or_url=s.command_or_url,
                is_enabled=s.is_enabled,
                status=s.status,
                last_connected_at=s.last_connected_at,
                error_message=s.error_message,
                tools_count=act.get("tools_count", 0),
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
    server = MCPServerConfig(
        name=payload.name,
        transport=payload.transport,
        command_or_url=payload.command_or_url,
        args_json=json.dumps(payload.args),
        env_json=json.dumps(payload.env),
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
        command_or_url=server.command_or_url,
        is_enabled=server.is_enabled,
        status=server.status,
        tools_count=0,
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
        env = json.loads(server.env_json) if server.env_json else {}
        tools = await mcp_manager.connect_server(
            name=server.name,
            transport=server.transport,
            command_or_url=server.command_or_url,
            args=args,
            env=env,
        )
        server.status = "connected"
        server.last_connected_at = datetime.utcnow()
        server.error_message = None
        await session.commit()
        return {"ok": True, "status": "connected", "tools_discovered": len(tools)}
    except Exception as e:
        server.status = "error"
        server.error_message = str(e)
        await session.commit()
        raise HTTPException(status_code=502, detail=f"Failed to connect MCP server: {e}")


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
    ingestion = KnowledgeIngestionService(
        embedding_provider=agent_runtime.embedding_provider,
        vector_store=agent_runtime.vector_store,
    )
    ok = await learning_service.promote_to_knowledge(
        session=session,
        candidate_id=candidate_id,
        ingestion_service=ingestion,
        reviewer_name=admin.username,
        faq_question=payload.faq_question,
        faq_answer=payload.faq_answer,
    )
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


# ---------------------------------------------------------------------------
# 7. Evaluations
# ---------------------------------------------------------------------------


@router.post("/evals/run", response_model=EvaluationSuiteResultDTO)
async def run_evaluation_suite(
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Execute the golden evaluation benchmark suite."""
    summary = await eval_runner.run_suite(session=session, runtime=agent_runtime)
    return EvaluationSuiteResultDTO(**summary)


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
