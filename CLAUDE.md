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
Default Voyage-3 (1024 dims). The original `0001_init.sql` set `vector(1536)` for OpenAI; `0004_voyage_embeddings.sql` aligns the column to the chosen provider. Pick one provider per deployment.

### `assessments` is a v1 extension over the spec data model
Migration `0007_assessments.sql` adds an `assessments` container that groups one or more modules. Assignments now bind to either a module (legacy) or an assessment (multi-module). Rationale and backwards-compat plan are in the migration header.

## Scoping conventions

- Server-authoritative time: candidate clients only display the deadline returned by `services/attempts.session_deadline()`. Submission endpoints reject expired sessions with 409.
- Integrity heartbeats return 200 (no-op) once the assignment is no longer `in_progress`, so the client console isn't littered as the page transitions to `/done`.
- Raw answers are immutable. Rescoring snapshots the previous score row into `attempt_scores_history` before recomputing.

## Repo layout pointers

- Migrations: `packages/db/migrations/00NN_*.sql`. `apps/api/scripts/apply_migrations.py` is idempotent.
- Seed: `apps/api/scripts/seed_test_assignment.py`. Honors `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`.
- Local dev: `bash scripts/link-env.sh` symlinks `.env.local` into each app, then `docker compose up -d --build`.

## Open spec items not yet implemented

- Generator self-verification loop (§6.3 #10): solver round-trip is simulated in the prompt but not enforced server-side after emission.
- Fairness pre-publish gate (§8.4): 50-sample sanity rubric is documented but not wired into `POST /api/modules/{id}/publish`.
- Generator post-emission em-dash sanitizer: relying on the prompt is insufficient; add a strip pass before persistence.
- WCAG 2.1 AA: timer is solid; consent gate, navigator, and Monaco/React-Flow wrappers need a focused audit.
- Integration tests beyond `test_health.py` and `test_pii_filter.py`.
