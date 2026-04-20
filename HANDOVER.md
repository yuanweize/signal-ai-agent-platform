# 🚀 Handover Document: Signal Market Bot Phase 6 & Beyond

Welcome to the **Signal Market Bot** project! 

The system has successfully completed Phase 5, achieving a fully operational Signal connection, a functioning fallback menu, and a premium React-based dashboard. This document serves as your technical blueprint to continue the backend integration.

---

## 🏗️ Architecture Status

The project consists of a **FastAPI backend** (SQLite DB, SQLAlchemy) and a **React + Vite frontend**. They communicate securely using JWT tokens.

### ✅ What works perfectly right now:
1. **Authentication & Security:**
   - Secure login via `/api/v1/auth/login`.
   - TOTP 2FA is fully integrated. If `ADMIN_TOTP_SECRET` is defined in `.env`, the UI enforces the 2FA flow.
   - Frontend route guarding and 401 Unauthorized handling are robust (automatically redirects expired sessions without endless loops).

2. **Signal API Gateway Connection:**
   - `signal_client.py` continuously polls the `secured-signal-api` (`http://100.90.182.100:8880`).
   - Receiving and sending messages works.
   - **Important:** We have implemented a **Fallback mechanism**. If the AI is disabled (`FEATURE_AI_ENABLED=false` in `.env`), `message_handler.py` outputs a structured hardcoded menu.

3. **Dashboard UI Structure (React SPA):**
   - **`SidebarLayout.tsx`**: Provides consistent, premium sidebar navigation.
   - **Overview (`/`)**: Displays real-time API connection health and database statistics.
   - **Products (`/products`)**: A fully wired CRUD interface for managing the product catalog.
   - **Chat Logs (`/logs`)**: A WhatsApp-style UI for reading AI conversations. *(Currently Mock UI)*
   - **Settings (`/settings`)**: A UI for managing API Keys, Prompts, and Feature Toggles. *(Currently Mock UI)*

---

## 🎯 Next Steps for Future Agents

Your mission is to connect the newly built UI components (`/logs` and `/settings`) to the FastAPI backend and SQLite database. 

### 1. Database & Dynamic Settings
**Goal:** Wire the `/settings` page to a persistent database store so configs can be changed without restarting the server.
*Currently, settings exist only in `.env` and are injected at runtime via `config.py`.*
- [ ] Create a `settings` table in the database (or use a JSON blob row) to store dynamic configs: `ai_prompt`, `is_ai_enabled`, `is_market_enabled`, `ai_api_key`.
- [ ] Create backend endpoints `GET /api/v1/settings` and `PUT /api/v1/settings` (suggested file: `app/api/settings.py`).
- [ ] Modify `frontend/src/api.ts` to call these new endpoints instead of managing local React state.
- [ ] Modify `message_handler.py` and `ai_engine.py` to fetch dynamic settings from the DB on the fly, replacing static reads from `config.py`.

### 2. Chat Logs Audit System
**Goal:** Make the `/logs` page display real, live chat histories.
*Currently, `ChatLogsPage.tsx` uses hardcoded dummy arrays.*
- [ ] Expand the database models (`models/chat.py` or similar) to ensure every incoming and outgoing message handled by `message_handler.py` is logged to `conversations` and `messages` tables.
- [ ] Build backend endpoints:
  - `GET /api/v1/chats` (List all recent conversations/contacts)
  - `GET /api/v1/chats/{number}/messages` (List chronological messages for a specific user)
- [ ] Update `ChatLogsPage.tsx` to fetch this data instead of `MOCK_CONTACTS` and `MOCK_MESSAGES`.
- [ ] **Bonus:** Implement "Manual Takeover" — an endpoint `POST /api/v1/chats/{number}/send` that calls `signal_client.send_message` so the admin can step in and chat directly from the dashboard.

### 3. Product & Order Flow Expansion
**Goal:** Complete the Market Loop.
*Currently, you can create products in the UI, but the AI lacks a fully robust system for placing actual orders.*
- [ ] Ensure the AI Engine (`ai_engine.py`) has specific tool-call access to a "Create Order" function.
- [ ] Create an `orders` table in the SQLite database linking a user's phone number to specific `product_ids` and total pricing.
- [ ] Create an `Orders` view in the React Dashboard (perhaps under a new sidebar link) to let the admin track and update order status (e.g., Pending -> Paid -> Shipped).

---

## 📝 Important Notes for the Next Agent

- **Code Location:** `/Users/yuanweize/我的文档/服务器/GITHUB/signal-market-bot/`
- **Starting Point:** Check `app/main.py` and the existing API endpoints in `app/api/auth.py` and `app/api/market.py` to understand the routing structure.
- **Frontend Styling:** Please preserve the premium aesthetic structure of the React app. Stick to the CSS classes and variables already defined in `frontend/src/index.css`.
- **Database Migrations:** Use Alembic! If you add a table (like `settings` or `orders`), run:
  ```bash
  docker compose exec backend alembic revision --autogenerate -m "Add settings table"
  docker compose exec backend alembic upgrade head
  ```

Good luck! The foundation is solid, you are clear for takeoff. 🚀
