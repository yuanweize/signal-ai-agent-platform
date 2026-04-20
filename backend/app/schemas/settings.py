"""Schemas for runtime settings API."""

from pydantic import BaseModel, Field


class RuntimeSettingsResponse(BaseModel):
    ai_prompt: str
    is_ai_enabled: bool
    is_market_enabled: bool
    has_ai_api_key: bool
    ai_api_key_masked: str
    retention_days: int
    ad_automation_enabled: bool
    ad_min_interval_minutes: int
    ad_quiet_hour_start: int
    ad_quiet_hour_end: int
    ad_group_blacklist: list[str]
    bot_name: str


class RuntimeSettingsUpdateRequest(BaseModel):
    ai_prompt: str | None = Field(default=None, max_length=5000)
    is_ai_enabled: bool | None = None
    is_market_enabled: bool | None = None
    ai_api_key: str | None = None
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    ad_automation_enabled: bool | None = None
    ad_min_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    ad_quiet_hour_start: int | None = Field(default=None, ge=0, le=23)
    ad_quiet_hour_end: int | None = Field(default=None, ge=0, le=23)
    ad_group_blacklist: list[str] | None = None
    bot_name: str | None = Field(default=None, max_length=80)


class RuntimeSettingsRollbackRequest(BaseModel):
    audit_log_id: int | None = None


class CleanupRequest(BaseModel):
    purge_all: bool = False


class CleanupResponse(BaseModel):
    messages_deleted: int
    conversations_deleted: int
    audit_logs_deleted: int
    campaign_logs_deleted: int
    retention_days: int | None = None


class AuditLogResponse(BaseModel):
    id: int
    actor: str
    action: str
    target: str
    status: str
    ip_address: str | None = None
    details: str
    created_at: str


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int


class CampaignBroadcastRequest(BaseModel):
    campaign_name: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=4000)
    target_group_ids: list[str] | None = None
    dry_run: bool = False


class CampaignBroadcastGroupResult(BaseModel):
    group_id: str
    status: str
    reason: str | None = None


class CampaignBroadcastResponse(BaseModel):
    campaign_name: str
    attempted: int
    sent: int
    skipped: int
    failed: int
    dry_run: bool
    items: list[CampaignBroadcastGroupResult]
