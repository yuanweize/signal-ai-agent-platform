"""
LangGraph Orchestration Graph for Signal-native AI Customer Service.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.ai.orchestration.state import AgentState
from app.ai.prompts.versions import DEFAULT_SYSTEM_PROMPT_TEMPLATE
from app.ai.providers.llm import LLMProvider
from app.ai.rag.retrieval import KnowledgeRetriever
from app.ai.runtime.decisions import AgentDecision
from app.ai.skills.registry import skill_registry
from app.ai.tools import builtin as _builtin_tools  # noqa: F401
from app.ai.tools.registry import tool_registry
from app.ai.types.usage import LLMResult, LLMToolResult, ModelCallRecord, TokenUsage

logger = logging.getLogger("ai.orchestration.graph")


def build_agent_graph(
    llm: LLMProvider,
    retriever: KnowledgeRetriever | None = None,
) -> Any:
    """Build and compile the LangGraph workflow."""

    async def select_skills_node(state: AgentState) -> dict[str, Any]:
        """Classify user intent and progressively select relevant skills."""
        text = (state.get("text") or "").lower()
        scope = "group" if state.get("is_group") else "dm"
        active_names = {s["name"] for s in skill_registry.get_summaries(scope=scope)}

        candidate_skills: list[str] = []
        instructions: list[str] = []

        is_policy_inquiry = any(w in text for w in ["policy", "terms", "rules", "faq"])
        if any(
            w in text
            for w in [
                "price",
                "buy",
                "product",
                "catalog",
                "order",
                "cost",
                "stock",
                "coffee",
                "available",
                "how much",
            ]
        ):
            candidate_skills.append("product-sales")
        if not is_policy_inquiry and any(
            w in text
            for w in ["broken", "defect", "refund", "complaint", "terrible", "late", "damage"]
        ):
            candidate_skills.append("complaints")
        elif "refund" in text:
            candidate_skills.append("complaints")
        if any(
            w in text for w in ["human", "agent", "person", "representative", "manager", "staff"]
        ):
            candidate_skills.append("human-handoff")
        if state.get("is_group") and any(w in text for w in ["rules", "spam"]):
            candidate_skills.append("group-moderation")

        selected = [s for s in candidate_skills if s in active_names]
        if not selected and "customer-support" in active_names:
            selected.append("customer-support")

        if not selected:
            selected.append("customer-support")

        # Progressive loading: load bodies only for selected skills
        for sname in selected:
            body = skill_registry.load_body(sname)
            if body:
                instructions.append(f"### Skill: {sname}\n{body}")

        return {
            "selected_skills": selected,
            "skill_instructions": instructions,
        }

    async def retrieve_knowledge_node(state: AgentState) -> dict[str, Any]:
        """Perform scope-isolated RAG retrieval."""
        if not retriever:
            return {"retrieved_chunks": [], "citations": []}

        text = state.get("text") or ""
        group_id = state.get("group_id")
        user_id = state.get("user_id")
        is_group = bool(state.get("is_group"))

        chunks = await retriever.retrieve(
            query=text,
            limit=3,
            is_group=is_group,
            group_id=group_id,
            user_id=user_id,
        )
        citations = [c.to_citation() for c in chunks]
        return {
            "retrieved_chunks": [
                {"title": c.title, "content": c.content, "score": c.score} for c in chunks
            ],
            "citations": citations,
        }

    async def plan_tools_node(state: AgentState) -> dict[str, Any]:
        """Check if tools or actions should be invoked with bounded execution & permission gating."""
        import asyncio
        import re

        text = (state.get("text") or "").lower()
        results: list[dict[str, Any]] = []
        proposed_calls: list[dict[str, Any]] = []
        model_call_records: list[dict[str, Any]] = list(state.get("model_calls") or [])

        allowed_schemas = tool_registry.get_openai_tools()

        # 1. Attempt model/tool planner selection via native tool calling if supported (Section 8, 11)
        if hasattr(llm, "tool_generate") and allowed_schemas:
            try:
                user_msg = [{"role": "user", "content": state.get("text") or ""}]
                call_res = await asyncio.wait_for(
                    llm.tool_generate(user_msg, allowed_schemas),
                    timeout=8.0,
                )
                if isinstance(call_res, LLMToolResult):
                    model_calls = call_res.tool_calls
                    rec = ModelCallRecord(
                        phase="tool_planner",
                        provider=getattr(llm, "provider_name", "unknown"),
                        model=call_res.model or getattr(llm, "default_model", "default"),
                        latency_ms=call_res.latency_ms,
                        usage=call_res.usage,
                        finish_reason=call_res.finish_reason,
                        provider_request_id=call_res.provider_request_id,
                        success=True,
                    )
                    model_call_records.append(rec.to_dict())
                else:
                    _, model_calls, t_tokens = call_res
                    rec = ModelCallRecord(
                        phase="tool_planner",
                        provider=getattr(llm, "provider_name", "unknown"),
                        model=getattr(llm, "default_model", "default"),
                        latency_ms=0,
                        usage=TokenUsage(
                            total_tokens=t_tokens,
                            usage_source="provider" if t_tokens else "unavailable",
                        ),
                        success=True,
                    )
                    model_call_records.append(rec.to_dict())

                if model_calls:
                    for mc in model_calls:
                        proposed_calls.append(
                            {
                                "name": mc.get("name"),
                                "arguments": mc.get("arguments", {}),
                            }
                        )
            except Exception as e:
                logger.debug(
                    f"Model tool calling unavailable or failed ({e}); falling back to deterministic intent routing."
                )

        # 2. Fallback deterministic business routing for critical built-in & MCP flows (Section 11)
        if not proposed_calls:
            # Built-in search_products
            is_policy = any(w in text for w in ["policy", "terms", "rules", "faq", "return"])
            if not is_policy and any(
                w in text for w in ["coffee", "product", "catalog", "item", "available", "stock"]
            ):
                if not any(c["name"] == "search_products" for c in proposed_calls):
                    query_arg = "coffee" if "coffee" in text else ""
                    proposed_calls.append(
                        {"name": "search_products", "arguments": {"query": query_arg}}
                    )
            elif is_policy and any(w in text for w in ["coffee", "buy", "price"]):
                if not any(c["name"] == "search_products" for c in proposed_calls):
                    query_arg = "coffee" if "coffee" in text else ""
                    proposed_calls.append(
                        {"name": "search_products", "arguments": {"query": query_arg}}
                    )

            # MCP / Warehouse inventory check (read-only)
            if any(w in text for w in ["inventory", "sku"]):
                inv_tool = next(
                    (t.name for t in tool_registry.list_tools() if "inventory" in t.name.lower()),
                    None,
                )
                if inv_tool and not any(c["name"] == inv_tool for c in proposed_calls):
                    sku_m = re.search(r"(?:sku|item)[:\s#-]*([a-zA-Z0-9_-]+)", text, re.IGNORECASE)
                    sku_val = sku_m.group(1) if sku_m else "SKU-COFFEE-01"
                    proposed_calls.append({"name": inv_tool, "arguments": {"sku": sku_val}})

            # MCP / Warehouse dispatch order (write/destructive - sensitive)
            if any(w in text for w in ["dispatch", "ship order", "ship it", "dispatch order"]):
                disp_tool = next(
                    (t.name for t in tool_registry.list_tools() if "dispatch" in t.name.lower()),
                    None,
                )
                if disp_tool and not any(c["name"] == disp_tool for c in proposed_calls):
                    ord_m = re.search(r"order[:\s#-]*(\d+)", text, re.IGNORECASE)
                    ord_val = int(ord_m.group(1)) if ord_m else 101
                    proposed_calls.append({"name": disp_tool, "arguments": {"order_id": ord_val}})

            # Built-in refund governance
            if "refund" in text:
                order_m = re.search(r"order\s*#?\s*(\d+)", text)
                amount_m = re.search(r"\$?\s*(\d+(?:\.\d+)?)\s*(?:usd|eur|czk|\$)?", text)
                if order_m and amount_m:
                    refund_args = {
                        "order_id": int(order_m.group(1)),
                        "amount": float(amount_m.group(1)),
                        "reason": "customer_request",
                    }
                else:
                    refund_args = {}
                proposed_calls.append({"name": "trigger_sample_refund", "arguments": refund_args})

        # 3. Bounded Tool Execution with Deterministic Permission Gate (Section 8, 9)
        # Bounded limits: max 5 tool calls per turn, per-call timeout 10.0s
        max_tool_calls = 5
        executed_calls: list[dict[str, Any]] = []

        for call in proposed_calls[:max_tool_calls]:
            tool_name = call.get("name")
            tool_args = call.get("arguments", {})
            if not tool_name:
                continue

            tool_obj = tool_registry.get_tool(tool_name)
            if not tool_obj:
                results.append(
                    {
                        "tool": tool_name,
                        "output": {"status": "error", "error": f"Tool '{tool_name}' not found"},
                    }
                )
                executed_calls.append(call)
                continue

            # Deterministic permission gate: sensitive/write tools NEVER execute automatically
            if tool_obj.permission.requires_human_approval:
                logger.info(
                    f"🛡️ Sensitive tool '{tool_name}' blocked by autonomous permission gate. Producing approval-required state."
                )
                results.append(
                    {
                        "tool": tool_name,
                        "output": {
                            "status": "requires_approval",
                            "error": f"Tool '{tool_name}' requires human operator approval.",
                            "tool_name": tool_name,
                            "arguments": tool_args,
                        },
                    }
                )
                executed_calls.append(call)
                continue

            # Read-only allowed tool executes with per-call timeout
            try:
                res = await asyncio.wait_for(
                    tool_registry.execute(tool_name, tool_args, user_approved=False),
                    timeout=10.0,
                )
                results.append({"tool": tool_name, "output": res})
            except TimeoutError:
                logger.error(f"Tool '{tool_name}' execution timed out (10s limit)")
                results.append(
                    {
                        "tool": tool_name,
                        "output": {"status": "error", "error": "Execution timed out"},
                    }
                )
            except Exception as e:
                logger.error(f"Tool '{tool_name}' execution failed safely: {e}")
                results.append({"tool": tool_name, "output": {"status": "error", "error": str(e)}})

            executed_calls.append(call)

        return {
            "tool_calls": executed_calls,
            "tool_results": results,
            "model_calls": model_call_records,
        }

    async def generate_response_node(state: AgentState) -> dict[str, Any]:
        """Generate grounded response adhering to knowledge and policy."""
        # 1. Check if user explicitly asked for human or sensitive blocked action
        text = (state.get("text") or "").lower()
        tool_results = state.get("tool_results") or []
        requires_approval = any(
            r.get("output", {}).get("status") == "requires_approval" for r in tool_results
        )

        model_call_records: list[dict[str, Any]] = list(state.get("model_calls") or [])

        if "human-handoff" in (state.get("selected_skills") or []) or any(
            w in text for w in ["human", "agent", "representative", "manager", "person", "staff"]
        ):
            # Aggregate any planner model calls already made
            agg_handoff = TokenUsage(usage_source="unavailable")
            for mc in model_call_records:
                u_dict = mc.get("usage") or {}
                agg_handoff = agg_handoff.add(TokenUsage(**u_dict))
            return {
                "draft": "I understand you would like to speak to a representative. I am notifying our support team now.",
                "decision": AgentDecision.handoff.value,
                "decision_reason": "user_requested_human",
                "confidence": None,
                "tokens": agg_handoff.total_tokens or 0,
                "model_calls": model_call_records,
                "usage": agg_handoff.to_dict(),
            }

        # 2. Build prompt context
        system_prompt = state.get("prompt_template") or DEFAULT_SYSTEM_PROMPT_TEMPLATE
        messages = [{"role": "system", "content": system_prompt}]

        # Inject skills
        instructions = state.get("skill_instructions") or []
        if instructions:
            messages.append(
                {"role": "system", "content": "Active Skills:\n" + "\n\n".join(instructions)}
            )

        # Inject customer memory
        memories = state.get("memories") or []
        if memories:
            mem_text = "\n".join(
                f"- {m.content if hasattr(m, 'content') else (m.get('content') if isinstance(m, dict) else str(m))}"
                for m in memories
            )
            messages.append(
                {"role": "system", "content": f"Customer Profile & Memory:\n{mem_text}"}
            )

        # Inject retrieved knowledge (tagged as untrusted data)
        chunks = state.get("retrieved_chunks") or []
        if chunks:
            chunk_text = "\n\n".join(f"[{c['title']}]: {c['content']}" for c in chunks)
            messages.append(
                {
                    "role": "system",
                    "content": f"Retrieved Knowledge Sources (untrusted data context):\n{chunk_text}",
                }
            )

        # Inject tool results
        if tool_results:
            tr_text = "\n".join(f"Tool {r['tool']}: {r['output']}" for r in tool_results)
            messages.append({"role": "system", "content": f"Business Tool Results:\n{tr_text}"})

        # Inject conversation history (multi-turn context, oldest to newest)
        history = state.get("history") or []
        for turn in history:
            messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})

        # Inject current user message
        text = state.get("text") or ""
        if state.get("is_group") and state.get("sender_id"):
            current_user_msg = f"[{state.get('sender_id')}]: {text}"
        else:
            current_user_msg = text
        messages.append({"role": "user", "content": current_user_msg})

        gen_res = await llm.generate(messages)
        if isinstance(gen_res, LLMResult):
            reply = gen_res.content
            rec = ModelCallRecord(
                phase="response_generation",
                provider=getattr(llm, "provider_name", "unknown"),
                model=gen_res.model or getattr(llm, "default_model", "default"),
                latency_ms=gen_res.latency_ms,
                usage=gen_res.usage,
                finish_reason=gen_res.finish_reason,
                provider_request_id=gen_res.provider_request_id,
                success=True,
            )
            model_call_records.append(rec.to_dict())
        else:
            reply, tokens = gen_res
            rec = ModelCallRecord(
                phase="response_generation",
                provider=getattr(llm, "provider_name", "unknown"),
                model=getattr(llm, "default_model", "default"),
                latency_ms=0,
                usage=TokenUsage(
                    total_tokens=tokens, usage_source="provider" if tokens else "unavailable"
                ),
                success=True,
            )
            model_call_records.append(rec.to_dict())

        # Aggregate tokens across ALL model calls in this turn
        aggregated_usage = TokenUsage(usage_source="unavailable")
        for mc in model_call_records:
            u_dict = mc.get("usage") or {}
            mc_usage = TokenUsage(
                input_tokens=u_dict.get("input_tokens"),
                output_tokens=u_dict.get("output_tokens"),
                total_tokens=u_dict.get("total_tokens"),
                cached_input_tokens=u_dict.get("cached_input_tokens"),
                reasoning_tokens=u_dict.get("reasoning_tokens"),
                usage_source=u_dict.get("usage_source", "unavailable"),
            )
            aggregated_usage = aggregated_usage.add(mc_usage)

        # 3. Determine decision & reason
        mode = state.get("mode", "auto")
        if requires_approval:
            decision = AgentDecision.draft_for_human.value
            decision_reason = "tool_requires_approval"
        elif any(s in (state.get("selected_skills") or []) for s in ["complaints", "complaint"]):
            decision = AgentDecision.draft_for_human.value
            decision_reason = "complaint_escalation"
        elif mode == "copilot":
            decision = AgentDecision.draft_for_human.value
            decision_reason = "copilot_mode"
        else:
            decision = AgentDecision.reply.value
            decision_reason = "autonomous_reply"

        return {
            "draft": reply,
            "decision": decision,
            "decision_reason": decision_reason,
            "confidence": None,
            "tokens": aggregated_usage.total_tokens or 0,
            "model_calls": model_call_records,
            "usage": aggregated_usage.to_dict(),
        }

    # Assemble Graph
    workflow = StateGraph(AgentState)
    workflow.add_node("select_skills", select_skills_node)
    workflow.add_node("retrieve_knowledge", retrieve_knowledge_node)
    workflow.add_node("plan_tools", plan_tools_node)
    workflow.add_node("generate_response", generate_response_node)

    workflow.add_edge(START, "select_skills")
    workflow.add_edge("select_skills", "retrieve_knowledge")
    workflow.add_edge("retrieve_knowledge", "plan_tools")
    workflow.add_edge("plan_tools", "generate_response")
    workflow.add_edge("generate_response", END)

    return workflow.compile()
