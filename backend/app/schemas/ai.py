"""
Pydantic schemas for AI Platform v0.4: Copilot, Knowledge, Memory, Skills, MCP, Learning, Evals.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

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
    memory: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    decision: str
    confidence: float | None = None
    latency_ms: int | None = None
    tokens: int | None = None
    errors: str | None = None
    final_message_id: int | None = None
    created_at: datetime


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


class CreateMCPServerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    transport: str = Field(default="stdio", pattern="^(stdio|http|sse)$")
    command_or_url: str = Field(min_length=1, max_length=512)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


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
    action: str | None = None
    faq_question: str | None = None
    faq_answer: str | None = None
    category: str = "general"
    scope_type: str = Field(default="global", pattern="^(global|group|user)$")
    scope_id: str | None = None
    confirm_global_privacy: bool = False


# --- Evaluation & Overview ---


class EvaluationSuiteResultDTO(BaseModel):
    total_cases: int
    passed_cases: int
    pass_rate: float
    decision_accuracy: float
    average_latency_ms: float
    total_tokens: int
    results: list[dict[str, Any]]


class AIOverviewMetricsDTO(BaseModel):
    total_ai_runs: int = 0
    total_runs: int = 0
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
    memory_items_count: int = 0
    knowledge_documents_count: int = 0
    knowledge_sources_count: int = 0
    knowledge_chunks_count: int = 0
    average_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    total_tokens_used: int = 0
    total_tokens: int = 0
