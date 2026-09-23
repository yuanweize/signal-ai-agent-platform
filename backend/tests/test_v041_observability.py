"""
Comprehensive Test Suite for AI Studio v0.4.1 Product Completion & Observability.

Covers:
- Provider-neutral structured TokenUsage and LLMResult/LLMToolResult
- OpenAI usage parsing: exact tokens, cached tokens, reasoning tokens, and unavailable provenance
- Elimination of fake len(content)//4 token estimation
- Pricing telemetry: truthful cost calculation; never guesses for unconfigured models
- Multi-step turn token aggregation (Planner + Final Generation -> cumulative AIRun totals & AIModelCall traces)
- Learning loop promotion routing: action='training' vs action='knowledge' vs invalid (422)
- Explicit global privacy confirmation invariant
- Scoped Memory 'All Scopes' retrieval bugfix
- Persistent EvaluationRun history (fixing [] stub)
- Evaluation traffic source isolation from production KPIs
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.ai.providers.llm import parse_openai_usage
from app.ai.telemetry.pricing import calculate_cost
from app.ai.types.usage import ModelCallRecord, TokenUsage
from app.main import app
from app.models.ai import (
    AIModelCall,
    AIRun,
    EvaluationRun,
    LearningCandidate,
    MemoryItem,
    TrainingExample,
)
from app.models.conversation import Conversation, ConversationType


@pytest.fixture(autouse=True)
def override_deps(session):
    from app.api.deps import get_current_admin
    from app.database import get_session
    from app.schemas.auth import AdminUser

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_admin] = lambda: AdminUser(
        username="admin", is_super_admin=True
    )
    yield
    app.dependency_overrides.clear()


# ===========================================================================
# 1. Token Telemetry & Usage Contract Tests
# ===========================================================================


def test_parse_openai_usage_exact_and_extended_fields():
    class DummyPromptDetails:
        cached_tokens = 45

    class DummyCompletionDetails:
        reasoning_tokens = 30

    class DummyUsage:
        prompt_tokens = 120
        completion_tokens = 60
        total_tokens = 180
        prompt_tokens_details = DummyPromptDetails()
        completion_tokens_details = DummyCompletionDetails()

    usage = parse_openai_usage(DummyUsage())
    assert usage.input_tokens == 120
    assert usage.output_tokens == 60
    assert usage.total_tokens == 180
    assert usage.cached_input_tokens == 45
    assert usage.reasoning_tokens == 30
    assert usage.usage_source == "provider"


def test_parse_openai_usage_missing_never_fakes_tokens():
    usage = parse_openai_usage(None)
    assert usage.usage_source == "unavailable"
    assert usage.total_tokens is None
    assert usage.input_tokens is None
    assert usage.output_tokens is None

    empty_usage = parse_openai_usage(object())
    assert empty_usage.usage_source == "unavailable"
    assert empty_usage.total_tokens is None


def test_pricing_never_guesses_for_unconfigured_model():
    # Unknown model -> Must return (None, None)
    cost, curr = calculate_cost("custom-unconfigured-model", 500, 100)
    assert cost is None
    assert curr is None

    # Known model -> Calculates exact cost
    cost, curr = calculate_cost("gpt-4o-mini", 1_000_000, 1_000_000)
    assert cost == 0.75  # 0.15 + 0.60
    assert curr == "USD"


# ===========================================================================
# 2. Token Aggregation Across Planner + Final Generation
# ===========================================================================


@pytest.mark.asyncio
async def test_planner_and_final_generation_token_aggregation(session):
    from app.ai.observability.tracing import LocalTracer

    tracer = LocalTracer()
    conv = Conversation(type=ConversationType.dm.value, signal_id="+1001", mode="copilot")
    session.add(conv)
    await session.commit()
    await session.refresh(conv)

    planner_call = ModelCallRecord(
        phase="tool_planner",
        provider="openai_compatible",
        model="test-planner",
        latency_ms=150,
        usage=TokenUsage(
            input_tokens=100,
            output_tokens=10,
            total_tokens=110,
            usage_source="provider",
        ),
        success=True,
    )
    generation_call = ModelCallRecord(
        phase="response_generation",
        provider="openai_compatible",
        model="test-gen",
        latency_ms=400,
        usage=TokenUsage(
            input_tokens=300,
            output_tokens=40,
            total_tokens=340,
            usage_source="provider",
        ),
        success=True,
    )

    run = await tracer.record_run(
        session=session,
        conversation_id=conv.id,
        decision="reply",
        model="test-gen",
        provider="openai_compatible",
        input_tokens=400,
        output_tokens=50,
        total_tokens=450,
        usage_source="provider",
        llm_call_count=2,
        model_calls=[planner_call, generation_call],
        traffic_source="production",
    )

    assert run.input_tokens == 400
    assert run.output_tokens == 50
    assert run.total_tokens == 450
    assert run.llm_call_count == 2
    assert run.traffic_source == "production"

    # Verify per-call AIModelCall records were persisted
    model_calls = (
        (await session.execute(select(AIModelCall).where(AIModelCall.ai_run_id == run.id)))
        .scalars()
        .all()
    )
    assert len(model_calls) == 2
    phases = {mc.phase for mc in model_calls}
    assert phases == {"tool_planner", "response_generation"}


# ===========================================================================
# 3. Learning Loop Promotion Routing & Privacy Confirmation
# ===========================================================================


@pytest.mark.asyncio
async def test_learning_promotion_routing_training_vs_knowledge(session):
    conv = Conversation(type=ConversationType.dm.value, signal_id="+1002", mode="copilot")
    session.add(conv)
    await session.commit()
    await session.refresh(conv)

    cand1 = LearningCandidate(
        conversation_id=conv.id,
        customer_question="What are your hours?",
        human_answer="We are open 9am to 5pm CET.",
        status="pending",
        source_quality="high",
        category="general",
        language="en",
    )
    cand2 = LearningCandidate(
        conversation_id=conv.id,
        customer_question="Can I pay with Bitcoin?",
        human_answer="Yes, Bitcoin is accepted on checkout.",
        status="pending",
        source_quality="high",
        category="payment",
        language="en",
    )
    session.add_all([cand1, cand2])
    await session.commit()
    await session.refresh(cand1)
    await session.refresh(cand2)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Action = training -> Must create TrainingExample, NOT KnowledgeDocument
        resp_train = await client.post(
            f"/api/ai-studio/learning/candidates/{cand1.id}/promote",
            json={"action": "training"},
        )
        assert resp_train.status_code == 200, resp_train.text
        assert resp_train.json()["status"] == "approved"

        train_ex = (
            await session.execute(
                select(TrainingExample).where(TrainingExample.source_candidate_id == cand1.id)
            )
        ).scalar_one_or_none()
        assert train_ex is not None
        assert "What are your hours?" in train_ex.input_context

        # 2. Action = knowledge without explicit privacy confirmation -> Rejected
        resp_know_unconf = await client.post(
            f"/api/ai-studio/learning/candidates/{cand2.id}/promote",
            json={
                "action": "knowledge",
                "scope_type": "global",
                "confirm_global_privacy": False,
            },
        )
        assert resp_know_unconf.status_code == 400
        assert "explicit privacy confirmation" in resp_know_unconf.text

        # 3. Action = knowledge with confirm_global_privacy=True -> Promoted to Knowledge
        resp_know_conf = await client.post(
            f"/api/ai-studio/learning/candidates/{cand2.id}/promote",
            json={
                "action": "knowledge",
                "scope_type": "global",
                "confirm_global_privacy": True,
            },
        )
        assert resp_know_conf.status_code == 200, resp_know_conf.text
        assert resp_know_conf.json()["status"] == "promoted"

        # 4. Invalid action -> 422
        resp_invalid = await client.post(
            f"/api/ai-studio/learning/candidates/{cand1.id}/promote",
            json={"action": "unsupported_action"},
        )
        assert resp_invalid.status_code == 422


# ===========================================================================
# 4. Scoped Memory 'All Scopes' Bugfix
# ===========================================================================


@pytest.mark.asyncio
async def test_memory_all_scopes_query(session):
    m_user = MemoryItem(
        scope_type="user",
        scope_id="123",
        content="Prefers dark roast",
        memory_type="preference",
        importance=4,
        created_by="system",
    )
    m_group = MemoryItem(
        scope_type="group",
        scope_id="grp_456",
        content="Group rules discussed",
        memory_type="fact",
        importance=3,
        created_by="system",
    )
    m_global = MemoryItem(
        scope_type="global",
        scope_id="",
        content="Store holiday schedule",
        memory_type="fact",
        importance=5,
        created_by="system",
    )
    session.add_all([m_user, m_group, m_global])
    await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Omitting scope_type or scope_type=all should return all 3 scopes
        resp_all = await client.get("/api/ai-studio/memory")
        assert resp_all.status_code == 200
        items = resp_all.json()
        assert len(items) >= 3
        scopes = {i["scope_type"] for i in items}
        assert "user" in scopes
        assert "group" in scopes
        assert "global" in scopes

        # Querying specific scope works
        resp_user = await client.get("/api/ai-studio/memory?scope_type=user")
        assert resp_user.status_code == 200
        user_items = resp_user.json()
        assert all(i["scope_type"] == "user" for i in user_items)


# ===========================================================================
# 5. Persistent Evaluation Runs & Traffic Source Isolation
# ===========================================================================


@pytest.mark.asyncio
async def test_evaluation_run_persistence_and_traffic_isolation(session):
    conv = Conversation(type=ConversationType.dm.value, signal_id="+1003", mode="copilot")
    session.add(conv)
    await session.commit()
    await session.refresh(conv)

    # 1. Run evaluation
    from app.ai.evals.runner import EvaluationRunner
    from app.ai.providers.llm import FakeLLMProvider
    from app.ai.runtime.agent_runtime import AgentRuntime

    runtime = AgentRuntime(llm_provider=FakeLLMProvider(), is_test=True)
    runner = EvaluationRunner()
    summary = await runner.run_suite(session=session, runtime=runtime, limit=2)
    assert summary["total_cases"] == 2

    # 2. Verify EvaluationRun persisted in database
    eval_runs = (await session.execute(select(EvaluationRun))).scalars().all()
    assert len(eval_runs) >= 1
    latest = eval_runs[-1]
    assert latest.total_cases == 2
    assert latest.status == "completed"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /api/ai-studio/evals/runs must return real persisted records (not [])
        resp_history = await client.get("/api/ai-studio/evals/runs")
        assert resp_history.status_code == 200
        history = resp_history.json()
        assert len(history) >= 1
        assert history[0]["id"] == latest.id

        # 3. Overview must isolate evaluation runs from production total_ai_runs
        resp_overview = await client.get("/api/ai-studio/overview?time_range=all")
        assert resp_overview.status_code == 200
        overview = resp_overview.json()
        all_runs = (await session.execute(select(AIRun))).scalars().all()
        eval_run_count = sum(1 for r in all_runs if r.traffic_source == "evaluation")
        prod_run_count = sum(1 for r in all_runs if r.traffic_source == "production")
        assert eval_run_count >= 2
        assert overview["total_runs"] == prod_run_count


def test_token_usage_combine_seedless_provenance():
    u1 = TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15, usage_source="provider")
    u2 = TokenUsage(input_tokens=20, output_tokens=10, total_tokens=30, usage_source="provider")
    combined = TokenUsage.combine([u1, u2])
    assert combined.total_tokens == 45
    assert combined.usage_source == "provider"

    # With unavailable call
    u3 = TokenUsage(usage_source="unavailable")
    combined_partial = TokenUsage.combine([u1, u3])
    assert combined_partial.usage_source == "partial"

    # Empty list
    empty = TokenUsage.combine([])
    assert empty.usage_source == "unavailable"


def test_pricing_dated_snapshots_vs_variants():
    # Dated snapshot resolves to family pricing
    cost, curr = calculate_cost("gpt-4o-2024-08-06", 1_000_000, 1_000_000)
    assert cost == 12.50
    assert curr == "USD"

    cost_mini, _ = calculate_cost("gpt-4o-mini-2024-07-18", 1_000_000, 1_000_000)
    assert cost_mini == 0.75

    # Distinct variants are NOT aliased
    cost_rt, _ = calculate_cost("gpt-4o-realtime-preview", 1000, 1000)
    assert cost_rt is None

    cost_audio, _ = calculate_cost("gpt-4o-audio-preview", 1000, 1000)
    assert cost_audio is None


def test_tool_registry_duplicate_mcp_tool_protection():
    from app.ai.tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(
        name="search",
        description="Server A search",
        func=lambda: "A",
        is_mcp=True,
        mcp_server_name="server_a",
    )
    # Server B tries to register same tool name
    registry.register(
        name="search",
        description="Server B search",
        func=lambda: "B",
        is_mcp=True,
        mcp_server_name="server_b",
    )
    # Must preserve server A tool
    tool = registry.get_tool("search")
    assert tool is not None
    assert tool.mcp_server_name == "server_a"
    assert tool.description == "Server A search"


@pytest.mark.asyncio
async def test_diagnostics_endpoint_configured_provider_no_unbound_error(session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/ai-studio/diagnostics")
        assert resp.status_code == 200
        data = resp.json()
        assert "llm" in data
        assert data["llm"]["status"] in (
            "configured",
            "not_validated",
            "degraded",
            "disabled",
            "live_verified",
        )
