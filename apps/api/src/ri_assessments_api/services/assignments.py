"""Assignment lookup and consent transitions backed by Supabase (spec §4.4)."""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from supabase import Client

from ..auth import decode_candidate_token
from ..config import get_settings
from ..models.candidate import (
    CandidateAssignmentView,
    CandidateModuleView,
    CandidateSubjectView,
    ConsentResponse,
)
from .tokens import hash_token, is_expired

log = logging.getLogger(__name__)


def _question_count(module_snapshot: dict[str, Any]) -> int:
    questions = module_snapshot.get("questions") or []
    return len(questions)


def resolve_token(supabase: Client, raw_token: str) -> CandidateAssignmentView:
    """Look up an assignment by its magic-link token. Raises 404/410 on any
    failure path so we never leak whether a token exists.

    Verifies the JWT signature, audience, and exp claim BEFORE the DB
    lookup so a forged or tampered token is rejected without leaking
    timing information about which token hashes exist. Skipped only when
    JWT_SIGNING_SECRET is unset (local dev without a configured secret),
    so production rotation of the secret invalidates outstanding links."""

    if get_settings().jwt_signing_secret:
        # decode_candidate_token raises 401 on bad sig / wrong aud / exp.
        decode_candidate_token(raw_token)

    token_hash = hash_token(raw_token)

    assignment_q = (
        supabase.table("assignments")
        .select(
            "id, status, expires_at, started_at, consent_at, "
            "module_snapshot, assessment_snapshot, subject_id, "
            "consumed_at, consumed_user_agent, consumed_ip_hash"
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

    # Prefer assessment_snapshot when present; falls back to
    # module_snapshot for legacy assignments. See migration 0007 +
    # CLAUDE.md note on the dual-write cutover.
    snapshot = row.get("assessment_snapshot") or row.get("module_snapshot") or {}
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


def _client_binding_matches(
    row: dict[str, Any],
    *,
    ip_hash: str | None,
    user_agent: str | None,
) -> bool:
    """Match the current request against the consumer fingerprint stored
    at first consent. Tolerant: if either the UA or the IP hash matches
    the stored value, we admit the call. Only a hard divergence on both
    axes (different device AND different network fingerprint) is treated
    as a session hijack.

    A null stored value never matches, so the check is conservative when
    the original consent did not capture a fingerprint."""

    stored_ua = row.get("consumed_user_agent")
    stored_ip = row.get("consumed_ip_hash")
    if stored_ua and user_agent and stored_ua == user_agent:
        return True
    return bool(stored_ip and ip_hash and stored_ip == ip_hash)


def record_consent(
    supabase: Client,
    raw_token: str,
    ip_hash: str | None,
    *,
    user_agent: str | None = None,
) -> ConsentResponse:
    """Records consent and flips the assignment to in_progress (spec §10.5).

    On first consent we capture the consumer fingerprint (consumed_at,
    consumed_user_agent, consumed_ip_hash). On subsequent calls the
    fingerprint must match (see _client_binding_matches) or we 409.
    This is the defense against a leaked magic-link token being replayed
    from a second device.

    Idempotent on the original device: re-submitting consent from the
    bound client returns the existing started_at without re-recording."""

    view = resolve_token(supabase, raw_token)

    if view.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This assessment has already been submitted.",
        )

    now = datetime.now(UTC)

    from .attempts import session_deadline as _session_deadline

    # Re-read the raw row to access binding columns (resolve_token returns
    # the projected CandidateAssignmentView which deliberately omits them).
    raw_q = (
        supabase.table("assignments")
        .select(
            "id, consumed_at, consumed_user_agent, consumed_ip_hash"
        )
        .eq("id", view.assignment_id)
        .limit(1)
        .execute()
    )
    raw_rows = raw_q.data or []
    raw_row = raw_rows[0] if raw_rows else {}
    already_consumed = bool(raw_row.get("consumed_at"))

    if already_consumed and not _client_binding_matches(
        raw_row, ip_hash=ip_hash, user_agent=user_agent
    ):
        log.warning(
            "magic-link consent rejected: client binding mismatch "
            "(assignment=%s stored_ua_present=%s stored_ip_present=%s)",
            view.assignment_id,
            bool(raw_row.get("consumed_user_agent")),
            bool(raw_row.get("consumed_ip_hash")),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This assessment link has already been opened on a "
                "different device. Contact your administrator if you "
                "need a fresh link."
            ),
        )

    if view.status == "in_progress" and view.started_at:
        deadline = _session_deadline(
            {
                "started_at": view.started_at.isoformat(),
                "expires_at": view.expires_at.isoformat(),
                "module_snapshot": {
                    "target_duration_minutes": view.module.target_duration_minutes,
                },
            }
        )
        # Already consented. Return the existing state.
        return ConsentResponse(
            assignment_id=view.assignment_id,
            status="in_progress",
            started_at=view.started_at,
            server_deadline=deadline or view.expires_at,
        )

    update = {
        "status": "in_progress",
        "started_at": now.isoformat(),
        "consent_at": now.isoformat(),
    }
    if ip_hash:
        update["consent_ip_hash"] = ip_hash
    if not already_consumed:
        update["consumed_at"] = now.isoformat()
        if user_agent:
            update["consumed_user_agent"] = user_agent
        if ip_hash:
            update["consumed_ip_hash"] = ip_hash

    supabase.table("assignments").update(update).eq(
        "id", view.assignment_id
    ).execute()

    deadline = _session_deadline(
        {
            "started_at": now.isoformat(),
            "expires_at": view.expires_at.isoformat(),
            "module_snapshot": {
                "target_duration_minutes": view.module.target_duration_minutes,
            },
        }
    )

    return ConsentResponse(
        assignment_id=view.assignment_id,
        status="in_progress",
        started_at=now,
        server_deadline=deadline or view.expires_at,
    )


def _parse_ts(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
