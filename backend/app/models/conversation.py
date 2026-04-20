"""
Conversation & Message models — chat history and AI memory.

A Conversation groups messages between the bot and a user (optionally in a group).
Messages track the full dialogue with role labels for AI context.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Conversation(Base):
    """A conversation thread between the bot and a user."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Who is this conversation with
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    signal_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Which group (NULL = direct message / private chat)
    group_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # AI-generated summary for long-term memory compression
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Total message count (for quick stats without counting)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Whether conversation is still active
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message", back_populates="conversation", order_by="Message.timestamp", lazy="selectin"
    )

    def __repr__(self) -> str:
        ctx = f"group={self.group_id}" if self.group_id else "DM"
        return f"<Conversation(id={self.id}, user='{self.signal_id}', {ctx})>"


class Message(Base):
    """A single message in a conversation."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Parent conversation
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), nullable=False, index=True
    )

    # Role: "user", "assistant", or "system"
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    # Message content
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Detected intent (e.g., "product_inquiry", "buy", "complaint", "greeting")
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Confidence score for intent detection (0.0 - 1.0)
    intent_confidence: Mapped[float | None] = mapped_column(nullable=True)

    # Token usage for AI responses (for cost tracking)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self) -> str:
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<Message(id={self.id}, role='{self.role}', content='{preview}')>"
