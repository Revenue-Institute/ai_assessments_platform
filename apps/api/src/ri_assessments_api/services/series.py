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
