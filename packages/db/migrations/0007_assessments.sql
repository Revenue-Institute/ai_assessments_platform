-- 0007_assessments.sql
-- Introduce a real "Assessment" container that groups one or more modules.
-- Modules continue to own question_templates; an assessment is an ordered
-- collection of modules. Assignments now bind a subject to an assessment
-- (snapshotted at assignment time, same pattern as the old module snapshot).
--
-- Backwards compatibility: existing assignments keep their module_snapshot
-- and module_id columns; new assignments populate assessment_id +
-- assessment_snapshot. Application code reads assessment_snapshot first
-- and falls back to module_snapshot for legacy rows.

create table assessments (
  id uuid primary key default gen_random_uuid(),
  slug text not null,
  title text not null,
  description text,
  status text not null check (status in ('draft','published','archived')),
  version int not null default 1,
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  published_at timestamptz,
  unique (slug, version)
);

create index assessments_status_idx on assessments(status);

create table assessment_modules (
  assessment_id uuid not null references assessments(id) on delete cascade,
  module_id uuid not null references modules(id),
  position int not null,
  primary key (assessment_id, module_id),
  unique (assessment_id, position)
);

create index assessment_modules_assessment_idx
  on assessment_modules(assessment_id, position);

alter table assignments
  add column if not exists assessment_id uuid references assessments(id);
alter table assignments
  add column if not exists assessment_snapshot jsonb;

create index if not exists assignments_assessment_idx on assignments(assessment_id);

-- Auto-create a single-module assessment for every existing published
-- module so the catalog isn't empty after deploy. Slugged off the module
-- so they're easy to find.
do $$
declare
  m record;
  new_assessment_id uuid;
begin
  for m in
    select id, slug, title, description, status, created_by, published_at
    from modules
    where status = 'published'
  loop
    -- Skip if we already migrated this module.
    if exists (
      select 1 from assessments where slug = m.slug
    ) then
      continue;
    end if;

    insert into assessments (
      slug, title, description, status, version, created_by, published_at
    ) values (
      m.slug,
      m.title,
      m.description,
      m.status,
      1,
      m.created_by,
      m.published_at
    )
    returning id into new_assessment_id;

    insert into assessment_modules (assessment_id, module_id, position)
    values (new_assessment_id, m.id, 0);
  end loop;
end$$;
