# Testing Architecture & Verification Matrix

## Overview

The test suite verifies application correctness, data integrity, and privacy invariants across both backend (Python 3.12 / pytest) and frontend (React 18 / Vitest) layers.

---

## 1. Test Categories & Execution

### A. Backend Test Suite (Pytest)
Command:
```bash
cd backend
.venv/bin/pytest -v
```
- **Current Release Baseline**: 141 backend passing tests.
- **Coverage Highlights**:
  - `tests/test_v04_final_production_hardening.py` (15 tests):
    - `test_real_app_startup_routes_ai_through_agent_runtime_factory`: Asserts real app lifespan routes all AI traffic via AgentRuntime.
    - `test_non_test_runtime_rejects_fake_vector_store`: Asserts runtime rejects Fake providers in non-test mode.
    - `test_runtime_settings_include_embedding_and_qdrant_configuration`: Verifies dynamic DB settings for embeddings and Qdrant.
    - `test_ai_disabled_does_not_call_external_llm`: Asserts zero external LLM calls when AI toggle is off.
    - `test_agent_uses_recent_conversation_history`: Verifies multi-turn history loading and chronological ordering.
    - `test_current_inbound_not_duplicated`: Asserts current turn message is not duplicated in prompt.
    - `test_group_history_preserves_sender_attribution`: Verifies `Alice: ` and `AI: ` prefix attribution in group history.
    - `test_context_window_respects_limit`: Asserts budget truncation for long message history.
    - `test_active_prompt_is_used_by_llm_and_recorded_in_airun`: Verifies dynamic prompt selection and provenance recording.
    - `test_skill_toggle_survives_registry_restart`: Asserts skill enable/disable persistence across restarts.
    - `test_mcp_env_secrets_not_stored_plaintext_and_auto_reconnects`: Asserts MCP env secrets encryption and auto-reconnect.
    - `test_learning_pair_uses_reply_target_and_rejects_failed_send`: Verifies human reply pairing with explicit reply_to_id.
    - `test_private_learning_candidate_not_promoted_global_without_explicit_scope`: Asserts privacy safety confirmation gate.
    - `test_user_purge_removes_private_vectors_and_memory`: Verifies comprehensive cascading wipe of user data and vector points.
    - `test_prompt_injection_adversarial_negative_suite`: Asserts adversarial prompt injection and approval bypass defenses.
  - `tests/test_production_wiring_and_hardening.py` (8 tests):
    - `test_production_runtime_does_not_use_fake_providers`: Asserts runtime factory builds real OpenAI/Qdrant adapters and blocks Fake providers in production mode.
    - `test_auto_mode_uses_agent_runtime`: Verifies auto reply dispatches via `AgentRuntime.run()` and logs `AIRun`.
    - `test_copilot_mode_uses_same_agent_runtime`: Verifies copilot suggestions share the identical `AgentRuntime`.
    - `test_real_qdrant_adapter_roundtrip`: Verifies `QdrantVectorStore` indexing, point UUID mapping, and `query_points` retrieval.
    - `test_real_mcp_sdk_discovery_and_call`: Verifies official `mcp` Python SDK stdio connection, discovery, and execution.
    - `test_mcp_write_requires_approval`: Asserts destructive or write actions trigger administrative approval gates.
    - `test_ai_dashboard_has_no_hardcoded_metrics`: Asserts hit rates and diagnostic metrics are computed from stored events rather than hardcoded floats.
    - `test_reindex_pipeline`: Asserts relational document re-chunking and vector re-indexing endpoint.
  - `tests/test_ai_platform.py`: Scope isolation, group privacy invariants, canonical memory sharing.
  - `tests/test_message_pipeline.py`: Deduplication, conversation routing, block policies.
  - `tests/test_round2_messaging_pipeline.py`: Admin takeover race protection, delivery retry transitions.
  - `tests/test_conversations_api.py`, `tests/test_groups_sync.py`, `tests/test_auth_audit.py`: Full API and CRUD suite.

### B. Deterministic Agent Contract Evaluation Suite
Command:
```bash
cd backend
.venv/bin/python evals/run_evals.py
```
- **Total Test Cases**: 32 invariant cases.
- **Pass Rate**: 100.0% (32/32 cases passing).
- **Decision Accuracy**: 100.0%.
- **Average Latency**: ~1.7 ms.
- **Invariants Evaluated**: Product catalog inquiries, refund governance approval gates, explicit human handoff requests, copilot draft generation, group moderation queries, prompt injection defense, multi-language processing (English, Chinese, Czech).

### C. Frontend Test Suite (Vitest)
Command:
```bash
cd frontend
npm test
```
- **Total Test Cases**: 20 passing tests across 6 test suites.
- **Components Covered**: `AIPlatform.test.tsx`, `AIStudioContract.test.tsx`, `DevicesPage.test.tsx`, `InboxPage.test.tsx`, `LoginPage.test.tsx`, `SettingsPage.test.tsx`.

### D. Database Migration Tests
Verified across 5 distinct lifecycles (`backend/tests/test_migrations.py`):
1. **Fresh Install**: Empty database → `alembic upgrade head`.
2. **Legacy Upgrade**: `112aa6e29383` → `alembic upgrade head`.
3. **v0.3 → v0.4 Upgrade**: `c8927140f12a` → `alembic upgrade head`.
4. **v0.4.0 → v0.4.1 Upgrade**: `e1f2a3b4c5d6` → `f3b4c5d6e7f8`.
5. **v0.4.1 → v0.4.2 Hardening & Downgrade**: `f3b4c5d6e7f8` → `g4c5d6e7f8a9` (correcting legacy `llm_call_count` heuristics) and rollback verification.

---

## 2. CI Automation Gate

Every push and pull request validates the following sequential pipeline:
1. **Backend Lint & Format**: `ruff check app tests evals` and `ruff format --check app tests evals`.
2. **Backend Unit & Integration**: `pytest -q` (141 tests).
3. **Deterministic Evaluation Suite**: `python evals/run_evals.py` (32 invariant cases).
4. **Database Migrations**: Verification of full linear revision upgrade and downgrade chain.
5. **Frontend Lint & Build**: `npm run lint`, `npx tsc --noEmit`, `npm test -- --run`, `npm run build`.
6. **Docker Compose Runtime Smoke**: Builds and launches real Qdrant, backend, and frontend containers, verifying `/health/ready`, `/health/live`, Qdrant cluster readiness, and frontend HTTP response, with automatic container diagnostics on failure.
