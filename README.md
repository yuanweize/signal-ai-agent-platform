<div align="center">

# 🤖 Signal Market Bot

### Conversational Commerce & AI Customer Support Platform for Signal

[![Release](https://img.shields.io/github/v/release/yuanweize/signal-market-bot?color=7c3aed&label=Release)](https://github.com/yuanweize/signal-market-bot/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/yuanweize/signal-market-bot/ci.yml?branch=main&label=CI)](https://github.com/yuanweize/signal-market-bot/actions)
[![Docker Ready](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://github.com/yuanweize/signal-market-bot/pkgs/container/signal-market-bot-backend)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](backend/pyproject.toml)
[![React](https://img.shields.io/badge/React-18%20%2B%20Vite-61DAFB?logo=react&logoColor=black)](frontend/package.json)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[English](README.md) • [简体中文](README.zh-CN.md) • [Documentation](docs/ARCHITECTURE.md) • [Release Notes](CHANGELOG.md)

</div>

---

<div align="center">
  <img src="assets/admin_overview.png" width="900" alt="Signal Market Bot Admin Overview" style="border-radius: 12px; box-shadow: 0 12px 36px rgba(0,0,0,0.35);">
  <p><em>Signal Market Bot Executive Console — Real-time operational telemetry, messaging volume, marketing broadcasts, and product metrics</em></p>
</div>

<div align="center">
  <img src="assets/ai_engine_setting.png" width="900" alt="Signal Market Bot AI Engine Configuration" style="border-radius: 12px; box-shadow: 0 12px 36px rgba(0,0,0,0.35);">
  <p><em>Runtime AI Engine Configuration — Universal OpenAI-compatible endpoint integration, temperature tuning, dynamic prompt injection, and hot reloading</em></p>
</div>

---

## 🌟 Overview

**Signal Market Bot** is a **Signal-native AI customer service and conversational commerce platform** designed specifically for the Signal messaging ecosystem. It bridges end-to-end Signal messaging with modern LLM intelligence, human agent intervention, e-commerce catalog management, and automated broadcast campaigns.

With **AI Platform v0.4**, the system introduces an agentic architecture powered by **LangGraph**, offering **Copilot mode with message provenance**, **Progressive Skills**, **Scoped RAG retrieval with cross-tenant isolation**, **Durable Scoped Memory**, **MCP tool governance**, and a **Human-in-the-Loop continuous learning loop**.

---

## 🚀 Key Features

### 🤖 AI Platform & Agent Runtime (v0.4)
- **LangGraph Agent Workflow**: Directed state graph executing progressive skill discovery, multi-scope RAG, tool authorization, grounded generation, and decision classification (`reply`, `draft_for_human`, `handoff`, `no_reply`).
- **Production Runtime Factory**: Eliminates silent fallback to fake providers in production. Production deployments connect directly to live OpenAI-compatible LLM/Embedding endpoints and Qdrant vector database.
- **Strict Group Privacy Invariant (P0)**: Group chat conversations are strictly forbidden from retrieving private user documents or loading private user memories.
- **Inbox Copilot Mode**: Real-time drafting assistant for human operators with one-click **Accept & Send**, **Edit in Composer**, **Discard**, and an **Evidence Drawer** revealing citations, memories, and tools used.
- **Message Provenance Tracking**: Strict origin classification (`customer`, `ai_auto`, `human_ai_assisted`, `human_manual`, `system`, `campaign`) linked to `ai_run_id` for explainable AI auditing.
- **Scoped RAG Knowledge Base**: Qdrant vector storage with point UUID mapping, dense retrieval, and full relational-to-vector reindexing (`POST /api/ai-studio/knowledge/reindex`).
- **Durable Scoped Memory**: Automated customer preference extraction bound to canonical user identity (phone number & Signal UUID map to the same namespace) with individual deletion support.
- **Governed Tools & Model Context Protocol (MCP)**: Official Python `mcp` SDK stdio client integration. Sensitive tools (e.g. refunds) trigger supervisor drafts (`draft_for_human`) rather than autonomous execution.
- **Human-in-the-Loop Learning Loop**: Detects operator edits, curates learning candidates, allows one-click FAQ promotion, and exports fine-tuning JSONL datasets.
- **Deterministic Contract Evaluation**: 32-case deterministic evaluation suite (`python evals/run_evals.py`) scoring pass rate, decision accuracy, keyword recall, and latency with 100% CI pass rate.

### 📥 Support Inbox & Takeover
- **Dual-Pane Conversation Console**: Complete customer conversation visibility with unread counters, message search, and type filters (DMs / Groups / Unread).
- **4-State Takeover Engine**: Seamlessly toggle between **Auto (AI)**, **Copilot (Assisted Drafts)**, **Manual (Human Only)**, and **Paused (Mute)** with pre-send state locks.
- **Delivery State Machine**: Comprehensive message lifecycle tracking (`received` / `pending` -> `sent` / `failed` -> `delivered` -> `read`) with one-click failed message retries.
- **Media & Reactions**: Native parsing and rendering of media attachments and emoji reactions.

### ⚡ Resilient Event Ingestion Pipeline
- **Backpressure-Controlled Queue**: Bounded in-memory event pipeline (`maxsize=1000`) preventing memory spikes during message surges.
- **Concurrent Worker Pool**: Multi-worker asynchronous processing with per-conversation partition locking to guarantee strict chronological message order without blocking unrelated chats.
- **Robust Deduplication**: Dual-layer deduplication combining fast LRU in-memory filtering with database unique constraints across reconnect cycles.

### 📢 Targeted Campaign Broadcasts
- **Smart Group Broadcasting**: Disseminate announcements and updates to selected Signal groups.
- **Policy Guardrails**: Built-in quiet hours protection, group blacklisting, and a zero-risk dry-run preview mode.

### 🔒 Operational Security & Zero-.env Configuration
- **First-Run Security Bootstrap**: One-time setup wizard configuring administrative credentials with scrypt password hashing and optional TOTP 2FA.
- **Encrypted Runtime Configuration**: Configure Signal gateways, AI API keys, retention periods, and prompts directly in the UI with automated credential masking and encrypted DB storage.
- **Comprehensive Audit Trail**: Structured event logging recording authentication attempts, takeover actions, and configuration updates.

---

## 📚 Technical Documentation

- 🏛️ [System Architecture & Data Flows](docs/ARCHITECTURE.md)
- 🤖 [AI Platform Subsystems & Runtime Factory](docs/AI_PLATFORM.md)
- 🔒 [Security & Privacy Invariants](docs/SECURITY_PRIVACY.md)
- 📊 [Capabilities & Reality Matrix](docs/CAPABILITIES.md)
- 🧪 [Testing Architecture & Verification Matrix](docs/TESTING.md)
- 🗺️ [Product Roadmap](docs/ROADMAP.md)
- 🔄 [Database Migration Guide (Alembic)](docs/MIGRATION.md)
- 🔌 [Signal Gateway API Contract & Webhooks](docs/SIGNAL_API_CONTRACT.md)
- 📱 [Real Signal Environment Validation Guide](docs/REAL_SIGNAL_VALIDATION.md)
- 🔍 [v0.4 Reality Audit Report](docs/V04_REALITY_AUDIT.md)

---

## 🏗️ Architecture

```mermaid
flowchart TD
    subgraph Signal Gateway
        SG[Signal-CLI REST API]
    end

    subgraph Core Pipeline
        EV[Event Ingestion Pipeline]
        WQ[Bounded Worker Queue]
        PL[Partition Locking]
        OMS[Outbound Message Service]
    end

    subgraph AI Runtime
        AR[AgentRuntime Factory]
        LG[LangGraph StateGraph]
        RAG[Qdrant Scoped RAG]
        MEM[Durable Scoped Memory]
        MCP[MCP Tool Gateway]
    end

    subgraph Storage
        DB[(SQLite / PostgreSQL DB)]
        QD[(Qdrant Vector DB)]
    end

    SG -->|Webhook| EV
    EV --> WQ
    WQ --> PL
    PL --> AR
    AR --> LG
    LG --> RAG
    LG --> MEM
    LG --> MCP
    RAG --> QD
    MEM --> DB

    LG -->|Decision: Reply| OMS
    LG -->|Decision: Draft| DB
    OMS --> SG
```

---

## 🛠️ Local Development

### Backend Setup

```bash
cd backend

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies in editable mode
pip install -e ".[dev]"

# Run test suite and lint checks
pytest tests/ -v
ruff check app tests evals
ruff format --check app tests evals

# Run deterministic agent contract evaluation suite (32 cases)
python evals/run_evals.py

# Launch development server
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend

# Install Node dependencies
npm ci

# Run component test suites and linter
npm test
npm run lint
npx tsc --noEmit
npm run build

# Start development server with HMR
npm run dev
```

---

## 📊 Technical Specifications

| Layer | Technologies |
|---|---|
| **Backend Framework** | [FastAPI](https://fastapi.tiangolo.com/) 0.115+ (Asynchronous Python 3.11+) |
| **Agent Orchestration**| [LangGraph](https://github.com/langchain-ai/langgraph) + StateGraph + Progressive Skills |
| **Vector Store** | [Qdrant](https://qdrant.tech/) via official `qdrant-client` 1.10+ (`query_points`) |
| **Tool Protocol** | Official [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) Python SDK 2.x |
| **ORM & Database** | [SQLAlchemy](https://www.sqlalchemy.org/) 2.0 (AsyncIO) + [aiosqlite](https://github.com/omnilib/aiosqlite) + [Alembic](https://alembic.sqlalchemy.org/) linear migrations |
| **Frontend Stack** | [React](https://react.dev/) 18 + [Vite](https://vitejs.dev/) + [TypeScript](https://www.typescriptlang.org/) + [React Router](https://reactrouter.com/) 7.18+ |
| **Styling System** | [Tailwind CSS](https://tailwindcss.com/) + [DaisyUI](https://daisyui.com/) |
| **Security & Auth** | Scrypt KDF + [PyOTP](https://github.com/pyauth/pyotp) (TOTP 2FA) + [python-jose](https://github.com/mpdavis/python-jose) (JWT) |
| **Quality Gates** | [pytest](https://docs.pytest.org/) (75 passing tests) + [Vitest](https://vitest.dev/) (18 passing tests) + Deterministic AI eval (32 cases) |
| **Deployment** | Docker multi-stage builds + Docker Compose + GitHub Container Registry (GHCR) |

---

## 📄 License

This project is open-source software licensed under the [MIT License](LICENSE).
