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
from app.ai.tools.registry import tool_registry

logger = logging.getLogger("ai.orchestration.graph")


def build_agent_graph(
    llm: LLMProvider,
    retriever: KnowledgeRetriever,
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
        """Check if product tools or actions should be invoked."""
        text = (state.get("text") or "").lower()
        results: list[dict[str, Any]] = []
        calls: list[dict[str, Any]] = []

        # Built-in heuristic or LLM tool selection
        if any(w in text for w in ["coffee", "product", "catalog", "item", "available", "stock"]):
            tool_name = "search_products"
            query_arg = "coffee" if "coffee" in text else ""
            calls.append({"name": tool_name, "arguments": {"query": query_arg}})
            res = await tool_registry.execute(tool_name, {"query": query_arg})
            results.append({"tool": tool_name, "output": res})

        if "refund" in text:
            # Sensitive financial action: extract validated parameters from text instead of hardcoding dummy values
            import re

            order_m = re.search(r"order\s*#?\s*(\d+)", text)
            amount_m = re.search(r"\$?\s*(\d+(?:\.\d+)?)\s*(?:usd|eur|czk|\$)?", text)

            if order_m and amount_m:
                refund_args = {
                    "order_id": int(order_m.group(1)),
                    "amount": float(amount_m.group(1)),
                    "reason": "customer_request",
                }
                calls.append({"name": "trigger_sample_refund", "arguments": refund_args})
                res = await tool_registry.execute(
                    "trigger_sample_refund",
                    refund_args,
                    user_approved=False,
                )
                results.append({"tool": "trigger_sample_refund", "output": res})
            else:
                calls.append({"name": "trigger_sample_refund", "arguments": {}})
                results.append(
                    {
                        "tool": "trigger_sample_refund",
                        "output": {
                            "status": "requires_approval",
                            "error": "Missing validated order_id and amount for refund action.",
                        },
                    }
                )

        return {
            "tool_calls": calls,
            "tool_results": results,
        }

    async def generate_response_node(state: AgentState) -> dict[str, Any]:
        """Generate grounded response adhering to knowledge and policy."""
        # 1. Check if user explicitly asked for human or sensitive blocked action
        text = (state.get("text") or "").lower()
        tool_results = state.get("tool_results") or []
        requires_approval = any(
            r.get("output", {}).get("status") == "requires_approval" for r in tool_results
        )

        if "human-handoff" in (state.get("selected_skills") or []) or any(
            w in text for w in ["human", "agent", "representative", "manager", "person", "staff"]
        ):
            return {
                "draft": "I understand you would like to speak to a representative. I am notifying our support team now.",
                "decision": AgentDecision.handoff.value,
                "decision_reason": "user_requested_human",
                "confidence": None,
                "tokens": 25,
            }

        # 2. Build prompt context
        messages = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT_TEMPLATE}]

        # Inject skills
        instructions = state.get("skill_instructions") or []
        if instructions:
            messages.append(
                {"role": "system", "content": "Active Skills:\n" + "\n\n".join(instructions)}
            )

        # Inject customer memory
        memories = state.get("memories") or []
        if memories:
            mem_text = "\n".join(f"- {m.get('content')}" for m in memories)
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

        # Inject user message
        messages.append({"role": "user", "content": state.get("text") or ""})

        reply, tokens = await llm.generate(messages)

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
            "tokens": tokens,
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
