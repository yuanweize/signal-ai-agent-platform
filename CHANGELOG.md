# Changelog

All notable changes to this project will be documented in this file.

## [v0.4.1] - 2026-09-23

### AI Studio Product Completion & Observability (v0.4.1 Release)

#### Highlights
- **Truthful Runtime Observability**: Eliminated all mock metrics, decorative zeroes, and hardcoded 'Enterprise Production' badges. AI Studio operational telemetry and readiness badges are strictly derived from live component health checks, database diagnostics, and execution records.
- **Provider-Neutral Token Telemetry**: Added exact usage breakdowns (`input_tokens`, `output_tokens`, `total_tokens`, `cached_input_tokens`, `reasoning_tokens`) across LLM providers, graph orchestration nodes, and persisted traces (`ai_runs` and `ai_model_calls`). Removed synthetic `len // 4` token estimates.
- **Truthful Pricing Engine**: Realistic cost calculation with provider-neutral pricing matrices and graceful fallback to `None` for unconfigured custom models (preventing misleading zero-cost figures).
- **Responsive 4-Group Information Architecture**: Reorganized AI Studio console into **Operate** (Overview, Runs & Traces, Diagnostics), **Knowledge** (RAG Knowledge, Scoped Memory, Progressive Skills), **Automation** (Tools & MCP Governance), and **Improve** (Learning Loop, Prompt Versions, Evaluation Suite).
- **Runs & Traces Explorer**: Comprehensive execution tracing with decision filtering, error filtering, RAG/tool usage filters, pagination, and slide-over execution inspector with per-model-call execution traces and citations.
- **Interactive Provider Diagnostics**: Real-time component health checks and live provider probes measuring latency, tool calling, embeddings, response preview, and token telemetry with zero mock responses.
- **RAG Vector Search Playground & Scoped Memory**: Interactive vector search testing and memory management supporting scoped isolation across user, group, and global contexts.
- **Learning Loop & Fine-Tuning Pipeline**: Safe promotion of learning candidates into knowledge sources (requiring explicit privacy confirmation) or exportable training datasets with JSONL download.
- **Live Evaluation Suite & Run Persistence**: Golden benchmark runner supporting deterministic contract invariants (32 cases) and live provider evaluation with case limits and evaluation history persistence.
- **Linear Migration `f3b4c5d6e7f8`**: Upgrades `ai_runs` with token breakdowns, traffic sources, and cost estimates, and creates `ai_model_calls`, `evaluation_runs`, and `evaluation_case_results`.

---

## [v0.4.0] - 2026-09-23

### AI Customer Service & Conversational Commerce Platform (v0.4.0 Final Release)

#### Highlights
- **Unified AgentRuntime**: Unified both Auto and Copilot modes on a single LangGraph-based `AgentRuntime` engine.
- **Production Runtime Factory**: Eliminates silent fallback to fake providers in production; instantiates live OpenAI-compatible LLM/Embedding adapters and Qdrant vector store.
- **Signal Zero-Env Dynamic Configuration**: Signal listener dynamically starts and stops based solely on runtime database configuration (`KEY_SIGNAL_API_URL`, `KEY_SIGNAL_PHONE_NUMBER`), requiring zero restart and zero environment variables.
- **Strict Group Privacy Invariant (P0)**: Group chat conversations are strictly forbidden from retrieving private user documents or loading private user memories.
- **Canonical Privacy Erasure (Fail-Closed)**: Purges all private user artifacts (memory items, knowledge documents, chunks, vectors, identities, and message history) mapped to canonical user ID. Fails closed and rolls back on vector deletion errors.
- **Master Encryption Key Hardening**: Persistent key stored in `./data/.master_key` with strict `0600` permissions. Automatic, transparent migration of legacy fallback ciphertext on startup.
- **Qdrant Vector Database Integration**: Native vector storage with point UUID mapping, `query_points` search, and full relational-to-vector reindexing (`/api/ai-studio/knowledge/reindex`).
- **Official Model Context Protocol (MCP) SDK Integration**: Dynamic discovery and execution of external tools over stdio sessions using the official Python `mcp` SDK.
- **Deterministic Tool Permission Governance**: Sensitive tools (e.g. refunds) trigger supervisor drafts (`draft_for_human`) rather than autonomous execution.
- **API Contract Drift Elimination**: Zero contract drift across FastAPI backend routes, OpenAPI schema, and frontend client DTOs, verified by automated HTTP integration smoke tests.
- **Human-in-the-Loop Copilot**: Inbound messages in copilot mode generate pending `AISuggestion` drafts linked to underlying `AIRun` traces for human operator review and provenance tracking.
- **Deterministic Agent Contract Evaluation**: 32-case deterministic evaluation suite covering prompt injection, human handoff, refund approval gates, multi-language support, and privacy boundaries with 100% accuracy in CI.
- **Full Quality Gates**: 109 pytest backend tests (100% pass), 18 Vitest frontend tests (100% pass), and 32 deterministic AI eval cases (100% pass).

#### Security & Privacy Hardening
- Reject user-scoped knowledge retrieval when `is_group=True`.
- Disable loading individual user memories in group contexts.
- Enforce canonical user identity mapping across telephone numbers and Signal UUIDs.
- Bound financial or destructive tool actions (e.g. refunds) behind administrative approval gates.
- Tag retrieved knowledge chunks as untrusted data context to mitigate prompt injection.
- Fail closed and rollback on vector deletion errors during privacy erasure.

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
