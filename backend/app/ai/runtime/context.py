"""
Agent Context dataclass carrying conversation and message state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class AgentContext:
    """Serializable execution context provided to the Agent Runtime."""

    conversation_id: int
    message_id: int | None = None
    sender_id: str = ""
    text: str = ""
    is_group: bool = False
    group_id: str | None = None
    user_id: int | None = None
    user_name: str | None = None
    language: str = "en"
    mode: str = "auto"  # auto | copilot | manual | paused
    recent_messages: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
