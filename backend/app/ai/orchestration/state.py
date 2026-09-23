"""
Serializable Agent State for LangGraph workflow execution.
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """Clean serializable state passed between graph nodes (NO ORM objects!)."""

    conversation_id: int
    message_id: int | None
    sender_id: str
    user_id: int | None
    group_id: str | None
    is_group: bool
    text: str
    language: str
    mode: str  # auto | copilot | manual | paused

    # Context items
    memories: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]]
    selected_skills: list[str]
    skill_instructions: list[str]
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    history: list[dict[str, str]]
    prompt_template: str | None
    prompt_version: str | None

    # Response decision
    decision: str  # reply | draft_for_human | ask_clarifying | handoff | no_reply
    decision_reason: str | None
    draft: str | None
    confidence: float | None
    citations: list[dict[str, Any]]
    tokens: int
    error: str | None

    # Telemetry & per-call model execution records
    model_calls: list[dict[str, Any]]
    usage: dict[str, Any]
