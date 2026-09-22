#!/bin/sh
set -e

# Run database migrations to head before starting the application
echo "==> Running Alembic migrations to head..."
alembic upgrade head

echo "==> Starting application..."
exec "$@"
