# Changelog

All notable changes to this project will be documented in this file.

## [v0.3.0] - 2026-09-21

### Highlights
- **Admin Inbox**: Modern dual-pane support inbox replacing legacy chat logs, with real-time optimistic messaging, search, filters, unread counters, and responsive mobile navigation.
- **Signal Event Ingestion Pipeline**: Bounded in-memory event queue with backpressure, partition-based concurrent worker pool, and thread-safe deduplication.
- **Conversation-Based Architecture**: Unified `Conversation` model distinguishing direct messages and group chats with dedicated `GroupMember` mappings and Signal UUID/E164 identity resolution.
- **Reliable Outbound Delivery**: Formal delivery state machine (`pending` -> `sent` / `failed` -> `delivered` -> `read`) with explicit operator retry and audit logging.
- **Attachments & Reactions**: Full persistence and display support for media attachments and emoji reactions.
- **Manual Takeover Protection**: Concurrency double-check on conversation mode (`auto`, `manual`, `paused`) before AI gateway dispatch to prevent AI replies racing with human operators.
- **Alembic Migration Hardening**: SQLite `batch_alter_table` schema migrations with automated regression tests covering fresh installs and legacy database upgrades.
- **Comprehensive Quality Gates**: Frontend Vitest component test suite, typed backend pytest test suite, and automated Docker build validation in CI.

### Reliability & Fixes
- Fixed AI/manual takeover race by verifying conversation state right before outbound AI dispatch.
- Fixed duplicate inbound message handling with LRU deduplication cache and DB unique constraints.
- Decoupled LLM latency from Signal listener through asynchronous event pipeline processing.
- Resolved SQLite migration compatibility issues with Alembic batch mode operations.
- Added responsive drawer and collapsible dual-pane view for mobile viewports.

### Known Limitations
- Orders and Payments remain model-only skeletons.
- Automated campaign cron scheduling is not implemented.
- Automatic AI conversation summarization is not implemented.
- End-to-end Signal messaging validation requires an external Signal gateway and registered account.

### Upgrade Instructions
1. Backup your existing database:
   ```bash
   cp data/bot.db data/bot.db.bak
   ```
2. Pull latest code or container images:
   ```bash
   docker compose pull
   # or rebuild locally
   docker compose build
   ```
3. Run Alembic migrations:
   ```bash
   alembic -c backend/alembic.ini upgrade head
   ```
4. Restart services:
   ```bash
   docker compose up -d
   ```
