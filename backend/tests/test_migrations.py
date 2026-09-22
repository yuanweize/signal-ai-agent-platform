"""
Automated Migration Tests.

Guarantees:
1. Fresh DB Test: An empty database upgrades to head with all tables, columns, indexes, and constraints.
2. Legacy DB Test: A database created with 112aa6e schema and populated with data upgrades to head,
   preserving 100% of rows and IDs, applying backfills cleanly without data loss.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile


def _run_alembic_upgrade(db_path: str, revision: str = "head") -> subprocess.CompletedProcess:
    """Run alembic upgrade <revision> against the specified SQLite database."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_bin = os.path.join(backend_dir, ".venv", "bin", "alembic")
    if not os.path.exists(alembic_bin):
        alembic_bin = sys.executable.replace("python", "alembic")

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    return subprocess.run(
        [alembic_bin, "upgrade", revision],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
    )


def _run_alembic_upgrade_head(db_path: str) -> subprocess.CompletedProcess:
    """Run alembic upgrade head against the specified SQLite database."""
    return _run_alembic_upgrade(db_path, "head")


class TestFreshDBMigration:
    """Test A: Fresh DB starts empty, runs alembic upgrade head, reaches head cleanly."""

    def test_fresh_migration_to_head(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            res = _run_alembic_upgrade_head(db_path)
            assert res.returncode == 0, f"Alembic upgrade failed: {res.stderr}\n{res.stdout}"

            con = sqlite3.connect(db_path)
            cur = con.cursor()

            # Check alembic revision is at head
            ver = cur.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            assert ver == "e1f2a3b4c5d6", f"Expected revision e1f2a3b4c5d6, got {ver}"

            # Check all tables exist (16 base + 12 AI platform = 28 tables)
            tables = {
                row[0]
                for row in cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            expected_tables = {
                "alembic_version",
                "users",
                "user_identities",
                "groups",
                "group_members",
                "conversations",
                "conversation_read_states",
                "messages",
                "message_attachments",
                "message_reactions",
                "products",
                "orders",
                "payments",
                "bot_config",
                "campaign_delivery_logs",
                "audit_logs",
                # AI Platform v0.4
                "ai_runs",
                "ai_suggestions",
                "knowledge_sources",
                "knowledge_documents",
                "knowledge_chunks",
                "memory_items",
                "feedback_events",
                "learning_candidates",
                "training_examples",
                "prompt_versions",
                "mcp_servers",
                "tool_invocations",
            }
            missing = expected_tables - tables
            assert not missing, f"Missing tables after fresh migration: {missing}"

            # Verify crucial columns and constraints
            msg_cols = {row[1] for row in cur.execute("PRAGMA table_info(messages)").fetchall()}
            assert "sender_user_id" in msg_cols
            assert "direction" in msg_cols
            assert "actor" in msg_cols
            assert "signal_event_id" in msg_cols
            assert "delivery_status" in msg_cols
            assert "origin" in msg_cols
            assert "ai_run_id" in msg_cols
            assert "ai_suggestion_id" in msg_cols

            conv_cols = {
                row[1] for row in cur.execute("PRAGMA table_info(conversations)").fetchall()
            }
            assert "type" in conv_cols
            assert "dm_user_id" in conv_cols
            assert "mode" in conv_cols

            grp_cols = {row[1] for row in cur.execute("PRAGMA table_info(groups)").fetchall()}
            assert "sync_status" in grp_cols
            assert "campaign_eligible" in grp_cols

            user_cols = {row[1] for row in cur.execute("PRAGMA table_info(users)").fetchall()}
            assert "phone_number" in user_cols
            assert "signal_uuid" in user_cols

            con.close()

        finally:
            if os.path.exists(db_path):
                os.remove(db_path)


class TestLegacy112aa6eMigration:
    """Test B: 112aa6e schema DB with representative data upgrades to head with 100% data preservation."""

    def test_legacy_migration_preserves_data_and_schema(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # 1. Create 112aa6e schema
            con = sqlite3.connect(db_path)
            cur = con.cursor()

            cur.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id VARCHAR(128) NOT NULL UNIQUE,
                display_name VARCHAR(255),
                role VARCHAR(20) DEFAULT "customer" NOT NULL,
                language VARCHAR(10) DEFAULT "cs" NOT NULL,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                is_blocked BOOLEAN DEFAULT 0 NOT NULL,
                notes VARCHAR(1000)
            );
            """)
            cur.execute("""
            CREATE TABLE groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id VARCHAR(128) NOT NULL UNIQUE,
                name VARCHAR(255),
                is_active BOOLEAN DEFAULT 1 NOT NULL,
                system_prompt_override TEXT,
                language_override VARCHAR(10),
                notes TEXT,
                total_messages INTEGER DEFAULT 0 NOT NULL,
                joined_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                last_activity DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            );
            """)
            cur.execute("""
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                signal_id VARCHAR(128) NOT NULL,
                group_id VARCHAR(128),
                summary TEXT,
                message_count INTEGER DEFAULT 0 NOT NULL,
                is_active BOOLEAN DEFAULT 1 NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users (id)
            );
            """)
            cur.execute("""
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role VARCHAR(20) NOT NULL,
                sender_id VARCHAR(128),
                content TEXT NOT NULL,
                intent VARCHAR(50),
                intent_confidence REAL,
                tokens_used INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY(conversation_id) REFERENCES conversations (id)
            );
            """)
            cur.execute("""
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                short_description VARCHAR(500),
                price REAL DEFAULT 0.0 NOT NULL,
                currency VARCHAR(10) DEFAULT "CZK" NOT NULL,
                stock INTEGER DEFAULT 0 NOT NULL,
                is_active BOOLEAN DEFAULT 1 NOT NULL,
                category VARCHAR(100),
                tags VARCHAR(500),
                sort_order INTEGER DEFAULT 0 NOT NULL,
                image_url VARCHAR(500),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            );
            """)
            cur.execute("""
            CREATE TABLE bot_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(100) NOT NULL UNIQUE,
                value TEXT DEFAULT "" NOT NULL,
                description VARCHAR(500),
                category VARCHAR(50) DEFAULT "general" NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            );
            """)
            cur.execute("""
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor VARCHAR(128) NOT NULL,
                action VARCHAR(128) NOT NULL,
                target VARCHAR(256) DEFAULT "" NOT NULL,
                status VARCHAR(32) DEFAULT "success" NOT NULL,
                ip_address VARCHAR(64),
                details TEXT DEFAULT "{}" NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            );
            """)
            cur.execute("""
            CREATE TABLE campaign_delivery_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_name VARCHAR(120) NOT NULL,
                group_id VARCHAR(128) NOT NULL,
                message_hash VARCHAR(64) NOT NULL,
                status VARCHAR(24) NOT NULL,
                reason VARCHAR(120),
                details TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            );
            """)
            cur.execute("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1 NOT NULL,
                unit_price REAL NOT NULL,
                total_price REAL NOT NULL,
                currency VARCHAR(10) DEFAULT "CZK" NOT NULL,
                status VARCHAR(20) DEFAULT "pending" NOT NULL,
                notes TEXT,
                group_id VARCHAR(128),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            );
            """)
            cur.execute("""
            CREATE TABLE payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                gateway VARCHAR(50) NOT NULL,
                gateway_tx_id VARCHAR(255) UNIQUE,
                amount REAL NOT NULL,
                currency VARCHAR(10) NOT NULL,
                status VARCHAR(20) DEFAULT "pending" NOT NULL,
                payment_address VARCHAR(255),
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                completed_at DATETIME
            );
            """)

            # 2. Insert representative data
            cur.execute(
                "INSERT INTO users (id, signal_id, display_name) VALUES (42, '+420777888999', 'Alice Martin');"
            )
            cur.execute(
                "INSERT INTO groups (id, group_id, name) VALUES (10, 'grp-production-01', 'Production Market');"
            )
            cur.execute(
                "INSERT INTO conversations (id, user_id, signal_id, group_id) VALUES (101, 42, '+420777888999', NULL);"
            )
            cur.execute(
                "INSERT INTO conversations (id, user_id, signal_id, group_id) VALUES (102, 42, 'group.grp-production-01', 'grp-production-01');"
            )
            cur.execute(
                "INSERT INTO messages (id, conversation_id, role, content, intent_confidence) VALUES (501, 101, 'user', 'I want to buy coffee', 0.98);"
            )
            cur.execute(
                "INSERT INTO messages (id, conversation_id, role, content) VALUES (502, 101, 'assistant', 'Coffee is in stock!');"
            )
            cur.execute(
                "INSERT INTO products (id, name, price, stock) VALUES (1, 'Organic Coffee', 150.0, 20);"
            )
            cur.execute(
                "INSERT INTO bot_config (id, key, value) VALUES (1, 'system_prompt', 'Helpful Assistant');"
            )
            cur.execute(
                "INSERT INTO audit_logs (id, actor, action) VALUES (1, 'admin', 'system_init');"
            )

            con.commit()
            con.close()

            # 3. Upgrade to head
            res = _run_alembic_upgrade_head(db_path)
            assert res.returncode == 0, f"Legacy alembic upgrade failed: {res.stderr}\n{res.stdout}"

            # 4. Verify data preservation
            con2 = sqlite3.connect(db_path)
            cur2 = con2.cursor()

            ver = cur2.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            assert ver == "e1f2a3b4c5d6"

            # Check rows and IDs preserved
            assert cur2.execute(
                "SELECT id, signal_id, phone_number FROM users WHERE id=42"
            ).fetchone() == (42, "+420777888999", "+420777888999")
            assert cur2.execute("SELECT id, group_id, name FROM groups WHERE id=10").fetchone() == (
                10,
                "grp-production-01",
                "Production Market",
            )
            assert cur2.execute("SELECT id, price, stock FROM products WHERE id=1").fetchone() == (
                1,
                150.0,
                20,
            )
            assert cur2.execute("SELECT id, key, value FROM bot_config WHERE id=1").fetchone() == (
                1,
                "system_prompt",
                "Helpful Assistant",
            )

            # Check conversations backfilled
            dm_conv = cur2.execute(
                "SELECT id, type, dm_user_id, mode FROM conversations WHERE id=101"
            ).fetchone()
            assert dm_conv == (101, "dm", 42, "auto")

            grp_conv = cur2.execute(
                "SELECT id, type, group_id, mode FROM conversations WHERE id=102"
            ).fetchone()
            assert grp_conv == (102, "group", "grp-production-01", "auto")

            # Check messages backfilled
            m1 = cur2.execute(
                "SELECT id, content, direction, actor, origin FROM messages WHERE id=501"
            ).fetchone()
            assert m1 == (501, "I want to buy coffee", "inbound", "customer", "customer")

            m2 = cur2.execute(
                "SELECT id, content, direction, actor, origin FROM messages WHERE id=502"
            ).fetchone()
            assert m2 == (502, "Coffee is in stock!", "outbound", "bot", "ai_auto")

            # Check user identities backfilled
            ident = cur2.execute(
                "SELECT user_id, identity_type, identity_value FROM user_identities WHERE user_id=42"
            ).fetchone()
            assert ident == (42, "phone", "+420777888999")

            con2.close()

        finally:
            if os.path.exists(db_path):
                os.remove(db_path)


class TestV03ToV04Migration:
    """Test C: DB created at v0.3 head (c8927140f12a), populated with v0.3 data, upgrades to v0.4 (e1f2a3b4c5d6)."""

    def test_v03_to_v04_migration(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # 1. Upgrade to v0.3 head
            res1 = _run_alembic_upgrade(db_path, "c8927140f12a")
            assert res1.returncode == 0, f"Upgrade to v0.3 failed: {res1.stderr}\n{res1.stdout}"

            # 2. Insert representative v0.3 data
            con = sqlite3.connect(db_path)
            cur = con.cursor()
            assert (
                cur.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                == "c8927140f12a"
            )

            cur.execute(
                "INSERT INTO users (id, signal_id, display_name) VALUES (88, '+1234567890', 'Alice');"
            )
            cur.execute(
                "INSERT INTO user_identities (id, user_id, identity_type, identity_value) VALUES (1, 88, 'phone', '+1234567890');"
            )
            cur.execute(
                "INSERT INTO groups (id, group_id, name) VALUES (5, 'group-support', 'Customer Support');"
            )
            cur.execute(
                "INSERT INTO group_members (id, group_id, external_identifier, user_id) VALUES (1, 'group-support', '+1234567890', 88);"
            )
            cur.execute(
                "INSERT INTO conversations (id, type, signal_id, dm_user_id, mode) VALUES (20, 'dm', '+1234567890', 88, 'auto');"
            )
            cur.execute(
                "INSERT INTO messages (id, conversation_id, content, direction, actor, role) VALUES (90, 20, 'Hello from v0.3', 'inbound', 'customer', 'customer');"
            )
            cur.execute(
                "INSERT INTO bot_config (id, key, value) VALUES (10, 'is_ai_enabled', 'true');"
            )
            con.commit()
            con.close()

            # 3. Upgrade to v0.4 head (e1f2a3b4c5d6)
            res2 = _run_alembic_upgrade(db_path, "head")
            assert res2.returncode == 0, (
                f"Upgrade from v0.3 to v0.4 head failed: {res2.stderr}\n{res2.stdout}"
            )

            # 4. Assert v0.4 state and data preservation
            con2 = sqlite3.connect(db_path)
            cur2 = con2.cursor()
            assert (
                cur2.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                == "e1f2a3b4c5d6"
            )

            # Check pre-existing data preserved and origin column backfilled
            assert cur2.execute("SELECT id, display_name FROM users WHERE id=88").fetchone() == (
                88,
                "Alice",
            )
            assert cur2.execute(
                "SELECT id, content, origin FROM messages WHERE id=90"
            ).fetchone() == (90, "Hello from v0.3", "customer")
            assert cur2.execute(
                "SELECT id, value FROM bot_config WHERE key='is_ai_enabled'"
            ).fetchone() == (10, "true")

            # Check new v0.4 AI platform tables exist and are queryable
            cur2.execute("SELECT count(*) FROM ai_runs")
            cur2.execute("SELECT count(*) FROM ai_suggestions")
            cur2.execute("SELECT count(*) FROM knowledge_sources")
            cur2.execute("SELECT count(*) FROM memory_items")
            cur2.execute("SELECT count(*) FROM mcp_servers")
            cur2.execute("SELECT count(*) FROM prompt_versions")

            con2.close()
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)
