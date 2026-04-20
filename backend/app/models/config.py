"""
BotConfig model — key-value store for runtime bot configuration.

Allows admin to change bot behavior without restarting:
- System prompts, AI parameters, greeting messages, etc.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BotConfig(Base):
    """Runtime configuration stored as key-value pairs."""

    __tablename__ = "bot_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Config key (unique identifier)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    # Config value (stored as text, parsed by application)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Human-readable description
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Category for grouping in admin UI
    category: Mapped[str] = mapped_column(String(50), default="general", nullable=False)

    # Timestamps
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        preview = self.value[:30] + "..." if len(self.value) > 30 else self.value
        return f"<BotConfig(key='{self.key}', value='{preview}')>"
