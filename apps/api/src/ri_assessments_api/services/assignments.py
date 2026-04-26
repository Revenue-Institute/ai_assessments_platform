"""Assignment lookup and consent transitions backed by Supabase (spec §4.4)."""

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from supabase import Client

from ..models.candidate import (
    CandidateAssignmentView,
    CandidateModuleView,
    CandidateSubjectView,
    ConsentResponse,
)
from .tokens import hash_token, is_expired


def _question_count(module_snapshot: dict[str, Any]) -> int:
    questions = module_snapshot.get("questions") or []
    return len(questions)


def resolve_token(supabase: Client, raw_token: str) -> CandidateAssignmentView:
    """Look up an assignment by its magic-link token. Raises 404/410 on any
    failure path so we never leak whether a token exists."""

    token_hash = hash_token(raw_token)

    assignment_q = (
        supabase.table("assignments")
        .select(
            "id, status, expires_at, started_at, consent_at, "
            "module_snapshot, subject_id"
        )
        .eq("token_hash", token_hash)
        .limit(1)
        .execute()
    )

    rows = assignment_q.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found.",
        )

    row = rows[0]

    expires_at = _parse_ts(row["expires_at"])
    if is_expired(expires_at, datetime.now(UTC)):
        # Idempotent: stamp expired status so the admin view stays accurate.
        if row["status"] not in ("completed", "expired", "cancelled"):
            supabase.table("assignments").update({"status": "expired"}).eq(
                "id", row["id"]
            ).execute()
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This assessment link has expired.",
        )

    if row["status"] == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This assessment has been cancelled.",
        )

    subject_q = (
        supabase.table("subjects")
        .select("full_name, type")
        .eq("id", row["subject_id"])
        .limit(1)
        .execute()
    )
    subject_rows = subject_q.data or []
    if not subject_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment subject is missing.",
        )

    snapshot = row["module_snapshot"] or {}
    module = CandidateModuleView(
        title=snapshot.get("title", "Assessment"),
        description=snapshot.get("description", ""),
        target_duration_minutes=int(snapshot.get("target_duration_minutes", 0)),
        question_count=_question_count(snapshot),
    )

    return CandidateAssignmentView(
        assignment_id=row["id"],
        status=row["status"],
        expires_at=expires_at,
        started_at=_parse_ts(row.get("started_at")),
        consent_at=_parse_ts(row.get("consent_at")),
        subject=CandidateSubjectView(
            full_name=subject_rows[0]["full_name"],
            type=subject_rows[0]["type"],
        ),
        module=module,
    )


def record_consent(
    supabase: Client,
    raw_token: str,
    ip_hash: str | None,
) -> ConsentResponse:
    """Records consent and flips the assignment to in_progress (spec §10.5).

    Idempotent: re-submitting consent for an in-progress assignment returns
    the existing started_at without re-recording."""

    view = resolve_token(supabase, raw_token)

    if view.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This assessment has already been submitted.",
        )

    now = datetime.now(UTC)

    if view.status == "in_progress" and view.started_at:
        # Already consented. Return the existing state.
        return ConsentResponse(
            assignment_id=view.assignment_id,
            status="in_progress",
            started_at=view.started_at,
            server_deadline=view.expires_at,
        )

    update = {
        "status": "in_progress",
        "started_at": now.isoformat(),
        "consent_at": now.isoformat(),
    }
    if ip_hash:
        update["consent_ip_hash"] = ip_hash

    supabase.table("assignments").update(update).eq(
        "id", view.assignment_id
    ).execute()

    return ConsentResponse(
        assignment_id=view.assignment_id,
        status="in_progress",
        started_at=now,
        server_deadline=view.expires_at,
    )


def _parse_ts(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
