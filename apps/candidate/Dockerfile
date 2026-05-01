# syntax=docker/dockerfile:1
# Multi-stage build for apps/candidate (Next.js 15 standalone). Listens
# on $PORT (defaults to 3001).
FROM oven/bun:1.3 AS deps
WORKDIR /repo
COPY package.json bun.lock turbo.json tsconfig.json biome.jsonc ./
COPY packages packages
COPY apps/candidate/package.json apps/candidate/package.json
COPY apps/email/package.json apps/email/package.json
RUN bun install

FROM node:22-alpine AS builder
RUN npm install -g bun
WORKDIR /repo
COPY --from=deps /repo /repo
COPY .env.local* ./
COPY apps/candidate apps/candidate
ENV NEXT_TELEMETRY_DISABLED=1
RUN bun --filter candidate build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3001
COPY --from=builder /repo/apps/candidate/.next/standalone ./
COPY --from=builder /repo/apps/candidate/.next/static ./apps/candidate/.next/static
EXPOSE 3001
CMD ["node", "apps/candidate/server.js"]
