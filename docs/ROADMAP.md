# Product Roadmap

## Milestone Overview

```mermaid
timeline
    title Signal AI Agent Platform Evolution
    section v0.3
        Messaging Foundation : Full Signal webhook pipeline
                             : Message deduplication & state tracking
                             : Identity resolution & group roster
    section v0.4
        AI Customer Platform : LangGraph AgentRuntime orchestration
                             : Scoped RAG with Qdrant vector store
                             : Human-in-the-loop Copilot mode
                             : Official MCP Python SDK tool discovery
                             : Group privacy invariants
    section v0.5
        Realtime & Multimodal : Server-Sent Events (SSE) live updates
                              : Inbound image & voice note comprehension
                              : Streaming LLM token delivery
    section v0.6 (Planned)
        Commerce Automation   : Native catalog synchronization
                              : Self-service Signal checkout flows
                              : ERP / CRM bi-directional webhooks
```

---

## Versions

### [v0.3.0] — Production Messaging Foundation (Released)
- Signal gateway integration via `signal-cli-rest-api`.
- Asynchronous database layer with SQLite and Alembic migrations.
- Contact synchronization, group rosters, and administrative manual takeover.

### [v0.4.0] — AI Customer Service Platform (Released)
- Unified `AgentRuntime` for both Auto and Copilot modes.
- Production adapter wiring (OpenAI-compatible LLM/Embedding, Qdrant vector store).
- Strict Group Privacy Invariant: Group contexts never leak private user notes or memories.
- Official `mcp` SDK stdio integration with administrative governance.
- Deterministic Agent Contract Evaluation Suite (32 cases, 100% decision accuracy).
- Scoped durable memory and progressive skill loading.

### [v0.4.1] — AI Studio Observability & Operations (Released)
- AI Studio unified management console (Overview, Runs, Knowledge, Memory, Skills, MCP, Learning, Prompts, Evals, Diagnostics).
- Truthful multi-source token usage & cost telemetry (`provider`, `estimated`, `unavailable`, `partial`).
- Model call tracking with latency breakdown, reasoning tokens, and failed tool attempt observability.
- MCP client lifecycle management with automatic tool unregistration upon disconnect.
- Learning curation idempotency with database-level uniqueness constraints.
- Evaluation sandbox isolation preventing customer conversation contamination.

### [v0.4.2] — Final Correctness & Production Hardening (Stable Release)
- Front/backend API contract alignment & complete DTO drift elimination.
- Atomic conditional state transitions for learning loop curation (HTTP 409 Conflict on race).
- Strict skill disabled filtering and graceful vector store unavailability degradation.
- Real execution run pagination (`X-Total-Count`) and nullable token telemetry preservation.
- CORS PATCH support and faithful MCP/lifespan `CancelledError` propagation.
- Migration `g4c5d6e7f8a9` correcting legacy `llm_call_count` heuristics.
- Production Docker Compose runtime smoke gate in CI.

### [v0.5.0] — Realtime & Multimodal Intelligence (Released)
- **Realtime SSE Architecture**: Enterprise application event broker with bounded queue backpressure (100 events/subscriber) and replay buffer (150 events). Authenticated `/api/realtime/events` endpoint with Bearer header support.
- **Streaming Copilot Drafts**: Incremental token generation with live cancellation (`POST /api/conversations/{id}/suggestion/generate-stream`). Model call telemetry tracks partial latencies and cancellation events without throwing 500 errors.
- **Multimodal Attachment Pipeline**: Inbound visual image understanding (10MB limit) and audio transcription (25MB limit, 0600 secure file hygiene). Truthful provider capability diagnostics (`LIVE_VERIFIED`, `SUPPORTED`, `UNSUPPORTED`).
- **Explainability & Provenance**: Evidence drawer surfaces attachment provenance, OCR/transcript text, and processor model breakdown under untrusted context blocks.
- **Migration `h5d6e7f8a9b0`**: Adds multimodal processing columns to `message_attachments`.

### [v0.6.0] — Commerce Automation & Integrations (Planned)
- Conversational cart management and checkout link dispatch.
- Multi-currency price catalog with automated inventory holds.
- Webhook notifications for external CRM/ERP synchronization.
