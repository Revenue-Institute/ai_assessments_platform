# Deployment & Operations

How to stand up the Revenue Institute Assessments Platform end-to-end.
Owner: ops + engineering. Last reviewed against `specs/requirements.md`
phases 0 through 5.

## Production readiness checklist

Run through this before flipping DNS at `assessments.revenueinstitute.com`.
Every secret listed must be a freshly rotated value, set in the platform
env block (Vercel for `apps/admin` and `apps/candidate`, Cloud Run for
`apps/api`), and never the same string as the development copy in
`.env.local`.

### Secrets to rotate and set

| Secret | Where set | How to rotate |
|---|---|---|
| `SUPABASE_SERVICE_ROLE_KEY` | Vercel admin, Cloud Run api | Supabase dashboard > Settings > API > Regenerate `service_role`. |
| `SUPABASE_JWT_SECRET` | Cloud Run api | Supabase dashboard > Settings > API > JWT Settings > Rotate. Triggers admin re-login. |
| `DATABASE_URL` | Cloud Run api | Supabase dashboard > Settings > Database > Connection string. Rotate the DB password under the same screen. |
| `ANTHROPIC_API_KEY_GENERATION` | Cloud Run api | https://console.anthropic.com/settings/keys -> create new, delete old. |
| `ANTHROPIC_API_KEY_SCORING` | Cloud Run api | Same dashboard, separate key for cost attribution. |
| `E2B_API_KEY` | Cloud Run api | https://e2b.dev/dashboard > API Keys. |
| `N8N_ADMIN_API_KEY` | Cloud Run api | n8n self-hosted UI > Settings > API > revoke + regenerate. |
| `RESEND_API_KEY` | Cloud Run api | https://resend.com/api-keys. |
| `RESEND_WEBHOOK_SECRET` | Cloud Run api + Resend dashboard | Resend > Webhooks > rotate signing secret; paste the same value on both sides. |
| `JWT_SIGNING_SECRET` | Cloud Run api | `openssl rand -hex 32`. Invalidates outstanding magic-links. |
| `SESSION_COOKIE_SECRET` | Vercel admin | `openssl rand -hex 32`. Forces admin re-login. |
| `OPENAI_API_KEY` | Cloud Run api | https://platform.openai.com/api-keys (embedding-only key recommended). |
| `SENTRY_AUTH_TOKEN` | Vercel admin + candidate, Cloud Run api | Sentry > User Settings > Auth Tokens (`project:releases` scope). |

### Sentry projects (one per surface)

Spec §15 + §16 require three independent Sentry projects so a flood of
errors on one app cannot drown out the others.

| App | Project slug | DSN env var | Reads from |
|---|---|---|---|
| admin (Next.js) | `ri-admin` | `NEXT_PUBLIC_SENTRY_DSN_ADMIN` | `apps/admin/sentry.{client,server,edge}.config.ts` |
| candidate (Next.js) | `ri-candidate` | `NEXT_PUBLIC_SENTRY_DSN_CANDIDATE` | `apps/candidate/sentry.{client,server,edge}.config.ts` |
| api (FastAPI) | `ri-api` | `SENTRY_DSN_API` | `apps/api/src/ri_assessments_api/main.py` |

Creation runbook: in the RI Sentry org, click "Create Project" three
times, picking the Next.js platform for `ri-admin` and `ri-candidate`
and the Python/FastAPI platform for `ri-api`. Copy the Client Key (DSN)
shown after creation into the matching env var. Generate one Auth Token
under User Settings > Auth Tokens with the `project:releases` scope and
paste it as `SENTRY_AUTH_TOKEN` in every build environment that should
ship source maps (Vercel admin, Vercel candidate, the GitHub Actions
deploy job for the API). Confirm by deploying once and verifying events
land in the right project; if an admin error appears under
`ri-candidate`, the DSN env var on the admin deployment is wrong. The
fallback `NEXT_PUBLIC_SENTRY_DSN` is still honored by
`packages/observability/keys.ts#resolveSentryDsn` for deployments that
have not migrated.

### Email + DNS

- Configure SPF, DKIM, and DMARC on the `assessments.revenueinstitute.com`
  subdomain per Resend's domain-verification wizard. Production deploys
  will not be allowed to send until DKIM is green.
- Set `RESEND_FROM_EMAIL=assessments@revenueinstitute.com`.
- `TRUSTED_PROXY_IPS` must be set on the Cloud Run service to the
  comma-separated egress CIDRs of the upstream load balancer so the API
  can trust `X-Forwarded-For` when computing `attempt_events.ip_hash`.

## Quickstart (production)

```sh
# 1. Clone + install local deps
git clone https://github.com/Revenue-Institute/ai_assessments_platform
cd ai_assessments_platform
bun install
cd apps/api && uv sync && cd ../..

# 2. Provision Supabase (link, push migrations, seed taxonomy)
SUPABASE_PROJECT_REF=<your-ref> bash scripts/setup-supabase.sh

# 3. Fill the consolidated .env at repo root
cp .env.example .env
$EDITOR .env

# 4. Verify every required variable is set
bash scripts/check-env.sh all

# 5. Deploy n8n to Cloud Run; paste the resulting URL into .env as N8N_HOST
N8N_ENCRYPTION_KEY=$(openssl rand -hex 32) \
N8N_HOSTNAME=ri-n8n-xxx.a.run.app \
GCP_PROJECT=<id> GCP_REGION=us-central1 \
bash infra/cloud-run/deploy-n8n.sh

# 6. Deploy FastAPI to Cloud Run
GCP_PROJECT=<id> GCP_REGION=us-central1 \
bash infra/cloud-run/deploy-api.sh

# 7. (Optional) Cron the series next-due dispatcher
GCP_PROJECT=<id> GCP_REGION=us-central1 \
API_URL=https://ri-assessments-api-xxx.a.run.app \
ADMIN_JWT=<service-account JWT signed with SUPABASE_JWT_SECRET> \
bash infra/scheduler/series-cron.sh

# 8. Connect Vercel projects (one-time, dashboard):
#    - Repo: this monorepo
#    - Root Directory: apps/admin (and a second project for apps/candidate)
#    - Env vars: copy from .env

# 9. Set GitHub Actions secrets (see CI/CD section below); future pushes
#    to main auto-deploy the API + both Vercel apps.
```

## CI/CD

| Workflow | Trigger | What it does |
|---|---|---|
| `.github/workflows/ci.yml` | PR + push to main | ruff + pytest on `apps/api`; bun typecheck + vitest on admin and `@repo/integrity`; `bun run check` (ultracite + check-copy + check-boundaries); schema codegen drift check; non-blocking `pip-audit` + `bun audit` security scan |
| `.github/workflows/deploy-api.yml` | push to main (api / db / infra paths) | Cloud Build, then Cloud Run deploy of FastAPI |
| `.github/workflows/deploy-frontend.yml` | push to main (frontend paths) | Vercel `pull`, `build`, `deploy` for admin + candidate |

Required GitHub repo secrets:

```
GCP_PROJECT, GCP_REGION
GCP_WORKLOAD_IDENTITY        # workload-identity provider path
GCP_SERVICE_ACCOUNT          # service account email with run.admin + storage.admin
API_ENV_VARS                 # KEY=VALUE\n KEY=VALUE\n ... block for FastAPI

VERCEL_TOKEN
VERCEL_ORG_ID
VERCEL_ADMIN_PROJECT_ID
VERCEL_CANDIDATE_PROJECT_ID
```

## 1. External services to provision

| Service | Why | Notes |
|---|---|---|
| Supabase project | Postgres + Auth + Storage + pgvector | Enable the `vector` extension in the SQL editor before running migrations. |
| Anthropic API | Generation + scoring (Claude Sonnet 4.6 default) | Two API keys recommended for cost attribution: one for generation, one for scoring. |
| E2B | Code / SQL / notebook sandboxes | Paid plan recommended for production quotas. |
| OpenAI | Reference-library embeddings (text-embedding-3-small, 1024 dims) | Matryoshka truncation via the `dimensions` parameter. The reference column is `vector(1024)`; switch providers only if you also alter the column. |
| Resend | Magic-link + result notifications | Configure SPF + DKIM on a subdomain (e.g. `assessments.revenueinstitute.com`). |
| Upstash Redis | BullMQ backing store (when async scoring lands) | Local docker-compose uses redis:alpine. |
| n8n (self-hosted) | Workflow assessments | docker-compose ships this; in production run on Cloud Run with a persistent volume. |
| Sentry | Error tracking | One project per app. `@repo/observability` is already wired. |
| Axiom (or similar) | Log ingestion | Stream from FastAPI + Vercel. |

## 2. Required env vars

**Local dev, single source of truth.** Copy `.env.example` at the repo
root to `.env.local`, fill in your values, then run:

```sh
cp .env.example .env.local
bash scripts/link-env.sh
```

That symlinks `apps/admin/.env.local`, `apps/candidate/.env.local`, and
`apps/api/.env` to the root file. Edit one file, all three apps see the
update. Re-run the script if you ever clone fresh or if a symlink gets
overwritten.

**Production deploy:** set vars per service in the host (Vercel
project settings for admin/candidate, Cloud Run service env for the
API). Do not ship `.env.local` to production.

Spec §16 has the canonical variable list. Highlights below.

**`apps/api/.env.example`** (FastAPI on Cloud Run). Critical:
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`,
  `DATABASE_URL`
- `JWT_SIGNING_SECRET` (32+ random chars; signs candidate magic-links)
- `ANTHROPIC_API_KEY_GENERATION`, `ANTHROPIC_API_KEY_SCORING`
- `E2B_API_KEY`
- `OPENAI_API_KEY`, `EMBEDDING_MODEL=text-embedding-3-small`, `EMBEDDING_DIMS=1024`
- `RESEND_API_KEY`, `RESEND_FROM_EMAIL=assessments@revenueinstitute.com`
- `RESEND_WEBHOOK_SECRET` (HMAC for `POST /webhooks/resend`; paste the
  same value into Resend's webhook signing-secret field)
- `N8N_HOST`, `N8N_ADMIN_API_KEY`, `N8N_WEBHOOK_SECRET`
- `NEXT_PUBLIC_CANDIDATE_URL` (used to build magic-link URLs in emails)
- `SUPABASE_STORAGE_BUCKET_ARTIFACTS` (default `ri-artifacts`; holds
  per-attempt `.ipynb` exports surfaced via
  `GET /api/attempts/{id}/notebook-download`)

**`apps/admin/.env.example`** (Next.js admin on Vercel). Critical:
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (server-side admin lookups)
- `INTERNAL_API_URL` (where admin's server actions reach FastAPI; Cloud
  Run URL in prod)

**`apps/candidate/.env.local`** (Next.js candidate on Vercel). Critical:
- `INTERNAL_API_URL` (server-side fetches for resolve / consent / submit)
- `NEXT_PUBLIC_API_URL` (browser fetches for heartbeat / events / code
  run / sql query / notebook run)
- `NEXT_PUBLIC_CANDIDATE_ASSET_PREFIX` (REQUIRED in single-host prod;
  hardcoded to `/a` by `.github/workflows/deploy-vm.yml` build-args).
  Single-VM prod runs admin and candidate behind one nginx on the same
  host; without this prefix the candidate HTML refers to
  `/_next/static/...` which nginx routes to admin (the `/` location)
  and admin 404s, breaking the page with a ChunkLoadError. The
  matching nginx regex location strips the prefix before proxying to
  candidate. Leave unset in dev.

## 3. Database setup

```sh
# Supabase project, vector extension enabled.
cd apps/api
bun run migrate    # applies packages/db/migrations/0001..0005
bun run seed       # optional: prints a magic-link URL for smoke testing
```

Migrations are idempotent (tracked in `public._migrations`). Re-running
is safe. `0005_retention.sql` installs the `prune_integrity_events(days)`
function used by `scripts/prune-integrity-events.sh` (wire this into
Cloud Scheduler weekly to enforce the 12-month TTL (spec §11.4).

## 4. Local dev (no Docker)

**One-shot.** After step 2 (env file + symlinks), run all three services
together with a single command:

```sh
bun install
bun run dev:full              # api :8000 · admin :3000 · candidate :3001
```

`dev:full` re-runs the symlink wiring, validates required env vars,
checks for `bun` + `uv`, then hands off to `turbo dev` (which runs each
app's `dev` script in a tabbed TUI). Hit `Ctrl-C` once to stop all three.

**Per-service** (when you only want one running):

```sh
bun --filter api dev          # FastAPI on :8000 (uv-managed)
bun --filter admin dev        # Next.js on :3000
bun --filter candidate dev    # Next.js on :3001
```

For the n8n runner specifically, point `N8N_HOST` at any reachable n8n
instance and set `N8N_ADMIN_API_KEY`.

## 5. Local dev (Docker)

```sh
docker compose up --build
```

This brings up FastAPI, admin, candidate, n8n (community edition), and
redis. Supabase and the SaaS providers stay external; fill
`apps/api/.env.local` first.

n8n on first run prints a signup URL in its log. Sign up locally → owner
account → Settings → API → create personal API key → put it in
`N8N_ADMIN_API_KEY`.

## 6. Production deploy

### Vercel (admin + candidate)

Each app has a `vercel.json`. In Vercel:

1. Create two projects, both pointing at this repo.
2. Set "Root Directory" to `apps/admin` for one, `apps/candidate` for
   the other.
3. The `vercel.json` overrides `installCommand` to `cd ../.. && bun
   install --frozen-lockfile` and `buildCommand` to a Bun workspace
   filter, so Vercel builds the whole monorepo and only deploys the
   target app.
4. Set the env vars from §2.

### Cloud Run (FastAPI + n8n)

```sh
# Build
gcloud builds submit --tag gcr.io/$PROJECT/ri-api ./apps/api

# Deploy
gcloud run deploy ri-api \
  --image gcr.io/$PROJECT/ri-api \
  --region us-central1 \
  --allow-unauthenticated \
  --concurrency 30 \
  --timeout 300 \
  --memory 1Gi \
  --set-env-vars "$(grep -v '^#' apps/api/.env.local | xargs)"
```

For n8n, deploy the `n8nio/n8n:latest` image with a Cloud Storage volume
mount or a Cloud SQL backend (consult n8n docs). `N8N_HOST` then points
at the Cloud Run URL.

The candidate iframe connects directly to the n8n URL, so the n8n
service must be publicly reachable. Restrict via Cloud Armor or n8n's
own auth in production.

## 7. Operational runbooks

### Rescore an attempt or assignment

- UI: `/assignments/[id]` → "Rescore all attempts" or per-attempt
  "Rescore" button.
- API: `POST /api/attempts/{id}/rescore` (single) or
  `POST /api/assignments/{id}/rescore` (batch).
- Old scores snapshot to `attempt_scores_history` automatically.

### Update reference library

- UI: `/references` → URL or text upload.
- API: `POST /api/references` (text), `POST /api/references/url`
  (trafilatura-extracted), `POST /api/references/pdf` (multipart).
- Embeddings use OpenAI text-embedding-3-small (1024 dims via the
  `dimensions` parameter) by default. Switch providers by altering
  `services/references.py:EMBEDDING_MODEL` and the migration's
  `vector(N)` column dimension to match.

### Issue the next assignment in a series

- UI: `/series` → "Issue next" button.
- API: `POST /api/series/{id}/issue-next?expires_in_days=7&send_email=true`
- Cron: hit the same endpoint from any scheduler (Cloud Scheduler, GitHub
  Action) on each series' cadence. The endpoint is admin-gated; use a
  service account JWT.

### n8n cluster operations

- Workflows are created on-demand at `/a/{token}/n8n/embed`. There is no
  ephemeral-user isolation in the v1 community-edition setup; every
  candidate's workflow lives on the same n8n instance.
- Deletion: workflows aren't auto-deleted today (best-effort). Run a
  weekly cron of `DELETE /api/v1/workflows/{id}` for any workflow whose
  associated assignment is `completed` or older than `expires_at`.
- Migration: dump / restore via n8n's `Settings → Source Control` or by
  copying the persistent volume.

### Scoring failures

- If E2B / OpenAI / Anthropic / n8n is briefly unavailable when the
  candidate submits, the answer is still saved (`raw_answer` and
  `submitted_at`) but `score` stays null. Run rescore once the upstream
  service is back.
- `attempts.needs_review = true` flags low-confidence rubric_ai scores
  (`scorer_confidence < 0.6`). Surface in admin via the per-attempt pill
  on `/assignments/[id]`.

### Resend webhook (delivery / bounce / complaint)

- Endpoint pattern: `POST https://<api-host>/webhooks/resend` on the
  FastAPI service. Verifies the Svix-style signature header
  (`svix-signature`, with `resend-signature` accepted as a fallback)
  HMAC-SHA256 against `RESEND_WEBHOOK_SECRET`.
- `RESEND_WEBHOOK_SECRET` is generated in the Resend dashboard
  (Webhooks > Signing Secret > Reveal). Paste the same value into the
  Cloud Run env block for the API service. Rotate by regenerating in
  the dashboard, redeploying the API, then re-saving the webhook so
  Resend issues the new secret to inbound payloads.
- Configure the dashboard webhook with the Cloud Run URL above and
  enable `email.bounced`, `email.complained`, `email.delivered`, and
  `email.opened` events.
- Effect: the most recent assignment per recipient gets the event
  appended to `assignments.metadata.email_delivery` (last 50 events).
  TODO: the admin assignment detail page does not yet read
  `email_delivery` and surface bounce/spam state. Until that lands,
  inspect via SQL or the admin debug router.

### Rate limits (slowapi)

Per-endpoint caps applied on the candidate router via the slowapi
limiter keyed on the magic-link token (falls back to client IP if the
token cannot be resolved). Limits below are enforced in
`apps/api/src/ri_assessments_api/routers/candidate.py`.

| Endpoint | Limit |
|---|---|
| `POST /a/{token}/heartbeat` | 60/minute |
| `POST /a/{token}/events` | 30/minute |
| `POST /a/{token}/code/run` (SSE) | 30/minute |
| `POST /a/{token}/code/test` | 30/minute |
| `POST /a/{token}/sql/query` | 60/minute |
| `POST /a/{token}/notebook/run` | 30/minute |
| `POST /a/{token}/notebook/run-cell` | 60/minute |
| `POST /a/{token}/n8n/embed` | 10/minute |

slowapi is imported defensively: if the package is missing the
decorator is a no-op so tests and dev environments still run, but
production images install `slowapi>=0.1.9` via `apps/api/pyproject.toml`.

### Health endpoints

| Endpoint | Purpose | Returns |
|---|---|---|
| `GET /health` | Liveness probe (Cloud Run + Vercel readiness route) | `{status: "ok", version: "<git-sha>"}` |
| `GET /health/ready` | Readiness probe: pings Supabase Postgres, Upstash Redis, and the E2B control plane | `200` when all three are reachable, `503` otherwise. Wire Cloud Run's startup + readiness probes at this path. |

The candidate Next app exposes the same liveness shape at `/api/health`;
the admin app re-exports `/api/health` for Vercel's health monitoring.

### Cron jobs (scheduled tasks)

All cron jobs run as Cloud Scheduler HTTP targets against the FastAPI
service. Authenticate via the `OIDC` token attached to a dedicated
service account; the API verifies admin role at the service layer.

| Job | Schedule (UTC) | Endpoint | Purpose |
|---|---|---|---|
| `ri-series-dispatch` | `*/15 * * * *` | `POST /api/series/dispatch-due` | Issues the next assignment in any `assessment_series` whose `next_due_at <= now()`. |
| `ri-prune-integrity-events` | `0 3 * * 0` (Sunday 03:00) | `POST /internal/prune-events` | Calls `prune_integrity_events(365)` to enforce the 12-month retention rule from spec §18. Override with `RETENTION_DAYS` for tighter windows. |
| `ri-rescore-dead-letter` | `0 4 * * *` (daily 04:00) | `POST /api/admin/rescore-dlq` | Drains the `ri:scoring:dlq` Redis list back into the main queue with backoff metadata; surfaces persistent failures to Sentry. |
| `ri-n8n-workflow-gc` | `0 2 * * 1` (Monday 02:00) | `POST /internal/n8n/cleanup` | Deletes n8n workflows for assignments that are `completed` or past `expires_at` (best-effort; see "n8n cluster operations"). |

Cloud Scheduler create snippet:

```sh
gcloud scheduler jobs create http ri-series-dispatch \
  --schedule "*/15 * * * *" \
  --time-zone "Etc/UTC" \
  --uri "https://<api-host>/api/series/dispatch-due" \
  --http-method POST \
  --oidc-service-account-email "$SCHED_SA"
```

### Backup and retention

- **Supabase Postgres:** point-in-time recovery (PITR) enabled on the
  production project. PITR window: 7 days minimum, 30 days
  recommended. Daily logical backups stored automatically by Supabase;
  download monthly snapshots to Cloud Storage as an external archive.
- **Supabase Storage buckets:** versioning on for
  `ri-artifacts` (notebook + workflow exports) and `ri-references`
  (uploaded reference documents). Lifecycle rule: previous versions
  expire after 90 days.
- **Integrity events:** 12 months per spec §18, enforced by the
  `ri-prune-integrity-events` cron (above).
- **Raw answers + scores:** retained indefinitely per spec §18. The
  `attempts.raw_answer` column is never overwritten; rescoring writes
  to `attempt_scores_history` instead.
- **Score audit history:** `attempt_scores_history` rows live forever.
  No purge job.

### Migration order

Migrations live in `packages/db/migrations/00NN_*.sql` and are applied
in lexical order by `apps/api/scripts/apply_migrations.py`
(idempotent; tracks state in `public._migrations`).

| File | Purpose |
|---|---|
| `0001_init.sql` | Core schema: users, subjects, competencies, modules, question_templates, assignments, attempts, attempt_events, generation_runs, references, series, competency_scores. |
| `0002_rls.sql` | Row-level security policies on every subject-scoped table. |
| `0003_seed_competencies.sql` | Seeds the competency taxonomy from `packages/competencies/taxonomy.json`. |
| `0004_voyage_embeddings.sql` | Realigns `reference_chunks.embedding` to `vector(1024)` to match the chosen embedding provider. |
| `0005_retention.sql` | Installs `prune_integrity_events(days)` for the 12-month TTL. |
| `0006_attempts_metadata.sql` | Adds per-attempt metadata jsonb for runner-specific state. |
| `0007_assessments.sql` | Introduces the `assessments` container (groups one or more modules); assignments can bind to a module or an assessment. |
| `0008_assignments_metadata.sql` | Adds `assignments.metadata` jsonb, used for email delivery events and runner notes. |
| `0009_attempt_active_seconds_increment.sql` | Server-side accumulator function for heartbeat-driven `active_time_seconds`. |
| `0010_rls_assessments.sql` | Extends RLS to the new assessment tables. |
| `0011_attempt_scores_history_trigger.sql` | Trigger that snapshots score columns to `attempt_scores_history` before any rescoring update. |
| `0012_series_assignments_unique_seq.sql` | Unique constraint on `(series_id, sequence_number)` to prevent dispatch races. |
| `0013_reference_documents_updated_at.sql` | Adds `updated_at` to reference documents with an update trigger. |
| `0014_user_fk_set_null.sql` | Switches `created_by` foreign keys to `ON DELETE SET NULL` so deleting an admin user does not cascade-delete content. |
| `0015_assignments_scored_at.sql` | Adds `assignments.scored_at` for fast filtering of completed-but-unscored assignments. |
| `0016_assignments_cascade.sql` | Restores cascade behavior between `assignments` and dependent tables after the FK rework. |
| `0017_attempt_score_breakdown.sql` | Adds `attempts.score_breakdown` jsonb for per-criterion rubric output. |

Apply on a fresh database:

```sh
cd apps/api && uv run python scripts/apply_migrations.py
```

### Local dev quickstart

```sh
# 1. Toolchain
brew install bun uv

# 2. Workspace deps
cd ai_assessments_platform
bun install
cd apps/api && uv sync && cd ../..

# 3. Env wiring (single .env.local at repo root, symlinked into each app)
cp .env.example .env.local
$EDITOR .env.local
bash scripts/link-env.sh

# 4. Docker stack (Postgres-less local; Supabase + SaaS providers stay external)
docker compose up -d --build

# 5. Apply migrations + seed a test assignment
bun --filter api migrate
bun --filter api seed       # prints a magic-link URL

# 6. Run all three apps (alternative to docker compose):
bun run dev:full
# or per app:
bun --filter api dev        # FastAPI on :8000
bun --filter admin dev      # Next.js on :3000
bun --filter candidate dev  # Next.js on :3001
```

### CI gate summary

`.github/workflows/ci.yml` runs on every PR + push to `main`.

| Job | What it runs | Blocking |
|---|---|---|
| `api-ruff` | `ruff check apps/api` | Yes |
| `api-pytest` | `uv run pytest -q` inside `apps/api` (covers `test_health.py`, `test_pii_filter.py`, integrity unit tests) | Yes |
| `typecheck` | `bun run typecheck` (turbo, all workspaces) | Yes |
| `check` | `bun run check` (ultracite + `check-copy` em/en-dash grep + `check-boundaries` package import rules) | Yes |
| `vitest` | `bun run test` (integrity + admin vitest suites) | Yes |
| `schema-codegen-drift` | Regenerates Pydantic from Zod and fails on a non-empty diff | Yes |
| `security-audit` | `pip-audit` + `bun audit` | No (informational) |

Deploy workflows (`deploy-api.yml`, `deploy-frontend.yml`) are gated on
`main` only and require the CI job to pass first.

### Integrity event retention (12-month TTL, spec §11.4)

- `packages/db/migrations/0005_retention.sql` installs
  `prune_integrity_events(days)`.
- `scripts/prune-integrity-events.sh` calls the function via either
  `DATABASE_URL` or the Supabase CLI. Schedule it in Cloud Scheduler
  (suggested: Sunday 03:00 UTC, weekly):

  ```sh
  gcloud scheduler jobs create http ri-prune-integrity-events \
    --schedule "0 3 * * 0" \
    --uri "https://<api-host>/internal/prune-events" \
    --http-method POST --oidc-service-account-email <sa>
  ```

  (Or invoke the script directly from a Cloud Run job.) Override with
  `RETENTION_DAYS=180` for a tighter window if compliance changes.

### Schema codegen

- TypeScript Zod schemas in `packages/schemas` are the single source of
  truth. Pydantic v2 models for FastAPI are generated from them.
- Run `bash apps/api/scripts/gen_schemas.sh` to regenerate after editing
  any `packages/schemas/src/*.ts` file. Output lands in
  `apps/api/src/ri_assessments_api/generated/` (gitignored).
- CI should run the same command and fail on a non-empty diff so the
  generated tree never drifts behind the canonical Zod source.

### Sentry / Axiom

`@repo/observability` is already wired into both Next.js apps and the
FastAPI service. Spec §15 + §16 require **three independent Sentry
projects**, one per surface, so errors stay attributed to the right
team and stack trace volume from one app cannot drown out the others:

| App | Public DSN env var | Notes |
|---|---|---|
| admin (Next.js) | `NEXT_PUBLIC_SENTRY_DSN_ADMIN` | Read by `apps/admin/sentry.{client,server,edge}.config.ts`. |
| candidate (Next.js) | `NEXT_PUBLIC_SENTRY_DSN_CANDIDATE` | Read by `apps/candidate/sentry.{client,server,edge}.config.ts`. |
| api (FastAPI) | `SENTRY_DSN_API` | Read by `apps/api/src/ri_assessments_api/main.py`. |

The legacy `NEXT_PUBLIC_SENTRY_DSN` is still honored as a fallback for
deployments that have not migrated yet; the resolver in
`packages/observability/keys.ts#resolveSentryDsn` picks the per-app DSN
first.

**Source-map upload** is gated on `SENTRY_AUTH_TOKEN`, not on a
hosting-provider sentinel like `VERCEL`. Any build platform that has
the token (Vercel, Cloud Run, GitHub Actions, a local build) uploads
maps to the matching Sentry project. Without the token, the Sentry
build plugin is skipped entirely, which keeps local `bun run build`
fast and avoids accidental uploads from developer machines.

Per-app build-time vars (set in Vercel project settings or the Cloud
Run env block):

- `SENTRY_AUTH_TOKEN` (one Auth Token, scope `project:releases`,
  reused across all three projects under the same org)
- `SENTRY_ORG` (org slug)
- `SENTRY_PROJECT_ADMIN`, `SENTRY_PROJECT_CANDIDATE` (project slugs)
- `SENTRY_PROJECT` (legacy single-project fallback, optional)

Other observability env vars:

- `AXIOM_TOKEN`, `AXIOM_DATASET`
- `BETTERSTACK_API_KEY`, `BETTERSTACK_URL` (uptime monitoring)

#### Creating the three Sentry projects

In Sentry, create one organization (existing RI org is fine) and three
projects under it: `ri-admin` (platform: Next.js), `ri-candidate`
(platform: Next.js), `ri-api` (platform: Python / FastAPI). Copy each
project's Client Keys (DSN) into the matching env var above. Generate
one Auth Token at User Settings > Auth Tokens with the
`project:releases` scope and paste it as `SENTRY_AUTH_TOKEN` into every
build environment that should ship source maps (Vercel admin + Vercel
candidate + the Cloud Run build env for the API). Confirm the wiring
by deploying once and verifying that events appear under the right
project in Sentry; if an admin error lands in `ri-candidate`, the DSN
env var on the admin deployment is misconfigured.

No code changes needed beyond setting env vars.

### Log + PII policy (spec §18)

- IPs are hashed at the API layer before being persisted to
  `attempt_events.ip_hash` or forwarded to log sinks. Raw IPs never
  appear in Axiom / Logtail / Sentry payloads.
- Candidate raw answers are never logged. Sentry's
  `beforeSend` strips request bodies on candidate routes; FastAPI's
  structured logger applies the same redaction via the PII filter
  (`apps/api/src/ri_assessments_api/services/pii.py`,
  tests in `apps/api/tests/test_pii_filter.py`).
- Magic-link tokens are only stored as `token_hash` on the
  `assignments` row; the raw JWT is never logged.
- Integrity events are retained for 12 months via
  `scripts/prune-integrity-events.sh` (see above). Score history is
  retained indefinitely per spec §18.

## 8. Phase 0 through 5 deliverables checklist (spec §20)

- [x] All migrations applied (`bun --filter api migrate`)
- [ ] 10 seed modules published via the generator (Phase 5 data-fill)
- [ ] 5 internal employees benchmarked (data-fill)
- [ ] 3 candidate assessments completed end-to-end (data-fill)
- [x] Admin dashboard shows integrity events, scores, rationale
- [x] Rescore endpoint works without data loss
- [x] All interactive runners scaffolded (code, sql, diagram, notebook,
      n8n)
- [ ] Load test passes with 50 concurrent (needs real infra)
- [x] Runbook for n8n cluster operations
- [x] Runbook for rescoring and reference-library updates
