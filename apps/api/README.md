# `apps/api`: RI Assessments FastAPI service

FastAPI backend for the Revenue Institute Assessments Platform. Serves admin endpoints (Supabase JWT auth) and candidate magic-link endpoints (signed-token auth) per spec §14.

## Local development

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
cd apps/api
uv sync
cp .env.example .env.local   # then fill in values
uv run uvicorn ri_assessments_api.main:app --reload --port 8000
```

Or from repo root:

```sh
bun --filter api dev
```

## Layout

```
apps/api/
├── pyproject.toml
├── package.json                      Bun shim so Turborepo sees the workspace
├── Dockerfile                        Cloud Run image
├── scripts/
│   ├── apply_migrations.py           Applies packages/db/migrations/*.sql
│   ├── gen_schemas.py                Zod -> JSON Schema -> Pydantic codegen
│   └── seed_test_assignment.py       Creates a test assignment, prints magic-link URL
└── src/ri_assessments_api/
    ├── main.py                       FastAPI app entrypoint
    ├── worker.py                     Long-running scoring worker (Redis BRPOP loop)
    ├── config.py                     pydantic-settings, all env vars from spec §16
    ├── db.py                         Supabase service-role client
    ├── auth.py                       Supabase JWT + signed magic-link tokens
    ├── logging_config.py             Structured JSON logging + PII redaction
    ├── models/                       Hand-written Pydantic, kept in sync with @repo/schemas
    │   ├── admin.py                  module / assessment / assignment / attempt response shapes
    │   ├── benchmarks.py             cohort + competency rollup shapes
    │   ├── candidate.py              consent, heartbeat, event-batch, runner I/O shapes
    │   ├── generator.py              GenerationBrief, GeneratedOutline, QuestionTemplate
    │   └── interactive.py            CodeConfig, N8nConfig, NotebookConfig, DiagramConfig, SqlConfig
    ├── prompts/                      Python string templates for Claude system prompts
    │   ├── outline.py
    │   ├── questions.py
    │   ├── revision.py
    │   └── scoring.py
    ├── services/                     Business logic, called from routers
    │   ├── admin.py                  CRUD + role checks for admin surfaces
    │   ├── assignments.py            Create / cancel / resend / dispatch series
    │   ├── attempts.py               Server-authoritative timer, heartbeat, submit
    │   ├── benchmarks.py             Cohort + competency rollups
    │   ├── code_runner.py            E2B wrapper, sync `run_user_code` + async `run_user_code_streaming`
    │   ├── diagram_runner.py
    │   ├── email.py                  Resend client + webhook verifier
    │   ├── generator.py              Outline + question generation pipeline
    │   ├── integrity.py              Event ingest + score computation
    │   ├── n8n_runner.py             Shared-workspace provisioner + diff grader
    │   ├── notebook_runner.py
    │   ├── notebook_export.py
    │   ├── pii.py                    Redaction filter applied by logging_config
    │   ├── queue.py                  Redis LIST scoring queue (LPUSH / BRPOP)
    │   ├── randomizer.py             Seeded variable sampling + prompt rendering
    │   ├── references.py             Reference upload + embedding (text-embedding-3-small, 1024 dims)
    │   ├── scoring.py                Orchestrator: dispatches per rubric.scoring_mode
    │   ├── series.py                 Assessment series cadence + dispatch
    │   ├── solver_runner.py          Trusted-Python solver execution in E2B
    │   ├── sql_runner.py
    │   └── tokens.py                 Magic-link JWT sign + verify
    └── routers/                      One file per route group
        ├── admin.py                  /api/* admin endpoints, JWT auth
        ├── benchmarks.py             /api/cohorts/*, /api/subjects/{id}/competency-scores
        ├── candidate.py              /a/{token}/* magic-link endpoints (rate-limited)
        ├── debug.py                  Internal-only utilities (gated to local + admin)
        ├── generator.py              /api/generator/* (outline, questions, revise, preview-variants)
        ├── health.py                 /health liveness; /health/ready readiness
        ├── references.py             /api/references/*
        └── webhooks.py               /webhooks/resend (Svix-verified)
```

## Worker process

The scoring queue is a Redis LIST drained by a long-lived worker
process. In production, run it as a sibling Cloud Run service or
Cloud Run Job (not the public FastAPI service):

```sh
uv run python -m ri_assessments_api.worker
```

The worker reads `ri:scoring:jobs` via `BRPOP`, executes the relevant
runner grade, persists results, and emits SSE events to the admin
dashboard. Failures land on `ri:scoring:dlq` and are surfaced by the
`ri-rescore-dead-letter` cron documented in `DEPLOYMENT.md`.

## Database migrations

Migrations live in `packages/db/migrations/00NN_*.sql` and are applied
in lexical order by an idempotent helper that tracks state in
`public._migrations`:

```sh
# From repo root
bun --filter api migrate

# Or directly
cd apps/api && uv run python scripts/apply_migrations.py
```

See `DEPLOYMENT.md > Migration order` for a one-line description of
every migration in the current tree.

## End-to-end smoke test (candidate flow)

1. Provision a Supabase project. Grab `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, the project's `DATABASE_URL` (Settings → Database → Connection string → URI), and the anon key.
2. Fill `apps/api/.env.local` with at least:

   ```
   SUPABASE_URL=...
   SUPABASE_SERVICE_ROLE_KEY=...
   DATABASE_URL=postgresql://...
   JWT_SIGNING_SECRET=<random 32+ char string>
   NEXT_PUBLIC_CANDIDATE_URL=http://localhost:3001
   ```

3. Apply migrations and seed a test assignment:

   ```sh
   bun --filter api migrate
   bun --filter api seed
   ```

   The seed script prints a magic-link URL like `http://localhost:3001/a/<jwt>`.

4. Start the API and candidate apps in separate terminals:

   ```sh
   bun --filter api dev          # FastAPI on :8000
   bun --filter candidate dev    # Next.js on :3001
   ```

5. Open the magic-link URL. You should see the assessment landing page with subject name, module title, time limit, and a consent button. Clicking consent flips the assignment to `in_progress` server-side and redirects to the in-progress placeholder page.

## Schema policy

Spec §5 originally proposed generating Pydantic from `packages/schemas` (Zod) via JSON Schema. For v1 we deliberately keep Pydantic hand-authored under `src/ri_assessments_api/models/`. Reasons:

- Pydantic generated from JSON Schema produces awkward discriminated unions (the spec uses several `discriminatedUnion` calls).
- Hand-authored models let us add Pydantic-only validators, defaults, and computed fields without fighting the generator.
- Drift is caught at runtime by FastAPI's request validation and at review time by the schema-parity checklist below.

Sync discipline when changing a shared type:

1. Edit the canonical Zod model in `packages/schemas`.
2. Mirror the change in the matching Pydantic model under `apps/api/src/ri_assessments_api/models/`.
3. Note the spec section in the commit message so reviewers can confirm coverage.

Revisit this decision once the runner packages move out of `apps/api/services/` (spec §3) - at that point a generated Pydantic distributed alongside `@repo/schemas` becomes more attractive.
