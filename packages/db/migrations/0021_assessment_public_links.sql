-- 0021_assessment_public_links.sql
-- Public self-enrollment links for assessments.
--
-- Lets an admin mint a shareable link for a published assessment. A
-- candidate opens the link, enters their name + email, and the backend
-- self-provisions a subject + assignment (mirroring
-- services/admin.create_assignment) and drops them into the normal
-- /a/{token} consent + attempt flow. This removes the
-- admin-adds-candidate-then-creates-assignment step for open / inbound
-- funnels.
--
-- The token is the unique public handle. Rotating a link inserts a fresh
-- row and disables the old one, so a leaked URL can be revoked without
-- touching the assessment. Registration validates enabled + expiry +
-- published and dedupes by subject so one email cannot spawn unbounded
-- attempts.

create table assessment_public_links (
  id uuid primary key default gen_random_uuid(),
  assessment_id uuid not null references assessments(id) on delete cascade,
  token text not null unique,
  enabled boolean not null default true,
  -- Optional hard cutoff for the link itself (distinct from the per
  -- assignment deadline below). Null means the link never expires.
  expires_at timestamptz,
  -- Deadline applied to each assignment minted through this link, in days
  -- from registration. Mirrors AssignmentCreateRequest.expires_in_days.
  assignment_expires_in_days int not null default 7
    check (assignment_expires_in_days between 1 and 365),
  -- Optional cap on total successful registrations. Null means unlimited.
  max_uses int check (max_uses is null or max_uses > 0),
  uses_count int not null default 0,
  created_by uuid references users(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create index assessment_public_links_assessment_idx
  on assessment_public_links(assessment_id);

-- Service-role API only; RLS denies the anon/authenticated roles by
-- default (no policies), matching the rest of the schema where the
-- FastAPI service key is the sole writer.
alter table assessment_public_links enable row level security;
