-- 0016_assignments_cascade.sql
-- Why:
--   Spec §4.7 says competency_scores is a rollup: rows are keyed by
--   (subject_id, competency_id, assignment_id). The current FK
--   `competency_scores.assignment_id -> assignments(id)` is RESTRICT,
--   which means deleting an assignment (admin cleanup, test data
--   teardown, GDPR-style purge) is blocked until the rollup rows are
--   deleted first. But a rollup row without its parent assignment is
--   meaningless: the subject score is no longer tied to a real attempt
--   and we cannot trace it back. The right policy is ON DELETE
--   CASCADE so the rollups die with the assignment.
--
-- Spec refs: §4.7 (competency_scores is a derived rollup), §18 (audit
-- of meaningful rows; orphan rollups are noise).
--
-- Idempotency:
--   * `drop constraint if exists` is a no-op on missing constraints.
--   * Drop-add pair with a fixed constraint name reinstalls the same
--     shape on every re-run.

alter table competency_scores
  drop constraint if exists competency_scores_assignment_id_fkey;

alter table competency_scores
  add constraint competency_scores_assignment_id_fkey
  foreign key (assignment_id) references assignments(id) on delete cascade;
