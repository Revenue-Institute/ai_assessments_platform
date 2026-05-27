-- 0019: bind magic-link consumption to a single client session.
--
-- Before this migration, a leaked candidate token was replayable from
-- any device for the entire expires_at window. The first party to call
-- /a/{token} could consent and "own" the assessment session, and the
-- legitimate candidate (or an attacker on a different device) could
-- then race for control. We had no record of which device claimed the
-- link first, so audit / forensics were blind.
--
-- This migration adds three columns capturing the first-consenter
-- fingerprint:
--   consumed_at        : timestamp of the first successful consent
--   consumed_user_agent: the User-Agent header at first consent
--   consumed_ip_hash   : sha256(client IP) at first consent (PII hygiene)
--
-- Service-layer policy (apps/api/src/ri_assessments_api/services/
-- assignments.py): once consumed_at is set, subsequent calls to
-- record_consent are admitted only when at least one of (user-agent,
-- ip_hash) matches the stored fingerprint. Tolerant on either axis
-- because mobile networks change IPs mid-session and ad blockers can
-- strip the UA. Hard fail (409) when both diverge: that is the
-- "second device, replay attack" shape.
--
-- Idempotent.

alter table public.assignments
  add column if not exists consumed_at timestamptz null,
  add column if not exists consumed_user_agent text null,
  add column if not exists consumed_ip_hash text null;

-- Index supports the rare admin query "show me assignments consumed by
-- a known-bad IP fingerprint" without table-scanning the whole table.
create index if not exists idx_assignments_consumed_ip_hash
  on public.assignments(consumed_ip_hash)
  where consumed_ip_hash is not null;
