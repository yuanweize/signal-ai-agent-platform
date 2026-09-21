# Signal Market Bot

[![CI](https://img.shields.io/github/actions/workflow/status/yuanweize/signal-market-bot/ci.yml?branch=main&label=CI)](https://github.com/yuanweize/signal-market-bot/actions)
[![Docker Publish](https://img.shields.io/github/actions/workflow/status/yuanweize/signal-market-bot/docker-publish.yml?branch=main&label=Docker%20Publish)](https://github.com/yuanweize/signal-market-bot/actions)
[![License](https://img.shields.io/github/license/yuanweize/signal-market-bot)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](backend/pyproject.toml)

Signal-based sales bot with FastAPI backend and React admin console.

Language: **English** | [中文](README.zh-CN.md)

## What Actually Works

| Feature | Status |
|---------|--------|
| First-run security bootstrap (password + TOTP + JWT) | ✅ Working |
| Signal gateway: WebSocket receive + HTTP polling fallback | ✅ Working |
| Signal send (DM and group) | ✅ Working |
| AI auto-reply (OpenAI-compatible, runtime configurable) | ✅ Working |
| Manual takeover (persisted mode: auto/manual/paused) | ✅ Working |
| Block user (enforced in inbound pipeline) | ✅ Working |
| Message deduplication (reconnect-safe) | ✅ Working |
| Outbound delivery state (pending→sent/failed) | ✅ Working |
| Group conversations (correct per-message attribution) | ✅ Working |
| AI context (sender names in group, no current-message duplication) | ✅ Working |
| Product catalog + AI injection | ✅ Working |
| Campaign broadcast (with quiet hours, blacklist, dry-run) | ✅ Working |
| Audit logs | ✅ Working |
| Runtime settings (hot-reload, no .env required) | ✅ Working |
| Dashboard stats | ✅ Working |
| User management (block/unblock, notes, language) | ✅ Working |
| Group sync from Signal gateway | ✅ Working |
| Devices list and unlink | ✅ Working (BLOCKED_EXTERNAL: requires real Signal account) |
| Data retention cleanup | ✅ Working |
| Docker deployment | ✅ Working |
| DB migrations (Alembic) | ✅ Working |
| Orders / Payments | ⚠️ DB models only — no API, no UI, not a supported feature |
| Campaign scheduling/automation | ⚠️ Broadcast on-demand only — no background scheduler |
| Attachment display | ⚠️ Metadata recorded, no file storage/preview |
| Read receipts / Typing indicators | ✅ Sent to gateway (BLOCKED_EXTERNAL: requires real Signal) |

## Architecture

- **Backend**: FastAPI + SQLAlchemy (async) + Alembic + runtime config in DB
- **Frontend**: React + Vite + TypeScript + Tailwind + DaisyUI
- **Storage**: SQLite (default: `data/bot.db`)
- **Runtime config**: managed from admin UI — no `.env` required for features

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
- OpenAPI docs: http://localhost:8000/docs

## First-Run Bootstrap

On first access to `/login`:
1. Set admin username and password
2. Configure TOTP secret (or auto-generate)
3. Login with username + password + TOTP code

Bootstrap is one-time and cannot be repeated after completion.

## Runtime Configuration

No `.env` required for application features. Configure via admin UI:

- **Signal Gateway**: `Settings → Signal Gateway` — API URL, phone number, auth token
- **AI Engine**: `Settings → AI Engine` — base URL, model, API key, system prompt
- **Campaign**: quiet hours, min interval, group blacklist

Secrets (AI key, Signal token, JWT signing secret) are encrypted at rest.

## Signal Gateway Requirements

This project requires [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) running separately.

- Tested against signal-cli-rest-api v0.x (see swagger.json)
- WebSocket endpoint: `ws://{host}/v1/receive/{number}`
- Send endpoint: `POST {host}/v2/send`
- Bearer token auth supported

## Development

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v

# Frontend
cd frontend
npm ci
npm run build
npx tsc --noEmit

# Migrations
cd backend
alembic upgrade head
alembic current
```

## CORS Configuration

Set `ALLOWED_ORIGINS` environment variable for production:

```bash
ALLOWED_ORIGINS=https://your-admin-domain.example.com docker compose up -d
```

Default (development only): `http://localhost:3000`

## Known External Limitations

The following features require a real Signal account and cannot be verified without one:

- Actual message delivery confirmation (gateway only returns HTTP 201)
- Device list / profile (gateway-dependent)
- Read receipts, typing indicators (sent but not confirmed)
- Group member lists (from Signal network)

All Signal API contract calls have deterministic mock tests (`tests/test_signal_gateway_contract.py`).

## Project Structure

```
backend/          FastAPI services, models, migrations, tests
frontend/         React admin dashboard
docs/             Audit report, architecture, migration guide, API contract
scripts/          Deployment helpers
.github/workflows/ CI (pytest + ruff + alembic + tsc + build)
```

## Additional Docs

- [Audit Report](docs/AUDIT_REPORT.md)
- [Signal API Contract](docs/SIGNAL_API_CONTRACT.md)
- [Migration Guide](docs/MIGRATION.md)
- [Deployment](SKILL_DEPLOYMENT.md)

## License

MIT — see [LICENSE](LICENSE)
