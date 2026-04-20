"""Schemas for runtime settings API."""

from pydantic import BaseModel, Field


class RuntimeSettingsResponse(BaseModel):
    signal_api_url: str
    signal_phone_number: str
    has_signal_api_token: bool
    signal_api_token_masked: str
    ai_prompt: str
    is_ai_enabled: bool
    is_market_enabled: bool
    has_ai_api_key: bool
    ai_api_key_masked: str
    ai_api_key_source: str
    ai_api_base_url: str
    ai_provider_detected: str
    ai_model: str
    ai_temperature: float
    ai_max_tokens: int
    ai_context_messages: int
    ai_models_cached: list[str] = []
    ai_models_cached_invalid: list[str] = []
    ai_models_listed_total: int = 0
    ai_models_cached_at: str | None = None
    retention_days: int
    ad_automation_enabled: bool
    ad_min_interval_minutes: int
    ad_quiet_hour_start: int
    ad_quiet_hour_end: int
    ad_group_blacklist: list[str]
    bot_name: str
    bot_default_language: str


class RuntimeSettingsUpdateRequest(BaseModel):
    signal_api_url: str | None = Field(default=None, max_length=500)
    signal_phone_number: str | None = Field(default=None, max_length=64)
    signal_api_token: str | None = None
    ai_prompt: str | None = Field(default=None, max_length=5000)
    is_ai_enabled: bool | None = None
    is_market_enabled: bool | None = None
    ai_api_key: str | None = None
    ai_api_base_url: str | None = Field(default=None, max_length=500)
    ai_model: str | None = Field(default=None, max_length=120)
    ai_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    ai_max_tokens: int | None = Field(default=None, ge=1, le=32000)
    ai_context_messages: int | None = Field(default=None, ge=1, le=200)
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    ad_automation_enabled: bool | None = None
    ad_min_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    ad_quiet_hour_start: int | None = Field(default=None, ge=0, le=23)
    ad_quiet_hour_end: int | None = Field(default=None, ge=0, le=23)
    ad_group_blacklist: list[str] | None = None
    bot_name: str | None = Field(default=None, max_length=80)
    bot_default_language: str | None = Field(default=None, max_length=12)


class RuntimeSettingsRollbackRequest(BaseModel):
    audit_log_id: int | None = None


class AiProbeRequest(BaseModel):
    ai_api_base_url: str | None = Field(default=None, max_length=500)
    ai_model: str | None = Field(default=None, max_length=120)
    ai_api_key: str | None = None


class AiProbeAttempt(BaseModel):
    base_url: str
    model: str
    status: int | None = None
    message: str


class AiProbeResponse(BaseModel):
    ok: bool
    provider_detected: str
    requested_base_url: str | None = None
    candidate_base_urls: list[str] = []
    verification_base_candidates: list[str] = []
    effective_base_url: str | None = None
    effective_model: str | None = None
    models: list[str] = []
    invalid_models: list[dict] = []
    listed_total: int = 0
    models_count: int = 0
    verified_total: int = 0
    probed_at: str | None = None
    cached_at: str | None = None
    message: str
    preview: str | None = None
    attempts: list[AiProbeAttempt]


class AiModelVerifyRequest(BaseModel):
    ai_api_base_url: str | None = Field(default=None, max_length=500)
    ai_model: str = Field(min_length=1, max_length=120)
    ai_api_key: str | None = None


class AiModelVerifyResponse(BaseModel):
    ok: bool
    model: str
    effective_model: str | None = None
    effective_base_url: str | None = None
    checked_at: str
    message: str
    preview: str | None = None
    attempts: list[AiProbeAttempt]


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
