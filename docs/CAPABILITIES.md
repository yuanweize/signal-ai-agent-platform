# Capability & Reality Matrix — Signal Market Bot v0.4

This document defines the verified reality status of all capabilities in the repository. Status definitions:
- **`VERIFIED`**: Implemented in production code, backed by automated unit, integration, or regression tests.
- **`PARTIAL`**: Core path functional; edge cases or extended configurations in progress.
- **`MOCK_ONLY`**: Implemented only for mock/testing environments.
- **`BLOCKED_EXTERNAL`**: Dependent on live external network services or third-party gateways.

---

## Capabilities Matrix

| Subsystem | Feature | Status | Runtime Code Path | Test Evidence |
|---|---|---|---|---|
| **Messaging Core** | Signal Webhook Ingestion | `VERIFIED` | `app/api/signal.py` | `test_message_pipeline.py` |
| **Messaging Core** | Deduplication & Message Ordering | `VERIFIED` | `app/services/message_handler.py` | `test_deduplication` in test suite |
| **Messaging Core** | Manual Mode Race Protection | `VERIFIED` | `app/services/message_handler.py` | `test_ai_outbound_discarded_if_admin_switches_manual` |
| **AI Runtime** | Unified AgentRuntime | `VERIFIED` | `app/ai/runtime/agent_runtime.py` | `test_auto_mode_uses_agent_runtime` |
| **AI Runtime** | Runtime Factory (No Silent Fake) | `VERIFIED` | `app/ai/runtime/factory.py` | `test_production_runtime_does_not_use_fake_providers` |
| **Copilot** | Suggestion Generation & Review | `VERIFIED` | `app/api/conversations.py` | `test_copilot_mode_uses_same_agent_runtime` |
| **RAG** | Scope-Isolated Retrieval | `VERIFIED` | `app/ai/rag/retrieval.py` | `test_group_cannot_retrieve_user_rag` |
| **RAG** | Qdrant Vector Store Adapter | `VERIFIED` | `app/ai/rag/qdrant_store.py` | `test_real_qdrant_adapter_roundtrip` |
| **RAG** | Full Reindexing Pipeline | `VERIFIED` | `app/ai/rag/ingestion.py` | `test_reindex_pipeline` |
| **Memory** | Canonical User Scoped Memory | `VERIFIED` | `app/ai/memory/providers.py` | `test_same_user_phone_uuid_share_memory` |
| **Memory** | Group Private Memory Isolation | `VERIFIED` | `app/ai/runtime/agent_runtime.py` | `test_group_prompt_contains_no_private_user_memory` |
| **Skills** | Progressive Skill Loading | `VERIFIED` | `app/ai/skills/registry.py` | `test_ai_platform.py` |
| **Tools** | Permission Governance Gates | `VERIFIED` | `app/ai/tools/registry.py` | `test_mcp_write_requires_approval` |
| **MCP** | Stdio SDK Discovery & Execution | `VERIFIED` | `app/ai/mcp/client.py` | `test_real_mcp_sdk_discovery_and_call` |
| **Observability**| Live Diagnostics Endpoint | `VERIFIED` | `app/api/ai_studio.py` | `test_ai_dashboard_has_no_hardcoded_metrics` |
| **Observability**| Dynamic Hit Rate & Metrics | `VERIFIED` | `app/api/ai_studio.py` | `test_ai_dashboard_has_no_hardcoded_metrics` |
| **Database** | Linear Alembic Migrations | `VERIFIED` | `alembic/versions/` | Migration verification script (fresh, legacy, v0.3→v0.4) |
| **Evaluation** | Deterministic Contract Suite (32 cases)| `VERIFIED` | `evals/run_evals.py` | 100% pass rate in CI runner |
| **Evaluation** | Live External Model Evaluation | `BLOCKED_EXTERNAL`| `evals/live_eval.py` | Requires external paid LLM API keys |
| **Signal Network** | Live Hardware Signal Delivery | `BLOCKED_EXTERNAL`| `app/services/signal_client.py` | Documented in `REAL_SIGNAL_VALIDATION.md` |
