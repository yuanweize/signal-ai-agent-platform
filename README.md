# 🤖 Signal Market Bot

A production-ready, open-source **Signal group market bot** with AI-powered customer service, automated sales, and a web admin dashboard.

## ✨ Features

- **Signal Integration** — Connects to Signal via [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) gateway. Verified and connected!
- **Multi-AI Provider** — Supports OpenAI, Azure, Tailscale AI Gateway, OpenRouter, Ollama, and any OpenAI-compatible API
- **Smart Sales** — AI assistant queries product catalog, handles inquiries, and processes orders (Fallback to generic text menu if AI is disabled)
- **Natural Language** — Localized conversational AI (Czech default) that sounds human, not robotic
- **Multi-Group** — Monitor and manage multiple Signal groups simultaneously
- **Memory** — Per-user conversation context for personalized interactions
- **Admin Dashboard** — Premium React Web UI featuring:
  - Sidebar Navigation with Overview, Products, Chat Logs, and Settings
  - Full CRUD Product Management
  - Mockups ready for real-time Chat Auditing and Manual Takeover
  - Dynamic AI settings toggle interface
- **Secure Admin** — Password authentication with TOTP 2FA fully implemented
- **Docker-First** — Fully containerized with Docker Compose for easy deployment

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────────┐    ┌─────────────────┐
│  Signal Network  │◄──►│  secured-signal-api   │◄──►│  Signal Market   │
│                  │    │  (signal-cli gateway) │    │     Bot          │
└─────────────────┘    └──────────────────────┘    │                  │
                                                    │  ┌──────────┐   │
                                                    │  │ AI Engine │   │
                                                    │  └──────────┘   │
                                                    │  ┌──────────┐   │
                                                    │  │  SQLite   │   │
                                                    │  └──────────┘   │
                                                    │  ┌──────────┐   │
                                                    │  │ Admin UI  │   │
                                                    │  └──────────┘   │
                                                    └─────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- A running [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) instance
- An AI API key (OpenAI, or any compatible provider)

### 1. Clone & Configure

```bash
git clone https://github.com/yuanweize/signal-market-bot.git
cd signal-market-bot
cp .env.example .env
```

Edit `.env` with your values:

```env
SIGNAL_API_URL=http://your-signal-api:8880
SIGNAL_API_TOKEN=your-bearer-token
SIGNAL_PHONE_NUMBER=+420123456789

AI_API_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-your-key
AI_MODEL=gpt-4o

ADMIN_PASSWORD=your-secure-password
JWT_SECRET_KEY=your-random-secret
```

### 2. Launch

```bash
docker compose up -d
```

### 3. Access

| Service | URL |
|---------|-----|
| Admin Dashboard | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |

### 4. Initialize Database

```bash
docker compose exec backend alembic upgrade head
```

## 🔧 Configuration

### AI Provider Setup

The bot supports **any OpenAI-compatible API**. Simply change `AI_API_BASE_URL`:

| Provider | Base URL |
|----------|----------|
| OpenAI | `https://api.openai.com/v1` |
| Azure OpenAI | `https://your-resource.openai.azure.com/openai/deployments/your-model` |
| Tailscale AI | `https://your-tailnet.ts.net/ai/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| Ollama (local) | `http://localhost:11434/v1` |
| vLLM | `http://localhost:8080/v1` |

### Admin 2FA Setup

```bash
# Generate TOTP secret
python -c "import pyotp; print(pyotp.random_base32())"
# Add the output to ADMIN_TOTP_SECRET in .env
# Scan the QR code with your authenticator app
```

## 🛠️ Development

### Backend (Python)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend (React)

```bash
cd frontend
npm install
npm run dev
```

## 📁 Project Structure

```
signal-market-bot/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   └── app/
│       ├── main.py          # FastAPI entry
│       ├── config.py         # Settings
│       ├── database.py       # SQLAlchemy
│       ├── models/           # ORM models
│       ├── schemas/          # Pydantic schemas
│       ├── services/         # Business logic
│       └── api/              # REST endpoints
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   └── src/                  # React app
└── data/                     # SQLite (mounted volume)
```

## 📝 License

[MIT](LICENSE) © IYUANWEIZE
