# syntax=docker/dockerfile:1
# Multi-stage build for apps/candidate (Next.js 15 standalone). Listens
# on $PORT (defaults to 3001).
FROM oven/bun:1.3 AS deps
WORKDIR /repo
COPY package.json bun.lock turbo.json tsconfig.json biome.jsonc ./
COPY packages packages
COPY apps/candidate/package.json apps/candidate/package.json
RUN bun install

FROM node:22-alpine AS builder
RUN npm install -g bun
WORKDIR /repo
COPY --from=deps /repo /repo
# Intentionally do NOT copy .env.local. Build-time env files bake
# secrets into the image. Vercel and Cloud Run inject env vars at
# runtime; the Next.js build only needs NEXT_PUBLIC_* values that the
# host platform passes through normally.
COPY apps/candidate apps/candidate

# NEXT_PUBLIC_* values are inlined into the client bundle at build time.
# Defaults match env.ts so local docker builds work without --build-arg.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_CANDIDATE_URL=http://localhost:3001
# Empty default: single-host nginx-fronted prod sets this to "/a" so
# Next bakes /a/_next/... into the HTML and nginx routes those chunks
# back to candidate. Dev keeps it empty for vanilla localhost serving.
ARG NEXT_PUBLIC_CANDIDATE_ASSET_PREFIX=""
ARG NEXT_PUBLIC_SENTRY_DSN_CANDIDATE=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_CANDIDATE_URL=$NEXT_PUBLIC_CANDIDATE_URL
ENV NEXT_PUBLIC_CANDIDATE_ASSET_PREFIX=$NEXT_PUBLIC_CANDIDATE_ASSET_PREFIX
ENV NEXT_PUBLIC_SENTRY_DSN_CANDIDATE=$NEXT_PUBLIC_SENTRY_DSN_CANDIDATE

ENV SKIP_ENV_VALIDATION=true
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
