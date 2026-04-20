# 🤖 Signal Market Bot

Signal 群营销机器人（FastAPI + React），支持 AI 自动回复、人工接管、群发投放、用户管理、审计追踪、保留期清理，以及 Docker 一键部署。

## 当前版本

- 单一版本源：`backend/pyproject.toml` 的 `[project].version`
- 运行时 API 版本读取：`backend/app/version.py`
- 当前：请以 `python3 scripts/get_version.py` 输出为准

## ✨ 核心能力

- Signal Gateway 接入（轮询 + WS 回退）
- AI 回复（运行时配置、加密 API Key、动态开关）
- 商品管理（Products CRUD）
- 聊天审计（会话分页、手动接管发送、重试）
- 群投放 Campaign（dry-run、静默时段、最小间隔、黑名单）
- 用户管理 Users（分页搜索、编辑、批量封禁/解封、活动详情）
- 审计日志（登录、设置、接管、批量用户动作、投放）
- 指标与告警快照（拉取失败率、5xx 比例、处理时延）
- 数据治理（保留期清理 + 一键清空）

## 🚀 快速启动

```bash
git clone https://github.com/yuanweize/signal-market-bot.git
cd signal-market-bot
cp .env.example .env
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

访问：

- Admin: http://localhost:3000
- API: http://localhost:8000
- Docs: http://localhost:8000/docs

## ⚙️ 版本与发布规范

### 1) 版本只改一个地方

只修改 `backend/pyproject.toml`：

```toml
[project]
version = "<new-version>"
```

### 2) 本地检查

```bash
python3 scripts/get_version.py
python3 -m compileall backend/app
cd frontend && npm run build
```

### 3) 本地容器重建

```bash
./scripts/redeploy.sh
```

### 4) 镜像发布（GitHub Actions）

仓库已提供：

- `.github/workflows/ci.yml`：后端编译 + 前端构建
- `.github/workflows/docker-publish.yml`：推送到 GHCR

发布触发：

- push 到 `main`（发布 `latest` + 当前版本）
- push tag（如 `v<new-version>`）

GHCR 镜像：

- `ghcr.io/<owner>/signal-market-bot-backend`
- `ghcr.io/<owner>/signal-market-bot-frontend`

## 🧪 运行审计建议

- 未登录访问管理接口应返回 `401`
- `/health` 中 `version` 与 `backend/pyproject.toml` 保持一致
- Settings 修改 `bot_name` 后，`/health` 立即反映
- Users 批量封禁/解封后审计日志可检索
- Campaign dry-run 与实际发送结果可在 summary 中追踪

## 📁 目录说明

```text
backend/                 FastAPI 服务与业务逻辑
frontend/                React 管理台
scripts/get_version.py   统一版本读取脚本
scripts/redeploy.sh      本地重建部署脚本
.github/workflows/       CI + Docker 发布
```

## 📄 License

[MIT](LICENSE)
