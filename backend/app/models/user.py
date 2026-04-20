"""
User model — tracks Signal users interacting with the bot.

Handles both phone-number and UUID identifiers from Signal.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Signal identifier — phone number (+420...) or UUID, depends on gateway
    signal_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

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
    orders = relationship("Order", back_populates="user", lazy="selectin")
    conversations = relationship("Conversation", back_populates="user", lazy="selectin")
    payments = relationship("Payment", back_populates="user", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, signal_id='{self.signal_id}', name='{self.display_name}')>"
