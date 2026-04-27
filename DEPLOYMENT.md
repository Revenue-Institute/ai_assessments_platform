# Deployment & Operations

How to stand up the Revenue Institute Assessments Platform end-to-end.
Owner: ops + engineering. Last reviewed against `specs/requirements.md`
phases 0–5.

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
| `.github/workflows/ci.yml` | PR + push to main | ruff + pytest on `apps/api`, bun typecheck on admin + candidate |
| `.github/workflows/deploy-api.yml` | push to main (api / db / infra paths) | Cloud Build → Cloud Run deploy of FastAPI |
| `.github/workflows/deploy-frontend.yml` | push to main (frontend paths) | Vercel `pull → build → deploy` for admin + candidate |

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
| Voyage AI | Reference-library embeddings (voyage-3, 1024 dims) | Or OpenAI text-embedding-3-small if you flip the migration to vector(1536). |
| Resend | Magic-link + result notifications | Configure SPF + DKIM on a subdomain (e.g. `assessments.revenueinstitute.com`). |
| Upstash Redis | BullMQ backing store (when async scoring lands) | Local docker-compose uses redis:alpine. |
| n8n (self-hosted) | Workflow assessments | docker-compose ships this; in production run on Cloud Run with a persistent volume. |
| Sentry | Error tracking | One project per app. `@repo/observability` is already wired. |
| Axiom (or similar) | Log ingestion | Stream from FastAPI + Vercel. |

## 2. Required env vars

**Local dev — single source of truth.** Copy `.env.example` at the repo
root to `.env.local`, fill in your values, then run:

```sh
cp .env.example .env.local
bash scripts/link-env.sh
```

That symlinks `apps/admin/.env.local`, `apps/candidate/.env.local`, and
`apps/api/.env` to the root file. Edit one file, all three apps see the
update. Re-run the script if you ever clone fresh or if a symlink gets
overwritten.

**Production deploy** — set vars per service in the host (Vercel
project settings for admin/candidate, Cloud Run service env for the
API). Don't ship `.env.local` to production.

Spec §16 has the canonical variable list. Highlights below.

**`apps/api/.env.example`** — FastAPI (Cloud Run). Critical:
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`,
  `DATABASE_URL`
- `JWT_SIGNING_SECRET` (32+ random chars; signs candidate magic-links)
- `ANTHROPIC_API_KEY_GENERATION`, `ANTHROPIC_API_KEY_SCORING`
- `E2B_API_KEY`
- `VOYAGE_API_KEY`, `EMBEDDING_MODEL=voyage-3`, `EMBEDDING_DIMS=1024`
- `RESEND_API_KEY`, `RESEND_FROM_EMAIL=assessments@revenueinstitute.com`
- `RESEND_WEBHOOK_SECRET` (HMAC for `POST /webhooks/resend` — paste the
  same value into Resend's webhook signing-secret field)
- `N8N_HOST`, `N8N_ADMIN_API_KEY`, `N8N_WEBHOOK_SECRET`
- `NEXT_PUBLIC_CANDIDATE_URL` (used to build magic-link URLs in emails)
- `SUPABASE_STORAGE_BUCKET_ARTIFACTS` (default `ri-artifacts`; holds
  per-attempt `.ipynb` exports surfaced via
  `GET /api/attempts/{id}/notebook-download`)

**`apps/admin/.env.example`** — Next.js admin (Vercel). Critical:
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (server-side admin lookups)
- `INTERNAL_API_URL` (where admin's server actions reach FastAPI; Cloud
  Run URL in prod)

**`apps/candidate/.env.local`** — Next.js candidate (Vercel). Critical:
- `INTERNAL_API_URL` (server-side fetches for resolve / consent / submit)
- `NEXT_PUBLIC_API_URL` (browser fetches for heartbeat / events / code
  run / sql query / notebook run)

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
Cloud Scheduler weekly to enforce the 12-month TTL — spec §11.4).

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

Add `bun --filter email dev` if you want React Email previews on `:3003`.

For the n8n runner specifically, point `N8N_HOST` at any reachable n8n
instance and set `N8N_ADMIN_API_KEY`.

## 5. Local dev (Docker)

```sh
docker compose up --build
```

This brings up FastAPI, admin, candidate, n8n (community edition), and
redis. Supabase + the SaaS providers stay external — fill
`apps/api/.env.local` first.

n8n on first run prints a signup URL in its log. Sign up locally → owner
account → Settings → API → create personal API key → put it in
`N8N_ADMIN_API_KEY`.

## 6. Production deploy

### Vercel — admin + candidate

Each app has a `vercel.json`. In Vercel:

1. Create two projects, both pointing at this repo.
2. Set "Root Directory" to `apps/admin` for one, `apps/candidate` for
   the other.
3. The `vercel.json` overrides `installCommand` to `cd ../.. && bun
   install --frozen-lockfile` and `buildCommand` to a Bun workspace
   filter, so Vercel builds the whole monorepo and only deploys the
   target app.
4. Set the env vars from §2.

### Cloud Run — FastAPI + n8n

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
- Embeddings use Voyage-3 by default. Switch providers by altering
  `services/references.py:EMBEDDING_MODEL` and the migration's
  `vector(N)` column dimension.

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

- If E2B / Voyage / Anthropic / n8n is briefly unavailable when the
  candidate submits, the answer is still saved (`raw_answer` and
  `submitted_at`) but `score` stays null. Run rescore once the upstream
  service is back.
- `attempts.needs_review = true` flags low-confidence rubric_ai scores
  (`scorer_confidence < 0.6`). Surface in admin via the per-attempt pill
  on `/assignments/[id]`.

### Resend webhook (delivery / bounce / complaint)

- Endpoint: `POST /webhooks/resend` on the FastAPI service. Verifies
  `svix-signature` (or `resend-signature`) HMAC against
  `RESEND_WEBHOOK_SECRET`.
- Configure in the Resend dashboard: add a webhook with the production
  Cloud Run URL `https://<api-host>/webhooks/resend`, paste the same
  secret, and enable the `email.bounced`, `email.complained`,
  `email.delivered`, `email.opened` events.
- Effect: the most recent assignment per recipient gets the event
  appended to `assignments.metadata.email_delivery` (last 50). Surface
  via the admin assignment detail page if needed.

### Integrity event retention (12-month TTL — spec §11.4)

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
FastAPI service. Set:

- `NEXT_PUBLIC_SENTRY_DSN`, `SENTRY_DSN_API`, `SENTRY_ORG`,
  `SENTRY_PROJECT`
- `AXIOM_TOKEN`, `AXIOM_DATASET`
- `BETTERSTACK_API_KEY`, `BETTERSTACK_URL` (uptime monitoring)

No code changes needed — env vars only.

## 8. Phase 0–5 deliverables checklist (spec §20)

- [x] All migrations applied — `bun --filter api migrate`
- [ ] 10 seed modules published via the generator — Phase 5 data-fill
- [ ] 5 internal employees benchmarked — data-fill
- [ ] 3 candidate assessments completed end-to-end — data-fill
- [x] Admin dashboard shows integrity events, scores, rationale
- [x] Rescore endpoint works without data loss
- [x] All interactive runners scaffolded (code, sql, diagram, notebook,
      n8n)
- [ ] Load test passes with 50 concurrent — needs real infra
- [x] Runbook for n8n cluster operations
- [x] Runbook for rescoring and reference-library updates
