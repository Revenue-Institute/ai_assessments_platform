-- 0014_user_fk_set_null.sql
-- Why:
--   Spec §18 requires preservation of audit history. Today, FKs that
--   reference users(id) use the default RESTRICT action: deleting a
--   user blocks the delete entirely, OR (if the FK ever cascades) drops
--   their work. Neither is what we want. The right policy for "created
--   by user X" / "uploaded by user X" / "recorded by user X" is ON
--   DELETE SET NULL: the audit row stays, the user pointer becomes
--   null, and downstream queries treat the actor as unknown.
--
--   Affected FKs (per 0001_init.sql and 0007_assessments.sql):
--     - modules.created_by              (nullable today, RESTRICT)
--     - assignments.created_by          (NOT NULL today, RESTRICT)
--     - assessment_series.created_by    (column may not exist yet)
--     - reference_documents.uploaded_by (nullable today, RESTRICT)
--     - generation_runs.created_by      (nullable today, RESTRICT)
--     - attempt_scores_history.recorded_by (nullable today, RESTRICT)
--     - assessments.created_by          (nullable today, RESTRICT)
--
-- Spec refs: §18 (audit retention; no actor row should be destroyed by
-- a user delete).
--
-- Side-effect: assignments.created_by is NOT NULL today. To allow the
-- ON DELETE SET NULL action, we drop the NOT NULL. The application
-- always populates this on insert; the constraint relaxation is purely
-- so the database action does not blow up.
--
-- Idempotency:
--   * `drop constraint if exists` is a no-op on missing constraints.
--   * `add constraint <fixed-name>` is idempotent when we always pair
--     drop+add together. Re-runs reinstall the same shape.
--   * `if exists` guards around `assessment_series.created_by` so we
--     don't break if that column was never added.

-- modules.created_by --------------------------------------------------------
alter table modules drop constraint if exists modules_created_by_fkey;
alter table modules
  add constraint modules_created_by_fkey
  foreign key (created_by) references users(id) on delete set null;

-- assignments.created_by ----------------------------------------------------
alter table assignments alter column created_by drop not null;
alter table assignments drop constraint if exists assignments_created_by_fkey;
alter table assignments
  add constraint assignments_created_by_fkey
  foreign key (created_by) references users(id) on delete set null;

-- reference_documents.uploaded_by -------------------------------------------
alter table reference_documents drop constraint if exists reference_documents_uploaded_by_fkey;
alter table reference_documents
  add constraint reference_documents_uploaded_by_fkey
  foreign key (uploaded_by) references users(id) on delete set null;

-- generation_runs.created_by ------------------------------------------------
alter table generation_runs drop constraint if exists generation_runs_created_by_fkey;
alter table generation_runs
  add constraint generation_runs_created_by_fkey
  foreign key (created_by) references users(id) on delete set null;

-- attempt_scores_history.recorded_by ----------------------------------------
alter table attempt_scores_history drop constraint if exists attempt_scores_history_recorded_by_fkey;
alter table attempt_scores_history
  add constraint attempt_scores_history_recorded_by_fkey
  foreign key (recorded_by) references users(id) on delete set null;

-- assessments.created_by (added in 0007_assessments.sql) --------------------
alter table assessments drop constraint if exists assessments_created_by_fkey;
alter table assessments
  add constraint assessments_created_by_fkey
  foreign key (created_by) references users(id) on delete set null;

-- assessment_series.created_by ----------------------------------------------
-- Column did not ship in 0001_init.sql. Guard the FK rewrite behind a
-- column-exists check so this migration is safe even if no later
-- migration ever adds it. If/when the column is added, re-running this
-- migration is harmless; the drop-add pair reinstalls the SET NULL
-- behavior on the existing constraint name.
do $$
begin
  if exists (
    select 1
      from information_schema.columns
     where table_schema = 'public'
       and table_name = 'assessment_series'
       and column_name = 'created_by'
  ) then
    execute 'alter table assessment_series drop constraint if exists assessment_series_created_by_fkey';
    execute 'alter table assessment_series '
            'add constraint assessment_series_created_by_fkey '
            'foreign key (created_by) references users(id) on delete set null';
  end if;
end$$;
