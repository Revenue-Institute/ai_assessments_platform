-- 0022_partial_evaluation.sql
-- Why:
--   Scoring previously ran only when an assignment flipped to
--   `completed`. Complex assessments often stall in_progress, so
--   answered questions never receive quality scores, gaming
--   summaries, or strengths/weaknesses. Admin "Evaluate now" and
--   partial backfill need durable columns for:
--     * attempts.quality_score (normalized 1-10)
--     * attempts.evaluation_report (analysis + timing flag)
--     * assignments.evaluation_report (gaming risk, strengths /
--       weaknesses, partial progress N of M)
--
-- Spec refs: §9 (scoring orchestrator), §10.4 (integrity formula),
-- §11 (competency / narrative surfaces for admin detail).
--
-- Idempotency:
--   `add column if not exists` is a true no-op on re-run.

alter table attempts
  add column if not exists quality_score numeric(4,1);

alter table attempts
  add column if not exists evaluation_report jsonb;

alter table assignments
  add column if not exists evaluation_report jsonb;

-- Soft bounds for the 1-10 quality scale. Null remains allowed for
-- unanswered / not-yet-evaluated attempts.
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'attempts_quality_score_range'
  ) then
    alter table attempts
      add constraint attempts_quality_score_range
      check (
        quality_score is null
        or (quality_score >= 1 and quality_score <= 10)
      );
  end if;
end $$;
