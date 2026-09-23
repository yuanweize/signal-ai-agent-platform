"""ai_studio_v041_observability

Revision ID: f3b4c5d6e7f8
Revises: e1f2a3b4c5d6
Create Date: 2026-09-23 03:00:00.000000

AI Studio v0.4.1 schema enhancements:
- ai_runs: structured token usage (input, output, total, cached, reasoning), call count, usage_source, cost, traffic_source
- ai_model_calls: detailed per-model-call telemetry during each AI turn
- evaluation_runs: historical test and benchmark executions
- evaluation_case_results: case-level evaluation outcomes
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3b4c5d6e7f8"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enhance ai_runs with structured token usage and cost telemetry
    with op.batch_alter_table("ai_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("input_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("output_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("total_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cached_input_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reasoning_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("llm_call_count", sa.Integer(), server_default="1", nullable=False))
        batch_op.add_column(sa.Column("usage_source", sa.String(length=32), server_default="unavailable", nullable=False))
        batch_op.add_column(sa.Column("estimated_cost", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("cost_currency", sa.String(length=8), server_default="USD", nullable=True))
        batch_op.add_column(sa.Column("traffic_source", sa.String(length=32), server_default="production", nullable=False))
        batch_op.create_index(batch_op.f("ix_ai_runs_traffic_source"), ["traffic_source"], unique=False)

    # Backfill historical ai_runs rows
    op.execute(
        "UPDATE ai_runs SET total_tokens = tokens, usage_source = 'legacy_total_only' WHERE tokens IS NOT NULL AND total_tokens IS NULL"
    )
    op.execute(
        "UPDATE ai_runs SET usage_source = 'unavailable' WHERE tokens IS NULL AND usage_source = 'unavailable'"
    )
    op.execute(
        "UPDATE ai_runs SET traffic_source = 'production' WHERE traffic_source IS NULL"
    )

    # 2. Create ai_model_calls table
    op.create_table(
        "ai_model_calls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ai_run_id", sa.Integer(), nullable=True),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("usage_source", sa.String(length=32), server_default="unavailable", nullable=False),
        sa.Column("finish_reason", sa.String(length=32), nullable=True),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("success", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=8), server_default="USD", nullable=True),
        sa.ForeignKeyConstraint(["ai_run_id"], ["ai_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("ai_model_calls", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_ai_model_calls_ai_run_id"), ["ai_run_id"], unique=False)

    # 3. Create evaluation_runs table
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("eval_type", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("dataset_version", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("total_cases", sa.Integer(), server_default="0", nullable=False),
        sa.Column("passed_cases", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pass_rate", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("decision_accuracy", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("avg_latency_ms", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("cost_currency", sa.String(length=8), server_default="USD", nullable=True),
        sa.Column("status", sa.String(length=32), server_default="completed", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("evaluation_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_evaluation_runs_started_at"), ["started_at"], unique=False)

    # 4. Create evaluation_case_results table
    op.create_table(
        "evaluation_case_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expected_decision", sa.String(length=64), nullable=True),
        sa.Column("actual_decision", sa.String(length=64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("evaluation_case_results", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_evaluation_case_results_run_id"), ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_table("evaluation_case_results")
    op.drop_table("evaluation_runs")
    op.drop_table("ai_model_calls")
    with op.batch_alter_table("ai_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ai_runs_traffic_source"))
        batch_op.drop_column("traffic_source")
        batch_op.drop_column("cost_currency")
        batch_op.drop_column("estimated_cost")
        batch_op.drop_column("usage_source")
        batch_op.drop_column("llm_call_count")
        batch_op.drop_column("reasoning_tokens")
        batch_op.drop_column("cached_input_tokens")
        batch_op.drop_column("total_tokens")
        batch_op.drop_column("output_tokens")
        batch_op.drop_column("input_tokens")
