# ============================================================
# Signal AI Agent Platform — Frontend (Admin Dashboard)
# Multi-stage build: Node build → Nginx serve
# ============================================================

# ---- Build stage ----
FROM node:20-alpine AS build

ARG APP_VERSION=dev

WORKDIR /app

# Install dependencies first (cache layer)
COPY package.json package-lock.json* ./
RUN npm install

# Copy source and build
COPY . .
RUN npm run build

# ---- Production stage ----
FROM nginx:alpine AS production

ARG APP_VERSION=dev
LABEL org.opencontainers.image.title="signal-ai-agent-platform-frontend"
LABEL org.opencontainers.image.version="${APP_VERSION}"
LABEL org.opencontainers.image.description="Signal AI Agent Platform admin dashboard"
LABEL org.opencontainers.image.source="https://github.com/yuanweize/signal-ai-agent-platform"

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
