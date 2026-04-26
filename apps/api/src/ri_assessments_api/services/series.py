"""Assessment series management (spec §11.4).

v1 scope: stores series rows + the link table to assignments. Auto-creating
the next assignment on cadence (and emailing the subject) lives in a
follow-up worker — for v1 the admin manually creates each assignment and
links it to a series."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from supabase import Client

from ..auth import AdminPrincipal
from ..models.benchmarks import (
    SeriesAssignmentSummary,
    SeriesCreateRequest,
    SeriesDetail,
    SeriesSummary,
)


def _ensure_role(principal: AdminPrincipal, *allowed: str) -> None:
    if principal.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{principal.role}' is not permitted for this action.",
        )


def _summary(row: dict[str, Any], *, assignment_count: int = 0) -> SeriesSummary:
    subject = row.get("subjects") or {}
    return SeriesSummary(
        id=row["id"],
        subject_id=row["subject_id"],
        subject_full_name=subject.get("full_name"),
        subject_email=subject.get("email"),
        name=row["name"],
        competency_focus=list(row.get("competency_focus") or []),
        cadence_days=row.get("cadence_days"),
        next_due_at=row.get("next_due_at"),
        created_at=row["created_at"],
        assignment_count=assignment_count,
    )


def list_series(supabase: Client) -> list[SeriesSummary]:
    res = (
        supabase.table("assessment_series")
        .select(
            "id, subject_id, name, competency_focus, cadence_days, "
            "next_due_at, created_at, subjects(full_name, email), "
            "series_assignments(assignment_id)"
        )
        .order("created_at", desc=True)
        .execute()
    )
    return [
        _summary(row, assignment_count=len(row.get("series_assignments") or []))
        for row in res.data or []
    ]


def create_series(
    supabase: Client, principal: AdminPrincipal, payload: SeriesCreateRequest
) -> SeriesSummary:
    _ensure_role(principal, "admin", "reviewer")
    next_due = payload.next_due_at
    if next_due is None and payload.cadence_days:
        next_due = datetime.now(UTC) + timedelta(days=payload.cadence_days)

    row = (
        supabase.table("assessment_series")
        .insert(
            {
                "id": str(uuid.uuid4()),
                "subject_id": payload.subject_id,
                "name": payload.name,
                "competency_focus": payload.competency_focus,
                "cadence_days": payload.cadence_days,
                "next_due_at": next_due.isoformat() if next_due else None,
            }
        )
        .execute()
    )
    if not row.data:
        raise HTTPException(status_code=500, detail="Failed to create series.")
    return _summary({**row.data[0], "subjects": None})


def get_series_detail(supabase: Client, series_id: str) -> SeriesDetail:
    res = (
        supabase.table("assessment_series")
        .select(
            "id, subject_id, name, competency_focus, cadence_days, "
            "next_due_at, created_at, subjects(full_name, email), "
            "series_assignments(sequence_number, assignments(id, status, "
            "final_score, max_possible_score, completed_at))"
        )
        .eq("id", series_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Series not found.")
    row = rows[0]
    links = row.get("series_assignments") or []
    summary_assignments: list[SeriesAssignmentSummary] = []
    for link in sorted(links, key=lambda x: x.get("sequence_number", 0)):
        a = link.get("assignments") or {}
        if not a:
            continue
        summary_assignments.append(
            SeriesAssignmentSummary(
                assignment_id=a["id"],
                sequence_number=int(link.get("sequence_number") or 0),
                status=a["status"],
                final_score=a.get("final_score"),
                max_possible_score=a.get("max_possible_score"),
                completed_at=a.get("completed_at"),
            )
        )
    summary = _summary(row, assignment_count=len(summary_assignments))
    return SeriesDetail(
        **summary.model_dump(),
        assignments=summary_assignments,
    )


def dispatch_due_series(
    supabase: Client,
    principal: AdminPrincipal,
    *,
    expires_in_days: int = 7,
    send_email: bool = True,
) -> dict[str, Any]:
    """Walks every series with next_due_at <= now and issues the next
    assignment for each. Designed to be called from a Cloud Scheduler
    cron — idempotent and partial-failure tolerant."""

    _ensure_role(principal, "admin", "reviewer")

    now = datetime.now(UTC).isoformat()
    rows = (
        supabase.table("assessment_series")
        .select("id, next_due_at")
        .lte("next_due_at", now)
        .execute()
    ).data or []

    issued: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        try:
            result = issue_next_for_series(
                supabase,
                principal,
                series_id=row["id"],
                expires_in_days=expires_in_days,
                send_email=send_email,
            )
            issued.append(result)
        except HTTPException as exc:
            skipped.append({"series_id": row["id"], "detail": str(exc.detail)})
        except Exception as exc:
            skipped.append({"series_id": row["id"], "detail": str(exc)})

    return {
        "checked": len(rows),
        "issued": issued,
        "skipped": skipped,
    }


def issue_next_for_series(
    supabase: Client,
    principal: AdminPrincipal,
    *,
    series_id: str,
    expires_in_days: int = 7,
    send_email: bool = True,
) -> dict[str, Any]:
    """Materialize the next assignment in a series.

    Picks the first published module whose question competency_tags overlap
    with the series' competency_focus. Issues a fresh magic-link assignment,
    links it to the series with sequence_number = max + 1, advances
    next_due_at by cadence_days. Caller is responsible for whether to invoke
    this on demand (admin button) or via cron."""

    _ensure_role(principal, "admin", "reviewer")

    # Lazy import to avoid circular import (admin.py imports series? — not yet,
    # but defensive).
    from ..models.admin import AssignmentCreateRequest
    from .admin import create_assignment

    detail = (
        supabase.table("assessment_series")
        .select(
            "id, subject_id, name, competency_focus, cadence_days, next_due_at"
        )
        .eq("id", series_id)
        .limit(1)
        .execute()
    ).data or []
    if not detail:
        raise HTTPException(status_code=404, detail="Series not found.")
    row = detail[0]
    focus: list[str] = list(row.get("competency_focus") or [])
    if not focus:
        raise HTTPException(
            status_code=409,
            detail="Series has no competency_focus; cannot pick a module.",
        )

    # Find a published module that covers the focus tags. supabase-py's array
    # overlap operator is `overlaps`. Fall back to "any module with any tag".
    candidate_q = (
        supabase.table("modules")
        .select(
            "id, slug, title, status, question_templates(competency_tags)"
        )
        .eq("status", "published")
        .order("published_at", desc=True)
        .limit(50)
        .execute()
    ).data or []
    chosen_id: str | None = None
    for module in candidate_q:
        templates = module.get("question_templates") or []
        flat_tags = {
            tag
            for t in templates
            for tag in (t.get("competency_tags") or [])
        }
        if flat_tags & set(focus):
            chosen_id = module["id"]
            break
    if chosen_id is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "No published module covers any of the series' "
                "competency_focus tags."
            ),
        )

    link = create_assignment(
        supabase,
        principal,
        AssignmentCreateRequest(
            module_id=chosen_id,
            subject_id=row["subject_id"],
            expires_in_days=expires_in_days,
            send_email=send_email,
        ),
        send_email=send_email,
    )

    existing_links = (
        supabase.table("series_assignments")
        .select("sequence_number")
        .eq("series_id", series_id)
        .execute()
    ).data or []
    next_seq = (
        max((int(r.get("sequence_number") or 0) for r in existing_links), default=0)
        + 1
    )
    supabase.table("series_assignments").insert(
        {
            "series_id": series_id,
            "assignment_id": link.assignment_id,
            "sequence_number": next_seq,
        }
    ).execute()

    cadence = row.get("cadence_days")
    update: dict[str, Any] = {}
    if cadence:
        update["next_due_at"] = (
            datetime.now(UTC) + timedelta(days=int(cadence))
        ).isoformat()
    if update:
        supabase.table("assessment_series").update(update).eq(
            "id", series_id
        ).execute()

    return {
        "series_id": series_id,
        "assignment_id": link.assignment_id,
        "module_id": chosen_id,
        "magic_link_url": link.magic_link_url,
        "expires_at": link.expires_at,
        "sequence_number": next_seq,
        "next_due_at": update.get("next_due_at"),
    }


def link_assignment(
    supabase: Client,
    principal: AdminPrincipal,
    *,
    series_id: str,
    assignment_id: str,
) -> SeriesDetail:
    """Append an existing assignment to a series. sequence_number is computed
    as max(existing) + 1."""

    _ensure_role(principal, "admin", "reviewer")
    existing = (
        supabase.table("series_assignments")
        .select("sequence_number")
        .eq("series_id", series_id)
        .execute()
    ).data or []
    next_seq = (
        max((int(r.get("sequence_number") or 0) for r in existing), default=0) + 1
    )
    supabase.table("series_assignments").insert(
        {
            "series_id": series_id,
            "assignment_id": assignment_id,
            "sequence_number": next_seq,
        }
    ).execute()
    return get_series_detail(supabase, series_id)
