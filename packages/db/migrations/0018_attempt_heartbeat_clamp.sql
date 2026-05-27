-- 0018: server-authoritative integrity heartbeat clamp (spec §10.4).
--
-- Before this migration, the candidate browser was free to claim any
-- focused_seconds_since_last delta on each heartbeat. A malicious client
-- could POST {"focused_seconds_since_last": 999} once per second and
-- inflate active_time_seconds to push the integrity score over the
-- "<30% active time" floor. Server had no wall-clock cross-check.
--
-- We add attempts.last_heartbeat_at and rewrite the increment RPC to:
--   * Clamp p_delta to the wall-clock elapsed since the previous
--     heartbeat (with a small grace for clock skew + transport jitter).
--   * Stamp last_heartbeat_at to now() on every successful increment.
--   * Treat the first heartbeat after attempt start as bounded by
--     (now() - attempts.started_at).
--
-- Idempotent: ADD COLUMN IF NOT EXISTS + CREATE OR REPLACE FUNCTION.

alter table public.attempts
  add column if not exists last_heartbeat_at timestamptz null;

create or replace function public.increment_attempt_active_seconds(
  p_attempt_id uuid,
  p_delta integer
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  new_total integer;
  v_started timestamptz;
  v_last    timestamptz;
  v_now     timestamptz := now();
  v_window  integer;
  v_clamped integer;
  -- Grace for client clock skew, network jitter, and the 10-second
  -- heartbeat cadence overshooting by half a tick. 5s lets a healthy
  -- 10s cadence client always credit its full interval; a malicious
  -- client claiming 999s gets clamped to (elapsed + 5).
  grace constant integer := 5;
begin
  if p_delta is null or p_delta <= 0 then
    select coalesce(active_time_seconds, 0) into new_total
    from attempts where id = p_attempt_id;
    return coalesce(new_total, 0);
  end if;

  select started_at, last_heartbeat_at
    into v_started, v_last
    from attempts
   where id = p_attempt_id;

  -- The wall-clock window the client could legitimately have been
  -- focused inside. Bounded below by 0 (never credit a backdated
  -- heartbeat) and above by grace + interval.
  v_window := greatest(
    0,
    ceil(extract(epoch from (v_now - coalesce(v_last, v_started, v_now))))::integer
  ) + grace;

  v_clamped := least(p_delta, v_window);

  update attempts
     set active_time_seconds = coalesce(active_time_seconds, 0) + v_clamped,
         last_heartbeat_at  = v_now
   where id = p_attempt_id
   returning active_time_seconds into new_total;

  return coalesce(new_total, 0);
end;
$$;

revoke all on function public.increment_attempt_active_seconds(uuid, integer) from public;
grant execute on function public.increment_attempt_active_seconds(uuid, integer) to anon, authenticated, service_role;
