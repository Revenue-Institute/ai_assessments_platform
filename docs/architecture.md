# Architecture Notes

This document records deliberate implementation decisions where the repo differs from `specs/requirements.md`.

## Current Service Boundaries

The spec describes separate packages for `generator`, `scoring`, `code-runner`, `n8n-runner`, `diagram-runner`, and `randomizer`. In this repo, those orchestration layers currently live inside FastAPI:

```text
apps/api/src/ri_assessments_api/services/
```

That is acceptable for the current v1 implementation because:

- runner calls need server-side secrets,
- scoring and generation are API-owned workflows,
- Python service tests can exercise these flows without a second runtime boundary.

The boundary to preserve is the contract layer:

- `packages/schemas` owns TypeScript/Zod shapes.
- API models should stay aligned with those shapes.
- database migrations should store shapes that match both.
- frontend apps should consume API responses, not database internals.

## Extraction Criteria

Extract a service into a top-level package only when at least one of these is true:

- a second app or worker needs to import the implementation directly,
- the service needs independent deployment or scaling,
- tests need a reusable runner adapter outside FastAPI,
- the service boundary is stable enough that extraction will reduce complexity.

Good first extraction candidates:

1. `randomizer`: deterministic, low-secret, easy to contract-test.
2. `scoring`: useful for worker deployment once async queueing lands.
3. `code-runner`: useful if runner adapters move to a separate worker pool.

## Security Hardening Backlog

Before production candidate use:

- replace broad authenticated read RLS policies with role-aware policies,
- add audit events for assignment and attempt views,
- keep service-role access limited to API and migration contexts,
- add tests proving viewers cannot mutate state and reviewers cannot manage users,
- add rate limits for candidate token endpoints and runner endpoints.

## UX Hardening Backlog

Before high-volume internal rollout:

- make dashboard widgets API-backed and actionable,
- add filters, sort, pagination, and CSV export to admin work surfaces,
- move question renderers into a shared package used by admin preview and candidate UI,
- add autosave and visible saved-state indicators to every interactive renderer,
- add responsive verification screenshots for text, code, SQL, diagram, notebook, and n8n question layouts.

## Runner Hardening Backlog

Before using interactive assessments externally:

- queue long runner work separately from request/response paths,
- collect per-runner latency, error, and cost telemetry,
- add runner health checks surfaced in the dashboard,
- persist execution artifacts with retention policies,
- add admin rescore retry visibility when a runner is unavailable.
