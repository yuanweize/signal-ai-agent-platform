# Signal Market Bot — Architecture Target (Evolutionary Roadmap)

## 1. Target Evolution Overview

While Round 2 has achieved end-to-end domain integrity, reliable event pipelines, explicit manual takeover, and a robust admin inbox, the target architecture outlines planned evolutions for multi-admin scaling, real-time push streaming, and distributed deployment.

```
┌────────────────────────────────────────────────────────┐
│                   Signal Network                       │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│           High-Availability Signal Gateway             │
│        (Failover pairing / Connection Health)          │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│                FastAPI Application Tier                │
│                                                        │
│  ┌─────────────────────────┐ ┌──────────────────────┐  │
│  │ SSE Real-time Hub       │ │ Redis / Distributed  │  │
│  │ - Multi-admin broadcast │ │ Event Queue (Celery) │  │
│  │ - Live cursor presence  │ └──────────────────────┘  │
│  └─────────────────────────┘                           │
│                                                        │
│  ┌─────────────────────────┐ ┌──────────────────────┐  │
│  │ PostgreSQL / SQLite WAL │ │ S3 Media Storage     │  │
│  │ - Row-level read state  │ │ - Presigned URLs     │  │
│  │ - Read replicas         │ │ - Virus scan / strip │  │
│  └─────────────────────────┘ └──────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

---

## 2. Key Target Enhancements

### 2.1 Server-Sent Events (SSE) / WebSocket Push
- Transition from 3-second active conversation polling to bi-directional SSE/WebSocket streams.
- Live typing indicators (`typing show/hide`) broadcasted to admin viewports.
- Real-time read receipt updates instantly reflecting on sent bubbles.

### 2.2 Multi-Admin Read Cursor Tracking
- Extend `conversation_read_states` to support `(admin_id, conversation_id)` composite keys.
- Admin presence indicators showing which operator is currently reading or typing in a conversation.

### 2.3 Binary Attachment Offloading
- Offload local binary storage from `data/attachments` to S3-compatible object storage (e.g., MinIO, Cloudflare R2).
- Automatic thumbnail generation and safe MIME-type sanitization for outbound/inbound media.

### 2.4 Autonomous Campaign Scheduler
- Transition campaign broadcasts from manual admin triggers to a cron-based scheduler with rate limiting, time-zone awareness, and automated quiet-hour pausing.
