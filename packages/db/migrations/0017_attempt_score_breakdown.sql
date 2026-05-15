-- 0017_attempt_score_breakdown.sql
-- Why:
--   Spec §9.2 defines the rubric_ai scoring tool schema with a
--   per-criterion `breakdown` array (criterion_id, score, max, note).
--   The scoring service (packages/scoring via apps/api) already
--   persists this structured breakdown onto the attempt row so the
--   admin UI can render a per-criterion breakdown next to the
--   overall rationale. The destination column `score_breakdown
--   jsonb` was never added to `attempts`, so the write currently
--   400s and the dashboard falls back to "no breakdown available".
--   This adds the missing column.
--
--   `score_breakdown` is distinct from `score_rationale` (free-text
--   overall narrative) and from `expected_answer` (immutable solver
--   output). It is the structured per-criterion result that backs
--   confidence flags and human-review routing per §9.2.
--
-- Spec refs: §9.2 (rubric_ai scoring tool schema, per-criterion
-- breakdown), §4.4 (attempts row holds scorer output alongside
-- score, rationale, scorer_model, scorer_version, rubric_version).
--
-- Idempotency:
--   `add column if not exists` is a true no-op on re-run.

alter table attempts
  add column if not exists score_breakdown jsonb;
