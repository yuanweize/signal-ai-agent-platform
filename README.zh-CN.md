# Signal Market Bot（中文文档）

[![CI](https://img.shields.io/github/actions/workflow/status/yuanweize/signal-market-bot/ci.yml?branch=main&label=CI)](https://github.com/yuanweize/signal-market-bot/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

基于 Signal 通信协议的客服与电商管理机器人，包含 FastAPI 异步后端与 React 管理后台。

语言: [English](README.md) | **中文**

## 实际可用功能（Round 2 真实闭环）

| 功能 | 状态 | 工程与领域实现细节 |
|---|---|---|
| 首次安全初始化 | ✅ 可用 | 管理员创建 + 密码强哈希 + TOTP 动态口令 + JWT 认证 |
| Signal 事件摄取流水线 | ✅ 可用 | 有界队列（`maxsize=1000`）+ 4 协程工作池 + 会话分区锁（解耦 LLM 耗时，防止消息风暴） |
| 统一出站发送服务 | ✅ 可用 | `OutboundMessageService` 状态机（`pending -> sent / failed`）+ 失败显式重试机制 |
| 全功能管理收件箱 Inbox | ✅ 可用 | 双栏 `/inbox`、新消息置底、向上游标翻页、3秒实时轮询、多行 Shift+Enter 输入 |
| 人工接管与竞态消除 | ✅ 可用 | 消息发送前实时核验会话模式，若管理员在生成中切换为人工，丢弃 AI 回复（0 出站泄漏） |
| 用户多重身份统一 | ✅ 可用 | `user_identities` 表支持手机号与 UUID 多别名映射至唯一物理 `User` |
| 群组成员花名册与同步 | ✅ 可用 | `group_members` 模型记录成员与管理员角色；群组会话无单一归属所有人 |
| 纯表情 Reaction 与纯附件 | ✅ 可用 | 识别并持久化 Reaction 与 Attachment 事件，前端会话时间线完整渲染 |
| 服务端已读状态 | ✅ 可用 | `conversation_read_states` 记录 `last_read_message_id`，浏览器刷新不丢失未读状态 |
| 模块化设置与脱敏显示 | ✅ 可用 | 分解为 7 个模块标签卡片；所有密钥（API Key/Token）均在数据库与 UI 中脱敏保护 |
| 容错设备与个人资料 | ✅ 可用 | 解耦 `Promise.all` 为独立加载，网关设备接口故障不影响资料表单交互 |
| 科学数据库迁移验证 | ✅ 可用 | 连续迁移链（`112aa6e29383 -> c8927140f12a`），含全新库与 112aa6e 旧库自动升级测试 |
| 自动化全量测试套件 | ✅ 可用 | 54 项后端 pytest 测试 + 14 项前端 Vitest 组件与交互测试 |
| 订单 / 支付 | ⚠️ 仅有模型 | 数据库中仅包含骨架 ORM 模型，无业务逻辑、API 及 UI |
| 定时/自动化投放 | ⚠️ 仅支持广播 | 支持即时群发广播，未实现自主定时调度器 |

---

## 系统架构

- **后端**: FastAPI + SQLAlchemy（异步 AsyncIO）+ Alembic + 数据库驱动配置
- **事件流**: `asyncio.Queue` 有界并发消费、会话级锁保序
- **前端**: React + Vite + TypeScript + Tailwind + DaisyUI + Vitest
- **存储**: SQLite WAL 模式（默认路径：`data/bot.db`）
- **运行时配置**: 后台操作动态生效，不依赖 `.env`

---

## 快速启动

```bash
git clone https://github.com/yuanweize/signal-market-bot.git
cd signal-market-bot
docker compose pull
docker compose up -d
docker compose exec backend alembic upgrade head
```

服务端口：
- 管理后台: http://localhost:3000
- 核心 API: http://localhost:8000
- 存活探针: http://localhost:8000/health/live
- 就绪探针: http://localhost:8000/health/ready
- OpenAPI 接口文档: http://localhost:8000/docs

---

## 开发与测试验证

```bash
# 后端测试与 Lint
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
ruff check app tests
ruff format --check app tests

# 数据库迁移升级回归测试
pytest tests/test_migrations.py -v

# 前端构建、代码检查与 Vitest 单测
cd ../frontend
npm ci
npm run lint
npx tsc --noEmit
npm test
npm run build
```

---

## 核心文档清单

- [当前系统架构文档](docs/ARCHITECTURE_CURRENT.md)
- [目标演进架构规划](docs/ARCHITECTURE_TARGET.md)
- [功能真实性矩阵 (Round 2)](docs/FEATURE_REALITY_MATRIX.md)
- [全量测试矩阵](docs/TEST_MATRIX.md)
- [UI/UX 设计系统审计报告](docs/UI_UX_AUDIT.md)
- [数据库迁移指南](docs/MIGRATION.md)
- [Signal API 网关契约](docs/SIGNAL_API_CONTRACT.md)
- [真实 Signal 联调验收清单](docs/REAL_SIGNAL_VALIDATION.md)

---

## 许可证

MIT — 详见 [LICENSE](LICENSE)
