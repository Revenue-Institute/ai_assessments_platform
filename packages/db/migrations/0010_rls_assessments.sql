-- 0010_rls_assessments.sql
-- Why:
--   Migration 0007 introduced `assessments` and `assessment_modules` but
--   did not enable row-level security on them. Every other table in the
--   spec (§4.1, §18) has RLS on; leaving these two off lets the anon
--   key (used by the candidate web app) list every assessment in the
--   catalog, including drafts. This migration fills the gap.
--
-- Spec refs: §4.1 (RLS on every table), §18 (security).
--
-- Policy decision: mirror the read pattern from 0002_rls.sql. The
-- FastAPI server uses the service_role key (bypasses RLS) for all
-- writes; authenticated admin users get SELECT only. Tighten to
-- per-role write policies when admin direct-edits land (same plan as
-- 0002's closing note).
--
-- Idempotency:
--   * `alter table ... enable row level security` is a no-op if RLS is
--     already on, but does not error.
--   * `create policy` errors on duplicate name, so we drop-if-exists
--     first. Names match 0002_rls.sql conventions.

alter table assessments enable row level security;
alter table assessment_modules enable row level security;

drop policy if exists "authenticated read assessments" on assessments;
create policy "authenticated read assessments"
  on assessments for select to authenticated using (true);

drop policy if exists "authenticated read assessment_modules" on assessment_modules;
create policy "authenticated read assessment_modules"
  on assessment_modules for select to authenticated using (true);

-- Writes intentionally absent: FastAPI uses the service role key, same
-- as every other table in 0002_rls.sql. Per-role write policies land
-- when the admin direct-edit UI does.
