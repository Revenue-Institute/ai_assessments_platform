# Revenue Institute Assessments Platform

Internal platform for AI-generated, interactive assessments. Recruiting screens for external candidates and longitudinal benchmarks for the internal team. Assessments are assembled by Claude, randomized per attempt, executed in real interactive runners (code, n8n, notebooks, SQL, diagrams), scored by Claude with rubrics, and rolled up into per-competency dashboards.

Tech stack: Next.js 15 (admin + candidate) on Vercel, FastAPI on Cloud Run, Supabase Postgres with pgvector, Upstash Redis for the scoring queue, E2B sandboxes for code execution, self-hosted n8n, Resend for transactional email, Anthropic Claude for generation and scoring, OpenAI for reference embeddings.

See [specs/requirements.md](specs/requirements.md) for the v1 spec, [CLAUDE.md](CLAUDE.md) for engineering notes and recorded divergences, and [DEPLOYMENT.md](DEPLOYMENT.md) for ops and provisioning.

## Quickstart

See the "Local dev quickstart" section of [DEPLOYMENT.md](DEPLOYMENT.md#local-dev-quickstart). The short version:

```sh
bun install
cd apps/api && uv sync && cd ../..
cp .env.example .env.local
bash scripts/link-env.sh
bun run dev:full
```

## Running with Docker

Docker brings up the full local stack: FastAPI, admin (Next.js :3000), candidate (Next.js :3001), n8n (:5678), and Redis. Supabase and all SaaS providers stay external.

**1. Fill in environment variables**

```sh
cp .env.example .env.local
```

Open `.env.local` and set at minimum:

| Variable | Where to find it |
| :-- | :-- |
| `SUPABASE_URL` | Supabase dashboard - Settings - API |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase dashboard - Settings - API |
| `NEXT_PUBLIC_SUPABASE_URL` | Same as `SUPABASE_URL` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase dashboard - Settings - API |
| `JWT_SIGNING_SECRET` | Any 32+ char random string |
| `SESSION_COOKIE_SECRET` | Any 32+ char random string |

**2. Symlink the env file into each app**

```sh
bash scripts/link-env.sh
```

This creates `apps/admin/.env.local`, `apps/candidate/.env.local`, and `apps/api/.env.local` as symlinks pointing to the root file. One file, no duplication.

**3. Build and start**

```sh
docker compose --env-file .env.local up -d --build
```

The `--env-file` flag is required so Docker Compose can pass the Supabase public keys as build args into the Next.js bundles at compile time.

**4. Apply migrations and seed**

```sh
bun --filter api migrate
bun --filter api seed     # prints a magic-link URL for the candidate app
```

**5. n8n first-run**

On first boot, n8n prints a one-time signup URL in its log (`docker compose logs n8n`). Create an owner account, then go to Settings - API and generate a personal API key. Add it to `.env.local` as `N8N_ADMIN_API_KEY` and restart: `docker compose restart api`.

## Apps

- `apps/admin` (Next.js, :3000) - internal dashboard. See [apps/admin/README.md](apps/admin/README.md).
- `apps/candidate` (Next.js, :3001) - magic-link assessment runner. See [apps/candidate/README.md](apps/candidate/README.md).
- `apps/api` (FastAPI, :8000) - backend services. See [apps/api/README.md](apps/api/README.md).

## Quality gates

```sh
bun run check        # ultracite, check-copy (no em/en dashes), check-boundaries
bun run typecheck    # turbo typecheck across the workspace
bun run test         # turbo test across the workspace
bun run check:all    # check + typecheck + test in one command
```
