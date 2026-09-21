"""
User model — tracks Signal users interacting with the bot.

Handles multi-identifier Signal identity strategy (phone, UUID, historical aliases).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Primary Signal identifier — phone number (+420...) or UUID for backward compatibility
    signal_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    # Specific canonical identities
    phone_number: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    signal_uuid: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    # Display name (from Signal profile or manually set)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Role: "customer" (default) or "admin"
    role: Mapped[str] = mapped_column(String(20), default="customer", nullable=False)

    # Preferred language (ISO 639-1: cs, en, zh, de, ...)
    language: Mapped[str] = mapped_column(String(10), default="cs", nullable=False)

    # Tracking
    first_seen: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Whether user is blocked from interacting
    is_blocked: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Notes (admin can add notes about the user)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Relationships
    identities = relationship(
        "UserIdentity", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    group_memberships = relationship("GroupMember", back_populates="user", lazy="selectin")
    orders = relationship("Order", back_populates="user", lazy="selectin")
    conversations = relationship(
        "Conversation",
        foreign_keys="[Conversation.user_id]",
        back_populates="user",
        lazy="selectin",
    )
    payments = relationship("Payment", back_populates="user", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, signal_id='{self.signal_id}', name='{self.display_name}')>"


class UserIdentity(Base):
    """Normalized identities associated with a logical User (phone, UUID, aliases)."""

    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("identity_type", "identity_value", name="uq_user_identities_type_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # 'phone', 'uuid', 'alias', etc.
    identity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    identity_value: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", back_populates="identities")

    def __repr__(self) -> str:
        return (
            f"<UserIdentity(user_id={self.user_id}, {self.identity_type}='{self.identity_value}')>"
        )
