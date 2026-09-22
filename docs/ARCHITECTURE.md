# System Architecture — Signal Market Bot v0.4

## Overview

Signal Market Bot is a **Signal-native AI customer support and conversational commerce platform** designed for secure, private, and high-reliability operations.

The system connects to Signal via an official `signal-cli-rest-api` gateway, ingests inbound JSON webhooks, normalizes them through an asynchronous message pipeline, and dispatches them through a unified LangGraph-based **AgentRuntime**. Outbound actions support autonomous replies, human-in-the-loop Copilot suggestions, or human handoff.

---

## High-Level Architecture Diagram

```mermaid
flowchart TD
    subgraph Signal Network
        Client[Signal Client / Group]
    end

    subgraph Infrastructure
        Gateway[signal-cli-rest-api Gateway]
        Qdrant[(Qdrant Vector DB)]
        SQLite[(SQLite / PostgreSQL DB)]
    end

    subgraph Backend Core
        Webhook[FastAPI Inbound Webhook]
        Handler[MessageHandler]
        Runtime[AgentRuntime Factory]
        Graph[LangGraph StateGraph]
        Outbound[OutboundMessageService]
    end

    subgraph AI Subsystems
        Retriever[KnowledgeRetriever / RAG]
        Memory[Scoped Native Memory]
        Skills[Skill Registry]
        Tools[Tool Registry & MCP SDK]
        LLM[OpenAI-Compatible LLM Adapter]
    end

    subgraph Frontend Admin
        Inbox[Inbox Copilot UI]
        Studio[AI Studio & Diagnostics]
    end

    Client -->|Encrypted Signal Event| Gateway
    Gateway -->|HTTP JSON Webhook| Webhook
    Webhook --> Handler
    Handler --> Runtime
    Runtime --> Graph

    Graph --> Retriever
    Graph --> Memory
    Graph --> Skills
    Graph --> Tools
    Graph --> LLM

    Retriever --> Qdrant
    Memory --> SQLite
    Runtime -->|AIRun Trace & Suggestion| SQLite

    Graph -->|Decision: Reply| Outbound
    Graph -->|Decision: Draft for Human| Inbox
    Graph -->|Decision: Handoff| Inbox
    Outbound --> Gateway
    Gateway -->|Encrypted Outbound| Client

    Inbox -->|Edit & Approve| Outbound
    Studio -->|Reindex & Config| Runtime
```

---

## Core Components

### 1. Inbound Webhook & Deduplication Pipeline
- **Webhook Endpoint**: `POST /api/signal/webhook` receives incoming messages, attachments, receipts, and typing indicators.
- **Message Deduplication**: Deduplicated on `signal_event_id` and `(conversation_id, signal_timestamp_ms)`.
- **Identity Normalization**: Canonical user resolution binds telephone numbers and UUIDs into a single consistent user identity.

### 2. Unified Agent Runtime (`app/ai/runtime/`)
Both **Auto** and **Copilot** modes invoke the same production-grade `AgentRuntime`:
- **Factory Architecture (`app/ai/runtime/factory.py`)**: Builds live providers based on database-backed configuration. In production (`ENVIRONMENT=production`), silently falling back to `FakeLLMProvider` or `FakeVectorStore` is strictly forbidden.
- **StateGraph Orchestration (`app/ai/orchestration/graph.py`)**:
  1. `route_skills`: Deterministic rule router + progressive skill loading.
  2. `retrieve_knowledge`: RAG retrieval with scope-based filtering.
  3. `plan_tools`: Structured tool selection (e.g. catalog lookup, sensitive actions).
  4. `generate_response`: LLM completion with untrusted data boundary enforcement.
  5. `decide_action`: Emits `reply`, `draft_for_human`, `handoff`, or `no_reply`.
- **Manual Takeover Race Protection**: If an admin switches a conversation from `auto` to `manual` while the AI is executing, the outbound response is dropped before sending.

### 3. Retrieval-Augmented Generation (RAG) (`app/ai/rag/`)
- **Vector Store**: Qdrant (`QdrantVectorStore`), supporting persistent collections and in-memory test instances.
- **Scope Isolation**:
  - `global`: Accessible across all conversations.
  - `group`: Accessible only within the specific group context.
  - `user`: Accessible only in direct 1-on-1 conversations with that user. **Strict invariant**: Group chats never retrieve private user knowledge.
- **Reindexing Pipeline**: Rebuilds vector indexes on demand from relational documents (`POST /api/ai-studio/knowledge/reindex`).

### 4. Scoped Durable Memory (`app/ai/memory/`)
- Extracted preferences, communication language, and verified customer facts stored per canonical user namespace.
- **Group Isolation**: AgentRuntime disables loading private user memory when `context.is_group == True`.

### 5. Tools & MCP Integration (`app/ai/tools/`, `app/ai/mcp/`)
- Official `mcp` Python SDK 2.x stdio client with session initialization and discovery.
- **Permission Governance**: Tools require explicit administrative privilege (`read_only`, `requires_approval`, `write`). Destructive or financial tools (e.g. refunds) trigger supervisor drafts (`draft_for_human`).

### 6. Human-in-the-Loop Copilot (`app/models/ai.py`, `frontend/src/InboxPage.tsx`)
- Generates `AISuggestion` records linked to underlying `AIRun` traces.
- Administrative agents review, edit, or accept suggested replies before sending.
- Tracks provenance (`MessageOrigin.human_ai_assisted`) and feedback events.
