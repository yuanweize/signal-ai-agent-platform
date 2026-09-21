# Signal Market Bot — Test Matrix & Quality Verification

## 1. Test Summary

| Test Domain | Framework | Count | Status | Notes |
|---|---|---|---|---|
| Backend Domain & Unit | Pytest / AsyncIO | 45 | PASS | Signal parsing, normalization, auth, user identity |
| Pipeline & Messaging Concurrency | Pytest / AsyncIO | 7 | PASS | Bounded queue, manual race, reaction/attachment, outbound |
| Roster & Group Synchronization | Pytest / AsyncIO | 2 | PASS | Signal gateway group pull, upserting `group_members` |
| Database Migration (Fresh DB) | Pytest / Alembic | 1 | PASS | Upgrades empty DB to `head` without stamp |
| Database Migration (Legacy 112aa6e) | Pytest / Alembic | 1 | PASS | Upgrades legacy snapshot to `head` preserving rows |
| Frontend Typecheck | TypeScript (`tsc -b`) | — | PASS | Strict mode, zero errors |
| Frontend Lint | ESLint 9 | — | PASS | Flat config, zero errors |
| Frontend Unit & Component | Vitest / RTL | 14 | PASS | Inbox, Devices isolation, Settings tabs, Login |
| Frontend Production Build | Vite / Rollup | — | PASS | Optimized bundle (assets + gzip) |
| Docker Compose Configuration | Docker Compose | — | PASS | Verified with `docker compose config` |

---

## 2. Backend Test Suites Breakdown

### 2.1 Messaging Pipeline (`test_round2_messaging_pipeline.py`)
- `test_bounded_queue_and_worker_dispatch`: Verifies that 10 inbound messages dispatched concurrently are processed by the worker pool through bounded queueing.
- `test_outbound_service_pending_to_sent`: Verifies that successful sends transition from `pending` to `sent` with external timestamps recorded.
- `test_outbound_service_failure_and_retry`: Verifies that failed gateway transmissions set `failed` status and store `delivery_error`, and can be retried via `retry_message`.
- `test_manual_takeover_race_condition`: Verifies that when an inbound message triggers an AI response, but an admin flips `conversation.mode` to `manual` during LLM generation, the resulting AI message is safely discarded and 0 outbound sends occur.
- `test_reaction_only_inbound_persisted`: Verifies that reaction-only Signal events are not filtered as empty text messages and are stored in `message_reactions`.
- `test_attachment_only_inbound_persisted`: Verifies that attachment-only events create an inbound `Message` record with linked `message_attachments`.
- `test_health_ready_checks_migration_head`: Verifies `/health/live` returns 200 and `/health/ready` returns 503 if migrations are not at `head`.

### 2.2 Conversations & Inbox API (`test_conversations_api.py`)
- `test_list_conversations_with_filters`: Tests `/conversations` search, type filter, mode filter, and unread counts.
- `test_get_conversation_detail_dm`: Tests loading DM conversation detail with sender identities.
- `test_get_conversation_messages_chronological_order`: Tests latest N messages returned chronologically and cursor pagination (`before_id`).
- `test_admin_send_message_via_conversation_api`: Tests admin message dispatch through OutboundMessageService.
- `test_update_conversation_mode`: Tests PATCH `/conversations/{id}/mode` toggles auto/manual/paused.
- `test_mark_conversation_read_persisted`: Tests server-side `ConversationReadState` persistence.

### 2.3 Groups Sync API (`test_groups_sync.py`)
- `test_sync_groups_from_gateway_upserts_roster`: Verifies syncing groups from Signal REST gateway persists group records, members, and admin roles.
- `test_list_group_members_endpoint`: Verifies `GET /groups/{id}/members` returns roster with admin roles.

### 2.4 Migration Tests (`test_migrations.py`)
- `test_fresh_db_migration_to_head`: Creates an empty SQLite file, runs `alembic upgrade head`, verifies all new tables (`user_identities`, `group_members`, `message_attachments`, `message_reactions`, `conversation_read_states`).
- `test_legacy_112aa6e_migration_preserves_data`: Constructs 112aa6e baseline schema, inserts seed data, runs `alembic upgrade head`, and verifies all records, users, and conversations are preserved without data loss or stamping.

---

## 3. Frontend Test Suites Breakdown

### 3.1 Inbox Suite (`src/InboxPage.test.tsx`)
- Renders conversation list with unread badges, mode badges, and display names.
- Opens conversation, loads message timeline, and marks conversation as read.
- Sends manual replies from composer with auto-scroll and optimistic display.
- Handles manual takeover mode changes (`auto` → `manual`).
- Displays outbound failure with `Retry Now` action and triggers explicit retry.

### 3.2 Devices Suite (`src/DevicesPage.test.tsx`)
- Verifies profile and device listing when both endpoints succeed.
- Tests isolated failure: when `api.getProfile()` fails, devices still load and display.
- Tests isolated failure: when `api.listDevices()` fails, profile still displays and can be saved.

### 3.3 Settings Suite (`src/SettingsPage.test.tsx`)
- Verifies general settings render properly with existing values.
- Tests tab navigation between General, Signal Gateway, AI Engine, Campaigns, Security, Retention, and Diagnostics.
- Verifies masked secrets (`signal_api_token_masked`, `ai_api_key_masked`) are rendered without revealing raw secrets.
- Tests updating and saving settings.

### 3.4 Login Suite (`src/LoginPage.test.tsx`)
- Verifies normal login flow with credentials and TOTP.
- Verifies error message display on invalid credentials.
- Verifies first-time setup form when `bootstrap_required` is true.
