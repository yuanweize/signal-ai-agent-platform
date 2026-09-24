"""v042_hardening

Revision ID: g4c5d6e7f8a9
Revises: f3b4c5d6e7f8
Create Date: 2026-09-24 10:00:00.000000

Signal Market Bot v0.4.2 Hardening:
- Correct historical legacy rows where llm_call_count was guessed as 1
  without actual AIModelCall telemetry evidence.
- Preserves actual v0.4.1+ measured call counts and real telemetry.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g4c5d6e7f8a9"
down_revision: Union[str, None] = "f3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure llm_call_count is explicitly nullable in SQLite before resetting values
    with op.batch_alter_table("ai_runs", schema=None) as batch_op:
        batch_op.alter_column(
            "llm_call_count",
            existing_type=sa.Integer(),
            nullable=True,
            server_default=None,
        )

    # Correct historical legacy rows where llm_call_count was heuristically guessed as 1
    # without corresponding ai_model_calls evidence.
    op.execute(
        """
        UPDATE ai_runs
        SET llm_call_count = NULL
        WHERE usage_source = 'legacy_total_only'
          AND NOT EXISTS (
              SELECT 1 FROM ai_model_calls WHERE ai_model_calls.ai_run_id = ai_runs.id
          )
        """
    )


def downgrade() -> None:
    # Restore heuristic fallback if rolling back to v0.4.1
    op.execute(
        """
        UPDATE ai_runs
        SET llm_call_count = 1
        WHERE usage_source = 'legacy_total_only'
          AND total_tokens IS NOT NULL
          AND total_tokens > 0
          AND llm_call_count IS NULL
        """
    )
