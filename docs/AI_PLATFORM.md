# AI Platform Subsystems — Signal Market Bot v0.4

## Overview

The v0.4 AI Platform upgrade modernizes Signal Market Bot into a multi-tier, verifiable, enterprise customer service architecture. This document details each AI subsystem, its code pathways, configuration contracts, and testing evidence.

---

## 1. Runtime Factory & Provider Wiring

### Production Wiring vs Testing Mode
Located in [`backend/app/ai/runtime/factory.py`](file:///Users/yuanweize/我的文档/服务器/GITHUB/signal-market-bot/backend/app/ai/runtime/factory.py):
- **`create_agent_runtime(settings, is_test=None)`**:
  - In production (`ENVIRONMENT=production`), strictly builds live adapters:
    - **LLM**: `OpenAICompatibleProvider` targeting configured `ai_api_base_url` and `ai_model`.
    - **Embedding**: `OpenAICompatibleEmbeddingProvider` targeting `embedding_base_url` and `embedding_model`.
    - **Vector Store**: `QdrantVectorStore` connecting to `qdrant_url` (with optional API key).
  - Silent fallback to `FakeLLMProvider`, `FakeEmbeddingProvider`, or `FakeVectorStore` in non-test environments is blocked by an explicit runtime assertion (`RuntimeError`).
  - Fake providers are restricted to automated testing (`ENVIRONMENT=test`).

### Database-Backed Configuration
All runtime settings are read from `bot_config` using existing encrypted database storage:
- `ai_api_base_url`, `ai_api_key`, `ai_model`, `ai_temperature`, `ai_max_tokens`
- `embedding_base_url`, `embedding_api_key`, `embedding_model`
- `vector_store_provider` (default `qdrant`), `qdrant_url`, `qdrant_api_key`
- `is_ai_enabled`

---

## 2. Knowledge Retrieval (RAG) & Qdrant

### Vector Store Architecture
Located in [`backend/app/ai/rag/qdrant_store.py`](file:///Users/yuanweize/我的文档/服务器/GITHUB/signal-market-bot/backend/app/ai/rag/qdrant_store.py):
- Uses official `AsyncQdrantClient` (`qdrant-client` 1.10+).
- Maps chunk identifiers to deterministic UUIDs (`uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id)`).
- Executes vector similarity searches using `client.query_points()`.
- Supports in-memory testing (`location=":memory:"`) as well as production container networking.

### Ingestion & Reindexing
Located in [`backend/app/ai/rag/ingestion.py`](file:///Users/yuanweize/我的文档/服务器/GITHUB/signal-market-bot/backend/app/ai/rag/ingestion.py):
- Relational documents (`KnowledgeDocument`) serve as the source of truth in SQLite/PostgreSQL.
- `reindex_document(session, document_id)`: Re-chunks and re-embeds a single document.
- `reindex_all(session)`: Reconstructs the entire vector index from the relational database.
- Endpoints: `POST /api/ai-studio/knowledge/documents/{id}/reindex` and `POST /api/ai-studio/knowledge/reindex`.

---

## 3. Scoped Durable Memory

Located in [`backend/app/ai/memory/`](file:///Users/yuanweize/我的文档/服务器/GITHUB/signal-market-bot/backend/app/ai/memory/):
- **Canonical Identity Mapping**: Memories bind to `canonical_user_id` so that contact alias, phone number, and Signal UUID map to the same namespace.
- **Group Isolation Policy**: When `context.is_group == True`, loading `scope_type="user"` memory is completely disabled. Group context is never tainted with individual private memories.
- **Safe Extraction**: Only durable preferences and stable facts (e.g. language, dietary choices) are auto-extracted. Sensitive tokens, credentials, and ephemeral chatter are excluded.

---

## 4. Skills & Tool Planning

Located in [`backend/app/ai/skills/`](file:///Users/yuanweize/我的文档/服务器/GITHUB/signal-market-bot/backend/app/ai/skills/) and [`backend/app/ai/tools/`](file:///Users/yuanweize/我的文档/服务器/GITHUB/signal-market-bot/backend/app/ai/tools/):
- **Progressive Skill Loading**: Only skills activated by routing (e.g. `product-sales`, `complaints`, `human-handoff`) have their instruction bodies injected into the system prompt.
- **Real Tool Execution**: Tools are registered in `ToolRegistry` and executed with validated conversation arguments. Hardcoded dummy arguments (e.g. dummy order IDs) are strictly eliminated.
- **Administrative Tool Governance**:
  - `read_only`: Permitted for automatic execution (e.g. `search_products`).
  - `requires_approval`: Actions requiring human review (e.g. `trigger_sample_refund`) generate a Copilot draft (`draft_for_human`) rather than executing autonomously.

---

## 5. Model Context Protocol (MCP) Integration

Located in [`backend/app/ai/mcp/client.py`](file:///Users/yuanweize/我的文档/服务器/GITHUB/signal-market-bot/backend/app/ai/mcp/client.py):
- Uses the official `mcp` Python SDK 2.x stdio client (`mcp.client.stdio.stdio_client` and `ClientSession`).
- Connects to external tool servers over standard I/O with timeout management.
- Dynamic tool discovery maps remote MCP tools directly into `tool_registry`.
- Governed under the same administrative approval policy as native tools.

---

## 6. Observability, Tracing & Diagnostics

Located in [`backend/app/ai/observability/`](file:///Users/yuanweize/我的文档/服务器/GITHUB/signal-market-bot/backend/app/ai/observability/):
- **Trace Persistence**: Every AI interaction logs an `AIRun` record capturing requested model, effective provider, prompt version, retrieved chunks, memories, tool calls, decision reason, tokens, and latency.
- **No Hardcoded Metrics**: Dashboard metrics (such as RAG hit rate) are dynamically computed from stored traces. If no traces exist, `null` is returned rather than misleading hardcoded numbers.
- **Diagnostics API**: `GET /api/ai-studio/diagnostics` reports live observable status (`configured`, `connected`, `degraded`, `disabled`) for LLM, Embedding, Qdrant, MCP, and Signal Gateway.
