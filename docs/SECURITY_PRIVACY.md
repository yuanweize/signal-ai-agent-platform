# Security, Privacy & Isolation Invariants

## Core Principles

Signal Market Bot handles sensitive customer conversations across direct messages (DMs) and multi-party Signal group chats. The architecture enforces strict privacy and safety invariants at both the database and prompt generation layers.

---

## 1. Group Privacy Invariant (P0)

> [!IMPORTANT]
> **Group context must NEVER retrieve or inject private user memories or documents.**

### Invariant Rules
1. In a **Direct Message (DM)** with User A:
   - Permitted scopes: `global` + User A's private scope (`user_id = UserA.id`).
   - Forbidden scopes: Any other user's scope, any group's scope.
2. In a **Group Chat (Group X)**:
   - Permitted scopes: `global` + Group X's scope (`group_id = GroupX.id`).
   - **Forbidden scopes**: Private user memory or documents belonging to ANY user, including the message sender.

### Implementation Verification
- [`backend/app/ai/rag/retrieval.py`](file:///Users/yuanweize/我的文档/服务器/GITHUB/signal-market-bot/backend/app/ai/rag/retrieval.py):
  ```python
  if is_group:
      # P0 Safety Guard: Groups must never retrieve individual user-scoped knowledge
      allowed_scopes.discard("user")
  ```
- [`backend/app/ai/runtime/agent_runtime.py`](file:///Users/yuanweize/我的文档/服务器/GITHUB/signal-market-bot/backend/app/ai/runtime/agent_runtime.py):
  ```python
  if context.is_group:
      # P0 Safety Guard: Groups must NEVER load individual user memories
      turn_memories = []
  ```
- Verified by automated regression tests in [`backend/tests/test_ai_platform.py`](file:///Users/yuanweize/我的文档/服务器/GITHUB/signal-market-bot/backend/tests/test_ai_platform.py) (`test_group_cannot_retrieve_user_rag` and `test_group_prompt_contains_no_private_user_memory`).

---

## 2. Canonical Identity Protection

Signal users may communicate via phone number, contact name, or Signal UUID.
- User memories and conversation attribution are tied to `canonical_user_id` in [`backend/app/models/user.py`](file:///Users/yuanweize/我的文档/服务器/GITHUB/signal-market-bot/backend/app/models/user.py).
- A user contacting via phone and later via UUID accesses the identical memory namespace without duplicate or conflicting profiles.
- Verified by `test_same_user_phone_uuid_share_memory`.

---

## 3. Tool Permission Governance & Approval Gates

All external tools and MCP integrations are subject to deterministic permission gates:
- `read_only`: Catalog lookups, order status checks. Permitted for automatic agent reply.
- `requires_approval`: Sensitive business or financial actions (e.g. issuing refunds, deleting accounts).
  - The runtime automatically suppresses direct autonomous execution.
  - Generates an `AISuggestion` flagged as `pending` with decision `draft_for_human`.
  - An administrative staff member must review and approve before any outbound or destructive action executes.
- Verified by `test_mcp_write_requires_approval`.

---

## 4. Prompt Injection Safeguards

- Knowledge chunks retrieved via RAG and external tool outputs are injected under explicit untrusted context blocks:
  ```text
  Retrieved Knowledge Sources (untrusted data context):
  [{Title}]: {Content}
  ```
- System directives are immutable and pinned at the highest priority in the prompt template.
- Verified against prompt injection payloads in the 32-case deterministic evaluation suite (`case_14_prompt_injection_safety` and `case_15_prompt_injection_tool_bypass`).

---

## 5. Privacy Controls & Data Deletion

- Individual user memories can be deleted on demand via `NativeMemoryProvider.delete()`.
- Missing records return explicit 404/False status rather than silent positive acknowledgments.
- Sensitive credentials (API keys, bot secrets) are encrypted at rest using AES-GCM database encryption.
- Traces and logs do not dump unmasked credentials or private payment tokens.
