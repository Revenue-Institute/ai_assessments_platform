-- 0002_rls.sql
-- Row-level security scaffolding (spec §4.1, §18).
-- v1 starting policy: service_role has full access (used by FastAPI server);
-- authenticated admins read everything; subject-scoped writes only via server.
-- Tighten per role (admin / reviewer / viewer) once user-management UI lands.

alter table users enable row level security;
alter table subjects enable row level security;
alter table competencies enable row level security;
alter table modules enable row level security;
alter table question_templates enable row level security;
alter table assignments enable row level security;
alter table attempts enable row level security;
alter table attempt_scores_history enable row level security;
alter table attempt_events enable row level security;
alter table generation_runs enable row level security;
alter table reference_documents enable row level security;
alter table reference_chunks enable row level security;
alter table assessment_series enable row level security;
alter table series_assignments enable row level security;
alter table competency_scores enable row level security;
alter table training_suggestions enable row level security;

-- Service role bypasses RLS by default in Supabase; no policy needed for it.

-- Read-only: any authenticated internal user can read most tables.
-- Candidates do not authenticate via Supabase Auth; their access is mediated
-- by the FastAPI server using a signed magic-link token, so they never hit RLS.

create policy "authenticated read users"
  on users for select to authenticated using (true);

create policy "authenticated read subjects"
  on subjects for select to authenticated using (true);

create policy "anon and authenticated read competencies"
  on competencies for select using (true);

create policy "authenticated read modules"
  on modules for select to authenticated using (true);

create policy "authenticated read question_templates"
  on question_templates for select to authenticated using (true);

create policy "authenticated read assignments"
  on assignments for select to authenticated using (true);

create policy "authenticated read attempts"
  on attempts for select to authenticated using (true);

create policy "authenticated read attempt_scores_history"
  on attempt_scores_history for select to authenticated using (true);

create policy "authenticated read attempt_events"
  on attempt_events for select to authenticated using (true);

create policy "authenticated read generation_runs"
  on generation_runs for select to authenticated using (true);

create policy "authenticated read reference_documents"
  on reference_documents for select to authenticated using (true);

create policy "authenticated read reference_chunks"
  on reference_chunks for select to authenticated using (true);

create policy "authenticated read assessment_series"
  on assessment_series for select to authenticated using (true);

create policy "authenticated read series_assignments"
  on series_assignments for select to authenticated using (true);

create policy "authenticated read competency_scores"
  on competency_scores for select to authenticated using (true);

create policy "authenticated read training_suggestions"
  on training_suggestions for select to authenticated using (true);

-- Writes intentionally absent: the FastAPI server uses the service role key.
-- When admin direct-edits land, add per-role write policies keyed off users.role.
