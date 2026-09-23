"""
AI Platform v0.4 ORM Models.

Entities:
- AIRun: AI invocation trace and provenance
- AISuggestion: Human Copilot drafts and lifecycle
- KnowledgeSource, KnowledgeDocument, KnowledgeChunk: RAG and Knowledge Base
- MemoryItem: Scoped durable memory (user, group, global)
- FeedbackEvent: Human feedback and learning telemetry
- LearningCandidate: Conversation-to-knowledge distillation candidates
- TrainingExample: Offline fine-tuning / evaluation datasets
- PromptVersion: Version-controlled system prompts
- MCPServerConfig: Governed MCP server connection profiles
- ToolInvocation: Audit trail of tool/action executions
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AISuggestionStatus(str, Enum):  # noqa: UP042
    pending = "pending"
    processing = "processing"
    accepted = "accepted"
    edited = "edited"
    rejected = "rejected"
    expired = "expired"
    auto_pending = "auto_pending"
    auto_sent = "auto_sent"
    send_failed = "send_failed"


class AIDecisionType(str, Enum):  # noqa: UP042
    reply = "reply"
    draft_for_human = "draft_for_human"
    ask_clarifying = "ask_clarifying"
    handoff = "handoff"
    no_reply = "no_reply"


class AIRun(Base):
    """Execution record for an AI interaction including telemetry and citations."""

    __tablename__ = "ai_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    input_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )

    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    skills: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of skill names
    retrieval: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON citations/chunks
    memory: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON memories referenced
    tool_calls: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON tool calls

    decision: Mapped[str] = mapped_column(
        String(32), default=AIDecisionType.reply.value, nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    errors: Mapped[str | None] = mapped_column(Text, nullable=True)

    final_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    # Structured token usage & cost telemetry (v0.4.1)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_call_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    usage_source: Mapped[str] = mapped_column(String(32), default="unavailable", nullable=False)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_currency: Mapped[str | None] = mapped_column(String(8), default="USD", nullable=True)
    traffic_source: Mapped[str] = mapped_column(
        String(32), default="production", nullable=False, index=True
    )

    conversation = relationship("Conversation", foreign_keys=[conversation_id], lazy="selectin")
    suggestions = relationship("AISuggestion", back_populates="ai_run", lazy="selectin")
    tool_invocations = relationship("ToolInvocation", back_populates="ai_run", lazy="selectin")
    model_calls = relationship(
        "AIModelCall", back_populates="ai_run", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<AIRun(id={self.id}, trace='{self.trace_id}', decision='{self.decision}', model='{self.model}')>"


class AISuggestion(Base):
    """Copilot suggestion drafted by AI for human review, edit, or dispatch."""

    __tablename__ = "ai_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    inbound_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ai_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    suggested_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=AISuggestionStatus.pending.value, nullable=False, index=True
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    final_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    edit_distance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    edit_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    conversation = relationship("Conversation", foreign_keys=[conversation_id], lazy="selectin")
    ai_run = relationship("AIRun", back_populates="suggestions", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<AISuggestion(id={self.id}, conv_id={self.conversation_id}, status='{self.status}')>"
        )


class KnowledgeSource(Base):
    """Represents a high-level source of truth (FAQ, document, catalog sync, etc.)."""

    __tablename__ = "knowledge_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(32), default="manual", nullable=False, index=True
    )
    source_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False, index=True)
    trust_level: Mapped[str] = mapped_column(String(32), default="standard", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), default="admin", nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    documents = relationship(
        "KnowledgeDocument", back_populates="source", cascade="all, delete-orphan", lazy="selectin"
    )
    chunks = relationship(
        "KnowledgeChunk", back_populates="source", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<KnowledgeSource(id={self.id}, title='{self.title}', type='{self.source_type}')>"


class KnowledgeDocument(Base):
    """Document within a knowledge source."""

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    scope_type: Mapped[str] = mapped_column(
        String(32), default="global", nullable=False, index=True
    )
    scope_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source = relationship("KnowledgeSource", back_populates="documents")
    chunks = relationship(
        "KnowledgeChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<KnowledgeDocument(id={self.id}, title='{self.title}', scope='{self.scope_type}')>"


class KnowledgeChunk(Base):
    """Chunk of text indexed for vector and lexical retrieval."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    vector_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    scope_type: Mapped[str] = mapped_column(
        String(32), default="global", nullable=False, index=True
    )
    scope_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    source = relationship("KnowledgeSource", back_populates="chunks")
    document = relationship("KnowledgeDocument", back_populates="chunks")

    def __repr__(self) -> str:
        return (
            f"<KnowledgeChunk(id={self.id}, doc_id={self.document_id}, scope='{self.scope_type}')>"
        )


class MemoryItem(Base):
    """Durable long-term memory item scoped to user, group, or organization."""

    __tablename__ = "memory_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scope_type: Mapped[str] = mapped_column(String(32), default="user", nullable=False, index=True)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    memory_type: Mapped[str] = mapped_column(String(32), default="fact", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(32), default="standard", nullable=False)

    source_message_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False, index=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), default="ai_extraction", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<MemoryItem(id={self.id}, scope='{self.scope_type}:{self.scope_id}', status='{self.status}')>"

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def to_dict(self) -> dict[str, Any]:
        imp = self.importance
        if imp is not None:
            try:
                imp = int(round(float(imp)))
            except Exception:
                imp = 3
        else:
            imp = 3

        return {
            "id": self.id,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "memory_type": self.memory_type,
            "content": self.content,
            "confidence": self.confidence,
            "importance": imp,
            "sensitivity": self.sensitivity,
            "status": self.status,
        }


class FeedbackEvent(Base):
    """User or operator feedback event recording AI utility and learning telemetry."""

    __tablename__ = "feedback_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    ai_suggestion_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_suggestions.id", ondelete="SET NULL"), nullable=True
    )
    ai_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="SET NULL"), nullable=True
    )

    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(128), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<FeedbackEvent(id={self.id}, event='{self.event_type}', actor='{self.actor}')>"


class LearningCandidate(Base):
    """High-quality Q&A pairs distilled from human interactions for review."""

    __tablename__ = "learning_candidates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    inbound_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    outbound_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )

    customer_question: Mapped[str] = mapped_column(Text, nullable=False)
    human_answer: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_faq_q: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_faq_a: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(64), default="general", nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    source_quality: Mapped[str] = mapped_column(String(32), default="high", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)

    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<LearningCandidate(id={self.id}, status='{self.status}', category='{self.category}')>"
        )


class TrainingExample(Base):
    """Approved example for dataset export and offline model fine-tuning."""

    __tablename__ = "training_examples"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_candidates.id", ondelete="SET NULL"), nullable=True
    )
    system_instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_context: Mapped[str] = mapped_column(Text, nullable=False)
    target_response: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<TrainingExample(id={self.id}, approved={self.is_approved})>"


class PromptVersion(Base):
    """Versioned system prompts for traceable agent behavior."""

    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(128), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<PromptVersion(id={self.id}, version='{self.version}', active={self.is_active})>"


class MCPServerConfig(Base):
    """Connection and governance configuration for Model Context Protocol servers."""

    __tablename__ = "mcp_servers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    transport: Mapped[str] = mapped_column(String(32), default="stdio", nullable=False)
    command_or_url: Mapped[str] = mapped_column(String(512), nullable=False)
    args_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    env_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="disconnected", nullable=False)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<MCPServerConfig(id={self.id}, name='{self.name}', status='{self.status}')>"


class ToolInvocation(Base):
    """Audit record for any tool call made by the AI engine or agent runtime."""

    __tablename__ = "tool_invocations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ai_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tool_type: Mapped[str] = mapped_column(String(32), default="builtin", nullable=False)
    arguments_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="success", nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    ai_run = relationship("AIRun", back_populates="tool_invocations")

    def __repr__(self) -> str:
        return f"<ToolInvocation(id={self.id}, tool='{self.tool_name}', status='{self.status}')>"


class AIModelCall(Base):
    """Detailed telemetry record for each individual model invocation during an AI turn."""

    __tablename__ = "ai_model_calls"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ai_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    phase: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # tool_planner, response_generation, diagnostics, other
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_source: Mapped[str] = mapped_column(String(32), default="unavailable", nullable=False)

    finish_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), default="USD", nullable=True)

    ai_run = relationship("AIRun", back_populates="model_calls")

    def __repr__(self) -> str:
        return f"<AIModelCall(id={self.id}, run={self.ai_run_id}, phase='{self.phase}', tokens={self.total_tokens})>"


class EvaluationRun(Base):
    """Historical benchmark and evaluation suite execution run."""

    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    eval_type: Mapped[str] = mapped_column(String(32), nullable=False)  # deterministic | live
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataset_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pass_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    decision_accuracy: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_currency: Mapped[str | None] = mapped_column(String(8), default="USD", nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    case_results = relationship(
        "EvaluationCaseResult",
        back_populates="run",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<EvaluationRun(id={self.id}, type='{self.eval_type}', pass_rate={self.pass_rate})>"


class EvaluationCaseResult(Base):
    """Result of an individual test case in an evaluation run."""

    __tablename__ = "evaluation_case_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # PASS | FAIL | ERROR
    expected_decision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actual_decision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    run = relationship("EvaluationRun", back_populates="case_results", lazy="selectin")

    def __repr__(self) -> str:
        return f"<EvaluationCaseResult(id={self.id}, run={self.run_id}, case='{self.case_id}', status='{self.status}')>"
