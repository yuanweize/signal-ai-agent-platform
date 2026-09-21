"""apply_messages_unique_constraint_batch

Revision ID: 397929583aa5
Revises: a0c4522143d4
Create Date: 2026-09-21

Applies the unique constraint on messages.signal_event_id using SQLite batch
mode (copy-and-move), and removes the legacy intent_confidence column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '397929583aa5'
down_revision: Union[str, None] = 'a0c4522143d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite requires batch mode for adding constraints to existing tables.
    # This rebuilds the messages table with the unique constraint applied.
    # NULL values in signal_event_id are excluded from uniqueness by SQLite semantics.
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_messages_signal_event_id', ['signal_event_id'])
        # Drop legacy column no longer used in new schema
        batch_op.drop_column('intent_confidence')


def downgrade() -> None:
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('intent_confidence', sa.Float(), nullable=True))
        batch_op.drop_constraint('uq_messages_signal_event_id', type_='unique')
