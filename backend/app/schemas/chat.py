"""Schemas for chat logs and manual takeover APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatConversationItem(BaseModel):
    id: int = 0  # internal conversation ID (use for mode API)
    signal_id: str
    display_name: str | None = None
    group_id: str | None = None
    mode: str = "auto"  # "auto" | "manual" | "paused"
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
    sender_name: str | None = None
    sender_id: str | None = None
    signal_timestamp_ms: int | None = None
    delivery_status: str | None = None
    delivery_error: str | None = None


class ChatMessagesResponse(BaseModel):
    signal_id: str
    display_name: str | None = None
    group_id: str | None = None
    conversation_id: int | None = None
    mode: str = "auto"
    items: list[ChatMessageItem]
    total: int
    page: int
    page_size: int


class ChatSendRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    group_id: str | None = None


class ChatSendResponse(BaseModel):
    success: bool
