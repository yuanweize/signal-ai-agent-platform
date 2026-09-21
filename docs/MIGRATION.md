# Database Migration Guide

## Overview

The project uses Alembic for schema migrations with SQLite (async via aiosqlite).  
`Base.metadata.create_all()` still runs at startup for **new installations** only.  
Existing deployments must run migrations manually.

## Migration History

| Revision | Description |
|----------|-------------|
| `a0c4522143d4` | Add `conversations.mode`, `groups.description`, `messages.sender_name`, `signal_timestamp_ms`, `signal_event_id`, `delivery_status`, `delivery_error` |
| `397929583aa5` | Apply `UNIQUE(signal_event_id)` constraint on messages via batch mode; drop legacy `intent_confidence` |

## Applying Migrations

### Docker (production)

```bash
docker compose exec backend alembic upgrade head
```

### Local development

```bash
cd backend
DATABASE_URL="sqlite+aiosqlite:////path/to/data/bot.db" alembic upgrade head
```

### Check current version

```bash
alembic current
```

## Migrating an Existing Database

If you have a pre-migration database (before this audit), the migration will:

1. **Preserve** all existing `users`, `conversations`, `messages`, `groups`, `products`, `bot_config`, `audit_logs`, `campaign_delivery_logs`
2. **Add** new nullable columns with safe defaults (`mode = 'auto'`, `sender_name = NULL`, etc.)
3. **Not drop** any existing data
4. **Remove** only `intent_confidence` (was never populated by the application)

### Before migrating a production database

```bash
# Backup first
cp data/bot.db data/bot.db.backup.$(date +%Y%m%d_%H%M%S)

# Run migration
alembic upgrade head

# Verify
alembic current
```

## Fresh Install

Fresh installs run through `create_all()` at startup, then you should stamp at head:

```bash
alembic stamp head
```

Or just run `alembic upgrade head` (no-op if already at head).

## Rollback

```bash
alembic downgrade -1
```

To rollback to a specific revision:

```bash
alembic downgrade a0c4522143d4
```

## Known Limitations

- SQLite does not support all ALTER TABLE operations. Migrations use `batch_alter_table` for constraint changes.
- The `UNIQUE(signal_event_id)` constraint only enforces uniqueness on non-NULL values (SQLite semantics). This is correct behavior — legacy messages have NULL `signal_event_id`.
