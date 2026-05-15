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
