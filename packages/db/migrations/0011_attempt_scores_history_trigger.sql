-- 0011_attempt_scores_history_trigger.sql
-- Why:
--   Spec §9.3 + §18 audit requirement: every score change must be
--   persisted to attempt_scores_history. Today that snapshot is written
--   from application code in services/scoring.py and services/admin.py
--   (the rescore endpoint). Any new write path (worker retry, manual
--   SQL fix, future admin direct-edit) silently bypasses the audit log.
--   This trigger makes the database the enforcement point so the audit
--   row is guaranteed regardless of who issues the UPDATE.
--
-- Spec refs: §9.3 (rescore + history), §18 (audit: every score change
-- written to attempt_scores_history).
--
-- Trigger fires BEFORE UPDATE on `attempts` when any of the scoring
-- columns change: score, score_rationale, scorer_model, scorer_version,
-- scorer_confidence, needs_review, rubric_version.
--
-- pg_trigger_depth() = 0 guard:
--   Defense in depth. If a future trigger ever causes a cascading
--   update to attempts (none exist today), we do not want to recurse
--   into another snapshot row. The guard makes the function safe to
--   compose with any future BEFORE/AFTER UPDATE trigger.
--
-- Idempotency:
--   * `create or replace function` is the standard re-runnable form.
--   * `drop trigger if exists ... ; create trigger ...` replaces any
--     prior version on re-apply.

create or replace function public.tg_snapshot_attempt_score()
returns trigger
language plpgsql
as $$
begin
  -- Only act when we are at the top of the trigger stack. Prevents
  -- recursion if a later trigger updates attempts from within a
  -- trigger context.
  if pg_trigger_depth() <> 1 then
    return new;
  end if;

  if (
    new.score is distinct from old.score
    or new.score_rationale is distinct from old.score_rationale
    or new.scorer_model is distinct from old.scorer_model
    or new.scorer_version is distinct from old.scorer_version
    or new.scorer_confidence is distinct from old.scorer_confidence
    or new.needs_review is distinct from old.needs_review
    or new.rubric_version is distinct from old.rubric_version
  ) then
    insert into attempt_scores_history (
      attempt_id,
      score,
      max_score,
      score_rationale,
      scorer_model,
      scorer_version,
      rubric_version,
      scorer_confidence,
      recorded_at
    ) values (
      old.id,
      old.score,
      old.max_score,
      old.score_rationale,
      old.scorer_model,
      old.scorer_version,
      old.rubric_version,
      old.scorer_confidence,
      now()
    );
  end if;

  return new;
end;
$$;

drop trigger if exists trg_attempts_snapshot_score on attempts;
create trigger trg_attempts_snapshot_score
before update on attempts
for each row
execute function public.tg_snapshot_attempt_score();

comment on function public.tg_snapshot_attempt_score is
  'Spec §9.3 / §18: snapshots OLD attempt scoring fields into '
  'attempt_scores_history on any change. Guard via pg_trigger_depth() '
  'prevents recursion. recorded_by stays null when the change comes '
  'from a non-user path; the FastAPI rescore handler still inserts a '
  'row with recorded_by populated, which is fine: history is append-only.';
