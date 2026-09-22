# AI Privacy Boundaries & Security Guardrails

## 1. Zero Model CoT Leakage

Thinking traces, scratchpads, and hidden chain-of-thought tokens from modern reasoning models (such as DeepSeek-R1, OpenAI o1/o3-mini, Gemini 2.0 Flash Thinking) must **never** leak to end recipients on Signal:
- Internal prompts separate developer reasoning from customer-facing text.
- Outbound sanitizers strip `<think>...</think>` tags and XML scratchpads before dispatching to the Signal Gateway.

---

## 2. Multi-Tenant Group Boundary Protection

In Signal groups, members must not be able to elicit information stored in other members' private direct message profiles:
- Group interactions **strictly set `allow_user_scope=False`** during RAG vector search.
- Scoped memories are isolated per `(scope_type, scope_id)`.
- System prompts in group contexts explicitly prohibit acknowledging private DM orders or addresses unless posted publicly by that user in the group.

---

## 3. PII & Secret Redaction

Before customer inputs or bot outputs are committed to long-term memory or training export datasets:
- Card numbers, social security numbers, and sensitive IDs are masked via regex heuristics.
- Bearer tokens, private keys, and webhook secrets are redacted.
- Administrators can audit and scrub any memory entry via the AI Studio console.
