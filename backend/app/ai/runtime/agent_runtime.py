"""
Agent Runtime: Unified AI workflow execution engine.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
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
from app.models.user import User

logger = logging.getLogger("ai.runtime")


class AgentRuntime:
    """Core runtime managing context, graph orchestration, idempotency, and traces."""

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        retriever: KnowledgeRetriever | None = None,
        memory_provider: NativeMemoryProvider | None = None,
        vector_store: Any | None = None,
        embedding_provider: Any | None = None,
        is_test: bool | None = None,
        rag_enabled: bool = True,
    ) -> None:
        self.rag_enabled = rag_enabled
        if is_test is None:
            if os.environ.get("ENVIRONMENT", "").lower() in ("production", "prod"):
                is_test = False
            else:
                is_test = (
                    os.getenv("TESTING", "").lower() in ("1", "true", "yes")
                    or os.getenv("ENVIRONMENT", "").lower() in ("test", "testing")
                    or bool(os.getenv("PYTEST_CURRENT_TEST"))
                    or "pytest" in sys.modules
                )
        if not is_test:
            if isinstance(llm_provider, FakeLLMProvider) or llm_provider is None:
                raise RuntimeError(
                    "FakeLLMProvider or empty provider is prohibited in non-test environment. Configure real AI provider."
                )
            if rag_enabled and (
                isinstance(vector_store, FakeVectorStore)
                or isinstance(getattr(retriever, "vector_store", None), FakeVectorStore)
            ):
                raise RuntimeError(
                    "FakeVectorStore is prohibited in non-test environment. Configure real vector store (e.g. Qdrant) or disable RAG."
                )
            if rag_enabled and (
                isinstance(embedding_provider, FakeEmbeddingProvider)
                or isinstance(getattr(retriever, "embedding_provider", None), FakeEmbeddingProvider)
            ):
                raise RuntimeError(
                    "FakeEmbeddingProvider is prohibited in non-test environment. Configure real embedding provider."
                )

        self.llm = llm_provider or (FakeLLMProvider() if is_test else None)
        self.llm_provider = self.llm
        if not rag_enabled:
            self.vector_store = None
            self.embedding_provider = None
            self.retriever = None
        else:
            self.vector_store = vector_store or (
                retriever.vector_store if retriever else (FakeVectorStore() if is_test else None)
            )
            self.embedding_provider = embedding_provider or (
                retriever.embedding_provider
                if retriever
                else (FakeEmbeddingProvider() if is_test else None)
            )
            self.retriever = retriever or (
                KnowledgeRetriever(self.embedding_provider, self.vector_store)
                if (self.embedding_provider and self.vector_store)
                else None
            )
        self.memory = memory_provider or NativeMemoryProvider()
        self.graph = build_agent_graph(self.llm, self.retriever)

    async def run(
        self,
        session: AsyncSession,
        context: AgentContext,
    ) -> AgentResponse:
        """Execute the agent workflow for an inbound interaction."""
        from app.ai.tools.context import current_tool_session
        from app.ai.tools.registry import tool_registry
        from app.models.ai import ToolInvocation

        token = current_tool_session.set(session)
        try:
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

            # Resolve canonical user ID for durable memory isolation
            canonical_user_id: str | None = (
                str(context.user_id) if context.user_id is not None else None
            )
            if not canonical_user_id and context.sender_id:
                stmt_user = select(User).where(
                    (User.signal_id == context.sender_id) | (User.signal_uuid == context.sender_id)
                )
                u_res = await session.execute(stmt_user)
                u = u_res.scalar_one_or_none()
                if u:
                    canonical_user_id = str(u.id)
                else:
                    canonical_user_id = context.sender_id

            # 2. Extract durable memories from user turn (background task style)
            # P0 Invariant: Never auto-extract private personal memories from public group chatter
            if not context.is_group and context.text and canonical_user_id:
                candidates = memory_extractor.extract_candidates(context.text)
                for c in candidates:
                    try:
                        await self.memory.add(
                            session=session,
                            scope_type="user",
                            scope_id=canonical_user_id,
                            content=c.content,
                            memory_type=c.memory_type,
                            importance=c.importance,
                            source_conversation_id=context.conversation_id,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to auto-save memory candidate: {e}")

            # 3. Retrieve relevant memory
            # P0 Invariant: Group chats MUST NEVER load private user memories.
            # Groups only load group-scoped memories. DMs load user-scoped memories.
            turn_memories: list[dict[str, Any]] = []
            if context.is_group:
                if context.group_id:
                    group_mems = await self.memory.search(
                        session=session,
                        scope_type="group",
                        scope_id=str(context.group_id),
                        query=context.text or "",
                        limit=3,
                    )
                    turn_memories.extend(group_mems)
            else:
                if canonical_user_id:
                    user_mems = await self.memory.search(
                        session=session,
                        scope_type="user",
                        scope_id=canonical_user_id,
                        query=context.text or "",
                        limit=3,
                    )
                    turn_memories.extend(user_mems)

            # Global organizational knowledge memory (available in both group & DM)
            try:
                global_mems = await self.memory.search(
                    session=session,
                    scope_type="global",
                    scope_id="system",
                    query=context.text or "",
                    limit=2,
                )
                turn_memories.extend(global_mems)
            except Exception:
                pass

            # 4. Load Conversation History
            from app.ai.runtime.context_loader import context_loader

            history_messages = await context_loader.load_context_messages(
                session=session,
                conversation_id=context.conversation_id,
                current_message_id=context.message_id,
                is_group=context.is_group,
            )

            # 5. Resolve active prompt version
            from app.ai.prompts.manager import prompt_manager

            prompt_template, prompt_version = await prompt_manager.get_active_prompt(session)

            # 6. Execute LangGraph workflow
            initial_state: AgentState = {
                "conversation_id": context.conversation_id,
                "message_id": context.message_id,
                "sender_id": context.sender_id,
                "user_id": context.user_id,
                "group_id": context.group_id,
                "is_group": context.is_group,
                "text": context.text,
                "mode": context.mode,
                "memories": turn_memories,
                "history": history_messages,
                "prompt_template": prompt_template,
                "prompt_version": prompt_version,
            }

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
                    "confidence": None,
                    "tokens": 0,
                    "citations": [],
                }
            except Exception as e:
                logger.error(f"Agent graph execution failed: {e}", exc_info=True)
                error_msg = str(e)
                output_state = {
                    "draft": "Thank you for reaching out. An operator will be with you in a moment.",
                    "decision": AgentDecision.handoff.value,
                    "confidence": None,
                    "tokens": 0,
                    "citations": [],
                }

            latency_ms = int((time.perf_counter() - start_time) * 1000)
            answer = output_state.get("draft") or ""
            decision = output_state.get("decision", AgentDecision.reply.value)
            citations = output_state.get("citations") or []
            skills_used = output_state.get("selected_skills") or []
            retrieved_chunks = output_state.get("retrieved_chunks") or []
            raw_tool_calls = output_state.get("tool_calls") or []
            raw_tool_results = output_state.get("tool_results") or []

            # Enrich tool calls with actual execution output & status for downstream evals & traces
            enriched_tool_calls = []
            for tc in raw_tool_calls:
                t_name = tc.get("name")
                matched_res = next((r for r in raw_tool_results if r.get("tool") == t_name), {})
                t_output = matched_res.get("output", {})
                t_status = (
                    "requires_approval"
                    if isinstance(t_output, dict) and t_output.get("status") == "requires_approval"
                    else (
                        "error"
                        if isinstance(t_output, dict) and t_output.get("status") == "error"
                        else "success"
                    )
                )
                enriched_tool_calls.append(
                    {
                        **tc,
                        "output": t_output,
                        "status": t_status,
                    }
                )

            model_name = getattr(self.llm_provider, "default_model", "default")
            provider_name = getattr(self.llm_provider, "provider_name", "unknown")

            # 7. Record AIRun trace
            run_record = await local_tracer.record_run(
                session=session,
                trace_id=trace_id,
                conversation_id=context.conversation_id,
                input_message_id=context.message_id,
                model=model_name,
                provider=provider_name,
                prompt_version=prompt_version,
                skills_used=skills_used,
                retrieved_chunks=retrieved_chunks,
                memories_used=turn_memories,
                tool_calls=enriched_tool_calls,
                decision=decision,
                confidence=output_state.get("confidence"),
                latency_ms=latency_ms,
                tokens=output_state.get("tokens", 0),
                errors=error_msg,
            )
            run_id = run_record.id

            # 8. Persist ToolInvocations for auditability
            for tc in enriched_tool_calls:
                t_name = tc.get("name") or "unknown"
                registered_tool = tool_registry.get_tool(t_name)
                is_mcp = getattr(registered_tool, "is_mcp", False) if registered_tool else False
                inv = ToolInvocation(
                    ai_run_id=run_id,
                    tool_name=t_name,
                    tool_type="mcp" if is_mcp else "builtin",
                    arguments_json=json.dumps(tc.get("arguments", {})),
                    result_json=json.dumps(tc.get("output", {})),
                    status=tc.get("status", "success"),
                    requires_approval=(tc.get("status") == "requires_approval"),
                    is_approved=False if tc.get("status") == "requires_approval" else True,
                )
                session.add(inv)
            if enriched_tool_calls:
                await session.commit()

            # 9. Copilot Draft Handling
            sug_id: int | None = None
            if context.mode == "copilot" or decision == AgentDecision.draft_for_human.value:
                sug = AISuggestion(
                    conversation_id=context.conversation_id,
                    inbound_message_id=context.message_id,
                    ai_run_id=run_id,
                    suggested_text=answer,
                    status=AISuggestionStatus.pending.value,
                    metadata_json=json.dumps(
                        {
                            "citations": citations,
                            "skills_used": skills_used,
                            "memories_used": turn_memories,
                            "tools_called": enriched_tool_calls,
                        }
                    ),
                )
                session.add(sug)
                await session.commit()
                await session.refresh(sug)
                sug_id = sug.id
                logger.info(
                    f"Created Copilot AISuggestion #{sug_id} for conversation #{context.conversation_id}"
                )
            elif context.mode == "auto" and decision == AgentDecision.reply.value:
                # In auto mode, initial status is auto_pending until confirmed sent by MessageHandler
                sug = AISuggestion(
                    conversation_id=context.conversation_id,
                    inbound_message_id=context.message_id,
                    ai_run_id=run_id,
                    suggested_text=answer,
                    status=AISuggestionStatus.auto_pending.value,
                    metadata_json=json.dumps(
                        {
                            "citations": citations,
                            "skills_used": skills_used,
                            "tools_called": enriched_tool_calls,
                        }
                    ),
                )
                session.add(sug)
                await session.commit()
                await session.refresh(sug)
                sug_id = sug.id

            return AgentResponse(
                answer=answer,
                decision=decision,
                confidence=output_state.get("confidence"),
                model=model_name,
                provider=provider_name,
                prompt_version=prompt_version,
                skills_used=skills_used,
                memories_used=turn_memories,
                knowledge_chunks=retrieved_chunks,
                tools_called=enriched_tool_calls,
                citations=citations,
                latency_ms=latency_ms,
                tokens=output_state.get("tokens", 0),
                trace_id=trace_id,
                ai_run_id=run_id,
                ai_suggestion_id=sug_id,
                error=error_msg,
            )
        finally:
            current_tool_session.reset(token)
