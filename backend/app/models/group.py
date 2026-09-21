"""
Group model — tracks Signal groups the bot is monitoring.

Supports multi-group operation with per-group configuration.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Group(Base):
    """A Signal group the bot is active in."""

    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Signal group ID (internal ID from signal-cli)
    group_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    # Human-readable name
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Description (synced from Signal or set manually)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Per-group settings
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Optional per-group system prompt override
    system_prompt_override: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional per-group language override
    language_override: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Admin notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Stats
    total_messages: Mapped[int] = mapped_column(default=0, nullable=False)

    # Timestamps
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_activity: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Alias for API compatibility — last_activity serves as updated_at
    @property
    def updated_at(self) -> datetime:
        return self.last_activity

    @property
    def created_at(self) -> datetime:
        return self.joined_at

    def __repr__(self) -> str:
        return f"<Group(id={self.id}, group_id='{self.group_id}', name='{self.name}')>"
