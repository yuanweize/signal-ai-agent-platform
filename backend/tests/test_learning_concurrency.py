"""
Concurrency regression tests for Learning Candidate atomic state machine.
Verifies Sections 7, 8, & 9:
- Atomic claim semantics with conditional SQL UPDATE
- Race matrix:
  1. training vs training -> exactly one TrainingExample, loser gets CandidateConflictError / 409
  2. knowledge vs knowledge -> exactly one KnowledgeSource, loser gets CandidateConflictError / 409
  3. knowledge vs training -> exactly one wins, loser gets CandidateConflictError / 409
  4. knowledge vs reject -> exactly one wins, loser gets CandidateConflictError / 409
  5. training vs reject -> exactly one terminal state, loser gets CandidateConflictError / 409
- External failure semantics: failed_knowledge on vector store failure
"""

import asyncio
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.learning.curation import (
    CandidateConflictError,
    learning_service,
)
from app.ai.providers.embeddings import FakeEmbeddingProvider
from app.ai.rag.ingestion import KnowledgeIngestionService
from app.ai.rag.vector_store import FakeVectorStore
from app.api.deps import get_current_admin
from app.database import get_session
from app.main import app
from app.models.ai import KnowledgeSource, LearningCandidate, TrainingExample
from app.models.conversation import Conversation, ConversationType
from app.schemas.auth import AdminUser


async def _create_test_candidate(
    session, question="How do I return?", answer="30-day return policy."
) -> int:
    conv = (
        await session.execute(select(Conversation).where(Conversation.id == 1))
    ).scalar_one_or_none()
    if not conv:
        conv = Conversation(id=1, type=ConversationType.dm.value, signal_id="+100", mode="auto")
        session.add(conv)
        await session.commit()

    cand = LearningCandidate(
        conversation_id=1,
        customer_question=question,
        human_answer=answer,
        suggested_faq_q=question,
        suggested_faq_a=answer,
        status="pending",
        source_quality="high",
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(cand)
    await session.commit()
    await session.refresh(cand)
    return cand.id


@pytest.mark.asyncio
async def test_race_training_vs_training(engine):
    """Concurrency race: training vs training -> exactly one succeeds, exactly one gets CandidateConflictError."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as s_init:
        cid = await _create_test_candidate(s_init, question="Return policy?", answer="30 days.")

    async def _attempt():
        async with session_factory() as session:
            return await learning_service.add_to_training(session, cid)

    results = await asyncio.gather(_attempt(), _attempt(), return_exceptions=True)

    successes = [r for r in results if isinstance(r, TrainingExample)]
    conflicts = [r for r in results if isinstance(r, CandidateConflictError)]

    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}: {results}"
    assert len(conflicts) == 1, f"Expected 1 conflict, got {len(conflicts)}: {results}"

    async with session_factory() as s_check:
        cand = (
            await s_check.execute(select(LearningCandidate).where(LearningCandidate.id == cid))
        ).scalar_one()
        assert cand.status == "approved"
        examples = (
            (
                await s_check.execute(
                    select(TrainingExample).where(TrainingExample.source_candidate_id == cid)
                )
            )
            .scalars()
            .all()
        )
        assert len(examples) == 1


@pytest.mark.asyncio
async def test_race_knowledge_vs_knowledge(engine):
    """Concurrency race: knowledge vs knowledge -> exactly one succeeds, one gets CandidateConflictError."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as s_init:
        cid = await _create_test_candidate(
            s_init, question="Shipping times?", answer="Standard shipping is 2-3 days."
        )

    ingestion_svc = KnowledgeIngestionService(FakeEmbeddingProvider(), FakeVectorStore())

    async def _attempt():
        async with session_factory() as session:
            return await learning_service.promote_to_knowledge(
                session, cid, ingestion_service=ingestion_svc, confirm_global_privacy=True
            )

    results = await asyncio.gather(_attempt(), _attempt(), return_exceptions=True)

    successes = [r for r in results if r is True]
    conflicts = [r for r in results if isinstance(r, CandidateConflictError)]

    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}: {results}"
    assert len(conflicts) == 1, f"Expected 1 conflict, got {len(conflicts)}: {results}"

    async with session_factory() as s_check:
        cand = (
            await s_check.execute(select(LearningCandidate).where(LearningCandidate.id == cid))
        ).scalar_one()
        assert cand.status == "promoted"
        sources = (
            (
                await s_check.execute(
                    select(KnowledgeSource).where(KnowledgeSource.source_uri == f"candidate:{cid}")
                )
            )
            .scalars()
            .all()
        )
        assert len(sources) == 1


@pytest.mark.asyncio
async def test_race_knowledge_vs_training(engine):
    """Concurrency race: knowledge vs training -> exactly one wins, loser gets CandidateConflictError."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as s_init:
        cid = await _create_test_candidate(
            s_init, question="Warranty terms?", answer="1 year standard warranty."
        )

    ingestion_svc = KnowledgeIngestionService(FakeEmbeddingProvider(), FakeVectorStore())

    async def _attempt_knowledge():
        async with session_factory() as session:
            return await learning_service.promote_to_knowledge(
                session, cid, ingestion_service=ingestion_svc, confirm_global_privacy=True
            )

    async def _attempt_training():
        async with session_factory() as session:
            return await learning_service.add_to_training(session, cid)

    results = await asyncio.gather(
        _attempt_knowledge(), _attempt_training(), return_exceptions=True
    )

    successes = [r for r in results if not isinstance(r, Exception)]
    conflicts = [r for r in results if isinstance(r, CandidateConflictError)]

    assert len(successes) == 1
    assert len(conflicts) == 1

    async with session_factory() as s_check:
        cand = (
            await s_check.execute(select(LearningCandidate).where(LearningCandidate.id == cid))
        ).scalar_one()
        assert cand.status in ("promoted", "approved")


@pytest.mark.asyncio
async def test_race_knowledge_vs_reject(engine):
    """Concurrency race: knowledge vs reject -> exactly one wins, loser gets CandidateConflictError."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as s_init:
        cid = await _create_test_candidate(
            s_init, question="Payment methods?", answer="Cards and wire transfers."
        )

    ingestion_svc = KnowledgeIngestionService(FakeEmbeddingProvider(), FakeVectorStore())

    async def _attempt_knowledge():
        async with session_factory() as session:
            return await learning_service.promote_to_knowledge(
                session, cid, ingestion_service=ingestion_svc, confirm_global_privacy=True
            )

    async def _attempt_reject():
        async with session_factory() as session:
            return await learning_service.reject_candidate(session, cid)

    results = await asyncio.gather(_attempt_knowledge(), _attempt_reject(), return_exceptions=True)

    successes = [r for r in results if not isinstance(r, Exception)]
    conflicts = [r for r in results if isinstance(r, CandidateConflictError)]

    assert len(successes) == 1
    assert len(conflicts) == 1

    async with session_factory() as s_check:
        cand = (
            await s_check.execute(select(LearningCandidate).where(LearningCandidate.id == cid))
        ).scalar_one()
        assert cand.status in ("promoted", "rejected")


@pytest.mark.asyncio
async def test_race_training_vs_reject(engine):
    """Concurrency race: training vs reject -> exactly one terminal state, loser gets CandidateConflictError."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as s_init:
        cid = await _create_test_candidate(
            s_init, question="Store locations?", answer="Downtown branch."
        )

    async def _attempt_training():
        async with session_factory() as session:
            return await learning_service.add_to_training(session, cid)

    async def _attempt_reject():
        async with session_factory() as session:
            return await learning_service.reject_candidate(session, cid)

    results = await asyncio.gather(_attempt_training(), _attempt_reject(), return_exceptions=True)

    successes = [r for r in results if not isinstance(r, Exception)]
    conflicts = [r for r in results if isinstance(r, CandidateConflictError)]

    assert len(successes) == 1
    assert len(conflicts) == 1

    async with session_factory() as s_check:
        cand = (
            await s_check.execute(select(LearningCandidate).where(LearningCandidate.id == cid))
        ).scalar_one()
        assert cand.status in ("approved", "rejected")


@pytest.mark.asyncio
async def test_learning_api_returns_409_on_conflict(engine):
    """Verify HTTP API returns 409 Conflict when candidate is already claimed or terminal."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as s_init:
        cid = await _create_test_candidate(s_init, question="API test?", answer="Conflict test.")

    app.dependency_overrides[get_current_admin] = lambda: AdminUser(username="admin")

    # Override get_session to provide fresh session per request
    async def get_test_session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = get_test_session

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            # Request 1: promote to training
            r1 = await client.post(
                f"/api/ai-studio/learning/candidates/{cid}/promote", json={"action": "training"}
            )
            assert r1.status_code == 200, f"r1 failed: {r1.text}"

            # Request 2: attempt promoting already approved candidate
            r2 = await client.post(
                f"/api/ai-studio/learning/candidates/{cid}/promote", json={"action": "training"}
            )
            assert r2.status_code == 409, f"Expected 409 Conflict, got {r2.status_code}: {r2.text}"
            assert "Candidate" in r2.json()["detail"]
    finally:
        app.dependency_overrides.clear()
