# Signal Market Bot（中文文档）

[![CI](https://img.shields.io/github/actions/workflow/status/yuanweize/signal-market-bot/ci.yml?branch=main&label=CI)](https://github.com/yuanweize/signal-market-bot/actions)
[![License](https://img.shields.io/github/license/yuanweize/signal-market-bot)](LICENSE)

Signal 销售机器人，包含 FastAPI 后端与 React 管理后台。

语言: [English](README.md) | **中文**

## 实际可用功能

| 功能 | 状态 |
|------|------|
| 首次安全初始化（密码 + TOTP + JWT） | ✅ 可用 |
| Signal 网关接入（WebSocket + HTTP 轮询回退） | ✅ 可用 |
| Signal 发送消息（DM 和群组） | ✅ 可用 |
| AI 自动回复（兼容 OpenAI 协议，运行时可配置） | ✅ 可用 |
| 人工接管（持久化 mode：auto/manual/paused） | ✅ 可用 |
| 封锁用户（在入站流水线中强制执行） | ✅ 可用 |
| 消息去重（重连安全） | ✅ 可用 |
| 出站消息状态机（pending→sent/failed） | ✅ 可用 |
| 群聊消息（每条消息正确归属发送者） | ✅ 可用 |
| AI 上下文（群组发送者姓名，当前消息不重复） | ✅ 可用 |
| 商品目录 + AI 注入 | ✅ 可用 |
| 群发投放（支持静默时段、黑名单、预演） | ✅ 可用 |
| 审计日志 | ✅ 可用 |
| 运行时配置（热重载，无需 .env） | ✅ 可用 |
| 仪表盘统计 | ✅ 可用 |
| 用户管理（封锁/解封、备注、语言） | ✅ 可用 |
| 群组同步（从 Signal 网关拉取） | ✅ 可用 |
| 设备管理（列表 + 取消链接） | ✅ 可用（需真实 Signal 账户） |
| 数据保留清理 | ✅ 可用 |
| Docker 部署 | ✅ 可用 |
| 数据库迁移（Alembic） | ✅ 可用 |
| 订单 / 支付 | ⚠️ 仅有数据模型，无 API 和 UI，不是已支持功能 |
| 定时/自动化群发 | ⚠️ 仅支持手动触发广播，无后台调度器 |
| 附件显示 | ⚠️ 记录元数据，无文件存储和预览 |

## 架构

- **后端**: FastAPI + SQLAlchemy（异步）+ Alembic + 数据库驱动配置
- **前端**: React + Vite + TypeScript + Tailwind + DaisyUI
- **存储**: SQLite（默认路径：`data/bot.db`）
- **运行时配置**: 管理后台操作，不依赖 `.env`

## 快速启动

```bash
git clone https://github.com/yuanweize/signal-market-bot.git
cd signal-market-bot
docker compose pull
docker compose up -d
docker compose exec backend alembic upgrade head
```

服务地址：
- 管理后台: http://localhost:3000
- API: http://localhost:8000
- OpenAPI 文档: http://localhost:8000/docs

## 首次初始化

首次访问 `/login` 时：
1. 设置管理员用户名和密码
2. 配置或自动生成 TOTP 密钥
3. 使用账号 + 密码 + 动态码登录

初始化仅执行一次，完成后入口关闭。

## 运行时配置（无 .env 依赖）

核心配置通过管理后台写入数据库：
- **Signal 配置**: `Settings → Signal Gateway`
- **AI 配置**: `Settings → AI Engine`
- **投放配置**: 静默时段、最小间隔、黑名单

密钥（AI key、Signal token、JWT signing secret）均加密存储。

## Signal 网关要求

本项目需要独立运行 [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api)。

## CORS 配置

生产环境请设置 `ALLOWED_ORIGINS` 环境变量：

```bash
ALLOWED_ORIGINS=https://your-admin-domain.example.com docker compose up -d
```

## 开发

```bash
# 后端
cd backend
pip install -e ".[dev]"
pytest tests/ -v

# 前端
cd frontend
npm ci && npm run build
npx tsc --noEmit

# 数据库迁移
cd backend && alembic upgrade head
```

## 已知外部依赖限制

以下功能需要真实 Signal 账户才能完整验证：
- 实际消息投递确认
- 设备列表 / 个人资料
- 已读回执、正在输入指示器
- 群组成员列表（来自 Signal 网络）

所有 Signal API 契约调用均有确定性 mock 测试（`tests/test_signal_gateway_contract.py`）。

## 相关文档

- [审计报告](docs/AUDIT_REPORT.md)
- [Signal API 契约](docs/SIGNAL_API_CONTRACT.md)
- [数据库迁移指南](docs/MIGRATION.md)

## License

MIT — 见 [LICENSE](LICENSE)
