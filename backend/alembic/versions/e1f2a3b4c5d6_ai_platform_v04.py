"""ai_platform_v04

Revision ID: e1f2a3b4c5d6
Revises: c8927140f12a
Create Date: 2026-09-22 16:10:00.000000

AI Platform v0.4 schema enhancements:
- ai_runs (AI execution telemetry and traces)
- ai_suggestions (Human Copilot drafts, reviews, edit metrics)
- knowledge_sources (High-level knowledge sources: manual, FAQ, document, product, etc.)
- knowledge_documents (Individual documents with scope isolation: global, group, user)
- knowledge_chunks (Indexed chunks for vector and lexical retrieval)
- memory_items (Scoped durable memory: user, group, global)
- feedback_events (Human-in-the-loop learning events: accept, edit, reject, manual reply)
- learning_candidates (Distilled conversation-to-knowledge candidates)
- training_examples (Approved data for fine-tuning and evaluation datasets)
- prompt_versions (Version-controlled system prompts)
- mcp_servers (Governed MCP server connection profiles)
- tool_invocations (Audit logs of tool and action executions)
- messages: origin, ai_run_id, ai_suggestion_id, admin_identity, model, prompt_version
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "c8927140f12a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1. ai_runs
    if "ai_runs" not in existing_tables:
        op.create_table(
            "ai_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("trace_id", sa.String(64), nullable=False),
            sa.Column(
                "conversation_id",
                sa.Integer(),
                sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "input_message_id",
                sa.Integer(),
                sa.ForeignKey("messages.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("model", sa.String(64), nullable=True),
            sa.Column("provider", sa.String(64), nullable=True),
            sa.Column("prompt_version", sa.String(64), nullable=True),
            sa.Column("skills", sa.Text(), nullable=True),
            sa.Column("retrieval", sa.Text(), nullable=True),
            sa.Column("memory", sa.Text(), nullable=True),
            sa.Column("tool_calls", sa.Text(), nullable=True),
            sa.Column("decision", sa.String(32), server_default="reply", nullable=False),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("tokens", sa.Integer(), nullable=True),
            sa.Column("errors", sa.Text(), nullable=True),
            sa.Column(
                "final_message_id",
                sa.Integer(),
                sa.ForeignKey("messages.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
        )
        op.create_index("ix_ai_runs_trace_id", "ai_runs", ["trace_id"])
        op.create_index("ix_ai_runs_conversation_id", "ai_runs", ["conversation_id"])
        op.create_index("ix_ai_runs_input_message_id", "ai_runs", ["input_message_id"])
        op.create_index("ix_ai_runs_created_at", "ai_runs", ["created_at"])

    # 2. ai_suggestions
    if "ai_suggestions" not in existing_tables:
        op.create_table(
            "ai_suggestions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "conversation_id",
                sa.Integer(),
                sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "inbound_message_id",
                sa.Integer(),
                sa.ForeignKey("messages.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "ai_run_id",
                sa.Integer(),
                sa.ForeignKey("ai_runs.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("suggested_text", sa.Text(), nullable=False),
            sa.Column("status", sa.String(32), server_default="pending", nullable=False),
            sa.Column(
                "generated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("reviewed_by", sa.String(128), nullable=True),
            sa.Column(
                "final_message_id",
                sa.Integer(),
                sa.ForeignKey("messages.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("edit_distance", sa.Integer(), nullable=True),
            sa.Column("edit_ratio", sa.Float(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
        )
        op.create_index("ix_ai_suggestions_conversation_id", "ai_suggestions", ["conversation_id"])
        op.create_index("ix_ai_suggestions_inbound_message_id", "ai_suggestions", ["inbound_message_id"])
        op.create_index("ix_ai_suggestions_ai_run_id", "ai_suggestions", ["ai_run_id"])
        op.create_index("ix_ai_suggestions_status", "ai_suggestions", ["status"])

    # 3. knowledge_sources
    if "knowledge_sources" not in existing_tables:
        op.create_table(
            "knowledge_sources",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("source_type", sa.String(32), server_default="manual", nullable=False),
            sa.Column("source_uri", sa.String(512), nullable=True),
            sa.Column("language", sa.String(16), server_default="en", nullable=False),
            sa.Column("status", sa.String(32), server_default="active", nullable=False),
            sa.Column("trust_level", sa.String(32), server_default="standard", nullable=False),
            sa.Column("version", sa.Integer(), server_default="1", nullable=False),
            sa.Column("checksum", sa.String(64), nullable=True),
            sa.Column("created_by", sa.String(128), server_default="admin", nullable=False),
            sa.Column("approved_by", sa.String(128), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
        )
        op.create_index("ix_knowledge_sources_source_type", "knowledge_sources", ["source_type"])
        op.create_index("ix_knowledge_sources_status", "knowledge_sources", ["status"])

    # 4. knowledge_documents
    if "knowledge_documents" not in existing_tables:
        op.create_table(
            "knowledge_documents",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "source_id",
                sa.Integer(),
                sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("scope_type", sa.String(32), server_default="global", nullable=False),
            sa.Column("scope_id", sa.String(128), nullable=True),
            sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
        )
        op.create_index("ix_knowledge_documents_source_id", "knowledge_documents", ["source_id"])
        op.create_index("ix_knowledge_documents_scope_type", "knowledge_documents", ["scope_type"])
        op.create_index("ix_knowledge_documents_scope_id", "knowledge_documents", ["scope_id"])

    # 5. knowledge_chunks
    if "knowledge_chunks" not in existing_tables:
        op.create_table(
            "knowledge_chunks",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "document_id",
                sa.Integer(),
                sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "source_id",
                sa.Integer(),
                sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("chunk_index", sa.Integer(), server_default="0", nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("vector_id", sa.String(128), nullable=True),
            sa.Column("scope_type", sa.String(32), server_default="global", nullable=False),
            sa.Column("scope_id", sa.String(128), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
        )
        op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])
        op.create_index("ix_knowledge_chunks_source_id", "knowledge_chunks", ["source_id"])
        op.create_index("ix_knowledge_chunks_vector_id", "knowledge_chunks", ["vector_id"])
        op.create_index("ix_knowledge_chunks_scope_type", "knowledge_chunks", ["scope_type"])
        op.create_index("ix_knowledge_chunks_scope_id", "knowledge_chunks", ["scope_id"])

    # 6. memory_items
    if "memory_items" not in existing_tables:
        op.create_table(
            "memory_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("scope_type", sa.String(32), server_default="user", nullable=False),
            sa.Column("scope_id", sa.String(128), nullable=False),
            sa.Column("memory_type", sa.String(32), server_default="fact", nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
            sa.Column("importance", sa.Integer(), server_default="3", nullable=False),
            sa.Column("sensitivity", sa.String(32), server_default="standard", nullable=False),
            sa.Column("source_message_ids", sa.Text(), nullable=True),
            sa.Column(
                "source_conversation_id",
                sa.Integer(),
                sa.ForeignKey("conversations.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("status", sa.String(32), server_default="active", nullable=False),
            sa.Column("valid_from", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.String(128), server_default="ai_extraction", nullable=False),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
        )
        op.create_index("ix_memory_items_scope_type", "memory_items", ["scope_type"])
        op.create_index("ix_memory_items_scope_id", "memory_items", ["scope_id"])
        op.create_index("ix_memory_items_status", "memory_items", ["status"])

    # 7. feedback_events
    if "feedback_events" not in existing_tables:
        op.create_table(
            "feedback_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("event_type", sa.String(64), nullable=False),
            sa.Column(
                "conversation_id",
                sa.Integer(),
                sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "message_id",
                sa.Integer(),
                sa.ForeignKey("messages.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "ai_suggestion_id",
                sa.Integer(),
                sa.ForeignKey("ai_suggestions.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "ai_run_id",
                sa.Integer(),
                sa.ForeignKey("ai_runs.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("rating", sa.Integer(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("actor", sa.String(128), server_default="system", nullable=False),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
        )
        op.create_index("ix_feedback_events_event_type", "feedback_events", ["event_type"])
        op.create_index("ix_feedback_events_conversation_id", "feedback_events", ["conversation_id"])
        op.create_index("ix_feedback_events_created_at", "feedback_events", ["created_at"])

    # 8. learning_candidates
    if "learning_candidates" not in existing_tables:
        op.create_table(
            "learning_candidates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "conversation_id",
                sa.Integer(),
                sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "inbound_message_id",
                sa.Integer(),
                sa.ForeignKey("messages.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "outbound_message_id",
                sa.Integer(),
                sa.ForeignKey("messages.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("customer_question", sa.Text(), nullable=False),
            sa.Column("human_answer", sa.Text(), nullable=False),
            sa.Column("suggested_faq_q", sa.Text(), nullable=True),
            sa.Column("suggested_faq_a", sa.Text(), nullable=True),
            sa.Column("category", sa.String(64), server_default="general", nullable=False),
            sa.Column("language", sa.String(16), server_default="en", nullable=False),
            sa.Column("source_quality", sa.String(32), server_default="high", nullable=False),
            sa.Column("status", sa.String(32), server_default="pending", nullable=False),
            sa.Column("reviewed_by", sa.String(128), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
        )
        op.create_index("ix_learning_candidates_conversation_id", "learning_candidates", ["conversation_id"])
        op.create_index("ix_learning_candidates_status", "learning_candidates", ["status"])
        op.create_index("ix_learning_candidates_created_at", "learning_candidates", ["created_at"])

    # 9. training_examples
    if "training_examples" not in existing_tables:
        op.create_table(
            "training_examples",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "source_candidate_id",
                sa.Integer(),
                sa.ForeignKey("learning_candidates.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("system_instruction", sa.Text(), nullable=True),
            sa.Column("input_context", sa.Text(), nullable=False),
            sa.Column("target_response", sa.Text(), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("is_approved", sa.Boolean(), server_default="1", nullable=False),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
        )
        op.create_index("ix_training_examples_is_approved", "training_examples", ["is_approved"])
        op.create_index("ix_training_examples_created_at", "training_examples", ["created_at"])

    # 10. prompt_versions
    if "prompt_versions" not in existing_tables:
        op.create_table(
            "prompt_versions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("version", sa.String(64), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("template", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default="0", nullable=False),
            sa.Column("created_by", sa.String(128), server_default="system", nullable=False),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
            sa.Column("activated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_prompt_versions_version", "prompt_versions", ["version"], unique=True)
        op.create_index("ix_prompt_versions_is_active", "prompt_versions", ["is_active"])

    # 11. mcp_servers
    if "mcp_servers" not in existing_tables:
        op.create_table(
            "mcp_servers",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("transport", sa.String(32), server_default="stdio", nullable=False),
            sa.Column("command_or_url", sa.String(512), nullable=False),
            sa.Column("args_json", sa.Text(), nullable=True),
            sa.Column("env_json", sa.Text(), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), server_default="1", nullable=False),
            sa.Column("status", sa.String(32), server_default="disconnected", nullable=False),
            sa.Column("last_connected_at", sa.DateTime(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
        )
        op.create_index("ix_mcp_servers_name", "mcp_servers", ["name"], unique=True)
        op.create_index("ix_mcp_servers_is_enabled", "mcp_servers", ["is_enabled"])

    # 12. tool_invocations
    if "tool_invocations" not in existing_tables:
        op.create_table(
            "tool_invocations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "ai_run_id",
                sa.Integer(),
                sa.ForeignKey("ai_runs.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("tool_name", sa.String(128), nullable=False),
            sa.Column("tool_type", sa.String(32), server_default="builtin", nullable=False),
            sa.Column("arguments_json", sa.Text(), nullable=True),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("status", sa.String(32), server_default="success", nullable=False),
            sa.Column("requires_approval", sa.Boolean(), server_default="0", nullable=False),
            sa.Column("is_approved", sa.Boolean(), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
        )
        op.create_index("ix_tool_invocations_ai_run_id", "tool_invocations", ["ai_run_id"])
        op.create_index("ix_tool_invocations_tool_name", "tool_invocations", ["tool_name"])

    # 13. messages table enhancements
    msg_cols = {c["name"] for c in inspector.get_columns("messages")}
    with op.batch_alter_table("messages") as batch_op:
        if "origin" not in msg_cols:
            batch_op.add_column(
                sa.Column("origin", sa.String(30), server_default="customer", nullable=True)
            )
            batch_op.create_index("ix_messages_origin", ["origin"])
        if "ai_run_id" not in msg_cols:
            batch_op.add_column(
                sa.Column("ai_run_id", sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                "fk_messages_ai_run_id", "ai_runs", ["ai_run_id"], ["id"], ondelete="SET NULL"
            )
            batch_op.create_index("ix_messages_ai_run_id", ["ai_run_id"])
        if "ai_suggestion_id" not in msg_cols:
            batch_op.add_column(
                sa.Column("ai_suggestion_id", sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                "fk_messages_ai_suggestion_id",
                "ai_suggestions",
                ["ai_suggestion_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_index("ix_messages_ai_suggestion_id", ["ai_suggestion_id"])
        if "admin_identity" not in msg_cols:
            batch_op.add_column(
                sa.Column("admin_identity", sa.String(128), nullable=True)
            )
        if "model" not in msg_cols:
            batch_op.add_column(
                sa.Column("model", sa.String(64), nullable=True)
            )
        if "prompt_version" not in msg_cols:
            batch_op.add_column(
                sa.Column("prompt_version", sa.String(64), nullable=True)
            )

    # Backfill origin for existing messages
    op.execute(
        "UPDATE messages SET origin = 'customer' WHERE direction = 'inbound' AND (origin IS NULL OR origin = 'customer')"
    )
    op.execute(
        "UPDATE messages SET origin = 'ai_auto' WHERE direction = 'outbound' AND actor = 'bot'"
    )
    op.execute(
        "UPDATE messages SET origin = 'human_manual' WHERE direction = 'outbound' AND actor = 'admin'"
    )
    op.execute(
        "UPDATE messages SET origin = 'system' WHERE actor = 'system'"
    )


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_index("ix_messages_ai_suggestion_id")
        batch_op.drop_index("ix_messages_ai_run_id")
        batch_op.drop_index("ix_messages_origin")
        batch_op.drop_column("prompt_version")
        batch_op.drop_column("model")
        batch_op.drop_column("admin_identity")
        batch_op.drop_column("ai_suggestion_id")
        batch_op.drop_column("ai_run_id")
        batch_op.drop_column("origin")

    op.drop_table("tool_invocations")
    op.drop_table("mcp_servers")
    op.drop_table("prompt_versions")
    op.drop_table("training_examples")
    op.drop_table("learning_candidates")
    op.drop_table("feedback_events")
    op.drop_table("memory_items")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_sources")
    op.drop_table("ai_suggestions")
    op.drop_table("ai_runs")
