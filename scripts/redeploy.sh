#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${APP_VERSION:-}" ]]; then
	APP_VERSION="$(python3 scripts/get_version.py)"
fi
export APP_VERSION

echo "[deploy] rebuilding frontend + backend..."
docker compose up -d --build frontend backend

echo "[deploy] done"
docker compose ps
