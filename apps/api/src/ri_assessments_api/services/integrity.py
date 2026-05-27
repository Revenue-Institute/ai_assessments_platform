"""Integrity event ingestion + heartbeat accumulation (spec §10)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from supabase import Client

from .attempts import get_assignment_for_token

log = logging.getLogger(__name__)

# Server-side cap on the client-claimed `focused_seconds_since_last`
# delta. Heartbeats fire every 10s; 30s leaves headroom for jitter and
# brief network outages while preventing a malicious client from
# inflating active_time_seconds in one shot. Defense-in-depth on top of
# the RPC-level wall-clock clamp installed in migration 0018.
_HEARTBEAT_MAX_DELTA_SECONDS = 30

# Allowed event_type values, mirrored from packages/schemas/src/integrity.ts.
# Server enforces the closed set so a misbehaving client cannot poison the log
# with arbitrary strings.
ALLOWED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "attempt_started",
        "question_served",
        "focus_gained",
        "focus_lost",
        "visibility_hidden",
        "visibility_visible",
        "fullscreen_entered",
        "fullscreen_exited",
        "copy_attempted",
        "cut_attempted",
        "paste_attempted",
        "context_menu_opened",
        "keyboard_shortcut_blocked",
        "window_resized",
        "devtools_opened",
        "network_offline",
        "network_online",
        "interactive_state_saved",
        "code_executed",
        "test_run",
        "n8n_workflow_saved",
        "notebook_cell_run",
        "question_submitted",
        "attempt_submitted",
    }
)


def _current_attempt_id(
    supabase: Client, assignment_id: str
) -> str | None:
    """Most-recently-started attempt for the assignment, used as the default
    pivot for an incoming event batch when the client does not name one."""
    res = (
        supabase.table("attempts")
        .select("id")
        .eq("assignment_id", assignment_id)
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0]["id"] if rows else None


def record_events(
    supabase: Client,
    raw_token: str,
    events: list[dict[str, Any]],
    *,
    user_agent: str | None,
    ip_hash: str | None,
) -> int:
    assignment = get_assignment_for_token(supabase, raw_token)

    # Resolve a default attempt id once. Per-event override still possible if
    # the payload carries one.
    default_attempt_id = _current_attempt_id(supabase, assignment["id"])

    rows: list[dict[str, Any]] = []
    dropped_types: list[str] = []
    for event in events:
        event_type = event.get("type")
        if event_type not in ALLOWED_EVENT_TYPES:
            dropped_types.append(str(event_type))
            continue
        attempt_id = event.get("attempt_id") or default_attempt_id
        if not attempt_id:
            dropped_types.append(f"{event_type}(no-attempt)")
            continue
        client_ts = event.get("client_timestamp")
        # supabase-py serializes via httpx's stdlib json.dumps, which
        # refuses datetime. Pydantic parses the inbound ISO string into
        # a datetime; coerce it back to ISO before the PostgREST insert.
        if hasattr(client_ts, "isoformat"):
            client_ts = client_ts.isoformat()
        rows.append(
            {
                "attempt_id": attempt_id,
                "assignment_id": assignment["id"],
                "event_type": event_type,
                "payload": event.get("payload") or {},
                "client_timestamp": client_ts,
                "user_agent": user_agent,
                "ip_hash": ip_hash,
            }
        )

    # Surface divergence between what the client submitted and what we
    # accepted. Unknown event types are usually a client/server schema
    # drift, and silent drops have historically masked the parity bug.
    if dropped_types:
        log.warning(
            "integrity events dropped (assignment=%s submitted=%d accepted=%d types=%s)",
            assignment["id"],
            len(events),
            len(rows),
            sorted(set(dropped_types)),
        )

    if not rows:
        return 0

    supabase.table("attempt_events").insert(rows).execute()
    return len(rows)


def record_heartbeat(
    supabase: Client,
    raw_token: str,
    focused_seconds_since_last: float,
) -> dict[str, Any]:
    """Accumulates focused-seconds on the most recent attempt. Server-side
    deadline check happens on every heartbeat so a stalled client does not
    silently overrun the time limit."""

    assignment = get_assignment_for_token(supabase, raw_token)
    if assignment["status"] != "in_progress":
        # Tolerate stale heartbeats arriving after the candidate has
        # consented but not yet started, or after they have completed.
        # Returning 200 here keeps the browser console quiet during the
        # natural race between the final submit and /done navigation.
        return {
            "ok": True,
            "applied": 0,
            "status": assignment.get("status"),
        }
    from .attempts import session_deadline

    deadline = session_deadline(assignment)
    if deadline and deadline <= datetime.now(UTC):
        # Spec §10.1 + CLAUDE.md: deadline-expired requests return 409, not
        # 410. Keeps the status code consistent with submit / save paths.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment time limit has elapsed.",
        )

    attempt_id = _current_attempt_id(supabase, assignment["id"])
    if not attempt_id:
        return {"ok": True, "applied": 0}

    # Defense-in-depth: cap the client-claimed delta BEFORE the RPC
    # sees it. The RPC (migration 0018) re-clamps server-side against
    # the wall-clock elapsed since the prior heartbeat. The double
    # clamp means a single malformed payload never gets credited for
    # more than a few seconds even on a fresh attempt that has no
    # last_heartbeat_at to compare against.
    requested = max(0, int(focused_seconds_since_last))
    delta = min(requested, _HEARTBEAT_MAX_DELTA_SECONDS)
    if requested > _HEARTBEAT_MAX_DELTA_SECONDS:
        log.warning(
            "integrity heartbeat over cadence (assignment=%s attempt=%s "
            "requested=%ds clamped=%ds)",
            assignment["id"],
            attempt_id,
            requested,
            delta,
        )
    if delta == 0:
        return {"ok": True, "applied": 0, "attempt_id": attempt_id}

    # Atomic server-side increment (migration 0009, hardened in 0018).
    # The RPC clamps p_delta against wall-clock elapsed and stamps
    # attempts.last_heartbeat_at so subsequent calls share the same
    # reference timestamp.
    rpc = supabase.rpc(
        "increment_attempt_active_seconds",
        {"p_attempt_id": attempt_id, "p_delta": delta},
    ).execute()
    new_total = rpc.data if isinstance(rpc.data, int) else int(rpc.data or 0)

    return {
        "ok": True,
        "applied": delta,
        "attempt_id": attempt_id,
        "total_active_seconds": new_total,
    }
