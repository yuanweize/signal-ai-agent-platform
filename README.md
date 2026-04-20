# Signal Market Bot

[![CI](https://img.shields.io/github/actions/workflow/status/yuanweize/signal-market-bot/ci.yml?branch=main&label=CI)](https://github.com/yuanweize/signal-market-bot/actions)
[![Docker Publish](https://img.shields.io/github/actions/workflow/status/yuanweize/signal-market-bot/docker-publish.yml?branch=main&label=Docker%20Publish)](https://github.com/yuanweize/signal-market-bot/actions)
[![License](https://img.shields.io/github/license/yuanweize/signal-market-bot)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](backend/pyproject.toml)

Production-ready Signal marketing assistant with FastAPI backend and React admin console.

Language: **English** | [中文](README.zh-CN.md)

## Why this project

Signal Market Bot helps operators run Signal-based sales workflows with secure admin controls, runtime AI configuration, campaign management, and audit visibility—without depending on `.env` for day-to-day operations.

## Table of Contents

- [Highlights](#highlights)
- [Quick Start (Prebuilt Images)](#quick-start-prebuilt-images)
- [Local Source Build Mode](#local-source-build-mode)
- [First-Run Security Bootstrap](#first-run-security-bootstrap)
- [Runtime Configuration Model](#runtime-configuration-model)
- [Release and Image Versioning](#release-and-image-versioning)
- [Documentation Tooling Recommendations](#documentation-tooling-recommendations)
- [Project Structure](#project-structure)

## Highlights

- Signal gateway integration with WebSocket primary + HTTP polling fallback
- Runtime-configurable AI engine (OpenAI-compatible providers)
- First-run secure bootstrap (password + TOTP + JWT signing secret)
- Product catalog, chat takeover, campaign broadcast, and user management
- Audit trail, retention cleanup, and operational metrics
- Docker-first deployment with CI and GHCR publish workflows

## Architecture

- Backend: FastAPI + SQLAlchemy + Alembic + runtime config in database
- Frontend: React + Vite + TypeScript
- Storage: SQLite by default (`data/bot.db`)
- Runtime config: managed from admin UI (no `.env` file required)

## Quick Start (Prebuilt Images)

```bash
git clone https://github.com/yuanweize/signal-market-bot.git
cd signal-market-bot
docker compose pull
docker compose up -d
docker compose exec backend alembic upgrade head
```

By default, `docker-compose.yml` uses prebuilt GHCR images:

- `ghcr.io/yuanweize/signal-market-bot-backend:<tag>`
- `ghcr.io/yuanweize/signal-market-bot-frontend:<tag>`

Set a version tag if needed:

```bash
APP_VERSION=0.2.0 docker compose pull
APP_VERSION=0.2.0 docker compose up -d
```

Service endpoints:

- Admin: http://localhost:3000
- API: http://localhost:8000
- OpenAPI: http://localhost:8000/docs

## Local Source Build Mode

Use this when you changed backend/frontend code locally:

```bash
./scripts/redeploy.sh
```

Equivalent command:

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build frontend backend
```

## First-Run Security Bootstrap

On first access to `/login`, you will see one-time bootstrap initialization.

1. Set admin password
2. Provide or auto-generate a TOTP secret
3. Login with username/password/TOTP

After bootstrap is completed, login works in normal mode and setup is disabled.

## Runtime Configuration Model

This project is runtime-driven and does not require `.env` for application features.

- Signal settings are managed in `Settings -> Signal Gateway`
- AI settings are managed in `Settings -> AI Engine`
- Secrets (AI key / Signal token / JWT signing secret) are stored encrypted in DB-backed config
- Changes apply immediately (including Signal listener reconfiguration)

## Internationalization

- Documentation is bilingual: English + Chinese
- Bot default language is configurable in admin settings (`bot_default_language`)
- UI and API text are English-first for global operator teams
- Chinese docs are maintained for local onboarding and operations

## Development Checks

Backend checks:

```bash
python3 -m compileall backend/app
```

Frontend build:

```bash
cd frontend
npm ci
npm run build
```

## Release and Image Versioning

Version source of truth:

- `backend/pyproject.toml` -> `[project].version`
- helper script: `python3 scripts/get_version.py`

GitHub workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/docker-publish.yml`

Published images:

- `ghcr.io/<owner>/signal-market-bot-backend`
- `ghcr.io/<owner>/signal-market-bot-frontend`

## Documentation Tooling Recommendations

Recommended tooling for GitHub-grade README quality:

- `markdownlint-cli2`: heading hierarchy, spacing, list style consistency
- `prettier --parser markdown`: stable formatting and diff cleanliness
- `lychee`: dead link detection (badges, docs links, external references)
- `vale`: writing quality and terminology consistency (English docs)
- GitHub Actions gate: run markdown/link checks on PRs before merge

Suggested CI commands:

```bash
npx markdownlint-cli2 "**/*.md"
npx prettier -c "**/*.md"
npx lychee README.md README.zh-CN.md
```

## Project Structure

```text
backend/                  FastAPI services and domain logic
frontend/                 React admin dashboard
scripts/redeploy.sh       local deploy helper
scripts/get_version.py    canonical version reader
.github/workflows/        CI and container publish
```

## Additional Docs

- Deployment routine: [SKILL_DEPLOYMENT.md](SKILL_DEPLOYMENT.md)

## License

MIT — see [LICENSE](LICENSE)
