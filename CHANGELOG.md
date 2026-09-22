# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### AI Customer Service Platform (v0.4 Release Candidate)

#### Highlights
- **Unified AgentRuntime**: Unified both Auto and Copilot modes on a single LangGraph-based `AgentRuntime` engine.
- **Production Runtime Factory**: Eliminates silent fallback to fake providers in production; instantiates live OpenAI-compatible LLM/Embedding adapters and Qdrant vector store.
- **Strict Group Privacy Invariant (P0)**: Group chat conversations are strictly forbidden from retrieving private user documents or loading private user memories.
- **Qdrant Vector Database Integration**: Native vector storage with point UUID mapping, `query_points` search, and full relational-to-vector reindexing (`/api/ai-studio/knowledge/reindex`).
- **Official Model Context Protocol (MCP) SDK Integration**: Dynamic discovery and execution of external tools over stdio sessions using the official Python `mcp` SDK.
- **Human-in-the-Loop Copilot**: Inbound messages in copilot mode generate pending `AISuggestion` drafts linked to underlying `AIRun` traces for human operator review and provenance tracking.
- **Deterministic Agent Contract Evaluation**: 32-case deterministic evaluation suite covering prompt injection, human handoff, refund approval gates, multi-language support, and privacy boundaries with 100% accuracy in CI.
- **No Hardcoded Metrics**: Dynamic RAG hit rate calculation from persisted `AIRun` records and real-time observability diagnostics endpoint (`GET /api/ai-studio/diagnostics`).
- **Linear Alembic Revision Chain**: Single linear migration chain from `<base>` to `e1f2a3b4c5d6` (head).

#### Security & Privacy Hardening
- Reject user-scoped knowledge retrieval when `is_group=True`.
- Disable loading individual user memories in group contexts.
- Enforce canonical user identity mapping across telephone numbers and Signal UUIDs.
- Bound financial or destructive tool actions (e.g. refunds) behind administrative approval gates.
- Tag retrieved knowledge chunks as untrusted data context to mitigate prompt injection.

---

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
