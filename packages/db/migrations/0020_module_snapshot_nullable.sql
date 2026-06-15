-- 0020_module_snapshot_nullable.sql
-- module_snapshot was originally NOT NULL (0001_init.sql). Migration 0007
-- introduced assessment_snapshot for assessment-bound assignments, which do
-- not populate module_snapshot. Drop the NOT NULL constraint and add a check
-- that ensures exactly one snapshot column is present per row.

alter table assignments
  alter column module_snapshot drop not null;

alter table assignments
  add constraint chk_assignments_snapshot_present
  check (module_snapshot is not null or assessment_snapshot is not null);
