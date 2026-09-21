"""initial_schema_112aa6e

Revision ID: 112aa6e29383
Revises: 
Create Date: 2026-09-21 22:20:00.000000

Baseline migration representing the initial 112aa6e commit schema.
Safely creates tables if they do not exist (idempotent for legacy DBs).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '112aa6e29383'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "bot_config" not in existing_tables:
        op.create_table(
            "bot_config",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("key", sa.String(length=100), nullable=False),
            sa.Column("value", sa.Text(), nullable=False, server_default=""),
            sa.Column("description", sa.String(length=500), nullable=True),
            sa.Column("category", sa.String(length=50), nullable=False, server_default="general"),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_bot_config_key", "bot_config", ["key"], unique=True)

    if "campaign_delivery_logs" not in existing_tables:
        op.create_table(
            "campaign_delivery_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("campaign_name", sa.String(length=120), nullable=False),
            sa.Column("group_id", sa.String(length=128), nullable=False),
            sa.Column("message_hash", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("reason", sa.String(length=120), nullable=True),
            sa.Column("details", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_campaign_delivery_logs_campaign_name", "campaign_delivery_logs", ["campaign_name"])
        op.create_index("ix_campaign_delivery_logs_group_id", "campaign_delivery_logs", ["group_id"])
        op.create_index("ix_campaign_delivery_logs_message_hash", "campaign_delivery_logs", ["message_hash"])
        op.create_index("ix_campaign_delivery_logs_status", "campaign_delivery_logs", ["status"])
        op.create_index("ix_campaign_delivery_logs_created_at", "campaign_delivery_logs", ["created_at"])

    if "groups" not in existing_tables:
        op.create_table(
            "groups",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("group_id", sa.String(length=128), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("system_prompt_override", sa.Text(), nullable=True),
            sa.Column("language_override", sa.String(length=10), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("total_messages", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("joined_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("last_activity", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_groups_group_id", "groups", ["group_id"], unique=True)

    if "audit_logs" not in existing_tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("actor", sa.String(length=128), nullable=False),
            sa.Column("action", sa.String(length=128), nullable=False),
            sa.Column("target", sa.String(length=256), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="success"),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("details", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_audit_logs_actor", "audit_logs", ["actor"])
        op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
        op.create_index("ix_audit_logs_ip_address", "audit_logs", ["ip_address"])
        op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    if "products" not in existing_tables:
        op.create_table(
            "products",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("short_description", sa.String(length=500), nullable=True),
            sa.Column("price", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="CZK"),
            sa.Column("stock", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("category", sa.String(length=100), nullable=True),
            sa.Column("tags", sa.String(length=500), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("image_url", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_products_name", "products", ["name"])
        op.create_index("ix_products_category", "products", ["category"])

    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("signal_id", sa.String(length=128), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=True),
            sa.Column("role", sa.String(length=20), nullable=False, server_default="customer"),
            sa.Column("language", sa.String(length=10), nullable=False, server_default="cs"),
            sa.Column("first_seen", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("last_seen", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("notes", sa.String(length=1000), nullable=True),
        )
        op.create_index("ix_users_signal_id", "users", ["signal_id"], unique=True)

    if "conversations" not in existing_tables:
        op.create_table(
            "conversations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("signal_id", sa.String(length=128), nullable=False),
            sa.Column("group_id", sa.String(length=128), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
        op.create_index("ix_conversations_signal_id", "conversations", ["signal_id"])
        op.create_index("ix_conversations_group_id", "conversations", ["group_id"])

    if "orders" not in existing_tables:
        op.create_table(
            "orders",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("unit_price", sa.Float(), nullable=False),
            sa.Column("total_price", sa.Float(), nullable=False),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="CZK"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("group_id", sa.String(length=128), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_orders_user_id", "orders", ["user_id"])
        op.create_index("ix_orders_product_id", "orders", ["product_id"])
        op.create_index("ix_orders_status", "orders", ["status"])

    if "payments" not in existing_tables:
        op.create_table(
            "payments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("gateway", sa.String(length=50), nullable=False),
            sa.Column("gateway_tx_id", sa.String(length=255), nullable=True, unique=True),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("currency", sa.String(length=10), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("payment_address", sa.String(length=255), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_payments_order_id", "payments", ["order_id"], unique=True)
        op.create_index("ix_payments_user_id", "payments", ["user_id"])
        op.create_index("ix_payments_status", "payments", ["status"])

    if "messages" not in existing_tables:
        op.create_table(
            "messages",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id"), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("sender_id", sa.String(length=128), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("intent", sa.String(length=50), nullable=True),
            sa.Column("intent_confidence", sa.Float(), nullable=True),
            sa.Column("tokens_used", sa.Integer(), nullable=True),
            sa.Column("timestamp", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
        op.create_index("ix_messages_sender_id", "messages", ["sender_id"])
        op.create_index("ix_messages_timestamp", "messages", ["timestamp"])


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("payments")
    op.drop_table("orders")
    op.drop_table("conversations")
    op.drop_table("users")
    op.drop_table("products")
    op.drop_table("audit_logs")
    op.drop_table("groups")
    op.drop_table("campaign_delivery_logs")
    op.drop_table("bot_config")
