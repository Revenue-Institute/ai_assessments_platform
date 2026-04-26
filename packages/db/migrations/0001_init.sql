-- 0001_init.sql
-- Revenue Institute Assessments Platform: initial schema (spec §4).
-- All timestamps UTC. All ids uuid unless noted. RLS scaffolding in 0002.

create extension if not exists "pgcrypto";
create extension if not exists "vector";

-- §4.1 Identity --------------------------------------------------------------

create table users (
  id uuid primary key references auth.users(id),
  email text not null unique,
  full_name text,
  role text not null check (role in ('admin','reviewer','viewer')),
  created_at timestamptz not null default now()
);

create table subjects (
  id uuid primary key default gen_random_uuid(),
  type text not null check (type in ('candidate','employee')),
  full_name text not null,
  email text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (email, type)
);

-- §4.2 Competencies ----------------------------------------------------------

create table competencies (
  id text primary key,
  domain text not null,
  label text not null,
  description text,
  parent_id text references competencies(id)
);

create index competencies_domain_idx on competencies(domain);
create index competencies_parent_idx on competencies(parent_id);

-- §4.3 Modules and question templates ---------------------------------------

create table modules (
  id uuid primary key default gen_random_uuid(),
  slug text not null,
  title text not null,
  description text,
  domain text not null,
  target_duration_minutes int not null,
  difficulty text not null check (difficulty in ('junior','mid','senior','expert')),
  status text not null check (status in ('draft','published','archived')),
  version int not null default 1,
  created_by uuid references users(id),
  source_generation_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  published_at timestamptz,
  unique (slug, version)
);

create index modules_status_idx on modules(status);

create table question_templates (
  id uuid primary key default gen_random_uuid(),
  module_id uuid not null references modules(id) on delete cascade,
  position int not null,
  type text not null,
  prompt_template text not null,
  variable_schema jsonb not null,
  solver_code text,
  solver_language text default 'python',
  interactive_config jsonb,
  rubric jsonb not null,
  competency_tags text[] not null default '{}',
  time_limit_seconds int,
  max_points numeric(6,2) not null default 10,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create index question_templates_module_position_idx on question_templates(module_id, position);

-- §4.4 Assignments and attempts ---------------------------------------------

create table assignments (
  id uuid primary key default gen_random_uuid(),
  subject_id uuid not null references subjects(id),
  module_snapshot jsonb not null,
  module_id uuid references modules(id),
  created_by uuid not null references users(id),
  token_hash text not null,
  expires_at timestamptz not null,
  status text not null default 'pending'
    check (status in ('pending','in_progress','completed','expired','cancelled')),
  started_at timestamptz,
  completed_at timestamptz,
  random_seed bigint not null,
  total_time_seconds int,
  integrity_score numeric(5,2),
  final_score numeric(6,2),
  max_possible_score numeric(6,2),
  consent_at timestamptz,
  consent_ip_hash text,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create index assignments_subject_idx on assignments(subject_id);
create index assignments_status_idx on assignments(status);
create index assignments_token_hash_idx on assignments(token_hash);

create table attempts (
  id uuid primary key default gen_random_uuid(),
  assignment_id uuid not null references assignments(id) on delete cascade,
  question_template_id uuid not null references question_templates(id),
  rendered_prompt text not null,
  variables_used jsonb not null,
  expected_answer jsonb,
  raw_answer jsonb,
  interactive_artifact_url text,
  started_at timestamptz,
  submitted_at timestamptz,
  active_time_seconds int,
  score numeric(6,2),
  max_score numeric(6,2) not null,
  score_rationale text,
  scorer_model text,
  scorer_version text,
  rubric_version text,
  scorer_confidence numeric(4,3),
  needs_review boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  unique (assignment_id, question_template_id)
);

create index attempts_assignment_idx on attempts(assignment_id);

-- §9.3 Score audit history (raw answers immutable, scores versioned)
create table attempt_scores_history (
  id bigserial primary key,
  attempt_id uuid not null references attempts(id) on delete cascade,
  score numeric(6,2),
  max_score numeric(6,2) not null,
  score_rationale text,
  scorer_model text,
  scorer_version text,
  rubric_version text,
  scorer_confidence numeric(4,3),
  recorded_at timestamptz not null default now(),
  recorded_by uuid references users(id)
);

create index attempt_scores_history_attempt_idx on attempt_scores_history(attempt_id, recorded_at desc);

-- §4.5 Events (integrity + timing) ------------------------------------------

create table attempt_events (
  id bigserial primary key,
  attempt_id uuid not null references attempts(id) on delete cascade,
  assignment_id uuid not null references assignments(id) on delete cascade,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  client_timestamp timestamptz,
  server_timestamp timestamptz not null default now(),
  user_agent text,
  ip_hash text
);

create index attempt_events_assignment_time_idx on attempt_events(assignment_id, server_timestamp);
create index attempt_events_attempt_idx on attempt_events(attempt_id);

-- §4.6 AI generation history ------------------------------------------------

create table generation_runs (
  id uuid primary key default gen_random_uuid(),
  created_by uuid references users(id),
  stage text not null check (stage in ('outline','full','single_question','revision')),
  input_brief jsonb not null,
  output jsonb not null,
  model text not null,
  tokens_in int,
  tokens_out int,
  latency_ms int,
  status text not null check (status in ('pending','success','failed')),
  error text,
  parent_run_id uuid references generation_runs(id),
  created_at timestamptz not null default now()
);

create index generation_runs_created_by_idx on generation_runs(created_by, created_at desc);
create index generation_runs_parent_idx on generation_runs(parent_run_id);

create table reference_documents (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  source_url text,
  content text,
  uploaded_by uuid references users(id),
  domain text,
  created_at timestamptz not null default now()
);

-- NOTE: spec §4.6 declares vector(1536) (matches OpenAI text-embedding-3-small).
-- Spec §19 defaults the embedding provider to Voyage-3 (1024 dims). Resolve before
-- committing to a provider; this column type cannot vary per row. Keeping the
-- spec literal (1536) here so OpenAI works out of the box; if Voyage-3 is chosen,
-- alter to vector(1024) before any chunks are inserted.
create table reference_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references reference_documents(id) on delete cascade,
  content text not null,
  embedding vector(1536),
  position int not null
);

create index reference_chunks_embedding_idx
  on reference_chunks
  using hnsw (embedding vector_cosine_ops);

create index reference_chunks_document_idx on reference_chunks(document_id, position);

-- §4.7 Assessment series and rollups ----------------------------------------

create table assessment_series (
  id uuid primary key default gen_random_uuid(),
  subject_id uuid not null references subjects(id),
  name text not null,
  competency_focus text[] not null,
  cadence_days int,
  next_due_at timestamptz,
  created_at timestamptz not null default now()
);

create index assessment_series_subject_idx on assessment_series(subject_id);
create index assessment_series_next_due_idx on assessment_series(next_due_at);

create table series_assignments (
  series_id uuid not null references assessment_series(id) on delete cascade,
  assignment_id uuid not null references assignments(id) on delete cascade,
  sequence_number int not null,
  primary key (series_id, assignment_id)
);

create table competency_scores (
  id uuid primary key default gen_random_uuid(),
  subject_id uuid not null references subjects(id),
  competency_id text not null references competencies(id),
  assignment_id uuid not null references assignments(id),
  score_pct numeric(5,2) not null,
  point_total numeric(6,2) not null,
  point_possible numeric(6,2) not null,
  computed_at timestamptz not null default now()
);

create index competency_scores_subject_competency_idx
  on competency_scores(subject_id, competency_id, computed_at desc);

-- §11.5 Training suggestions (wired, not auto-populated until v1.1) ---------

create table training_suggestions (
  id uuid primary key default gen_random_uuid(),
  subject_id uuid not null references subjects(id),
  competency_id text not null references competencies(id),
  suggested_at timestamptz not null default now(),
  linked_resource_url text,
  dismissed_at timestamptz
);

create index training_suggestions_subject_idx on training_suggestions(subject_id, suggested_at desc);

-- assignments.source_generation_id should resolve to a generation_run once published.
alter table modules
  add constraint modules_source_generation_id_fkey
  foreign key (source_generation_id) references generation_runs(id);
