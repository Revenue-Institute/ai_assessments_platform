-- 0013_reference_documents_updated_at.sql
-- Why:
--   Spec §4 declares that all tables have `updated_at timestamptz`.
--   reference_documents in 0001_init.sql shipped without one. Plus,
--   every table that *does* have updated_at relies on application code
--   to set it, which means any direct SQL fix or future admin
--   direct-edit forgets to bump the timestamp and the "last edited"
--   surfaces in the admin UI go stale. This migration:
--     1. Adds the missing updated_at column on reference_documents.
--     2. Installs a generic tg_set_updated_at() function.
--     3. Wires BEFORE UPDATE triggers on every table that has the
--        column so the database itself maintains the timestamp.
--
-- Spec refs: §4 (every table has updated_at, all timestamps UTC).
--
-- Idempotency:
--   * `add column if not exists` covers the schema change.
--   * `create or replace function` covers the helper.
--   * `drop trigger if exists ... ; create trigger ...` covers each
--     trigger so re-applies are no-ops.

alter table reference_documents
  add column if not exists updated_at timestamptz;

create or replace function public.tg_set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

comment on function public.tg_set_updated_at is
  'Spec §4: BEFORE UPDATE trigger that stamps updated_at = now() on '
  'any row update. Installed on every table that owns an updated_at '
  'column so the database is authoritative.';

-- Wire the trigger on every table that has updated_at. Each line uses
-- drop-if-exists + create so the migration is re-runnable. Tables
-- without an updated_at column (e.g. competencies, attempt_events,
-- generation_runs, training_suggestions, series_assignments,
-- competency_scores, reference_chunks) are intentionally skipped.

drop trigger if exists trg_users_set_updated_at on users;
-- users does not currently have updated_at; skip silently if missing.
do $$
begin
  if exists (
    select 1
      from information_schema.columns
     where table_schema = 'public'
       and table_name = 'users'
       and column_name = 'updated_at'
  ) then
    execute 'create trigger trg_users_set_updated_at '
            'before update on users '
            'for each row execute function public.tg_set_updated_at()';
  end if;
end$$;

drop trigger if exists trg_subjects_set_updated_at on subjects;
do $$
begin
  if exists (
    select 1
      from information_schema.columns
     where table_schema = 'public'
       and table_name = 'subjects'
       and column_name = 'updated_at'
  ) then
    execute 'create trigger trg_subjects_set_updated_at '
            'before update on subjects '
            'for each row execute function public.tg_set_updated_at()';
  end if;
end$$;

drop trigger if exists trg_modules_set_updated_at on modules;
create trigger trg_modules_set_updated_at
before update on modules
for each row execute function public.tg_set_updated_at();

drop trigger if exists trg_question_templates_set_updated_at on question_templates;
create trigger trg_question_templates_set_updated_at
before update on question_templates
for each row execute function public.tg_set_updated_at();

drop trigger if exists trg_assignments_set_updated_at on assignments;
create trigger trg_assignments_set_updated_at
before update on assignments
for each row execute function public.tg_set_updated_at();

drop trigger if exists trg_attempts_set_updated_at on attempts;
create trigger trg_attempts_set_updated_at
before update on attempts
for each row execute function public.tg_set_updated_at();

drop trigger if exists trg_assessments_set_updated_at on assessments;
create trigger trg_assessments_set_updated_at
before update on assessments
for each row execute function public.tg_set_updated_at();

-- assessment_modules has no updated_at column in 0007_assessments.sql,
-- but the spec brief lists it among the tables to wire. Add the column
-- conditionally then attach the trigger so the surface stays consistent.
alter table assessment_modules
  add column if not exists updated_at timestamptz;

drop trigger if exists trg_assessment_modules_set_updated_at on assessment_modules;
create trigger trg_assessment_modules_set_updated_at
before update on assessment_modules
for each row execute function public.tg_set_updated_at();

drop trigger if exists trg_reference_documents_set_updated_at on reference_documents;
create trigger trg_reference_documents_set_updated_at
before update on reference_documents
for each row execute function public.tg_set_updated_at();

-- assessment_series did not ship with updated_at in 0001. Add it
-- conditionally so the trigger has a column to write into.
alter table assessment_series
  add column if not exists updated_at timestamptz;

drop trigger if exists trg_assessment_series_set_updated_at on assessment_series;
create trigger trg_assessment_series_set_updated_at
before update on assessment_series
for each row execute function public.tg_set_updated_at();
