"""add_conversation_mode_message_dedup_group_description

Revision ID: a0c4522143d4
Revises: 
Create Date: 2026-09-21 18:06:34.294817

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0c4522143d4'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add mode with server_default='auto' so existing rows get a valid value
    op.add_column('conversations', sa.Column(
        'mode', sa.String(length=20), nullable=False, server_default='auto'
    ))
    # user_id stays nullable (was always effectively nullable for group conversations)
    op.alter_column('conversations', 'user_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.add_column('groups', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('messages', sa.Column('sender_name', sa.String(length=255), nullable=True))
    op.add_column('messages', sa.Column('signal_timestamp_ms', sa.Integer(), nullable=True))
    op.add_column('messages', sa.Column('signal_event_id', sa.String(length=256), nullable=True))
    op.add_column('messages', sa.Column('delivery_status', sa.String(length=20), nullable=True))
    op.add_column('messages', sa.Column('delivery_error', sa.String(length=500), nullable=True))
    op.create_index(op.f('ix_messages_delivery_status'), 'messages', ['delivery_status'], unique=False)
    op.create_index(op.f('ix_messages_sender_id'), 'messages', ['sender_id'], unique=False)
    op.create_index(op.f('ix_messages_signal_event_id'), 'messages', ['signal_event_id'], unique=False)
    op.create_index(op.f('ix_messages_signal_timestamp_ms'), 'messages', ['signal_timestamp_ms'], unique=False)

    # SQLite doesn't support ADD CONSTRAINT via ALTER TABLE.
    # Use batch mode (copy-and-move) to add the unique constraint.
    # NULL values are excluded from unique enforcement by SQLite semantics.
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_messages_signal_event_id', ['signal_event_id'])
        batch_op.drop_column('intent_confidence')


def downgrade() -> None:
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('intent_confidence', sa.FLOAT(), nullable=True))
        batch_op.drop_constraint('uq_messages_signal_event_id', type_='unique')

    op.drop_index(op.f('ix_messages_signal_timestamp_ms'), table_name='messages')
    op.drop_index(op.f('ix_messages_signal_event_id'), table_name='messages')
    op.drop_index(op.f('ix_messages_sender_id'), table_name='messages')
    op.drop_index(op.f('ix_messages_delivery_status'), table_name='messages')
    op.drop_column('messages', 'delivery_error')
    op.drop_column('messages', 'delivery_status')
    op.drop_column('messages', 'signal_event_id')
    op.drop_column('messages', 'signal_timestamp_ms')
    op.drop_column('messages', 'sender_name')
    op.drop_column('groups', 'description')
    op.alter_column('conversations', 'user_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.drop_column('conversations', 'mode')
