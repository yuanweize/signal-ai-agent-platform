# Signal Market Bot — Full Engineering Audit Report

> Audit date: 2025-07  
> Auditor: Principal/Staff Full-Stack Engineer (automated)  
> Branch: `refactor/full-system-audit` based on `main` HEAD `112aa6e`

---

## Executive Summary

The project is a Signal sales/marketing bot with a FastAPI backend, React frontend, SQLite persistence, and an optional OpenAI-compatible AI engine. It can **start and run**, but has **fundamental engineering defects** across every major domain:

- No automated tests whatsoever (CI only does `python -m compileall` and `npm run build`)
- No Alembic migrations — schema managed entirely by `create_all()` which silently diverges on updates
- Manual takeover is UI-only; no persisted `mode` field on Conversation — AI can still reply after admin clicks "takeover"
- `is_blocked` flag on User is stored but never checked in the inbound message pipeline
- AI context builder loads last N messages from DB **then appends the current user message a second time** — current input is duplicated
- Group conversation is attached to `Conversation.user_id` of the **first sender** — all group activity rolls up to that one user
- `Signal.test_connection` calls `GET /v1/receive/{number}` which **consumes pending messages** — a side-effectful health check
- Outbound message state machine is broken: bot reply is written to DB **before** gateway send; if send fails the DB record shows as delivered
- Frontend API client retries **all** 5xx failures including `POST /send`, risking duplicate sends
- CORS is `allow_origins=["*"]` — production wildcard with `allow_credentials=True`
- No deduplication on inbound messages — restart/reconnect replays produce duplicate DB records
- `quiet_hours` check uses `datetime.now().hour` — container local time, not a configured timezone
- No unique constraint on `(conversation_id, signal_timestamp)` for messages
- `last_tokens_used` is an instance variable on the singleton `AIEngine` — concurrent requests race on this field
- `GroupResponse` schema includes `description` and `created_at`/`updated_at` but `Group` model has no `description` column → runtime AttributeError on first call
- Frontend `DevicesPage` calls `/api/account/profile` (GET) but that route does not exist — only PUT exists
- Frontend `api.getProfile()` calls `/api/account/profile` (GET) — 404 on every devices page load
- No pagination on conversation messages sidebar load — loads all messages in one query
- Campaign broadcast runs synchronously in a single HTTP request — blocks for every group send

---

## P0 Findings (Must Fix Before Any Claim of Working)

| ID | Area | Finding | Impact |
|----|------|---------|--------|
| P0-1 | AI Pipeline | Current user message appended **twice** to LLM context | AI always sees duplicate input, garbled responses |
| P0-2 | Outbound | Bot reply written to DB before gateway send; failures show as success | False delivery records |
| P0-3 | Manual Takeover | No `mode` field on Conversation; AI still fires after takeover click | Double-reply in production |
| P0-4 | Block User | `is_blocked` never checked in `MessageHandler.handle()` | Blocked users still get AI replies |
| P0-5 | Group Attribution | Group conversations linked to `user_id` of first sender | All group stats attributed to one user |
| P0-6 | Inbound Dedup | No idempotency key on messages; reconnect re-processes same events | Duplicate messages in DB |
| P0-7 | Signal Health Check | `test_connection` calls receive endpoint, consuming real messages | Silent data loss on every "Test Connection" click |
| P0-8 | Schema Mismatch | `GroupResponse` references `group.description` and timestamps that don't exist on `Group` model | Runtime 500 on `/api/groups` |
| P0-9 | Missing Route | GET `/api/account/profile` does not exist; DevicesPage always 404 | Devices page broken |
| P0-10 | DB Migrations | No Alembic migration files; `create_all()` at startup diverges silently | Schema drift, no upgrade path |
| P0-11 | CORS | `allow_origins=["*"]` + `allow_credentials=True` is insecure | XSS + CSRF risk in production |
| P0-12 | API Client Retry | `retryCount=2` retries all methods including POST send | Potential duplicate sends |
| P0-13 | Concurrent AI State | `self._last_tokens_used` on singleton AIEngine races under concurrent requests | Token tracking wrong |

## P1 Findings (Must Fix For Reliable Operation)

| ID | Area | Finding |
|----|------|---------|
| P1-1 | Quiet Hours | Uses `datetime.now().hour` — no timezone awareness |
| P1-2 | Signal Reactions | `send_reaction` sends wrong body (has `emoji` but swagger requires `reaction`) |
| P1-3 | Signal Reactions | `remove_reaction` sends query params but swagger requires body JSON |
| P1-4 | Signal Remote Delete | `delete_message` sends query params but swagger requires body JSON with `recipient`+`timestamp` |
| P1-5 | Signal Typing Hide | `hide_typing` sends `recipient` as query param but swagger requires body JSON |
| P1-6 | Signal Receipt | `send_read_receipt` sends `target_author` but swagger requires `recipient` |
| P1-7 | Group Response | Missing `description` field in `Group` model; API returns 500 |
| P1-8 | Group Sync | Creating group via API doesn't upsert local Group record |
| P1-9 | Conversation Mode | Manual takeover has no backend state persistence |
| P1-10 | User Activity | `get_user_activity` queries messages by `conversation.user_id` — misses group messages |
| P1-11 | CI | CI only compiles code; no pytest, no type check — CI green = nothing |
| P1-12 | JWT | JWT algorithm is `HS256` but `python-jose` default has known CVEs; should enforce `algorithms=` on decode |
| P1-13 | Token Leakage | `ai_api_key` was stored in plaintext as `KEY_AI_API_KEY` before encryption added; migration leaves plaintext in DB |
| P1-14 | AI Group Context | Group messages don't include sender name in AI context — AI doesn't know who said what |
| P1-15 | Frontend Retry | `retryCount=2` default applies to all methods, not just GET |

## P2 Findings (Important But Not Blocking Core Function)

| ID | Area | Finding |
|----|------|---------|
| P2-1 | Payment | `Order.unit_price` and `total_price` use Python `Float` — precision loss on currency |
| P2-2 | Campaign | Synchronous HTTP broadcast blocks for N groups in one request |
| P2-3 | Group Model | No `GroupMember` table — can't track per-member attribution |
| P2-4 | Conversation | `signal_id` on Conversation is the sender_id of first message — meaningless for groups |
| P2-5 | Message | No `signal_timestamp` (milliseconds) stored — can't construct valid reactions/deletes from UI |
| P2-6 | Health | `/health` always returns `"status": "ok"` even if DB is down |
| P2-7 | Retention | `cleanup_expired_data` deletes messages but doesn't update conversation `message_count` |
| P2-8 | AI | Conversation `summary` column exists but nothing ever writes to it |
| P2-9 | Frontend | `ChatLogsPage` unread tracking based on `message_count` delta — not real read state |
| P2-10 | Security | `settings.jwt_secret_key` defaults to empty string — no entropy on fresh install |

## P3 Findings (Nice-to-Have / Technical Debt)

- No pagination on dashboard stats queries — O(N) full table scans
- `Group.total_messages` counter can drift (updated in handler but not on manual send)
- ESLint config missing in frontend — `npm run lint` likely fails
- No `Vitest` or any frontend unit tests
- `simulate.py` in backend root — dev tool not cleaned up

---

## Feature Reality Matrix

| Feature | README Claims | Backend DB | Backend API | Frontend UI | Signal Gateway | Tests | Status |
|---------|--------------|-----------|-------------|------------|----------------|-------|--------|
| Bootstrap/Login | ✓ | ✓ | ✓ | ✓ | N/A | ✗ | WORKING |
| JWT Auth | ✓ | ✓ | ✓ | ✓ | N/A | ✗ | WORKING |
| TOTP 2FA | ✓ | ✓ | ✓ | ✓ | N/A | ✗ | WORKING |
| Signal connection | ✓ | N/A | ✓ | ✓ | **BROKEN** (health check consumes msgs) | ✗ | BROKEN |
| Signal receive (WS) | ✓ | N/A | ✓ | N/A | ✓ | ✗ | PARTIAL |
| Signal send | ✓ | N/A | ✓ | ✓ | ✓ | ✗ | PARTIAL (no state machine) |
| Contacts | ✓ | ✗ | ✓ | ✗ | ✓ | ✗ | BACKEND_ONLY |
| Devices | ✓ | ✗ | ✓ (partial) | ✓ | ✓ | ✗ | BROKEN (no GET profile) |
| Groups list | ✓ | ✓ | **BROKEN** (schema error) | ✓ | ✓ | ✗ | BROKEN |
| Group members | ✓ | ✗ | ✓ | ✗ | ✓ | ✗ | BACKEND_ONLY |
| Group admins | ✓ | ✗ | ✓ | ✗ | ✓ | ✗ | BACKEND_ONLY |
| DM chats | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | PARTIAL |
| Group chats | ✓ | **BROKEN** (wrong attribution) | ✓ | ✓ | ✓ | ✗ | BROKEN |
| Chat history | ✓ | ✓ | ✓ | ✓ | N/A | ✗ | PARTIAL |
| Read receipts | ✓ | ✗ | ✓ | ✗ | **BROKEN** (wrong field) | ✗ | BROKEN |
| Typing indicators | ✓ | ✗ | ✓ | ✗ | **BROKEN** (hide uses wrong method) | ✗ | BROKEN |
| Attachments | ✗ | ✗ | PARTIAL | ✗ | ✓ | ✗ | PARTIAL |
| Reactions | ✗ | ✗ | **BROKEN** (wrong body) | ✗ | N/A | ✗ | BROKEN |
| Remote delete | ✗ | ✗ | **BROKEN** (wrong body) | ✗ | N/A | ✗ | BROKEN |
| Manual takeover | ✓ | ✗ (no mode field) | PARTIAL | PARTIAL | ✓ | ✗ | BROKEN |
| AI auto reply | ✓ | ✓ | ✓ | ✓ | N/A | ✗ | PARTIAL (dup input) |
| AI context memory | ✓ | ✓ | PARTIAL | ✗ | N/A | ✗ | PARTIAL |
| Block user | ✓ | ✓ | ✓ | ✓ | N/A | ✗ | BROKEN (not enforced) |
| Products | ✓ | ✓ | ✓ | ✓ | N/A | ✗ | WORKING |
| Orders | ✗ | ✓ | ✗ | ✗ | N/A | ✗ | MODEL_ONLY |
| Payments | ✗ | ✓ | ✗ | ✗ | N/A | ✗ | MODEL_ONLY |
| Campaign broadcast | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | PARTIAL (sync HTTP) |
| Campaign scheduling | ✗ | ✗ | ✗ | ✗ | N/A | ✗ | NOT_IMPLEMENTED |
| Dashboard | ✓ | ✓ | ✓ | ✓ | N/A | ✗ | WORKING |
| Audit logs | ✓ | ✓ | ✓ | ✓ | N/A | ✗ | WORKING |
| Data retention | ✓ | ✓ | ✓ | ✓ | N/A | ✗ | PARTIAL |
| Metrics | ✓ | N/A | ✓ | ✓ | N/A | ✗ | PARTIAL |
| Settings hot-reload | ✓ | ✓ | ✓ | ✓ | N/A | ✗ | WORKING |
| DB Migrations | ✓ | ✗ (empty versions/) | N/A | N/A | N/A | ✗ | BROKEN |
| Docker deploy | ✓ | N/A | N/A | N/A | N/A | ✗ | WORKING |
| CI/CD | ✓ | N/A | N/A | N/A | N/A | N/A | BROKEN (compile only) |
