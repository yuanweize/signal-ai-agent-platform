# Signal Market Bot

[![CI](https://img.shields.io/github/actions/workflow/status/yuanweize/signal-market-bot/ci.yml?branch=main&label=CI)](https://github.com/yuanweize/signal-market-bot/actions)
[![Docker Publish](https://img.shields.io/github/actions/workflow/status/yuanweize/signal-market-bot/docker-publish.yml?branch=main&label=Docker%20Publish)](https://github.com/yuanweize/signal-market-bot/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](backend/pyproject.toml)

Signal-based sales and customer support bot with FastAPI backend and React admin console.

Language: **English** | [中文](README.zh-CN.md)

## What Actually Works (Round 2 Verified)

| Feature | Status | Implementation Details |
|---|---|---|
| First-run security bootstrap | ✅ Working | Password hashing + TOTP + JWT token authentication |
| Signal gateway ingestion | ✅ Working | Bounded queue (`maxsize=1000`), 4 workers, conversation partition locks |
| Signal send (DM & Group) | ✅ Working | Unified `OutboundMessageService`: `pending -> sent / failed` + explicit retry |
| Full-featured Admin Inbox | ✅ Working | Dual-pane `/inbox`, latest-first load, upward cursor pagination, real-time 3s poll |
| Manual takeover & race prevention | ✅ Working | Pre-send mode verification discards stale AI outbound if admin takes over |
| User Identity Unification | ✅ Working | `user_identities` table maps phones and UUIDs to a single canonical `User` |
| Group Membership & Roster Sync | ✅ Working | `group_members` domain tracks membership and admin roles; groups have no single owner |
| Inbound Reactions & Attachments | ✅ Working | Reaction-only and attachment-only Signal events persisted and rendered |
| Server-side Unread State | ✅ Working | `conversation_read_states` tracks `last_read_message_id`, persists on browser reload |
| Modular Settings & Masked Secrets | ✅ Working | 7-tab interface; API tokens and keys masked at rest and in the UI |
| Fault-tolerant Devices & Profile | ✅ Working | Independent fetch boundaries prevent gateway errors from crashing the page |
| Scientific DB Migrations | ✅ Working | Continuous chain (`112aa6e29383 -> c8927140f12a`), fresh & legacy DB automated tests |
| Automated Test Suites | ✅ Working | 54 backend pytest suites + 14 frontend Vitest suites |
| Orders / Payments | ⚠️ Model Only | Skeleton models in DB; no API/UI, not an active feature |
| Campaign Scheduling | ⚠️ Broadcast Only | On-demand broadcast supported; autonomous scheduler not implemented |

---

## Architecture

- **Backend**: FastAPI + SQLAlchemy (async) + Alembic + runtime config in DB
- **Event Pipeline**: `asyncio.Queue` bounded ingestion, concurrent partition locks
- **Frontend**: React + Vite + TypeScript + Tailwind + DaisyUI + Vitest
- **Storage**: SQLite with WAL mode (default: `data/bot.db`)
- **Runtime config**: Managed from admin UI — no `.env` required for core features

---

## Quick Start

```bash
git clone https://github.com/yuanweize/signal-market-bot.git
cd signal-market-bot
docker compose pull
docker compose up -d
docker compose exec backend alembic upgrade head
```

Services:
- Admin UI: http://localhost:3000
- API: http://localhost:8000
- Health live check: http://localhost:8000/health/live
- Health ready check: http://localhost:8000/health/ready
- OpenAPI docs: http://localhost:8000/docs

---

## Development & Testing

```bash
# Backend Testing & Linting
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
ruff check app tests
ruff format --check app tests

# Database Migration Tests
pytest tests/test_migrations.py -v

# Frontend Testing & Linting
cd ../frontend
npm ci
npm run lint
npx tsc --noEmit
npm test
npm run build
```

---

## Documentation

- [Current Architecture](docs/ARCHITECTURE_CURRENT.md)
- [Target Architecture Roadmap](docs/ARCHITECTURE_TARGET.md)
- [Feature Reality Matrix](docs/FEATURE_REALITY_MATRIX.md)
- [Test Matrix](docs/TEST_MATRIX.md)
- [UI/UX Audit](docs/UI_UX_AUDIT.md)
- [Database Migration Guide](docs/MIGRATION.md)
- [Signal API Gateway Contract](docs/SIGNAL_API_CONTRACT.md)
- [Real Signal Validation Checklist](docs/REAL_SIGNAL_VALIDATION.md)

---

## License

MIT — see [LICENSE](LICENSE)
