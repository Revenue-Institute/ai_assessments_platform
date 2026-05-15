-- 0009: atomic increment for attempts.active_time_seconds.
--
-- Heartbeats POST a delta of focused-seconds-since-last-heartbeat. The
-- old read-modify-write pattern in services/integrity.py raced when two
-- heartbeats landed in the same second window. This RPC does the
-- increment server-side under the row's MVCC lock so concurrent
-- heartbeats are conflict-free.

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
begin
  if p_delta is null or p_delta <= 0 then
    select coalesce(active_time_seconds, 0) into new_total
    from attempts where id = p_attempt_id;
    return coalesce(new_total, 0);
  end if;

  update attempts
     set active_time_seconds = coalesce(active_time_seconds, 0) + p_delta
   where id = p_attempt_id
   returning active_time_seconds into new_total;

  return coalesce(new_total, 0);
end;
$$;

revoke all on function public.increment_attempt_active_seconds(uuid, integer) from public;
grant execute on function public.increment_attempt_active_seconds(uuid, integer) to anon, authenticated, service_role;
