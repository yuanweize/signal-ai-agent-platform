"""
Group and GroupMember models — tracks Signal groups and membership domain.

Supports multi-group operation, synchronization state, and explicit group rosters.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    # Group synchronization status from Signal: 'synced' | 'pending' | 'failed' | 'not_synced'
    sync_status: Mapped[str] = mapped_column(String(20), default="not_synced", nullable=False)
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Campaign eligibility flag
    campaign_eligible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Optional per-group system prompt override
    system_prompt_override: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional per-group language override
    language_override: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Admin notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Stats
    total_messages: Mapped[int] = mapped_column(default=0, nullable=False)

    # Timestamps
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    last_activity: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    members = relationship(
        "GroupMember", back_populates="group", cascade="all, delete-orphan", lazy="selectin"
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


class GroupMember(Base):
    """Membership record linking a User or external identifier to a Group."""

    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "external_identifier", name="uq_group_members_unique_member"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # External Signal identifier (phone or UUID)
    external_identifier: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Administrative role in group
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="group_memberships")

    def __repr__(self) -> str:
        admin_flag = " (admin)" if self.is_admin else ""
        return f"<GroupMember(group_id={self.group_id}, ident='{self.external_identifier}'{admin_flag})>"
