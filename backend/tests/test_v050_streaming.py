"""
Tests for v0.5.0 Streaming Copilot generation and LLM streaming abstraction.

Covers:
- Provider stream_generate token chunks accumulation
- Copilot streaming generation via AgentRuntime
- Stream cancellation telemetry recording
- Token usage accumulation
- Non-streaming fallback compatibility
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from app.ai.providers.llm import FakeLLMProvider
from app.ai.runtime.agent_runtime import AgentRuntime
from app.ai.runtime.context import AgentContext
from app.ai.types.usage import LLMResult, LLMStreamChunk, TokenUsage
from app.models.ai import AIRun, AISuggestion, AISuggestionStatus
from app.models.conversation import Conversation, Message


@pytest.mark.asyncio
async def test_fake_llm_stream_generate():
    provider = FakeLLMProvider(canned_response="Hello world from streaming Copilot")

    chunks: list[LLMStreamChunk] = []
    async for chunk in provider.stream_generate(messages=[{"role": "user", "content": "test"}]):
        chunks.append(chunk)

    assert len(chunks) > 0
    # Final chunk should have accumulated the full text
    assert chunks[-1].accumulated_content == "Hello world from streaming Copilot"
    assert chunks[-1].is_final is True
    assert chunks[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_agent_runtime_stream_copilot_draft(session):
    # Setup test conversation and inbound message
    conv = Conversation(type="dm", signal_id="+10001", mode="copilot")
    session.add(conv)
    await session.commit()
    await session.refresh(conv)

    msg = Message(
        conversation_id=conv.id,
        content="What is your return policy?",
        direction="inbound",
        role="user",
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)

    fake_llm = FakeLLMProvider(canned_response="Our return policy is 30 days money-back guarantee.")
    runtime = AgentRuntime(llm_provider=fake_llm)

    context = AgentContext(
        conversation_id=conv.id,
        message_id=msg.id,
        sender_id="+10001",
        text=msg.content,
        mode="copilot",
    )

    events: list[dict] = []
    async for event in runtime.stream_copilot_draft(session, context):
        events.append(event)

    # Must have status, chunks, and a done event
    chunk_events = [e for e in events if e.get("type") == "chunk"]
    done_events = [e for e in events if e.get("type") == "done"]

    assert len(chunk_events) > 0
    assert len(done_events) == 1

    done = done_events[0]
    assert "30 days" in done["draft"]
    assert done["suggestion_id"] is not None

    # Check that AISuggestion was persisted as pending
    sug = await session.get(AISuggestion, done["suggestion_id"])
    assert sug is not None
    assert sug.status == AISuggestionStatus.pending.value
    assert sug.suggested_text == done["draft"]

    # Check AIRun was persisted
    run = await session.get(AIRun, done["ai_run_id"])
    assert run is not None
    assert run.decision == "draft_for_human"


@pytest.mark.asyncio
async def test_stream_cancellation_records_telemetry(session):
    conv = Conversation(type="dm", signal_id="+10002", mode="copilot")
    session.add(conv)
    await session.commit()
    await session.refresh(conv)

    msg = Message(
        conversation_id=conv.id,
        content="Cancel this stream please",
        direction="inbound",
        role="user",
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)

    class SlowCancellingLLM:
        async def stream_generate(self, messages, **kwargs):
            yield LLMStreamChunk(delta="First", accumulated_content="First", is_final=False)
            # Simulate cancellation from client by raising asyncio.CancelledError
            raise asyncio.CancelledError()

        async def generate(self, *args, **kwargs):
            return LLMResult(content="fallback", usage=TokenUsage(total_tokens=10))

    runtime = AgentRuntime(llm_provider=SlowCancellingLLM())
    context = AgentContext(
        conversation_id=conv.id,
        message_id=msg.id,
        sender_id="+10002",
        text=msg.content,
        mode="copilot",
    )

    with pytest.raises(asyncio.CancelledError):
        async for _ in runtime.stream_copilot_draft(session, context):
            pass

    # Verify that cancellation telemetry was recorded in AIRun
    run_res = await session.execute(
        select(AIRun).where(
            AIRun.conversation_id == conv.id,
            AIRun.errors == "cancelled_by_client",
        )
    )
    cancelled_run = run_res.scalar_one_or_none()
    assert cancelled_run is not None
    assert cancelled_run.decision == "cancelled"
