# Signal Market Bot — Architecture Documentation (Current State)

## 1. System Overview

Signal Market Bot is an asynchronous, self-hosted messaging and e-commerce bot bridging the Signal messaging protocol with automated AI customer support, human administrative takeover, product catalog management, and broadcast campaign workflows.

```
┌────────────────────────────────────────────────────────┐
│               External Signal Network                  │
└──────────────────────────┬─────────────────────────────┘
                           │ WebSocket / HTTP REST
                           ▼
┌────────────────────────────────────────────────────────┐
│            signal-cli-rest-api Daemon                  │
└──────────────┬───────────────────────────▲─────────────┘
               │ Event Payload             │ Outbound REST
               ▼                           │
┌────────────────────────────────────────────────────────┐
│                FastAPI Backend Core                    │
│                                                        │
│  ┌────────────────────┐      ┌──────────────────────┐  │
│  │ EventPipeline      │      │ OutboundService      │  │
│  │ - Bounded Queue    │      │ - State Machine      │  │
│  │ - Worker Pool (4)  │      │ - Pending/Sent/Fail  │  │
│  │ - Partition Locks  │      │ - Explicit Retries   │  │
│  └─────────┬──────────┘      └──────────▲───────────┘  │
│            │                            │              │
│            ▼                            │              │
│  ┌────────────────────┐      ┌──────────┴───────────┐  │
│  │ MessageHandler     │─────►│ AIEngine (LLM)       │  │
│  │ - Deduplication    │      │ - Structured Context │  │
│  │ - Identity Mapping │      │ - Token Accounting   │  │
│  │ - Group Attribution│      │ - Mode Guard (Race)  │  │
│  └─────────┬──────────┘      └──────────────────────┘  │
│            │                                           │
│            ▼                                           │
│  ┌──────────────────────────────────────────────────┐  │
│  │ SQLAlchemy Async Engine (SQLite + WAL)           │  │
│  │ - User & UserIdentity                            │  │
│  │ - Group & GroupMember                            │  │
│  │ - Conversation & ConversationReadState           │  │
│  │ - Message, Attachment, Reaction                  │  │
│  └──────────────────────────▲───────────────────────┘  │
│                             │ REST API                 │
└─────────────────────────────┼──────────────────────────┘
                              │
┌─────────────────────────────┴──────────────────────────┐
│             Vite / React Admin Dashboard               │
│  - Inbox (Timeline, Cursor Pagination, Real-time Poll) │
│  - Groups (Signal Roster Sync, Member Roles)           │
│  - Users (Identities, Activity Attribution, Block)     │
│  - Settings (Modular Tabs, Secret Masking, Diagnostics)│
│  - Devices (Fault-tolerant, Independent Fetch)         │
└────────────────────────────────────────────────────────┘
```

---

## 2. Core Architectural Pillars

### 2.1 Decoupled Ingestion Pipeline
- **Bounded Ingestion**: The Signal WebSocket listener puts raw events into an `asyncio.Queue(maxsize=1000)` without awaiting LLM generation.
- **Worker Pool**: 4 background worker coroutines consume from the queue with backpressure handling.
- **Conversation Partition Locks**: Ensures sequential message processing within the same conversation while allowing parallel execution across distinct conversations.

### 2.2 Domain Attribution & Identity
- **Groups Have No Single Owner**: `Conversation.group_id` establishes group identity. Senders are mapped to `Message.sender_user_id` and tracked in `group_members`.
- **Identity Unification**: Phones and UUIDs map through `user_identities` to a single canonical `User` row, preventing identity fracturing.
- **Conversation Entity**: Distinguishes `dm` from `group` explicitly, with discrete `mode` (`auto`, `manual`, `paused`).

### 2.3 Outbound State Machine & Manual Takeover
- **Unified Delivery**: All outbound messages (AI auto-replies, manual admin replies, campaigns) flow through `OutboundMessageService`.
- **States**: `pending` → `sent` (with remote timestamp) or `failed` (with failure reason).
- **Race Condition Prevention**: AI re-checks `conversation.mode` immediately before transmission; if admin switched to `manual`, AI outbound is discarded.

### 2.4 Server-Side Read State
- Unread messages are tracked per conversation in `conversation_read_states` by `last_read_message_id`.
- Marking a conversation as read persists across browser reloads.
