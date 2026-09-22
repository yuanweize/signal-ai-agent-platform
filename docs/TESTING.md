# Testing Architecture & Verification Matrix

## Overview

The test suite verifies application correctness, data integrity, and privacy invariants across both backend (Python 3.14 / pytest) and frontend (React 18 / Vitest) layers.

---

## 1. Test Categories & Execution

### A. Backend Test Suite (Pytest)
Command:
```bash
cd backend
.venv/bin/pytest -v
```
- **Total Test Cases**: 73 passing tests.
- **Coverage Highlights**:
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
- **Total Test Cases**: 18 passing tests across 5 test suites.
- **Components Covered**: `AIPlatform.test.tsx`, `DevicesPage.test.tsx`, `InboxPage.test.tsx`, `LoginPage.test.tsx`, `SettingsPage.test.tsx`.

### D. Database Migration Tests
Verified across 3 distinct lifecycles:
1. **Fresh Install**: Empty database → `alembic upgrade head`.
2. **Legacy Upgrade**: `112aa6e29383` → `alembic upgrade head`.
3. **v0.3 → v0.4 Upgrade**: `c8927140f12a` → `alembic upgrade head`.

---

## 2. CI Automation Gate

Every push and pull request validates the following sequential pipeline:
1. **Backend Lint & Format**: `ruff check app tests evals` and `ruff format --check app tests evals`.
2. **Backend Unit & Integration**: `pytest -q`.
3. **Deterministic Evaluation Suite**: `python evals/run_evals.py`.
4. **Database Migrations**: Verification of linear revision head.
5. **Frontend Lint & Build**: `npm run lint`, `npx tsc --noEmit`, `npm test`, `npm run build`.
6. **Docker Compose Build**: Validates backend, frontend, and Qdrant container configurations.
