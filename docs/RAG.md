# Privacy-Preserving Scoped RAG

## 1. Multi-Scope Knowledge Isolation

Signal Market Bot operates across both 1-on-1 private direct messages and multi-user Signal groups. Preventing cross-tenant data leakage is a **P0 security invariant**.

The RAG retrieval engine (`app.ai.rag.retrieval.KnowledgeRetriever`) enforces strict mathematical filtering across three scope boundaries:

```
                    ┌────────────────────────────┐
                    │     Global Knowledge       │
                    │ (Public FAQs, Policies)    │
                    └─────────────┬──────────────┘
                                  │
                  ┌───────────────┴───────────────┐
                  ▼                               ▼
       ┌────────────────────┐          ┌────────────────────┐
       │   Group Scope      │          │   User Scope       │
       │ (Group Rules, Rosters)│       │ (Private Notes)    │
       └────────────────────┘          └────────────────────┘
```

### Retrieval Filter Matrix

| Interaction Context | Global Allowed | Group Allowed | User Allowed | Cross-Tenant Protection |
| :--- | :---: | :---: | :---: | :--- |
| **Direct Message (DM)** | Yes | No | Yes (Self only) | Blocks all group-internal information |
| **Group Chat** | Yes | Yes (Current group only) | No | **Strictly blocks private user notes** |

---

## 2. Ingestion Pipeline

The knowledge ingestion service (`app.ai.rag.ingestion.KnowledgeIngestionService`):
1. **Document Normalization**: Parses Markdown, text, and FAQ formats.
2. **Deterministic Chunking**: Splits documents into semantically coherent windows (target size ~500 chars with 50 chars overlap).
3. **Scoped Tagging**: Tags every chunk with `scope_type` (`global`, `group`, `user`) and `scope_id`.
4. **Vector Embedding**: Generates vector representations using `FakeEmbeddingProvider` (for testing) or production OpenAI text-embedding-3-small.
5. **Storage Backends**:
   - `FakeVectorStore`: In-memory cosine similarity store for fast tests and evaluation.
   - `QdrantVectorStore`: Production vector database with HNSW indexing and metadata filtering payload.

---

## 3. Defense Against Indirect Prompt Injection

Retrieved knowledge chunks are treated as **untrusted external data**:
- Injected chunks are enclosed in clear delimiter boundaries (`### Retrieved Knowledge Sources (untrusted data context)`).
- System instructions enforce that retrieved content cannot override core safety guidelines, execute unapproved commands, or impersonate system actors.
- Hidden chain-of-thought tokens are stripped before delivery to Signal recipients.
