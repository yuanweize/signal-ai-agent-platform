"""
Agent decisions and structured response models.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class AgentDecision(str, Enum):  # noqa: UP042
    reply = "reply"
    draft_for_human = "draft_for_human"
    ask_clarifying = "ask_clarifying"
    handoff = "handoff"
    no_reply = "no_reply"


@dataclass
class AgentResponse:
    """Structured response from the Agent Runtime."""

    answer: str
    decision: str = AgentDecision.reply.value
    confidence: float = 1.0
    model: str = "default"
    provider: str = "openai"
    prompt_version: str = "v1.0"

    skills_used: list[str] = field(default_factory=list)
    memories_used: list[dict] = field(default_factory=list)
    knowledge_chunks: list[dict] = field(default_factory=list)
    tools_called: list[dict] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)

    latency_ms: int = 0
    tokens: int = 0
    trace_id: str = ""
    ai_run_id: int | None = None
    ai_suggestion_id: int | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)
