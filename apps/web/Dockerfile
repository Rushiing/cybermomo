# CyberMOMO Web · Next.js 14 (App Router)
#
# Railway service 配置:
#   - Root Directory: apps/web
#   - Builder: Dockerfile(自动检测)
#   - Variables:
#       NEXT_PUBLIC_API_URL=https://cybermomo-production.up.railway.app
#       NEXT_PUBLIC_DEV_MOCK_AUTH=false   # prod 关掉 mock auth fallback,藏 DEV banner
#       PORT 由 Railway 自动注入
#
# 关键:NEXT_PUBLIC_* 必须在 BUILD 时就有,Next.js 会 bake 进 client bundle。
# Railway service Variables 在 Dockerfile build 阶段可用,所以这块没问题。

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json ./
# 没有 lockfile 就生成一个;有就用
COPY package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install --no-audit --no-fund; fi

FROM node:20-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL
# 默认 false(audit P0-3):build 默认安全,本地联调需显式 --build-arg NEXT_PUBLIC_DEV_MOCK_AUTH=true
ARG NEXT_PUBLIC_DEV_MOCK_AUTH=false
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_DEV_MOCK_AUTH=${NEXT_PUBLIC_DEV_MOCK_AUTH}
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# === Runtime 镜像(用 standalone 输出,镜像更小)===
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Next.js standalone 模式产物
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
# server.js 读 PORT(Railway 会注入)
CMD ["sh", "-c", "node server.js"]
