"""
Conversation & Message models — chat history and AI memory.

A Conversation groups messages between the bot and a user (optionally in a group).
Messages track the full dialogue with role labels for AI context.

Key design decisions:
- DM conversations: user_id is set, group_id is None
- Group conversations: group_id is set; user_id is the first-seen sender (legacy compat) but NOT used for attribution
- Message.sender_id is always authoritative for who sent a message
- mode controls AI auto-reply behaviour: "auto" | "manual" | "paused"
- signal_timestamp_ms stores the original Signal millisecond timestamp for reactions/deletes
- signal_event_id provides idempotency: same Signal event never stored twice
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ConversationMode(str, Enum):  # noqa: UP042 — StrEnum not available in 3.10
    auto = "auto"  # AI replies automatically
    manual = "manual"  # Admin replies; AI is suppressed
    paused = "paused"  # No auto-reply; messages are recorded only


class Conversation(Base):
    """A conversation thread between the bot and a user or group."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # For DM: user_id is set; for group: group_id is set.
    # user_id on a group conversation is the *first sender* kept for legacy compat — do not use for attribution.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    signal_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Which group (NULL = direct message / private chat)
    group_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Conversation mode — controls AI auto-reply
    # "auto": AI replies | "manual": admin only | "paused": no auto reply
    mode: Mapped[str] = mapped_column(
        String(20), default=ConversationMode.auto.value, nullable=False
    )

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
        return f"<Conversation(id={self.id}, mode={self.mode}, {ctx})>"


class Message(Base):
    """A single message in a conversation."""

    __tablename__ = "messages"

    __table_args__ = (
        # Idempotency: the same Signal event (identified by signal_event_id) must never
        # be stored twice, even on reconnect or polling fallback.
        UniqueConstraint("signal_event_id", name="uq_messages_signal_event_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Parent conversation
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), nullable=False, index=True
    )

    # Role: "user", "assistant", or "system"
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    # Sender Signal ID (authoritative — always set for user messages)
    sender_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Snapshot of display name at send time (avoids joins)
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Message content
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Original Signal timestamp in milliseconds (used for reactions/deletes)
    # NULL for bot-generated messages
    signal_timestamp_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Deduplication key: "{sender_id}:{signal_timestamp_ms}" for inbound user messages.
    # NULL for outbound bot/admin messages (no Signal timestamp yet at write time).
    signal_event_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)

    # Outbound delivery status: null (inbound) | pending | sent | failed
    delivery_status: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    # Error detail if delivery_status == "failed"
    delivery_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Detected intent (e.g., "product_inquiry", "buy", "complaint", "greeting")
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Token usage for AI responses (for cost tracking)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamp (wall-clock UTC when we stored this record)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self) -> str:
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<Message(id={self.id}, role='{self.role}', content='{preview}')>"
