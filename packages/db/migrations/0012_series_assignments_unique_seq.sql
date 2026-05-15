-- 0012_series_assignments_unique_seq.sql
-- Why:
--   Spec §11.4 says the series page shows the trend of each competency
--   across `sequence_number`. The current schema (0001_init.sql, lines
--   239-244) only enforces uniqueness on (series_id, assignment_id),
--   which lets two rows in the same series share a sequence_number.
--   That breaks the trend ordering: the UI cannot tell which attempt
--   is the first / second / third in the sequence. This adds the
--   missing unique constraint so the database guarantees a stable
--   ordering within a series.
--
-- Spec refs: §11.4 (retest and series; trend ordering by sequence).
--
-- Idempotency:
--   `alter table ... add constraint ... if not exists` is not supported
--   for constraints, but `add constraint <name>` errors on duplicates.
--   Wrap in a DO block that checks pg_constraint first so re-runs are
--   no-ops.

do $$
begin
  if not exists (
    select 1
      from pg_constraint
     where conname = 'series_assignments_series_sequence_key'
       and conrelid = 'series_assignments'::regclass
  ) then
    alter table series_assignments
      add constraint series_assignments_series_sequence_key
      unique (series_id, sequence_number);
  end if;
end$$;
