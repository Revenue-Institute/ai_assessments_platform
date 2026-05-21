# RI Assessments Platform - Working Notes

`specs/requirements.md` is the v1 spec. These notes capture decisions that diverge from the spec, conventions enforced across the tree, and pointers for future work.

## Style rules (codebase-enforced)

- **No em dashes** (U+2014) anywhere in source: UI copy, emails, generated content, AND code comments. Use a comma, hyphen, or parentheses. Spec §2 limits the rule to user-facing surfaces; we extend it to comments because the same rule then applies uniformly during reviews. CI grep blocks regressions.
- **No en dashes** (U+2013) either, same reason.
- ASCII hyphen for empty-cell placeholders.

## Architecture decisions that diverge from spec

### Generator / scoring / runners live in `apps/api`, not as packages
Spec §3 calls for `packages/{generator,scoring,code-runner,n8n-runner,diagram-runner,randomizer}`. We keep them as Python modules under `apps/api/src/ri_assessments_api/services/` because:
- The runners are Python-only; the candidate Next app talks to them via API, not direct import.
- Extracting them into npm packages adds toolchain weight without code reuse.

If a future scenario needs to share runner logic with another Python service, lift them out then.

### Pydantic models hand-authored, Zod canonical
See `apps/api/README.md#schema-policy`. Drift is caught at runtime by FastAPI validation and at review time. Revisit if the runner-package decision flips.

### Backend role enforcement at the service layer
Each admin service module (`services/admin.py`, `services/generator.py`, `services/series.py`, `services/references.py`) defines a private `_ensure_role(principal, *allowed)` and calls it at the top of every mutating handler. Routers only enforce authentication via `Depends(require_admin_jwt)`. This lets the same router handler be reused by helpers that pass different principals without duplicating role logic into the route layer.

The frontend mirrors role decisions via `apps/admin/lib/role-policy.ts`. Adjust both when adding new restricted routes.

### n8n runner is a shared workspace, not per-attempt ephemeral users
Spec §7.2 calls for one ephemeral n8n user per attempt with a scoped JWT. v1 uses a shared admin API key on a single n8n instance and creates a fresh workflow per attempt. Documented in `services/n8n_runner.py`. Lift when the security review requires per-tenant isolation, or when concurrent attempts start colliding on shared credentials.

### Async scoring via a small Redis LIST instead of BullMQ
Spec §15 names BullMQ + Upstash Redis. We use a 30-line `services/queue.py` that LPUSHes JSON envelopes onto a single `ri:scoring:jobs` list and a `worker.py` that BRPOPs them. Same Upstash/Redis store. Swap to BullMQ/RQ/Celery when we need retries with backoff, dead-letter inspection UIs, or scheduled jobs.

### Embedding dimension
Default OpenAI `text-embedding-3-small` (1024 dims via Matryoshka truncation, set through the `dimensions` API parameter). The original `0001_init.sql` set `vector(1536)`; migration `0004_voyage_embeddings.sql` is named historically and aligns the column to `vector(1024)` regardless of provider. Pick one provider per deployment and keep `EMBEDDING_DIMS` aligned with the column.

### `assessments` is a v1 extension over the spec data model
Migration `0007_assessments.sql` adds an `assessments` container that groups one or more modules. Assignments now bind to either a module (legacy) or an assessment (multi-module). Rationale and backwards-compat plan are in the migration header.

## Scoping conventions

- Server-authoritative time: candidate clients only display the deadline returned by `services/attempts.session_deadline()`. Submission endpoints reject expired sessions with 409.
- Integrity heartbeats return 200 (no-op) once the assignment is no longer `in_progress`, so the client console isn't littered as the page transitions to `/done`.
- Raw answers are immutable. Rescoring snapshots the previous score row into `attempt_scores_history` before recomputing.

## Environments and URLs

| Env | Admin | Candidate magic link |
| :-- | :-- | :-- |
| local | http://localhost:3000 | http://localhost:3001/a/{token} |
| dev (Vercel preview) | https://admin-<branch>.vercel.app | https://candidate-<branch>.vercel.app/a/{token} |
| prod | https://assessments.revenueinstitute.com | https://assessments.revenueinstitute.com/a/{token} |

Production is single-host: admin owns the root, `/a/*` is rewritten to
the candidate deployment. Wiring lives in `apps/admin/next.config.ts`
behind `NEXT_PUBLIC_CANDIDATE_URL`. To enable in any env:

```
# admin's .env.* (or Vercel project settings)
NEXT_PUBLIC_CANDIDATE_URL=https://candidate-prod.vercel.app
```

When unset (the local default), the rewrite is skipped and the two
apps just listen on their own ports. The candidate FastAPI route
(`/a/{token}` on apps/api) is unaffected; magic-link emails point at
`NEXT_PUBLIC_CANDIDATE_URL` for the link they serve to the recipient.

The candidate also needs `NEXT_PUBLIC_CANDIDATE_ASSET_ORIGIN` set to
its own absolute origin (the Vercel candidate URL, e.g.
`https://candidate-prod.vercel.app`) whenever it sits behind the
admin's `/a/*` rewrite. That value becomes `assetPrefix` on the
candidate's next.config, so the chunk URLs in the served HTML are
absolute and load directly from the candidate host. Without it, the
browser requests `/_next/static/...` from the admin origin (which
doesn't have those chunks), 404s, and renders a not-found page with
a ChunkLoadError in the console. Leave unset in dev (same-origin).

To launch the candidate experience yourself for QA:

1. From an admin session, run a seed (`bun --filter api seed`) or use
   the `/assignments/new` flow to pick a candidate + module.
2. The seed prints the magic-link URL; the assignments page exposes
   "Copy link" buttons for production.
3. Open the link in any browser. You will see exactly what the
   candidate sees, including the consent gate, server-driven timer,
   and integrity monitoring.

For passive review, the admin module/assessment preview pages
(`/modules/{id}/preview`, `/assessments/{id}/preview`) render every
question type in a read-only mirror so reviewers can scan the bank
without spinning up an attempt.

## Repo layout pointers

- Migrations: `packages/db/migrations/00NN_*.sql`. `apps/api/scripts/apply_migrations.py` is idempotent.
- Seed: `apps/api/scripts/seed_test_assignment.py`. Honors `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`.
- Local dev: `bash scripts/link-env.sh` symlinks `.env.local` into each app, then `docker compose up -d --build`.

## Open spec items not yet implemented

- WCAG 2.1 AA on the diagram (React Flow) and n8n iframe canvases. Timer, consent gate, navigator, and Monaco wrappers are addressed; the canvas runners are documented as "non-keyboard-accessible in v1" with a non-interactive fallback path.
- Integration test coverage beyond the current `test_health.py`, `test_pii_filter.py`, integrity vitest suite, and admin vitest suite. End-to-end runner tests (E2B / n8n) still pending.
- Per-attempt n8n user isolation (§7.2): v1 ships with the shared workspace documented above.
- BullMQ-style retry/dead-letter UI on the scoring queue. v1 has a dead-letter LIST (`ri:scoring:dlq`) plus a daily drain cron (see DEPLOYMENT.md), but no UI to inspect failures.
- Admin assignment detail page does not yet read `assignments.metadata.email_delivery`. Bounce / spam state currently visible only via SQL.

## Operational follow-ups

These are not v1-blocking but should land before the first external candidate uses the production deployment:

- Rotate every secret listed in `DEPLOYMENT.md > Secrets to rotate and set`. Current `.env.local` values are dev-only and must not appear in any Vercel / Cloud Run env block.
- Provision the three Sentry projects (`ri-admin`, `ri-candidate`, `ri-api`) and a single `SENTRY_AUTH_TOKEN` with `project:releases` scope. Source-map upload is gated on the token, not on a hosting-provider sentinel.
- Configure DKIM, SPF, and DMARC DNS records on `assessments.revenueinstitute.com` per Resend's domain-verification wizard before enabling magic-link sends.
- Set `TRUSTED_PROXY_IPS` on the Cloud Run API service to the load balancer's egress CIDRs so `attempt_events.ip_hash` is computed from the real client IP, not the proxy.

## Other documented divergences

These are deliberate departures from `specs/requirements.md` recorded for reviewer context. None block v1 ship.

- **Package manager: bun, not pnpm.** Spec §2 names pnpm. Repo uses bun 1.3.10 (see `package.json#packageManager`). Workspace protocol and turbo wiring are identical; the swap simplifies the local dev story.
- **`packages/ui` is `packages/design-system`.** Inherited from the next-forge starter naming, kept to avoid churn against shadcn upstream.
- **No `infra/docker/` tree.** Each app owns its own Dockerfile under `apps/*/Dockerfile`; the only top-level Docker artifact is `docker-compose.yml` for local dev. Collapses the spec's `infra/docker/` directory.
- **No `infra/terraform/`.** Spec §3 marks it optional; deferred until we need IaC for the FastAPI + n8n Cloud Run services.
- **No `apps/email` preview app.** The next-forge React Email scaffold (`apps/email`, `packages/email`) has no callers in the runtime code path, so both were removed. Re-introduce a transactional template package only when an actual sender lands.
- **Observability stack: Better Stack + Logtail alongside Axiom + Sentry.** Spec §15 only lists Sentry + Axiom; we wire Better Stack uptime and Logtail log ingestion via `@repo/observability` because the team already runs them.
- **`assessments` extension over base data model.** See migration `0007_assessments.sql`; recorded earlier in this file.
- **Embedding provider: OpenAI, not Voyage.** Spec §19 defaults to Voyage-3; we picked OpenAI `text-embedding-3-small` for ops familiarity. Migration column dimension and `EMBEDDING_DIMS` are aligned at 1024.
- **Code-run SSE streaming added (Phase-5 hardening).** Spec §14.3 names a generic `POST /a/{token}/code/run` that streams stdout via SSE. The candidate UI uses the streaming `fetch` API (not `EventSource`, because the request body must be a POST with the code buffer). The backend bridges E2B's blocking `sandbox.process.start_and_wait` to async via `code_runner.run_user_code_streaming`, which spawns the execution on a worker thread and pushes stdout/stderr chunks onto an asyncio queue. Non-streaming callers (`POST /a/{token}/code/test`, the scoring grader) still use the synchronous `run_user_code` entry point.
- **CI scope.** `.github/workflows/ci.yml` runs ruff + pytest on `apps/api`, bun typecheck on the two Next apps, the copy/boundaries lint (`bun run check`), the integrity vitest suite, the admin vitest suite, and a non-blocking `security-audit` job (pip-audit + bun audit). The schema codegen drift job also runs.
