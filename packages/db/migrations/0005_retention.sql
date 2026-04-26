-- Retention policy: integrity events older than 12 months get pruned by
-- the prune-integrity-events job (scripts/prune-integrity-events.sh).
-- Spec §11.4: behavioral data retention. We keep the row schema as-is and
-- rely on a scheduled job rather than partition rotation since the volume
-- per assignment is small.

-- Helper function: callable by the cron worker or directly via SQL.
create or replace function prune_integrity_events(retention_days int default 365)
returns table(deleted_count bigint)
language plpgsql
security definer
as $$
declare
  cutoff timestamptz := now() - make_interval(days => retention_days);
  removed bigint;
begin
  delete from attempt_events
   where server_timestamp < cutoff
  returning 1 into removed;
  -- The returning into above only captures one row; use row count instead.
  get diagnostics removed = row_count;
  return query select removed;
end;
$$;

comment on function prune_integrity_events is
  'Spec §11.4: deletes attempt_events older than the retention window (default 12 months).';
