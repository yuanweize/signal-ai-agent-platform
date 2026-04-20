# ============================================================
# Signal Market Bot — Frontend (Admin Dashboard)
# Multi-stage build: Node build → Nginx serve
# ============================================================

# ---- Build stage ----
FROM node:20-alpine AS build

WORKDIR /app

# Install dependencies first (cache layer)
COPY package.json package-lock.json* ./
RUN npm install

# Copy source and build
COPY . .
RUN npm run build

# ---- Production stage ----
FROM nginx:alpine AS production

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
