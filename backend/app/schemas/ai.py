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


class EditSuggestionRequest(BaseModel):
    edited_text: str = Field(min_length=1, max_length=10000)


class RejectSuggestionRequest(BaseModel):
    reason: str | None = None


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
    confidence: float
    importance: int
    sensitivity: str
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime


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
    faq_question: str | None = None
    faq_answer: str | None = None
    category: str = "general"


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
    total_ai_runs: int
    automation_rate: float
    copilot_rate: float
    human_takeover_rate: float
    suggestion_acceptance_rate: float
    suggestion_edit_rate: float
    suggestion_rejection_rate: float
    rag_hit_rate: float
    memory_items_count: int
    knowledge_documents_count: int
    average_latency_ms: float
    total_tokens_used: int
