# Deployment Skill (Mandatory)

## Rule
Default deployment should use prebuilt GHCR images:

```bash
docker compose pull
docker compose up -d
```

After **any** frontend/backend source code change (local development), run source-build mode:

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build frontend backend
```

## Why
- Prevent frontend-backend version drift
- Ensure new API/UI interactions are actually deployed
- Avoid "looks updated in code but not in runtime" incidents

## Quick command (source-build)
```bash
./scripts/redeploy.sh
```

## Verification checklist
1. `docker compose ps` shows `backend` healthy and `frontend` up.
2. `curl -s http://localhost:3000 | grep -Eo '/assets/index-[^" ]+'` returns latest bundle.
3. `curl -s http://localhost:8000/health` is `ok`.
4. Login, open Dashboard/Chat Logs/Settings and verify APIs return data.
