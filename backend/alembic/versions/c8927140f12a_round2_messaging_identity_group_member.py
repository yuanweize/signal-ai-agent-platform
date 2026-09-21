"""round2_messaging_identity_group_member

Revision ID: c8927140f12a
Revises: 397929583aa5
Create Date: 2026-09-21 22:30:00.000000

Round 2 schema enhancements:
- user_identities (multi-identifier support: phone, uuid, alias)
- group_members (tracks group membership, roles, admin status)
- message_attachments (persists inbound and outbound attachment metadata)
- message_reactions (persists inbound and outbound reactions)
- conversation_read_states (server-side persistent unread tracking)
- groups: sync_status, sync_error, last_synced_at, campaign_eligible
- conversations: type ('dm' | 'group'), dm_user_id, last_message_at
- users: phone_number, signal_uuid
- messages: sender_user_id, direction, actor, occurred_at, reply_to_id
- data backfill for existing rows
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c8927140f12a'
down_revision: Union[str, None] = '397929583aa5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1. user_identities
    if "user_identities" not in existing_tables:
        op.create_table(
            "user_identities",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("identity_type", sa.String(length=20), nullable=False),  # 'phone', 'uuid', 'alias'
            sa.Column("identity_value", sa.String(length=128), nullable=False),
            sa.Column("first_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])
        op.create_index("ix_user_identities_type_value", "user_identities", ["identity_type", "identity_value"], unique=True)

    # 2. group_members
    if "group_members" not in existing_tables:
        op.create_table(
            "group_members",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("external_identifier", sa.String(length=128), nullable=False),
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("role", sa.String(length=20), nullable=False, server_default="member"),
            sa.Column("first_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_group_members_group_id", "group_members", ["group_id"])
        op.create_index("ix_group_members_user_id", "group_members", ["user_id"])
        op.create_index("ix_group_members_external_identifier", "group_members", ["external_identifier"])
        op.create_index("ix_group_members_unique_member", "group_members", ["group_id", "external_identifier"], unique=True)

    # 3. message_attachments
    if "message_attachments" not in existing_tables:
        op.create_table(
            "message_attachments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
            sa.Column("external_attachment_id", sa.String(length=128), nullable=True),
            sa.Column("filename", sa.String(length=255), nullable=True),
            sa.Column("mime_type", sa.String(length=128), nullable=True),
            sa.Column("size", sa.Integer(), nullable=True),
            sa.Column("file_path", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_message_attachments_message_id", "message_attachments", ["message_id"])

    # 4. message_reactions
    if "message_reactions" not in existing_tables:
        op.create_table(
            "message_reactions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
            sa.Column("emoji", sa.String(length=32), nullable=False),
            sa.Column("reactor_identity", sa.String(length=128), nullable=False),
            sa.Column("reactor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("target_author", sa.String(length=128), nullable=True),
            sa.Column("target_timestamp", sa.BigInteger(), nullable=True),
            sa.Column("is_removed", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("occurred_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_message_reactions_message_id", "message_reactions", ["message_id"])
        op.create_index("ix_message_reactions_reactor", "message_reactions", ["reactor_identity"])

    # 5. conversation_read_states
    if "conversation_read_states" not in existing_tables:
        op.create_table(
            "conversation_read_states",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("admin_identity", sa.String(length=128), nullable=False, server_default="admin"),
            sa.Column("last_read_message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
            sa.Column("last_read_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_conv_read_states_conv_admin", "conversation_read_states", ["conversation_id", "admin_identity"], unique=True)

    # 6. Alter groups
    group_cols = [c["name"] for c in inspector.get_columns("groups")]
    if "sync_status" not in group_cols:
        op.add_column("groups", sa.Column("sync_status", sa.String(length=20), nullable=False, server_default="not_synced"))
    if "sync_error" not in group_cols:
        op.add_column("groups", sa.Column("sync_error", sa.Text(), nullable=True))
    if "last_synced_at" not in group_cols:
        op.add_column("groups", sa.Column("last_synced_at", sa.DateTime(), nullable=True))
    if "campaign_eligible" not in group_cols:
        op.add_column("groups", sa.Column("campaign_eligible", sa.Boolean(), nullable=False, server_default="1"))

    # 7. Alter conversations
    conv_cols = [c["name"] for c in inspector.get_columns("conversations")]
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        if "type" not in conv_cols:
            batch_op.add_column(sa.Column("type", sa.String(length=20), nullable=False, server_default="dm"))
        if "dm_user_id" not in conv_cols:
            batch_op.add_column(sa.Column("dm_user_id", sa.Integer(), sa.ForeignKey("users.id", name="fk_conversations_dm_user_id"), nullable=True))
        if "last_message_at" not in conv_cols:
            batch_op.add_column(sa.Column("last_message_at", sa.DateTime(), nullable=True))

    conv_indexes = [idx["name"] for idx in inspector.get_indexes("conversations")]
    if "ix_conversations_type" not in conv_indexes:
        op.create_index("ix_conversations_type", "conversations", ["type"])
    if "ix_conversations_dm_user_id" not in conv_indexes:
        op.create_index("ix_conversations_dm_user_id", "conversations", ["dm_user_id"])

    # 8. Alter users
    user_cols = [c["name"] for c in inspector.get_columns("users")]
    if "phone_number" not in user_cols:
        op.add_column("users", sa.Column("phone_number", sa.String(length=64), nullable=True))
    if "signal_uuid" not in user_cols:
        op.add_column("users", sa.Column("signal_uuid", sa.String(length=64), nullable=True))
    user_indexes = [idx["name"] for idx in inspector.get_indexes("users")]
    if "ix_users_phone_number" not in user_indexes:
        op.create_index("ix_users_phone_number", "users", ["phone_number"])
    if "ix_users_signal_uuid" not in user_indexes:
        op.create_index("ix_users_signal_uuid", "users", ["signal_uuid"])

    # 9. Alter messages
    msg_cols = [c["name"] for c in inspector.get_columns("messages")]
    with op.batch_alter_table("messages", schema=None) as batch_op:
        if "sender_user_id" not in msg_cols:
            batch_op.add_column(sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("users.id", name="fk_messages_sender_user_id"), nullable=True))
        if "direction" not in msg_cols:
            batch_op.add_column(sa.Column("direction", sa.String(length=20), nullable=False, server_default="inbound"))
        if "actor" not in msg_cols:
            batch_op.add_column(sa.Column("actor", sa.String(length=20), nullable=False, server_default="customer"))
        if "occurred_at" not in msg_cols:
            batch_op.add_column(sa.Column("occurred_at", sa.DateTime(), nullable=True))
        if "reply_to_id" not in msg_cols:
            batch_op.add_column(sa.Column("reply_to_id", sa.Integer(), sa.ForeignKey("messages.id", name="fk_messages_reply_to_id"), nullable=True))

    msg_indexes = [idx["name"] for idx in inspector.get_indexes("messages")]
    if "ix_messages_direction" not in msg_indexes:
        op.create_index("ix_messages_direction", "messages", ["direction"])
    if "ix_messages_actor" not in msg_indexes:
        op.create_index("ix_messages_actor", "messages", ["actor"])
    if "ix_messages_sender_user_id" not in msg_indexes:
        op.create_index("ix_messages_sender_user_id", "messages", ["sender_user_id"])


    # 10. Data backfill / migrations
    # 10.1 Backfill user identities and phone_number from signal_id
    op.execute("""
        INSERT OR IGNORE INTO user_identities (user_id, identity_type, identity_value, first_seen_at, last_seen_at)
        SELECT id, 
               CASE WHEN signal_id LIKE '+%' THEN 'phone' ELSE 'uuid' END,
               signal_id,
               first_seen,
               last_seen
        FROM users
    """)
    op.execute("""
        UPDATE users
        SET phone_number = signal_id
        WHERE signal_id LIKE '+%' AND phone_number IS NULL
    """)
    op.execute("""
        UPDATE users
        SET signal_uuid = signal_id
        WHERE NOT (signal_id LIKE '+%') AND signal_uuid IS NULL
    """)

    # 10.2 Backfill conversation types & dm_user_id
    op.execute("""
        UPDATE conversations
        SET type = 'group'
        WHERE group_id IS NOT NULL
    """)
    op.execute("""
        UPDATE conversations
        SET type = 'dm', dm_user_id = user_id
        WHERE group_id IS NULL
    """)

    # 10.3 Backfill messages direction, actor, occurred_at
    op.execute("""
        UPDATE messages
        SET direction = 'outbound', actor = 'bot'
        WHERE role != 'user'
    """)
    op.execute("""
        UPDATE messages
        SET occurred_at = timestamp
        WHERE occurred_at IS NULL
    """)


def downgrade() -> None:
    op.drop_table("conversation_read_states")
    op.drop_table("message_reactions")
    op.drop_table("message_attachments")
    op.drop_table("group_members")
    op.drop_table("user_identities")

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_column("reply_to_id")
        batch_op.drop_column("occurred_at")
        batch_op.drop_column("actor")
        batch_op.drop_column("direction")
        batch_op.drop_column("sender_user_id")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("signal_uuid")
        batch_op.drop_column("phone_number")

    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.drop_column("last_message_at")
        batch_op.drop_column("dm_user_id")
        batch_op.drop_column("type")

    with op.batch_alter_table("groups", schema=None) as batch_op:
        batch_op.drop_column("campaign_eligible")
        batch_op.drop_column("last_synced_at")
        batch_op.drop_column("sync_error")
        batch_op.drop_column("sync_status")
