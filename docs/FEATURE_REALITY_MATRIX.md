# Feature & Capability Matrix (v0.3.0)

This matrix outlines the architectural modules, verified domain behaviors, and platform capabilities in Signal Market Bot v0.3.0.

## Core Platform Capabilities

| Capability | Category | Verification Scope | Status | Details |
|---|---|---|---|---|
| **Security Bootstrap** | Identity & Access | Unit + Integration + UI | **GA** | First-run setup wizard with scrypt password hashing, TOTP 2FA, and JWT auth |
| **Admin Authentication** | Identity & Access | Unit + Integration + UI | **GA** | Rate-limited login guard, session expiration, and encrypted credentials |
| **Signal Event Ingestion** | Messaging Engine | Unit + Integration + Mock Gateway | **GA** | Bounded async queue (`maxsize=1000`), 4 worker pool, and partition locking |
| **Outbound Delivery Engine** | Messaging Engine | Unit + Integration + UI | **GA** | Strict state machine (`pending` -> `sent` / `failed` -> `delivered` -> `read`) + retry |
| **Direct Messaging (DM)** | Messaging Engine | Unit + Integration + UI | **GA** | Discrete DM conversation entity, user mapping, and unread state |
| **Group Conversations** | Messaging Engine | Unit + Integration + UI | **GA** | Multi-party attribution; sender identity mapped to message level |
| **Customer Inbox** | Admin UI | Vitest + Visual Inspection | **GA** | Dual-pane conversation list, optimistic message dispatch, and drawer inspection |
| **Manual Takeover** | AI & Workflow | Unit + Integration + UI | **GA** | Mode toggle (`auto`, `manual`, `paused`) with mid-generation race protection |
| **AI LLM Engine** | AI & Workflow | Unit + Integration | **GA** | OpenAI-compatible endpoint provider with prompt injection and context memory |
| **User Identity Resolution** | Domain Modeling | Unit + Integration | **GA** | Canonical user mapping across Signal UUID and E.164 phone numbers |
| **Group Roster Sync** | Domain Modeling | Unit + Integration + UI | **GA** | Member list synchronization and administrative role tracking |
| **Attachment & Reaction** | Messaging Engine | Unit + Integration + UI | **GA** | Native parsing, persistence, and UI rendering of media and emoji reactions |
| **Server-Side Read Cursor** | Domain Modeling | Unit + Integration + UI | **GA** | Persistent `last_read_message_id` tracking across client refreshes |
| **Product Catalog** | E-Commerce | Unit + Integration + UI | **GA** | Full CRUD inventory management grounded into AI context |
| **Campaign Broadcasts** | Marketing Engine | Unit + Integration + UI | **GA** | Multi-group broadcasts with quiet-hour restrictions, blacklists, and dry-runs |
| **Audit Logging** | Governance | Unit + Integration | **GA** | Structured event logging for security, configuration, and administrative actions |
| **Data Retention Cleanup** | Governance | Unit + Integration | **GA** | Automated expiration cleanup service based on configurable retention days |
| **Modular Settings Console** | Admin UI | Vitest + Visual Inspection | **GA** | 7-tab interface with live connection probing and credential masking |
| **Database Migrations** | Infrastructure | Automated CI Regression | **GA** | Continuous Alembic migration chain with SQLite batch alteration support |
| **Containerization & CI** | DevOps | Automated CI Gates | **GA** | Docker multi-stage builds, GHCR images, and end-to-end lint/test pipelines |

---

## Roadmap Capabilities

| Capability | Planned Release | Target Scope |
|---|---|---|
| **Server-Sent Events (SSE)** | v0.4.0 | Real-time push updates for inbox message timeline replacing 3s polling |
| **Rich Media Storage (S3)** | v0.5.0 | High-capacity audio/video storage with local cache and pre-signed URLs |
| **Automated Checkout & Orders** | v0.6.0 | End-to-end payment gateway integration (Stripe, Crypto) with order states |
| **Autonomous Campaign Scheduling** | v0.6.0 | Cron-based background campaign scheduler with recurring marketing triggers |
| **Multi-Agent Collision Detection** | v0.7.0 | Live typing indicators and read cursors across multiple concurrent operators |
