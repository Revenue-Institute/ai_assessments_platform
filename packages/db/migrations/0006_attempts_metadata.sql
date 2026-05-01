-- 0006_attempts_metadata.sql
-- Add metadata jsonb column to attempts. Used by services/attempts.py to
-- persist runner-specific artifacts (e.g. ipynb_path for notebook
-- attempts) without bloating the columned schema.

alter table attempts
  add column if not exists metadata jsonb not null default '{}'::jsonb;
