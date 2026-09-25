"""Realtime event model and standard event types."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


class RealtimeEventType:
    """Standardized event types for realtime transport."""

    MESSAGE_RECEIVED = "message.received"
    MESSAGE_UPDATED = "message.updated"
    MESSAGE_SENT = "message.sent"

    CONVERSATION_UPDATED = "conversation.updated"

    COPILOT_SUGGESTION_CREATED = "copilot.suggestion.created"
    COPILOT_SUGGESTION_UPDATED = "copilot.suggestion.updated"

    AI_RUN_STARTED = "ai_run.started"
    AI_RUN_COMPLETED = "ai_run.completed"
    AI_RUN_FAILED = "ai_run.failed"

    CAMPAIGN_UPDATED = "campaign.updated"

    SYSTEM_CONNECTED = "system.connected"
    SYSTEM_HEARTBEAT = "system.heartbeat"
    RESYNC_REQUIRED = "system.resync_required"


@dataclass
class RealtimeEvent:
    """Canonical realtime event passed through the broker to SSE clients."""

    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    scope: str = "global"
    conversation_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_sse(self) -> str:
        """Format as standard Server-Sent Events (SSE) packet."""
        data_str = json.dumps(self.to_dict(), ensure_ascii=False)
        return f"id: {self.id}\nevent: {self.type}\ndata: {data_str}\n\n"
