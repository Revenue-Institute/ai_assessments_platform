# `apps/api` — RI Assessments FastAPI service

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
│   ├── seed_test_assignment.py       Creates a test assignment, prints magic-link URL
│   └── gen_schemas.py                Zod → Pydantic codegen (TODO)
└── src/ri_assessments_api/
    ├── main.py                       FastAPI app entrypoint
    ├── config.py                     pydantic-settings, all env vars from spec §16
    ├── db.py                         Supabase service-role client
    ├── auth.py                       Supabase JWT + signed magic-link tokens
    ├── models/                       Hand-written Pydantic (until codegen lands)
    ├── services/                     Token, assignment, etc. business logic
    ├── routers/                      one file per route group
    └── generated/                    Pydantic generated from @repo/schemas (gitignored)
```

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

## Schema codegen

Pydantic models for shared types are generated from `packages/schemas` (Zod) per spec §5. The generator is not yet implemented (TODO); `src/ri_assessments_api/generated/` is intentionally empty until the Zod → JSON Schema → Pydantic pipeline lands. Hand-written Pydantic models live in `src/ri_assessments_api/models/` until then.
