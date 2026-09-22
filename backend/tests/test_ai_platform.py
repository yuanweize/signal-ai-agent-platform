"""
Comprehensive Test Suite for AI Platform v0.4
Covers:
- Progressive Skills loading & dynamic prompt assembly
- Scoped RAG retrieval & strict cross-scope privacy isolation (global / group / user)
- Scoped Memory extraction, PII redaction, search & deletion
- Tool permissions & governed execution (read auto-run vs write approval-required)
- Agent Runtime & Copilot Draft Generation
- Copilot Suggestion Lifecycle: Accept, Edit (distance & ratio), Reject
- Message Provenance tracking (origin, ai_run_id, ai_suggestion_id, admin_identity)
- Human-in-the-loop Learning Loop: Candidate creation, FAQ promotion, and JSONL training export
- Golden Dataset Evaluation Suite Runner & Metrics
- Inbound message pipeline idempotency
"""

import json
from datetime import UTC
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.evals.runner import EvaluationRunner
from app.ai.learning.curation import LearningCandidateService
from app.ai.learning.examples import TrainingDatasetExporter
from app.ai.memory.extraction import redact_sensitive_pii
from app.ai.memory.providers import NativeMemoryProvider
from app.ai.providers.embeddings import FakeEmbeddingProvider
from app.ai.providers.llm import FakeLLMProvider
from app.ai.rag.ingestion import KnowledgeIngestionService
from app.ai.rag.retrieval import KnowledgeRetriever
from app.ai.rag.vector_store import FakeVectorStore
from app.ai.runtime.agent_runtime import AgentRuntime
from app.ai.runtime.context import AgentContext
from app.ai.runtime.decisions import AgentDecision
from app.ai.skills.registry import SkillRegistry
from app.ai.tools.permissions import ToolPermission
from app.ai.tools.registry import ToolRegistry
from app.main import app
from app.models.ai import (
    AIRun,
    AISuggestion,
    KnowledgeSource,
)
from app.models.conversation import (
    Conversation,
    ConversationMode,
    Message,
    MessageActor,
    MessageDirection,
    MessageOrigin,
)
from app.models.user import User


@pytest.fixture(autouse=True)
def override_deps(session):
    from app.api.deps import get_current_admin
    from app.database import get_session
    from app.schemas.auth import AdminUser

    app.dependency_overrides[get_current_admin] = lambda: AdminUser(username="admin")
    app.dependency_overrides[get_session] = lambda: session
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}


# ---------------------------------------------------------------------------
# 1. Progressive Skills System Tests
# ---------------------------------------------------------------------------
def test_skills_progressive_loading():
    registry = SkillRegistry()
    skills = registry.list_skills()
    assert len(skills) >= 6
    skill_names = [s.name for s in skills]
    assert "product-sales" in skill_names
    assert "customer-support" in skill_names
    assert "complaints" in skill_names
    assert "order-status" in skill_names
    assert "human-handoff" in skill_names
    assert "group-moderation" in skill_names

    # Lightweight summaries for routing context
    summaries = registry.get_summaries()
    assert len(summaries) >= 6
    assert all("name" in s and "description" in s for s in summaries)

    # Progressive on-demand loading of full instructions
    body = registry.load_body("product-sales")
    assert len(body) > 0
    assert "Sales" in body or "product" in body

    # Skill toggle
    assert registry.set_enabled("product-sales", False) is True
    summaries_after = registry.get_summaries()
    assert not any(s["name"] == "product-sales" for s in summaries_after)
    registry.set_enabled("product-sales", True)


# ---------------------------------------------------------------------------
# 2. RAG Cross-Scope Isolation Tests (P0 Privacy)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rag_cross_scope_isolation(session):
    fake_vector_store = FakeVectorStore()
    fake_embed = FakeEmbeddingProvider()
    ingest = KnowledgeIngestionService(fake_embed, fake_vector_store)
    retriever = KnowledgeRetriever(fake_embed, fake_vector_store)

    # 1. Global doc
    global_source = KnowledgeSource(title="Global FAQs", source_type="faq")
    session.add(global_source)
    await session.flush()
    await ingest.ingest_document(
        session,
        source_id=global_source.id,
        title="General Store Policy",
        content="We are open 24/7 for all customers.",
        scope_type="global",
    )

    # 2. Group A doc
    group_a_source = KnowledgeSource(title="VIP Group", source_type="doc")
    session.add(group_a_source)
    await session.flush()
    await ingest.ingest_document(
        session,
        source_id=group_a_source.id,
        title="VIP Group Rules",
        content="VIP members get 30% discount in group_A only.",
        scope_type="group",
        scope_id="group_A",
    )

    # 3. User 1 private doc
    user_1_source = KnowledgeSource(title="User 1 Note", source_type="doc")
    session.add(user_1_source)
    await session.flush()
    await ingest.ingest_document(
        session,
        source_id=user_1_source.id,
        title="User 1 Medical Note",
        content="User 1 is strictly allergic to peanuts.",
        scope_type="user",
        scope_id="user_1",
    )

    # Query as User 2 in Group B: MUST NOT see Group A or User 1 docs
    res_b = await retriever.retrieve(
        query="open 24/7 discount rules peanuts policy",
        is_group=True,
        group_id="group_B",
        user_id="user_2",
        min_score=0.0,
    )
    res_b_texts = " ".join([c.content for c in res_b])
    assert "30% discount" not in res_b_texts, "Group A private data leaked to Group B!"
    assert "allergic to peanuts" not in res_b_texts, "User 1 private data leaked to Group B!"
    assert "open 24/7" in res_b_texts, "Global docs should be accessible to all groups"

    # Query as User 1 in Group A: CAN see Group A rules, but MUST NEVER see ANY user private scope!
    res_a = await retriever.retrieve(
        query="peanuts discount open",
        is_group=True,
        group_id="group_A",
        user_id="user_1",
        min_score=0.0,
    )
    res_a_texts = " ".join([c.content for c in res_a])
    assert "30% discount" in res_a_texts, "Group A members should see Group A documents"
    assert "open 24/7" in res_a_texts, "Group A members should see Global documents"
    assert "allergic to peanuts" not in res_a_texts, (
        "P0 VIOLATION: User 1 private medical note leaked into Group A context!"
    )

    # Query as User 1 in private DM: CAN see own user note and global, CANNOT see group rules
    res_dm1 = await retriever.retrieve(
        query="peanuts discount open",
        is_group=False,
        user_id="user_1",
        min_score=0.0,
    )
    res_dm1_texts = " ".join([c.content for c in res_dm1])
    assert "allergic to peanuts" in res_dm1_texts, "User 1 in DM should see their own notes"
    assert "open 24/7" in res_dm1_texts, "User 1 in DM should see global documents"
    assert "30% discount" not in res_dm1_texts, "Group A internal rules must not leak into DM"

    # Query as User 2 in private DM: CANNOT see User 1 note
    res_dm2 = await retriever.retrieve(
        query="peanuts open",
        is_group=False,
        user_id="user_2",
        min_score=0.0,
    )
    res_dm2_texts = " ".join([c.content for c in res_dm2])
    assert "allergic to peanuts" not in res_dm2_texts, "User 1 note leaked to User 2 in DM"


# ---------------------------------------------------------------------------
# 3. Scoped Memory Extraction, PII Redaction & Deletion Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scoped_memory_and_pii_redaction(session):
    text_with_pii = (
        "My card is 4111222233334444 and password: secretpassword123. I prefer dark roast coffee."
    )
    cleaned, found_sensitive = redact_sensitive_pii(text_with_pii)
    assert "4111222233334444" not in cleaned
    assert "secretpassword123" not in cleaned
    assert "dark roast coffee" in cleaned
    assert found_sensitive is True

    # Memory search & add
    memory_provider = NativeMemoryProvider()
    mem_item = await memory_provider.add(
        session,
        scope_type="user",
        scope_id="user_100",
        content="Customer prefers dark roast coffee",
        memory_type="preference",
    )
    assert mem_item.id is not None

    # Search for user_100
    results = await memory_provider.search(
        session, scope_type="user", scope_id="user_100", query="coffee"
    )
    assert len(results) >= 1
    assert "dark roast" in results[0].content

    # Scope isolation: user_200 must find zero
    results_other = await memory_provider.search(
        session, scope_type="user", scope_id="user_200", query="coffee"
    )
    assert len(results_other) == 0

    # Delete memory
    deleted = await memory_provider.delete(session, mem_item.id)
    assert deleted is True
    # Deleting already-deleted or non-existent memory ID must return False
    assert await memory_provider.delete(session, mem_item.id) is False
    assert await memory_provider.delete(session, 999999) is False

    remaining = await memory_provider.search(session, scope_type="user", scope_id="user_100")
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_group_prompt_contains_no_private_user_memory(session):
    """P0 Invariant: User private memory MUST NEVER be loaded in group conversations."""
    # 1. Setup user with private memory
    user = User(signal_id="+420777000999", display_name="Alice")
    session.add(user)
    await session.flush()

    mem_provider = NativeMemoryProvider()
    await mem_provider.add(
        session,
        scope_type="user",
        scope_id=str(user.id),
        content="Secret home address: 42 Secret St, Prague",
        memory_type="fact",
    )

    llm = FakeLLMProvider()
    runtime = AgentRuntime(llm_provider=llm, memory_provider=mem_provider)

    # 2. Inbound interaction in Group context
    ctx_group = AgentContext(
        conversation_id=8801,
        message_id=7701,
        sender_id=user.signal_id,
        user_id=user.id,
        group_id="secret_group_alpha",
        is_group=True,
        text="What is my address and what do you know about me?",
        mode="auto",
    )
    resp = await runtime.run(session=session, context=ctx_group)

    # Assert memories_used does not contain the secret address
    memories_used = resp.memories_used or []
    assert len(memories_used) == 0, "Group context MUST NOT load private user memories"
    for call in llm.invocations:
        prompt_text = " ".join([m["content"] for m in call.get("messages", [])])
        assert "42 Secret St" not in prompt_text, (
            "P0 VIOLATION: Private user memory injected into group prompt!"
        )


@pytest.mark.asyncio
async def test_same_user_phone_uuid_share_memory(session):
    """Canonical User identity: phone number and Signal UUID must resolve to same memory namespace."""
    user = User(
        signal_id="+420777222333",
        signal_uuid="b1111111-2222-3333-4444-555555555555",
        display_name="Bob",
    )
    session.add(user)
    await session.flush()

    mem_provider = NativeMemoryProvider()
    runtime = AgentRuntime(memory_provider=mem_provider)

    # 1. Add preference via phone number in DM
    ctx_phone = AgentContext(
        conversation_id=8802,
        message_id=7702,
        sender_id="+420777222333",
        text="Please remember I prefer oat milk in my latte.",
        is_group=False,
        mode="auto",
    )
    await runtime.run(session=session, context=ctx_phone)

    # 2. Query as same user using Signal UUID in DM
    ctx_uuid = AgentContext(
        conversation_id=8803,
        message_id=7703,
        sender_id="b1111111-2222-3333-4444-555555555555",
        text="What milk do I like?",
        is_group=False,
        mode="auto",
    )
    resp = await runtime.run(session=session, context=ctx_uuid)
    mems = resp.memories_used or []
    assert len(mems) >= 1
    assert any("oat milk" in m["content"] for m in mems)


# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tool_permissions():
    registry = ToolRegistry()

    # 1. Safe read tool
    registry.register(
        name="catalog_search",
        description="Search product catalog",
        func=lambda query: [{"id": 1, "name": "Espresso"}],
        permission=ToolPermission(
            name="catalog_search",
            description="Read catalog",
            read_only=True,
            requires_human_approval=False,
        ),
    )

    # 2. Sensitive write tool
    registry.register(
        name="create_order",
        description="Create an order",
        func=lambda item_id: {"order_id": 999},
        permission=ToolPermission(
            name="create_order",
            description="Write order",
            read_only=False,
            writes_data=True,
            requires_human_approval=True,
        ),
    )

    # Execution without approval: safe read succeeds
    res_read = await registry.execute("catalog_search", {"query": "beans"})
    assert res_read["status"] == "success"
    assert len(res_read["result"]) == 1

    # Execution without approval: sensitive write is blocked
    res_write_blocked = await registry.execute("create_order", {"item_id": 1}, user_approved=False)
    assert res_write_blocked["status"] == "requires_approval"

    # Execution with approval: sensitive write succeeds
    res_write_allowed = await registry.execute("create_order", {"item_id": 1}, user_approved=True)
    assert res_write_allowed["status"] == "success"
    assert res_write_allowed["result"]["order_id"] == 999

    # Unregistered tool
    res_not_found = await registry.execute("unknown_tool", {})
    assert res_not_found["status"] == "error"


# ---------------------------------------------------------------------------
# 5. Agent Runtime Execution & Modes
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_agent_runtime_auto_and_copilot_modes(session):
    llm = FakeLLMProvider()
    runtime = AgentRuntime(llm_provider=llm)

    # 1. Test Auto mode -> executes direct reply
    ctx_auto = AgentContext(
        conversation_id=1,
        message_id=101,
        sender_id="+420777000111",
        text="What products do you offer?",
        mode="auto",
    )
    resp_auto = await runtime.run(session=session, context=ctx_auto)
    assert resp_auto.decision in [AgentDecision.reply.value, AgentDecision.ask_clarifying.value]
    assert len(resp_auto.answer) > 0
    assert resp_auto.ai_run_id is not None

    # Verify AIRun record in DB
    ai_run = await session.get(AIRun, resp_auto.ai_run_id)
    assert ai_run is not None
    assert ai_run.conversation_id == 1

    # 2. Test Copilot mode -> creates pending AISuggestion
    ctx_copilot = AgentContext(
        conversation_id=2,
        message_id=102,
        sender_id="+420777000222",
        text="Where is my order?",
        mode="copilot",
    )
    resp_copilot = await runtime.run(session=session, context=ctx_copilot)
    assert resp_copilot.decision == AgentDecision.draft_for_human.value
    assert resp_copilot.ai_suggestion_id is not None

    suggestion = await session.get(AISuggestion, resp_copilot.ai_suggestion_id)
    assert suggestion is not None
    assert suggestion.status == "pending"
    assert len(suggestion.suggested_text) > 0


# ---------------------------------------------------------------------------
# 6. Copilot Suggestion API Workflow (Accept, Edit, Reject)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_copilot_suggestion_api_workflow(session, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user & conversation
        user = User(signal_id="+420777333444", display_name="Bob")
        session.add(user)
        await session.flush()

        conv = Conversation(
            user_id=user.id,
            dm_user_id=user.id,
            signal_id="+420777333444",
            type="dm",
            mode=ConversationMode.copilot.value,
            is_active=True,
        )
        session.add(conv)
        await session.flush()

        # 1. Accept Suggestion
        sug_1 = AISuggestion(
            conversation_id=conv.id,
            suggested_text="Hello Bob! How can I help you today?",
            status="pending",
        )
        session.add(sug_1)
        await session.commit()

        from datetime import datetime

        now = datetime.now(UTC)
        with patch(
            "app.api.conversations.outbound_service.send_message",
            new_callable=AsyncMock,
        ) as mock_send:
            mock_send.return_value = Message(
                id=501,
                conversation_id=conv.id,
                role="assistant",
                actor=MessageActor.admin.value,
                content=sug_1.suggested_text,
                direction=MessageDirection.outbound.value,
                origin=MessageOrigin.human_ai_assisted.value,
                timestamp=now,
            )

            resp = await client.post(
                f"/api/conversations/{conv.id}/suggestion/accept",
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["content"] == sug_1.suggested_text
            assert data["origin"] == MessageOrigin.human_ai_assisted.value
            sug_1_db = await session.get(AISuggestion, sug_1.id, populate_existing=True)
            assert sug_1_db.status == "accepted"

        # 2. Edit Suggestion
        sug_2 = AISuggestion(
            conversation_id=conv.id,
            suggested_text="We have Colombian beans in stock.",
            status="pending",
        )
        session.add(sug_2)
        await session.commit()

        with patch(
            "app.api.conversations.outbound_service.send_message",
            new_callable=AsyncMock,
        ) as mock_send:
            mock_send.return_value = Message(
                id=502,
                conversation_id=conv.id,
                role="assistant",
                actor=MessageActor.admin.value,
                content="We have Colombian and Ethiopian beans in stock.",
                direction=MessageDirection.outbound.value,
                origin=MessageOrigin.human_ai_assisted.value,
                timestamp=now,
            )

            resp = await client.post(
                f"/api/conversations/{conv.id}/suggestion/edit",
                json={
                    "suggestion_id": sug_2.id,
                    "edited_text": "We have Colombian and Ethiopian beans in stock.",
                },
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["content"] == "We have Colombian and Ethiopian beans in stock."
            assert data["origin"] == MessageOrigin.human_ai_assisted.value

            sug_2_db = await session.get(AISuggestion, sug_2.id, populate_existing=True)
            assert sug_2_db.status == "edited"
            assert sug_2_db.edit_distance > 0
            assert 0.0 < sug_2_db.edit_ratio <= 1.0

        # 3. Reject Suggestion
        sug_3 = AISuggestion(
            conversation_id=conv.id,
            suggested_text="Random irrelevant text",
            status="pending",
        )
        session.add(sug_3)
        await session.commit()

        resp = await client.post(
            f"/api/conversations/{conv.id}/suggestion/reject",
            json={"suggestion_id": sug_3.id, "reason": "hallucination"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["status"] == "rejected"
        assert data["suggestion_id"] == sug_3.id


# ---------------------------------------------------------------------------
# 7. Learning Loop: Candidate Creation, FAQ Promotion & JSONL Export
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_learning_loop_curation_and_export(session):
    cand_service = LearningCandidateService()
    exporter = TrainingDatasetExporter()

    # 1. Create a candidate from human answer
    cand = await cand_service.create_candidate(
        session=session,
        conversation_id=10,
        customer_question="What is your exchange policy for roasted coffee?",
        human_answer="Unopened beans can be exchanged within 14 days of delivery.",
        category="policy",
    )
    assert cand is not None
    assert cand.status == "pending"

    # 2. Promote to Knowledge FAQ
    fake_vector_store = FakeVectorStore()
    fake_embed = FakeEmbeddingProvider()
    ingest = KnowledgeIngestionService(fake_embed, fake_vector_store)

    promoted_ok = await cand_service.promote_to_knowledge(
        session=session,
        candidate_id=cand.id,
        ingestion_service=ingest,
        confirm_global_privacy=True,
    )
    assert promoted_ok is True
    assert cand.status == "promoted"

    # 3. Promote another to fine-tuning dataset
    cand2 = await cand_service.create_candidate(
        session=session,
        conversation_id=11,
        customer_question="Do you ship to Germany?",
        human_answer="Yes, EU shipping takes 2-4 business days.",
        category="shipping",
    )
    assert cand2 is not None
    training_example = await cand_service.add_to_training(
        session=session,
        candidate_id=cand2.id,
    )
    assert training_example is not None
    assert cand2.status == "approved"

    # 4. Export JSONL
    jsonl_output = await exporter.export_jsonl(session)
    assert isinstance(jsonl_output, str)
    lines = [json.loads(line) for line in jsonl_output.strip().split("\n") if line]
    assert len(lines) >= 1
    assert any("EU shipping" in line["messages"][-1]["content"] for line in lines)


# ---------------------------------------------------------------------------
# 8. Golden Dataset Evaluation Runner
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_evaluation_runner_golden_dataset(session):
    runner = EvaluationRunner()
    llm = FakeLLMProvider()
    runtime = AgentRuntime(llm_provider=llm)

    summary = await runner.run_suite(session=session, runtime=runtime)
    assert summary["total_cases"] > 0
    assert "pass_rate" in summary
    assert "average_latency_ms" in summary
    assert len(summary["results"]) == summary["total_cases"]


# ---------------------------------------------------------------------------
# 9. Inbound Pipeline Idempotency & Provenance Tracking
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_message_pipeline_idempotency_and_provenance(session):
    # Setup conversation and inbound message
    user = User(signal_id="+420777999888", display_name="Carol")
    session.add(user)
    await session.flush()

    conv = Conversation(
        user_id=user.id,
        dm_user_id=user.id,
        signal_id="+420777999888",
        type="dm",
        mode=ConversationMode.auto.value,
        is_active=True,
    )
    session.add(conv)
    await session.flush()

    msg = Message(
        conversation_id=conv.id,
        sender_id=user.signal_id,
        role="user",
        content="Hello, do you roast coffee locally?",
        direction=MessageDirection.inbound.value,
        origin=MessageOrigin.customer.value,
    )
    session.add(msg)
    await session.flush()

    llm = FakeLLMProvider()
    runtime = AgentRuntime(llm_provider=llm)

    ctx = AgentContext(
        conversation_id=conv.id,
        message_id=msg.id,
        sender_id=user.signal_id,
        text=msg.content,
        mode="auto",
    )

    # First run
    resp1 = await runtime.run(session=session, context=ctx)
    assert resp1.ai_run_id is not None

    # Idempotent re-run on same message_id: must reuse existing AIRun and suppress duplicate reply
    resp2 = await runtime.run(session=session, context=ctx)
    assert resp2.ai_run_id == resp1.ai_run_id
    assert resp2.decision == AgentDecision.no_reply.value
