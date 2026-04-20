# Signal Market Bot — Handover (Current)

## 1) 当前状态

项目已从“原型阶段”进入“可发布阶段”：

- 后端：FastAPI + SQLAlchemy + SQLite
- 前端：React + Vite + Nginx
- 运行：Docker Compose
- 安全：JWT + TOTP 2FA + 登录限流 + 审计日志
- 运维：数据保留清理、指标快照、Campaign 策略护栏

已落地页面：

- `/` Dashboard
- `/products` 产品管理
- `/logs` 聊天审计/人工接管
- `/campaigns` 群发运营
- `/users` 用户管理（批量封禁/解封 + 活动详情）
- `/settings` 运行时配置

## 2) 版本治理（重点）

唯一版本源：

- `backend/pyproject.toml` -> `[project].version`

统一读取方式：

- 后端运行时通过 `backend/app/version.py` 读取版本
- `/health` 与 `/` 的 `version` 统一来自该版本

辅助脚本：

- `python scripts/get_version.py`

## 3) CI/CD 与容器发布

仓库工作流：

- `.github/workflows/ci.yml`
   - 后端：依赖安装 + `compileall`
   - 前端：`npm ci` + `npm run build`
- `.github/workflows/docker-publish.yml`
   - 读取统一版本
   - 构建并推送 GHCR 镜像：
      - `ghcr.io/<owner>/signal-market-bot-backend`
      - `ghcr.io/<owner>/signal-market-bot-frontend`

Dockerfile 已支持：

- `APP_VERSION` 构建参数
- OCI 镜像版本标签

## 4) 本地发布规范

代码变更后必须执行：

```bash
./scripts/redeploy.sh
```

并验证：

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:3000 | grep -Eo '/assets/index-[^" ]+'
```

## 5) 仍建议后续完善

1. 将登录限流从内存迁移到 Redis（重启不丢状态）
2. 增加数据库迁移脚本（当前依赖 `init_db` 自动建表）
3. 增加后端单元测试（Users/Campaigns/Settings 关键路径）
4. 增加基于 tag 的 Release Notes 自动发布

## 6) 交接给下位开发者的原则

- 先改版本，再发版（不要反过来）
- 不要在代码里硬编码版本号
- 所有管理动作都应产生日志（audit）
