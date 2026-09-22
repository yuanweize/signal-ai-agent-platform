"""
Feedback Event telemetry service for tracking AI utility and human interaction.
"""

from __future__ import annotations

import logging
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import FeedbackEvent

logger = logging.getLogger("ai.learning.feedback")


class FeedbackEventType(str, Enum):  # noqa: UP042
    ai_auto_sent = "ai_auto_sent"
    suggestion_accepted = "suggestion_accepted"
    suggestion_edited = "suggestion_edited"
    suggestion_rejected = "suggestion_rejected"
    human_manual_reply = "human_manual_reply"
    human_takeover = "human_takeover"
    conversation_resolved = "conversation_resolved"
    positive_feedback = "positive_feedback"
    negative_feedback = "negative_feedback"


class FeedbackService:
    """Records feedback events for learning analytics and fine-tuning curation."""

    async def record_event(
        self,
        session: AsyncSession,
        event_type: str,
        conversation_id: int,
        message_id: int | None = None,
        ai_suggestion_id: int | None = None,
        ai_run_id: int | None = None,
        rating: int | None = None,
        notes: str | None = None,
        actor: str = "system",
    ) -> FeedbackEvent:
        event = FeedbackEvent(
            event_type=event_type,
            conversation_id=conversation_id,
            message_id=message_id,
            ai_suggestion_id=ai_suggestion_id,
            ai_run_id=ai_run_id,
            rating=rating,
            notes=notes,
            actor=actor,
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        logger.debug(f"Recorded FeedbackEvent #{event.id}: {event_type} by {actor}")
        return event


feedback_service = FeedbackService()
