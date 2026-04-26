"""Integrity event ingestion + heartbeat accumulation (spec §10)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from supabase import Client

from .attempts import get_assignment_for_token

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
    for event in events:
        event_type = event.get("type")
        if event_type not in ALLOWED_EVENT_TYPES:
            continue
        attempt_id = event.get("attempt_id") or default_attempt_id
        if not attempt_id:
            continue
        rows.append(
            {
                "attempt_id": attempt_id,
                "assignment_id": assignment["id"],
                "event_type": event_type,
                "payload": event.get("payload") or {},
                "client_timestamp": event.get("client_timestamp"),
                "user_agent": user_agent,
                "ip_hash": ip_hash,
            }
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment is not in progress.",
        )
    expires_at = assignment.get("expires_at")
    if expires_at:
        deadline = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if deadline <= datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Assessment time limit has elapsed.",
            )

    attempt_id = _current_attempt_id(supabase, assignment["id"])
    if not attempt_id:
        return {"ok": True, "applied": 0}

    delta = max(0, int(focused_seconds_since_last))
    if delta == 0:
        return {"ok": True, "applied": 0, "attempt_id": attempt_id}

    current = (
        supabase.table("attempts")
        .select("active_time_seconds")
        .eq("id", attempt_id)
        .limit(1)
        .execute()
    )
    rows = current.data or []
    existing = int(rows[0].get("active_time_seconds") or 0) if rows else 0

    supabase.table("attempts").update(
        {"active_time_seconds": existing + delta}
    ).eq("id", attempt_id).execute()

    return {
        "ok": True,
        "applied": delta,
        "attempt_id": attempt_id,
        "total_active_seconds": existing + delta,
    }
