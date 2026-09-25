"""
Schemas for Inbox Conversations API.

Supports:
- Distinct DM vs Group conversations
- Cursor-based message pagination
- Rich attachments and reactions
- Delivery status tracking
- Server-persisted read cursor
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AttachmentDTO(BaseModel):
    id: int
    filename: str | None = None
    mime_type: str | None = None
    size: int | None = None
    external_attachment_id: str | None = None
    processing_status: str = "pending"
    extracted_text: str | None = None
    processor_model: str | None = None
    processor_type: str | None = None
    processing_error: str | None = None


class ReactionDTO(BaseModel):
    id: int
    emoji: str
    reactor_identity: str
    reactor_name: str | None = None
    target_timestamp: int | None = None
    is_removed: bool = False
    occurred_at: datetime | None = None


class MessageDTO(BaseModel):
    id: int
    conversation_id: int
    direction: str = "inbound"  # "inbound" | "outbound"
    actor: str = "customer"  # "customer" | "bot" | "admin" | "system"
    role: str = "user"  # "user" | "assistant" | "system"
    sender_id: str | None = None
    sender_name: str | None = None
    content: str
    tokens_used: int | None = None
    reply_to_id: int | None = None
    delivery_status: str | None = (
        None  # "received" | "pending" | "sent" | "failed" | "delivered" | "read"
    )
    delivery_error: str | None = None
    signal_timestamp_ms: int | None = None
    occurred_at: datetime | None = None
    origin: str | None = (
        None  # "customer" | "ai_auto" | "human_manual" | "human_ai_assisted" | "system" | "campaign"
    )
    ai_run_id: int | None = None
    ai_suggestion_id: int | None = None
    admin_identity: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    timestamp: datetime
    attachments: list[AttachmentDTO] = Field(default_factory=list)
    reactions: list[ReactionDTO] = Field(default_factory=list)


class ConversationDTO(BaseModel):
    id: int
    type: str = "dm"  # "dm" | "group"
    signal_id: str
    group_id: str | None = None
    display_name: str
    mode: str = "auto"  # "auto" | "copilot" | "manual" | "paused"
    is_blocked: bool = False
    is_active: bool = True
    summary: str | None = None
    message_count: int = 0
    unread_count: int = 0
    has_failed_outbound: bool = False
    last_message: str = ""
    last_message_at: datetime | None = None
    last_message_actor: str | None = None
    created_at: datetime
    updated_at: datetime


class ConversationDetailDTO(ConversationDTO):
    notes: str | None = None
    dm_user_id: int | None = None
    phone_number: str | None = None
    signal_uuid: str | None = None
    members_count: int = 0
    admins_count: int = 0
    sync_status: str | None = None


class ConversationListResponse(BaseModel):
    items: list[ConversationDTO]
    total: int
    total_unread: int = 0


class ConversationMessagesResponse(BaseModel):
    conversation_id: int
    items: list[MessageDTO]
    has_more_before: bool = False
    has_more_after: bool = False
    oldest_id: int | None = None
    newest_id: int | None = None


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    reply_to_id: int | None = None


class UpdateModeRequest(BaseModel):
    mode: str = Field(pattern="^(auto|copilot|manual|paused)$")


class MarkReadRequest(BaseModel):
    last_message_id: int | None = None
