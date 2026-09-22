"""
Agent Runtime: Unified AI workflow execution engine.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory.extraction import memory_extractor
from app.ai.memory.providers import NativeMemoryProvider
from app.ai.observability.tracing import local_tracer
from app.ai.orchestration.graph import build_agent_graph
from app.ai.orchestration.state import AgentState
from app.ai.providers.embeddings import FakeEmbeddingProvider
from app.ai.providers.llm import FakeLLMProvider, LLMProvider
from app.ai.rag.retrieval import KnowledgeRetriever
from app.ai.rag.vector_store import FakeVectorStore
from app.ai.runtime.context import AgentContext
from app.ai.runtime.decisions import AgentDecision, AgentResponse
from app.models.ai import AIRun, AISuggestion, AISuggestionStatus

logger = logging.getLogger("ai.runtime")


class AgentRuntime:
    """Core runtime managing context, graph orchestration, idempotency, and traces."""

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        retriever: KnowledgeRetriever | None = None,
        memory_provider: NativeMemoryProvider | None = None,
    ) -> None:
        self.llm = llm_provider or FakeLLMProvider()
        self.vector_store = FakeVectorStore()
        self.embedding_provider = FakeEmbeddingProvider()
        self.retriever = retriever or KnowledgeRetriever(self.embedding_provider, self.vector_store)
        self.memory = memory_provider or NativeMemoryProvider()
        self.graph = build_agent_graph(self.llm, self.retriever)

    async def run(
        self,
        session: AsyncSession,
        context: AgentContext,
    ) -> AgentResponse:
        """Execute the agent workflow for an inbound interaction."""
        start_time = time.perf_counter()
        trace_id = f"tr_{uuid.uuid4().hex[:12]}"

        # 1. Idempotency check: do not run duplicate AI for same inbound message
        if context.message_id:
            stmt = select(AIRun).where(AIRun.input_message_id == context.message_id)
            res = await session.execute(stmt)
            existing_run = res.scalar_one_or_none()
            if existing_run:
                logger.info(
                    f"Duplicate AI invocation suppressed for inbound message #{context.message_id}"
                )
                return AgentResponse(
                    answer="",
                    decision=AgentDecision.no_reply.value,
                    trace_id=existing_run.trace_id,
                    ai_run_id=existing_run.id,
                )

        # 2. Extract durable memories from user turn (background task style)
        if context.text and context.sender_id:
            candidates = memory_extractor.extract_candidates(context.text)
            for c in candidates:
                try:
                    await self.memory.add(
                        session=session,
                        scope_type="user",
                        scope_id=context.sender_id,
                        content=c.content,
                        memory_type=c.memory_type,
                        importance=c.importance,
                        source_conversation_id=context.conversation_id,
                    )
                except Exception as e:
                    logger.warning(f"Failed to auto-save memory candidate: {e}")

        # 3. Retrieve relevant customer memory
        user_memories: list[dict[str, Any]] = []
        if context.sender_id:
            mem_items = await self.memory.search(
                session=session,
                scope_type="user",
                scope_id=context.sender_id,
                query=context.text,
                limit=3,
            )
            user_memories = [
                {"id": m.id, "content": m.content, "type": m.memory_type} for m in mem_items
            ]

        # 4. Prepare initial state
        initial_state: AgentState = {
            "conversation_id": context.conversation_id,
            "message_id": context.message_id,
            "sender_id": context.sender_id,
            "user_id": context.user_id,
            "group_id": context.group_id,
            "is_group": context.is_group,
            "text": context.text,
            "language": context.language,
            "mode": context.mode,
            "memories": user_memories,
            "retrieved_chunks": [],
            "selected_skills": [],
            "skill_instructions": [],
            "tool_calls": [],
            "tool_results": [],
            "decision": AgentDecision.reply.value,
            "draft": None,
            "confidence": 1.0,
            "citations": [],
            "tokens": 0,
            "error": None,
        }

        # 5. Execute Graph with Timeout Protection
        output_state: dict[str, Any] = {}
        error_msg: str | None = None
        try:
            output_state = await asyncio.wait_for(
                self.graph.ainvoke(initial_state),
                timeout=15.0,
            )
        except TimeoutError:
            logger.error(f"Agent graph execution timed out for conv #{context.conversation_id}")
            error_msg = "Agent execution timed out (15s limit reached)"
            output_state = {
                "draft": "I am looking into this for you. A customer service representative will assist you shortly.",
                "decision": AgentDecision.handoff.value,
                "confidence": 0.5,
                "tokens": 0,
                "citations": [],
            }
        except Exception as e:
            logger.error(f"Agent graph execution failed: {e}", exc_info=True)
            error_msg = str(e)
            output_state = {
                "draft": "Thank you for reaching out. An operator will be with you in a moment.",
                "decision": AgentDecision.handoff.value,
                "confidence": 0.5,
                "tokens": 0,
                "citations": [],
            }

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        answer = output_state.get("draft") or ""
        decision = output_state.get("decision", AgentDecision.reply.value)
        citations = output_state.get("citations") or []
        skills_used = output_state.get("selected_skills") or []
        retrieved_chunks = output_state.get("retrieved_chunks") or []
        tool_calls = output_state.get("tool_calls") or []

        # 6. Record AIRun trace
        run_record = await local_tracer.record_run(
            session=session,
            trace_id=trace_id,
            conversation_id=context.conversation_id,
            input_message_id=context.message_id,
            model="default",
            provider="openai",
            prompt_version="v1.0",
            skills_used=skills_used,
            retrieved_chunks=retrieved_chunks,
            memories_used=user_memories,
            tool_calls=tool_calls,
            decision=decision,
            confidence=output_state.get("confidence", 1.0),
            latency_ms=latency_ms,
            tokens=output_state.get("tokens", 0),
            errors=error_msg,
        )

        # 7. Copilot Draft Handling
        sug: AISuggestion | None = None
        if context.mode == "copilot" or decision == AgentDecision.draft_for_human.value:
            sug = AISuggestion(
                conversation_id=context.conversation_id,
                inbound_message_id=context.message_id,
                ai_run_id=run_record.id,
                suggested_text=answer,
                status=AISuggestionStatus.pending.value,
                metadata_json=json.dumps(
                    {
                        "citations": citations,
                        "skills_used": skills_used,
                        "memories_used": user_memories,
                        "tools_called": tool_calls,
                    }
                ),
            )
            session.add(sug)
            await session.commit()
            logger.info(
                f"Created Copilot AISuggestion #{sug.id} for conversation #{context.conversation_id}"
            )
        elif context.mode == "auto" and decision == AgentDecision.reply.value:
            # In auto mode with direct reply, record suggestion as auto_sent
            sug = AISuggestion(
                conversation_id=context.conversation_id,
                inbound_message_id=context.message_id,
                ai_run_id=run_record.id,
                suggested_text=answer,
                status=AISuggestionStatus.auto_sent.value,
                metadata_json=json.dumps(
                    {
                        "citations": citations,
                        "skills_used": skills_used,
                    }
                ),
            )
            session.add(sug)
            await session.commit()

        return AgentResponse(
            answer=answer,
            decision=decision,
            confidence=output_state.get("confidence", 1.0),
            model="default",
            provider="openai",
            prompt_version="v1.0",
            skills_used=skills_used,
            memories_used=user_memories,
            knowledge_chunks=retrieved_chunks,
            tools_called=tool_calls,
            citations=citations,
            latency_ms=latency_ms,
            tokens=output_state.get("tokens", 0),
            trace_id=trace_id,
            ai_run_id=run_record.id,
            ai_suggestion_id=sug.id if sug else None,
            error=error_msg,
        )


agent_runtime = AgentRuntime()
