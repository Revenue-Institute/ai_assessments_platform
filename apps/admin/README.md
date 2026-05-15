# `apps/admin`: RI Assessments admin console

Next.js 15 App Router. Internal-only dashboard for module authors,
recruiters, and team leads. Sign-in via Supabase Auth. All mutations
proxy through the FastAPI backend at `INTERNAL_API_URL`.

## Local development

```sh
bun --filter admin dev    # http://localhost:3000
```

Requires the root `.env.local` to be filled in and
`bash scripts/link-env.sh` to have been run so the symlink is in
place. See `DEPLOYMENT.md > Local dev quickstart`.

## Auth and role policy

- Sign-in is Supabase Auth (email/password or magic-link). Sessions
  ride a server-side cookie signed with `SESSION_COOKIE_SECRET`.
- Role gating lives in `apps/admin/lib/role-policy.ts`. It mirrors the
  backend's `_ensure_role(principal, *allowed)` calls in the FastAPI
  service layer (`apps/api/src/ri_assessments_api/services/admin.py`
  and friends). When adding a restricted route, update both files in
  the same commit; the backend is the authoritative enforcer and the
  frontend policy exists to hide UI affordances pre-flight.
- Server actions in `app/(authenticated)/**/actions.ts` re-resolve the
  Supabase user on every call and forward the access token to FastAPI
  as a Bearer credential; client components never see service-role
  keys.

## SSE endpoints

Two server-sent-event channels live under `apps/admin/app/api/`:

- `GET /api/scoring-events` - streams scoring progress and final
  rationale for the current admin's pending assignments. Sourced from
  FastAPI `GET /api/scoring-events` via a server-side proxy that
  attaches the admin JWT and re-broadcasts the upstream stream.
- `GET /api/generation-events` - streams AI generation progress for
  the current outline / question-generation job. Used by the
  generation wizard on `/modules/new`.

Both proxy routes set `cache-control: no-store` and forward the
upstream `event:` + `data:` frames unmodified.

## Route inventory

| Path | Purpose |
|---|---|
| `/` | Dashboard: recent assignments, pending reviews, integrity flags. |
| `/modules` | Module library list (status, domain, difficulty filters). |
| `/modules/new` | Generation wizard entry: brief form, outline review, fan-out generation. |
| `/modules/new/manual` | Manual module creation (no AI). |
| `/modules/new/[run_id]` | Resume an in-progress generation run. |
| `/modules/[id]` | Module editor: edit questions, rubrics, variant previews, publish. |
| `/modules/[id]/preview` | Read-only candidate-perspective mirror for review. |
| `/assessments` | Assessment containers (multi-module groupings). |
| `/assessments/[id]` | Edit an assessment's module list and metadata. |
| `/assessments/[id]/preview` | Read-only preview of every module in the assessment. |
| `/candidates` | Subject list (candidates + employees). Filter by type, domain, role. |
| `/candidates/[id]` | Subject detail: competency radar, trend lines, assignment history. |
| `/assignments` | All assignments table with status, integrity, and copy-link affordances. |
| `/assignments/new` | Bulk-assign flow: pick module or assessment, pick subjects, set expiry. |
| `/assignments/[id]` | Per-assignment detail: results, integrity events timeline, rescore. |
| `/cohorts` | Cohort heatmap, weak-spot detection, peer percentile views. |
| `/series` | Assessment series management (cadence + auto-dispatch). |
| `/references` | Reference library upload + search (markdown, PDF, URL). |
| `/competencies` | Read-only taxonomy browser. |
| `/settings/users` | Manage internal users + roles (admin only). |

## Components and helpers

- `app/(authenticated)/components/` - shared admin widgets: competency
  radar, heatmap, distribution box, code preview, sidebar, etc.
- `app/(authenticated)/components/question-preview-renderer.tsx` -
  read-only renderer used by the `/preview` routes. Dispatches on
  `question.type` the same way the candidate runner does, but with
  inputs disabled and Monaco set to read-only.
- `lib/api-helpers.ts` - thin wrappers around `@repo/api-client` that
  thread the admin JWT through to FastAPI.
- `lib/role-policy.ts` - role-to-route policy, mirrored on the
  backend.

## Production rewrites

Production is single-host: admin owns the root, and `/a/*` is
rewritten to the candidate deployment via `apps/admin/next.config.ts`
gated on `NEXT_PUBLIC_CANDIDATE_URL`. See `CLAUDE.md > Environments
and URLs` for the full story.
