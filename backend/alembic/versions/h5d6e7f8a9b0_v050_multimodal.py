"""v050_multimodal

Revision ID: h5d6e7f8a9b0
Revises: g4c5d6e7f8a9
Create Date: 2026-09-25 00:00:00.000000

Signal AI Agent Platform v0.5.0 Multimodal Intelligence:
- Adds processing_status, extracted_text, processor_model, processor_type,
  and processing_error to message_attachments.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h5d6e7f8a9b0"
down_revision: Union[str, None] = "g4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("message_attachments", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "processing_status",
                sa.String(32),
                nullable=False,
                server_default="pending",
            )
        )
        batch_op.add_column(sa.Column("extracted_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("processor_model", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("processor_type", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("processing_error", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("message_attachments", schema=None) as batch_op:
        batch_op.drop_column("processing_error")
        batch_op.drop_column("processor_type")
        batch_op.drop_column("processor_model")
        batch_op.drop_column("extracted_text")
        batch_op.drop_column("processing_status")
