-- 0008_assignments_metadata.sql
-- The Resend webhook handler stashes delivery / bounce / complaint
-- events on the assignment row so admin can see whether the magic link
-- ever landed. The `assignments.metadata` jsonb column was missing from
-- the original schema; this fills it in. Mirrors the attempts.metadata
-- backfill from migration 0006.

alter table assignments
  add column if not exists metadata jsonb not null default '{}'::jsonb;
