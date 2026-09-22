# ============================================================
# Signal Market Bot — Backend
# Multi-stage build for minimal image size
# ============================================================

FROM python:3.12-slim AS base

ARG APP_VERSION=dev

# Prevent Python from writing .pyc and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ---- Dependencies stage ----
FROM base AS deps

# Install build tools for native extensions
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[prod]"

# ---- Runtime stage ----
FROM base AS runtime

ARG APP_VERSION=dev
LABEL org.opencontainers.image.title="signal-market-bot-backend"
LABEL org.opencontainers.image.version="${APP_VERSION}"
LABEL org.opencontainers.image.description="Signal Market Bot backend API"

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Create data directory and ensure entrypoint script permissions
RUN mkdir -p /app/data && chmod +x /app/entrypoint.sh

EXPOSE 8000

# Run migrations then start uvicorn
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
