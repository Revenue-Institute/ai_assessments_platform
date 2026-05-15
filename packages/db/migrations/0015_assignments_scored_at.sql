-- 0015_assignments_scored_at.sql
-- Why:
--   apps/api/src/ri_assessments_api/routers/webhooks.py at line 150
--   writes `{"scored_at": now()}` onto the assignment row when the
--   scoring worker reports completion. The column was never added
--   to the schema, so the write currently 400s and the admin UI
--   shows no "scored at" timestamp. This adds the missing column.
--
--   The column is distinct from `completed_at` (when the candidate
--   finished) and from `updated_at` (touched by any update). It
--   represents "the moment the scoring pipeline finished writing
--   scores", which is what the admin "Scored on ..." surface wants.
--
-- Spec refs: §9.1 (scoring orchestrator emits a "scored" signal),
-- §14.4 (POST /webhooks/scoring-complete).
--
-- Idempotency:
--   `add column if not exists` is a true no-op on re-run.

alter table assignments
  add column if not exists scored_at timestamptz;

create index if not exists assignments_scored_at_idx
  on assignments(scored_at);
