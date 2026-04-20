# Signal Market Bot（中文文档）

[![CI](https://img.shields.io/github/actions/workflow/status/yuanweize/signal-market-bot/ci.yml?branch=main&label=CI)](https://github.com/yuanweize/signal-market-bot/actions)
[![Docker Publish](https://img.shields.io/github/actions/workflow/status/yuanweize/signal-market-bot/docker-publish.yml?branch=main&label=Docker%20Publish)](https://github.com/yuanweize/signal-market-bot/actions)
[![License](https://img.shields.io/github/license/yuanweize/signal-market-bot)](LICENSE)

Signal Market Bot 是一个面向 Signal 场景的营销机器人系统，包含 FastAPI 后端与 React 管理后台，支持运行时配置、审计追踪与安全初始化。

语言: [English](README.md) | **中文**

## 项目价值

这个项目用于快速搭建 Signal 销售运营中台：

- 接收并处理用户消息
- AI 自动回复与人工接管并存
- 商品、用户、投放、审计统一管理
- 不依赖 `.env` 的后台运行时配置

## 目录导航

- [核心能力](#核心能力)
- [快速启动（预构建镜像）](#快速启动预构建镜像)
- [本地源码构建模式](#本地源码构建模式)
- [首次安全初始化](#首次安全初始化)
- [运行时配置模型](#运行时配置模型无-env-依赖)
- [发布与版本管理](#发布与版本管理)
- [文档质量工具建议](#文档质量工具建议)
- [目录说明](#目录说明)

## 核心能力

- Signal 网关接入（WebSocket 主链路 + HTTP 轮询回退）
- AI 自动回复（兼容 OpenAI 协议的多平台）
- 首次安全初始化（管理员密码 + TOTP + JWT 签名密钥）
- 商品管理、会话接管、群发投放、用户管理
- 审计日志、数据保留清理、运行指标
- Docker 一键部署 + GitHub Actions 持续集成与镜像发布

## 快速启动（默认使用 GHCR 预构建镜像）

```bash
git clone https://github.com/yuanweize/signal-market-bot.git
cd signal-market-bot
docker compose pull
docker compose up -d
docker compose exec backend alembic upgrade head
```

默认 `docker-compose.yml` 直接使用 GitHub Packages（GHCR）镜像：

- `ghcr.io/yuanweize/signal-market-bot-backend:<tag>`
- `ghcr.io/yuanweize/signal-market-bot-frontend:<tag>`

可指定版本：

```bash
APP_VERSION=0.2.0 docker compose pull
APP_VERSION=0.2.0 docker compose up -d
```

服务地址：

- 管理后台: http://localhost:3000
- API: http://localhost:8000
- OpenAPI 文档: http://localhost:8000/docs

## 本地源码构建模式

当你修改了本地代码，需要重新构建镜像时：

```bash
./scripts/redeploy.sh
```

等价命令：

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build frontend backend
```

## 首次部署初始化

首次访问 `/login` 时会进入一次性初始化流程：

1. 设置管理员密码
2. 配置或自动生成 TOTP Secret
3. 使用账号 + 密码 + 动态码登录

初始化完成后，该入口将关闭并进入常规登录。

## 运行时配置（无 .env 依赖）

本项目采用运行时配置模型，核心配置通过管理后台写入数据库：

- Signal 配置：`Settings -> Signal Gateway`
- AI 配置：`Settings -> AI Engine`
- 密钥信息（AI key、Signal token、JWT signing secret）采用加密存储
- 配置保存后立即生效（包含 Signal 监听器重载）

## 国际化支持

- 文档双语：英文 + 中文
- 机器人默认语言支持后台配置（`bot_default_language`）
- 管理端与 API 描述采用英语优先，便于国际团队协作
- 中文文档用于本地部署与运维说明

## 开发检查

后端检查：

```bash
python3 -m compileall backend/app
```

前端构建：

```bash
cd frontend
npm ci
npm run build
```

## 发布与版本管理

版本来源：

- `backend/pyproject.toml` 的 `[project].version`
- 读取脚本：`python3 scripts/get_version.py`

镜像发布流程：

- CI：`.github/workflows/ci.yml`
- Docker 发布：`.github/workflows/docker-publish.yml`
- GHCR 镜像：
	- `ghcr.io/<owner>/signal-market-bot-backend`
	- `ghcr.io/<owner>/signal-market-bot-frontend`

## 文档质量工具建议

建议对 README 引入自动化质量门禁：

- `markdownlint-cli2`：标题层级、列表规范、空行一致性
- `prettier`（Markdown）：统一格式，减少无意义 diff
- `lychee`：链接有效性检查（徽章/文档/外链）
- `vale`：英文文案质量与术语一致性

建议在 CI 中加入：

```bash
npx markdownlint-cli2 "**/*.md"
npx prettier -c "**/*.md"
npx lychee README.md README.zh-CN.md
```

## 目录说明

```text
backend/                  FastAPI 服务与业务逻辑
frontend/                 React 管理后台
scripts/redeploy.sh       本地部署脚本
scripts/get_version.py    版本读取脚本
.github/workflows/        CI 与镜像发布
```

## 相关文档

- 部署规范: [SKILL_DEPLOYMENT.md](SKILL_DEPLOYMENT.md)

## License

MIT — 见 [LICENSE](LICENSE)
