# syntax=docker/dockerfile:1
# Multi-stage build for apps/admin (Next.js 15 standalone). Suitable for
# Cloud Run / Fly / Railway. Listens on $PORT (defaults to 3000).
FROM oven/bun:1.3 AS deps
WORKDIR /repo
COPY package.json bun.lock turbo.json tsconfig.json biome.jsonc ./
COPY packages packages
COPY apps/admin/package.json apps/admin/package.json
COPY apps/email/package.json apps/email/package.json
RUN bun install

FROM node:22-alpine AS builder
RUN npm install -g bun
WORKDIR /repo
COPY --from=deps /repo /repo
COPY .env.local* ./
COPY apps/admin apps/admin
ENV NEXT_TELEMETRY_DISABLED=1
ENV ANALYZE=false
RUN bun --filter admin build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
COPY --from=builder /repo/apps/admin/.next/standalone ./
COPY --from=builder /repo/apps/admin/.next/static ./apps/admin/.next/static

EXPOSE 3000
CMD ["node", "apps/admin/server.js"]
