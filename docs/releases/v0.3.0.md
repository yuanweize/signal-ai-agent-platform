# v0.3.0 — Messaging & Admin Inbox Overhaul

## Highlights

- **New Modern Admin Inbox**: Dual-pane conversation interface with real-time optimistic messaging, filter chips (All/DMs/Groups/Unread), takeover controls (Auto/Manual/Paused), details drawer, and responsive mobile layout.
- **Bounded Event Ingestion Pipeline**: In-memory queue with backpressure, partition-based concurrent worker pool, and thread-safe deduplication.
- **Unified Conversation Architecture**: Distinct DM and Group conversation handling with explicit `GroupMember` mappings and Signal UUID/E164 identity resolution.
- **Reliable Outbound Delivery**: Formal delivery state machine (`pending` -> `sent` / `failed` -> `delivered` -> `read`) with explicit admin retry and audit logging.
- **Attachments & Reactions**: Full persistence and UI presentation for media attachments and emoji reactions.
- **Manual Takeover Race Protection**: Concurrency double-check on conversation mode right before outbound AI dispatch to avoid bot replies racing human operators.
- **Safe Alembic Migrations**: SQLite `batch_alter_table` schema migrations with automated regression coverage for fresh installs and legacy upgrades.
- **Frontend & CI Quality Gates**: 14+ Vitest component tests, 54+ pytest backend suites, and automated Docker build validation.

## Reliability

- Fixed AI/manual takeover race by locking and verifying conversation state before AI invocation.
- Fixed duplicate inbound message handling with LRU deduplication cache and database unique constraints.
- Decoupled LLM latency from the Signal listener loop via asynchronous background workers.
- Added comprehensive migration regression tests for legacy schemas.

## UI / UX

- Replaced legacy Chat Logs with a responsive Admin Inbox featuring optimistic updates and failed message retries.
- Modular 7-tab Settings interface with secret masking and live test triggers.
- Fault-tolerant Devices & Profile page with graceful degradation when Signal gateway is unreachable.
- Mobile-first responsiveness tested across 1440×900, 1024×768, and 390×844 viewports.

## Known Limitations

- Orders and Payments remain model-only skeletons.
- Campaign automated cron scheduling is not implemented.
- Automatic AI conversation summarization is not implemented.
- Real Signal messaging operations depend on an external Signal CLI REST gateway and registered account.

## Upgrade

1. Backup your existing database:
   ```bash
   cp data/bot.db data/bot.db.bak
   ```
2. Pull latest code or container images:
   ```bash
   docker compose pull
   # or build locally:
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
