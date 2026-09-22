# Signal Market Bot v0.4 — Reality Audit & Verification Report

**Audit Completed**: 2026-09-22  
**Branch**: `feat/ai-platform-v0.4`  
**Auditor**: Principal AI Engineer & Staff Backend Engineer  
**Policy**: No marketing claims. Code path, dependency injection, and test evidence determine status.

---

## 1. Reality Status Matrix

| Capability | Initial Audit | Final Status | Production Wiring | Test Evidence | Notes & Verifications |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **AgentRuntime** | `MOCK_ONLY` | **`VERIFIED`** | `app/ai/runtime/factory.py` | `test_production_runtime_does_not_use_fake_providers` | Fake singleton eliminated; runtime assertion forbids FakeLLM in production; DB config drives live adapters. |
| **LLM Provider** | `PARTIAL` | **`VERIFIED`** | `OpenAICompatibleProvider` | `test_production_runtime_does_not_use_fake_providers` | Connected to `ai_api_base_url` & `ai_model`; handles timeouts and custom credentials. |
| **Copilot** | `PARTIAL` | **`VERIFIED`** | `app/api/conversations.py` | `test_copilot_mode_uses_same_agent_runtime` | Shared `AgentRuntime.run()`; generates `AISuggestion` linked to `AIRun`; admin edit/send with provenance. |
| **Auto AI** | `BROKEN` | **`VERIFIED`** | `app/services/message_handler.py` | `test_auto_mode_uses_agent_runtime` | Unified on `AgentRuntime.run()`; logs `AIRun`; manual takeover race check verified. |
| **RAG Retrieval** | `MOCK_ONLY` | **`VERIFIED`** | `app/ai/rag/retrieval.py` | `test_real_qdrant_adapter_roundtrip`, `test_group_cannot_retrieve_user_rag` | Scope filtering strictly enforces isolation; reindex pipeline rebuilds index from DB. |
| **Embedding Provider**| `MOCK_ONLY` | **`VERIFIED`** | `OpenAICompatibleEmbeddingProvider`| `test_production_runtime_does_not_use_fake_providers` | Dynamic embedding adapter configured from DB settings; degraded mode on missing keys. |
| **Qdrant Vector DB** | `MOCK_ONLY` | **`VERIFIED`** | `app/ai/rag/qdrant_store.py` | `test_real_qdrant_adapter_roundtrip` | Real Qdrant adapter with deterministic UUID mapping and `query_points` retrieval. |
| **Scoped Memory** | `BROKEN` | **`VERIFIED`** | `app/ai/memory/providers.py` | `test_same_user_phone_uuid_share_memory`, `test_group_prompt_contains_no_private_user_memory` | Tied to canonical user ID; group isolation prevents loading private memories; `delete()` returns False if missing. |
| **Progressive Skills**| `PARTIAL` | **`VERIFIED`** | `app/ai/skills/registry.py` | `evals/run_evals.py` (32 cases) | Progressive loading injects only active skill instructions into prompt; router falls back cleanly. |
| **Governed Tools** | `PARTIAL` | **`VERIFIED`** | `app/ai/tools/registry.py` | `test_mcp_write_requires_approval` | Hardcoded arguments removed; write/sensitive tools trigger `draft_for_human` supervisor review. |
| **MCP Integration** | `MOCK_ONLY` | **`VERIFIED`** | `app/ai/mcp/client.py` | `test_real_mcp_sdk_discovery_and_call` | Official `mcp` Python SDK 2.x stdio client session, dynamic discovery, and permission gating. |
| **Learning Loop** | `PARTIAL` | **`VERIFIED`** | `app/ai/learning/curation.py` | `test_ai_platform.py` | Approved/edited copilot suggestions generate `FeedbackEvent` and `LearningCandidate`. |
| **AI Evaluation** | `VERIFIED (5)`| **`VERIFIED (32)`**| `evals/run_evals.py` | 32/32 cases passing (100% accuracy) | Deterministic contract evaluation suite expanded to 32 invariants covering safety, injection, handoff, RAG. |
| **AI Studio Console** | `PARTIAL` | **`VERIFIED`** | `app/api/ai_studio.py` | `test_ai_dashboard_has_no_hardcoded_metrics` | Hardcoded hit rates removed; dynamic calculation from `AIRun`; real diagnostics endpoint added. |
| **Message Provenance**| `PARTIAL` | **`VERIFIED`** | `app/models/conversation.py` | `test_auto_mode_uses_agent_runtime`, `test_copilot_mode_uses_same_agent_runtime` | `Message.origin` (`ai_auto`, `human_ai_assisted`, `human_manual`) with `ai_run_id` linkage. |
| **Privacy Isolation** | `BROKEN` | **`VERIFIED`** | `app/ai/rag/retrieval.py` | `test_group_cannot_retrieve_user_rag`, `test_group_prompt_contains_no_private_user_memory` | P0 Invariant enforced: Group turns strictly reject user scope retrieval and user memory loading. |

---

## 2. Priority 0 / Priority 1 Remediation Log

| Issue ID | Severity | Description | Status | Verification Evidence |
|---|---|---|---|---|
| **SEC-01** | **P0** | Group chat context retrieved and leaked user private RAG notes. | **FIXED** | In `retrieval.py`, `allowed_scopes.discard("user")` when `is_group=True`. Verified by `test_group_cannot_retrieve_user_rag`. |
| **SEC-02** | **P0** | Group chat context loaded private user memory into LLM prompt. | **FIXED** | In `agent_runtime.py`, loading user memory skipped when `context.is_group=True`. Verified by `test_group_prompt_contains_no_private_user_memory`. |
| **ARCH-01** | **P0** | Production runtime defaulted to `FakeLLMProvider` singleton. | **FIXED** | Deleted global fake singleton; added `create_agent_runtime` factory reading DB config; added runtime assertion prohibiting Fake in production. |
| **ARCH-02** | **P0** | Auto AI routed to legacy `AIEngine`, while Copilot routed to `AgentRuntime`. | **FIXED** | Unified `MessageHandler` on `AgentRuntime.run()` for both Auto and Copilot; preserved manual race protection check. |
| **RAG-01** | **P0** | Production RAG used in-memory fake store instead of Qdrant. | **FIXED** | Implemented `QdrantVectorStore` with official `qdrant-client` `query_points` and UUID mapping. Verified by `test_real_qdrant_adapter_roundtrip`. |
| **MCP-01** | **P1** | MCP integration was dummy list without real SDK connection. | **FIXED** | Implemented real stdio client using official `mcp` Python SDK 2.x; verified by `test_real_mcp_sdk_discovery_and_call`. |
| **MET-01** | **P1** | AI Studio hardcoded `rag_hit_rate = 0.85` and fake confidence scores `0.92/0.99`. | **FIXED** | Removed hardcoded constants; metrics computed dynamically from persisted `AIRun` traces; `confidence` defaults to None with clear `decision_reason`. |
| **MEM-01** | **P1** | `NativeMemoryProvider.delete()` unconditionally returned `True`. | **FIXED** | Fixed `delete()` to check `rowcount > 0` and return `False` when record is missing. |
| **TOOL-01** | **P1** | Hardcoded destructive refund arguments (`order_id=1, amount=25.0`) in graph. | **FIXED** | Removed hardcoded values; validated arguments extracted from context or flagged for admin approval. |
