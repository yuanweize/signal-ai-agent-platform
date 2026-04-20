"""Schemas for chat logs and manual takeover APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatConversationItem(BaseModel):
    signal_id: str
    display_name: str | None = None
    group_id: str | None = None
    last_message: str = ""
    last_message_at: datetime | None = None
    message_count: int = 0


class ChatConversationListResponse(BaseModel):
    items: list[ChatConversationItem]
    total: int


class ChatMessageItem(BaseModel):
    id: int
    role: str
    content: str
    timestamp: datetime


class ChatMessagesResponse(BaseModel):
    signal_id: str
    display_name: str | None = None
    group_id: str | None = None
    items: list[ChatMessageItem]
    total: int
    page: int
    page_size: int


class ChatSendRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    group_id: str | None = None


class ChatSendResponse(BaseModel):
    success: bool
