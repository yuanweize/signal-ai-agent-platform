"""
Conversation, Message, Attachment, Reaction, and ReadState models.

Key design decisions for Round 2:
- Conversation types: "dm" (dm_user_id set, group_id null) vs "group" (group_id set, dm_user_id null)
- Group conversations have no single user "owner"; sender attribution is purely on Message.sender_user_id
- Outbound delivery status state machine: pending -> sent | failed -> delivered -> read
- MessageAttachments persist metadata for media sent or received
- MessageReactions track emoji reactions with external target timestamps
- ConversationReadStates store server-side read markers per admin
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ConversationMode(str, Enum):  # noqa: UP042
    auto = "auto"  # AI replies automatically
    manual = "manual"  # Admin replies; AI is suppressed
    paused = "paused"  # No auto-reply; messages are recorded only


class ConversationType(str, Enum):  # noqa: UP042
    dm = "dm"
    group = "group"


class MessageDirection(str, Enum):  # noqa: UP042
    inbound = "inbound"
    outbound = "outbound"


class MessageActor(str, Enum):  # noqa: UP042
    customer = "customer"
    bot = "bot"
    admin = "admin"
    system = "system"


class MessageDeliveryStatus(str, Enum):  # noqa: UP042
    received = "received"
    pending = "pending"
    sent = "sent"
    failed = "failed"
    delivered = "delivered"
    read = "read"
    deleted = "deleted"


class Conversation(Base):
    """A conversation thread between the bot and a user or group."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Type: "dm" or "group"
    type: Mapped[str] = mapped_column(String(20), default=ConversationType.dm.value, nullable=False, index=True)

    # Direct message user (NULL for group conversations)
    dm_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    # Legacy user_id column retained for backward compatibility (mirrors dm_user_id for DM, NULL for groups)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    signal_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Signal group ID (NULL = direct message / private chat)
    group_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Conversation mode — controls AI auto-reply
    mode: Mapped[str] = mapped_column(
        String(20), default=ConversationMode.auto.value, nullable=False
    )

    # AI-generated summary for long-term memory compression
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Total message count
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Whether conversation is still active
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Timestamp of the most recent message in the conversation
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="conversations")
    dm_user = relationship("User", foreign_keys=[dm_user_id], lazy="selectin")
    messages = relationship(
        "Message", back_populates="conversation", order_by="Message.timestamp", lazy="selectin"
    )
    read_states = relationship(
        "ConversationReadState", back_populates="conversation", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        ctx = f"group={self.group_id}" if self.type == ConversationType.group.value or self.group_id else f"dm_user={self.dm_user_id}"
        return f"<Conversation(id={self.id}, type={self.type}, mode={self.mode}, {ctx})>"


class Message(Base):
    """A single messaging entity in a conversation."""

    __tablename__ = "messages"

    __table_args__ = (
        UniqueConstraint("signal_event_id", name="uq_messages_signal_event_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Parent conversation
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), nullable=False, index=True
    )

    # Role: "user", "assistant", or "system" (legacy AI format)
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    # Direction: "inbound" | "outbound"
    direction: Mapped[str] = mapped_column(String(20), default=MessageDirection.inbound.value, nullable=False, index=True)

    # Actor: "customer" | "bot" | "admin" | "system"
    actor: Mapped[str] = mapped_column(String(20), default=MessageActor.customer.value, nullable=False, index=True)

    # Sender Signal ID (phone number or UUID)
    sender_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Sender resolved User ID
    sender_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    # Snapshot of display name at send time
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Message content / text
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Original Signal timestamp in milliseconds
    signal_timestamp_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    # Deduplication key: "{sender_id}:{signal_timestamp_ms}"
    signal_event_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)

    # Outbound delivery status: received | pending | sent | failed | delivered | read | deleted
    delivery_status: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    # Error detail if delivery_status == "failed"
    delivery_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Detected intent (for customer inquiries)
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Token usage for AI responses
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Quoted reply target message ID
    reply_to_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)

    # Exact time the event occurred externally (Signal timestamp converted to UTC datetime)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Storage insertion timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    sender_user = relationship("User", foreign_keys=[sender_user_id], lazy="selectin")
    attachments = relationship("MessageAttachment", back_populates="message", cascade="all, delete-orphan", lazy="selectin")
    reactions = relationship("MessageReaction", back_populates="message", cascade="all, delete-orphan", lazy="selectin")

    def __repr__(self) -> str:
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<Message(id={self.id}, dir={self.direction}, actor={self.actor}, content='{preview}')>"


class MessageAttachment(Base):
    """File/media attachment associated with a message."""

    __tablename__ = "message_attachments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)

    external_attachment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    message = relationship("Message", back_populates="attachments")

    def __repr__(self) -> str:
        return f"<MessageAttachment(id={self.id}, filename='{self.filename}', mime='{self.mime_type}')>"


class MessageReaction(Base):
    """Emoji reaction associated with a message."""

    __tablename__ = "message_reactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)

    emoji: Mapped[str] = mapped_column(String(32), nullable=False)
    reactor_identity: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reactor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    target_author: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_timestamp: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    is_removed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    message = relationship("Message", back_populates="reactions")
    reactor_user = relationship("User", foreign_keys=[reactor_user_id], lazy="selectin")

    def __repr__(self) -> str:
        state = " [removed]" if self.is_removed else ""
        return f"<MessageReaction(message_id={self.message_id}, emoji='{self.emoji}', by='{self.reactor_identity}'{state})>"


class ConversationReadState(Base):
    """Tracks read pointer per admin for persistent unread counts."""

    __tablename__ = "conversation_read_states"
    __table_args__ = (
        UniqueConstraint("conversation_id", "admin_identity", name="ix_conv_read_states_conv_admin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    admin_identity: Mapped[str] = mapped_column(String(128), default="admin", nullable=False)

    last_read_message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    conversation = relationship("Conversation", back_populates="read_states")
    last_read_message = relationship("Message", foreign_keys=[last_read_message_id], lazy="selectin")

    def __repr__(self) -> str:
        return f"<ConversationReadState(conv_id={self.conversation_id}, admin='{self.admin_identity}', last_read_msg_id={self.last_read_message_id})>"
