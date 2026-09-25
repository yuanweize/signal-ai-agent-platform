"""
Pydantic schemas for AI Platform v0.4: Copilot, Knowledge, Memory, Skills, MCP, Learning, Evals.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, StrictBool, model_validator

# --- Copilot & Suggestions ---


class AISuggestionDTO(BaseModel):
    id: int
    conversation_id: int
    inbound_message_id: int | None = None
    ai_run_id: int | None = None
    suggested_text: str
    status: str  # pending | accepted | edited | rejected | expired | auto_sent
    generated_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    final_message_id: int | None = None
    edit_distance: int | None = None
    edit_ratio: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AcceptSuggestionRequest(BaseModel):
    suggestion_id: int | None = None


class EditSuggestionRequest(BaseModel):
    edited_text: str = Field(min_length=1, max_length=10000)
    suggestion_id: int | None = None


class RejectSuggestionRequest(BaseModel):
    reason: str | None = None
    suggestion_id: int | None = None


# --- AI Runs & Traces ---


class AIRunDTO(BaseModel):
    id: int
    trace_id: str
    conversation_id: int
    input_message_id: int | None = None
    model: str | None = None
    provider: str | None = None
    prompt_version: str | None = None
    skills: list[str] = Field(default_factory=list)
    retrieval: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    memory: list[dict[str, Any]] = Field(default_factory=list)
    memories: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    rag_hit_count: int = 0
    tool_call_count: int = 0
    decision: str
    confidence: float | None = None
    latency_ms: int | None = None
    tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    llm_call_count: int | None = None
    usage_source: str = "unavailable"
    estimated_cost: float | None = None
    cost_currency: str = "USD"
    traffic_source: str = "production"
    errors: str | None = None
    final_message_id: int | None = None
    created_at: datetime
    model_calls: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class AIRunListResponse(BaseModel):
    items: list[AIRunDTO]
    total: int
    limit: int
    offset: int


# --- Knowledge Base & RAG ---


class KnowledgeSourceDTO(BaseModel):
    id: int
    title: str
    source_type: str  # manual | faq | document | product | conversation | website | api
    source_uri: str | None = None
    language: str
    status: str
    trust_level: str
    version: int
    created_by: str
    created_at: datetime
    updated_at: datetime
    documents_count: int = 0


class KnowledgeDocumentDTO(BaseModel):
    id: int
    source_id: int
    title: str
    content: str
    scope_type: str
    scope_id: str | None = None
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime


class KnowledgeSourceDetailDTO(BaseModel):
    source: KnowledgeSourceDTO
    documents: list[KnowledgeDocumentDTO] = Field(default_factory=list)


class CreateKnowledgeSourceRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    source_type: str = Field(
        default="manual", pattern="^(manual|faq|document|product|conversation|website|api)$"
    )
    source_uri: str | None = None
    language: str = "en"
    trust_level: str = "standard"


class CreateDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    scope_type: str = Field(default="global", pattern="^(global|group|user)$")
    scope_id: str | None = None


class CreateFAQRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=5000)
    category: str = "general"
    scope_type: str = "global"
    scope_id: str | None = None


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)
    group_id: str | None = None
    user_id: str | None = None


class KnowledgeSearchResultDTO(BaseModel):
    chunk_id: int
    document_id: int
    source_id: int
    title: str
    content: str
    score: float
    scope_type: str
    scope_id: str | None = None


# --- Memory ---


class MemoryItemDTO(BaseModel):
    id: int
    scope_type: str  # user | group | global
    scope_id: str
    memory_type: str  # preference | fact | case | constraint
    content: str
    confidence: float = 1.0
    importance: int = 3
    sensitivity: str = "standard"
    status: str = "active"
    created_by: str = "ai_extraction"
    created_at: datetime
    updated_at: datetime | None = None
    is_pii_redacted: bool = False


class CreateMemoryRequest(BaseModel):
    scope_type: str = Field(default="user", pattern="^(user|group|global)$")
    scope_id: str = Field(min_length=1)
    memory_type: str = Field(default="fact", pattern="^(preference|fact|case|constraint)$")
    content: str = Field(min_length=1, max_length=2000)
    importance: int = Field(default=3, ge=1, le=5)


# --- Skills ---


class SkillDTO(BaseModel):
    name: str
    description: str
    version: str
    scope: str
    is_enabled: bool
    body: str | None = None


class ToggleSkillRequest(BaseModel):
    is_enabled: bool


# --- MCP ---


class MCPServerDTO(BaseModel):
    id: int
    name: str
    transport: str  # stdio | http | sse
    command_or_url: str
    is_enabled: bool
    status: str
    last_connected_at: datetime | None = None
    error_message: str | None = None
    tools_count: int = 0
    # Backward compatibility aliases
    transport_type: str | None = None
    command: str | None = None
    endpoint_url: str | None = None
    tool_count: int | None = None
    last_health_check: datetime | None = None


class MCPServerDetailDTO(BaseModel):
    server: MCPServerDTO
    discovered_tools: list[dict[str, Any]] = Field(default_factory=list)
    # Convenience flattened fields for UI compatibility
    id: int | None = None
    name: str | None = None
    transport: str | None = None
    transport_type: str | None = None
    endpoint_url: str | None = None
    command: str | None = None
    is_enabled: bool | None = None
    status: str | None = None
    tools: list[dict[str, Any]] = Field(default_factory=list)


class CreateMCPServerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    transport: str = Field(default="stdio")
    transport_type: str | None = None
    command_or_url: str = Field(default="", max_length=512)
    command: str | None = None
    endpoint_url: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        raw = data.get("transport") or data.get("transport_type") or "stdio"
        if not isinstance(raw, str):
            raise ValueError("transport must be a string")
        transport = raw.strip().lower()
        if transport not in ("stdio", "http", "sse"):
            raise ValueError(f"Unsupported transport '{raw}'. Expected stdio, http, or sse.")
        data["transport"] = transport
        if not data.get("command_or_url"):
            if transport == "stdio":
                data["command_or_url"] = data.get("command") or ""
            else:
                data["command_or_url"] = data.get("endpoint_url") or data.get("command") or ""
        if not str(data.get("command_or_url") or "").strip():
            raise ValueError("command_or_url (or command/endpoint_url) is required")
        return data


class UpdateMCPServerRequest(BaseModel):
    is_enabled: StrictBool | None = None


# --- Learning Loop ---


class LearningCandidateDTO(BaseModel):
    id: int
    conversation_id: int
    customer_question: str
    human_answer: str
    suggested_faq_q: str | None = None
    suggested_faq_a: str | None = None
    category: str
    language: str
    source_quality: str
    status: str  # pending | approved | rejected | promoted
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class PromoteCandidateRequest(BaseModel):
    action: Literal["knowledge", "training"] = "knowledge"
    faq_question: str | None = None
    faq_answer: str | None = None
    category: str = "general"
    scope_type: str = Field(default="global", pattern="^(global|group|user)$")
    scope_id: str | None = None
    confirm_global_privacy: bool = False


class TrainingStatsDTO(BaseModel):
    total_approved_examples: int


# --- Prompts ---


class PromptVersionDTO(BaseModel):
    id: int
    version: str
    name: str
    template: str
    is_active: bool
    created_by: str
    created_at: datetime
    activated_at: datetime | None = None


class CreatePromptVersionRequest(BaseModel):
    version: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    template: str = Field(min_length=10, max_length=50000)
    set_active: bool = False


# --- Evaluation & Overview ---


class EvaluationSuiteResultDTO(BaseModel):
    total_cases: int
    passed_cases: int
    pass_rate: float
    decision_accuracy: float
    average_latency_ms: float
    total_tokens: int | None = None
    results: list[dict[str, Any]]
    run_id: int | None = None
    eval_type: str = "deterministic"


class EvaluationRunDTO(BaseModel):
    id: int
    eval_type: str
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    dataset_version: str | None = None
    total_cases: int
    passed_cases: int
    pass_rate: float
    decision_accuracy: float
    average_latency_ms: float
    total_tokens: int | None = None
    estimated_cost: float | None = None
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)


class ProviderLiveTestRequest(BaseModel):
    test_tools: bool = True
    test_embeddings: bool = True


class ProviderLiveTestResponse(BaseModel):
    connected: bool
    connection_status: str = "connected"
    provider: str
    provider_detected: str = "openai_compatible"
    model: str
    endpoint: str
    latency_ms: int = 0
    preview: str = ""
    response_preview: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    usage_source: str = "unavailable"
    finish_reason: str | None = None
    tool_calling_status: str = "not_verified"
    native_tool_calling: str = "not_verified"
    embedding_status: str = "not_configured"
    embeddings: str = "not_configured"
    streaming_status: str = "not_verified"
    vision_status: str = "not_verified"
    audio_status: str = "not_verified"
    tested_at: datetime
    error: str | None = None
    error_message: str | None = None


# --- Usage Telemetry ---


class UsageSummaryDTO(BaseModel):
    time_range: str
    total_runs: int = 0
    total_tokens: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    estimated_cost: float | None = None
    currency: str = "USD"
    cost_currency: str = "USD"
    total_model_calls: int = 0
    avg_latency_ms: float = 0.0
    errors: int = 0
    error_rate: float = 0.0


class UsageTimeseriesPointDTO(BaseModel):
    timestamp: str
    runs: int = 0
    errors: int = 0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    avg_latency_ms: float = 0.0


class UsageTimeseriesResponseDTO(BaseModel):
    points: list[UsageTimeseriesPointDTO]
    time_range: str
    timezone: str = "UTC"


class ModelUsageItemDTO(BaseModel):
    provider: str
    model: str
    runs: int
    errors: int
    error_rate: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    avg_latency_ms: float
    estimated_cost: float | None = None
    currency: str = "USD"


class ModelUsageResponseDTO(BaseModel):
    models: list[ModelUsageItemDTO]


class AIOverviewMetricsDTO(BaseModel):
    total_ai_runs: int = 0
    total_runs: int = 0
    successful_runs: int = 0
    error_runs: int = 0
    error_rate: float = 0.0
    automation_rate: float = 0.0
    copilot_rate: float = 0.0
    human_takeover_rate: float = 0.0
    suggestion_acceptance_rate: float = 0.0
    copilot_acceptance_rate: float = 0.0
    copilot_suggestions_count: int = 0
    suggestion_edit_rate: float = 0.0
    copilot_avg_edit_ratio: float = 0.0
    suggestion_rejection_rate: float = 0.0
    rag_hit_rate: float = 0.0
    tool_call_success_rate: float = 0.0
    tool_approval_rate: float = 0.0
    memory_items_count: int = 0
    knowledge_documents_count: int = 0
    knowledge_sources_count: int = 0
    knowledge_chunks_count: int = 0
    average_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    total_tokens_used: int = 0
    total_tokens: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    tokens_source: str = "unavailable"
    estimated_cost: float | None = None
    cost_currency: str = "USD"
    time_range: str = "all"
    timezone: str = "UTC"
