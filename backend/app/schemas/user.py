"""Schemas for admin user management APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ManagedUserItem(BaseModel):
    id: int
    signal_id: str
    display_name: str | None = None
    role: str
    language: str
    is_blocked: bool
    notes: str | None = None
    first_seen: datetime
    last_seen: datetime


class ManagedUserListResponse(BaseModel):
    items: list[ManagedUserItem]
    total: int
    page: int
    page_size: int


class ManagedUserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=20)
    language: str | None = Field(default=None, max_length=10)
    is_blocked: bool | None = None
    notes: str | None = Field(default=None, max_length=1000)


class ManagedUsersBatchRequest(BaseModel):
    user_ids: list[int] = Field(min_length=1)
    action: str = Field(pattern="^(block|unblock)$")


class ManagedUsersBatchResponse(BaseModel):
    updated_count: int
    action: str


class UserConversationSummary(BaseModel):
    conversation_id: int
    group_id: str | None = None
    message_count: int
    updated_at: datetime
    last_message: str | None = None


class UserRecentMessage(BaseModel):
    id: int
    role: str
    content: str
    timestamp: datetime
    group_id: str | None = None


class ManagedUserActivityResponse(BaseModel):
    user: ManagedUserItem
    conversation_count: int
    message_count: int
    recent_conversations: list[UserConversationSummary]
    recent_messages: list[UserRecentMessage]
