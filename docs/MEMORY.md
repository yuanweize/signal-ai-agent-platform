# Scoped Memory & PII Redaction

## 1. Dual-Tier Memory Architecture

Signal Market Bot maintains two tiers of conversational state:
1. **Short-Term Context**: Last $N$ conversation messages fetched dynamically during inference to preserve conversational continuity.
2. **Durable Scoped Memory**: Persistent profile preferences, dietary restrictions, address notes, and delivery preferences stored in the `customer_memories` table.

```
Incoming Turn ──> MemoryExtractor ──> Redact PII/Secrets ──> NativeMemoryProvider ──> SQLite / DB
                                                                     │
                                             Query at Runtime <──────┘
```

---

## 2. Automatic PII & Secret Redaction

Before durable storage, memories pass through `redact_sensitive_pii`:
- **Payment Cards**: 16-digit credit/debit card numbers are replaced with `[REDACTED_CARD]`.
- **API Keys & Tokens**: Bearer tokens, JWTs, and OpenAI/Signal keys are stripped.
- **Passwords & Pins**: Passwords and PIN codes are permanently removed.

---

## 3. GDPR Compliance & Right to be Forgotten

Users have the right to inspect and permanently erase their recorded profile memory:
- **Deletion API**: `DELETE /api/ai/memories/{memory_id}`.
- **Scope Erasure**: Deleting a user or customer purges all associated memory items across the relational database and vector indexes simultaneously.
- **Dual Deletion**: Soft-deleted records are decoupled from conversational history, preventing residual traces in future prompt completions.
