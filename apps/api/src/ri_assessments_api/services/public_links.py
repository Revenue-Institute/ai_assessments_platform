"""Public self-enrollment links for assessments (spec extension).

An admin mints a shareable link per assessment; an unauthenticated
candidate opens it, submits name + email, and we self-provision a subject
+ assignment that feeds the standard /a/{token} consent + attempt flow.

This mirrors services.admin.create_assignment for the assessment-bound
path but without an admin principal: the link itself is the authorization
to enroll. Abuse is bounded by per-IP rate limiting (router layer), the
link's enabled / expiry / max_uses gates, and per-email dedupe so one
candidate cannot spawn unbounded attempts.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from supabase import Client

from ..auth import AdminPrincipal, ensure_role, issue_candidate_token
from ..config import get_settings
from ..models.admin import PublicLinkCreateRequest, PublicLinkView
from ..models.public import (
    PublicAssessmentView,
    PublicRegisterRequest,
    PublicRegisterResponse,
)
from .admin import _assessment_snapshot, get_assessment_detail
from .assignments import _parse_ts
from .tokens import candidate_token_url, hash_token

log = logging.getLogger(__name__)

_TABLE = "assessment_public_links"


def _enroll_url(token: str) -> str:
    """Public landing URL. Lives under /a/* so the single-host prod nginx
    routes it to the candidate app without a new location block."""

    base = get_settings().next_public_candidate_url.rstrip("/")
    return f"{base}/a/enroll/{token}"


def _to_view(row: dict[str, Any]) -> PublicLinkView:
    return PublicLinkView(
        id=row["id"],
        assessment_id=row["assessment_id"],
        token=row["token"],
        enabled=row["enabled"],
        url=_enroll_url(row["token"]),
        expires_at=_parse_ts(row.get("expires_at")),
        assignment_expires_in_days=row["assignment_expires_in_days"],
        max_uses=row.get("max_uses"),
        uses_count=row["uses_count"],
        created_at=_parse_ts(row["created_at"]),
    )


# -- Admin management --------------------------------------------------------


def _active_link_row(
    supabase: Client, assessment_id: str
) -> dict[str, Any] | None:
    res = (
        supabase.table(_TABLE)
        .select("*")
        .eq("assessment_id", assessment_id)
        .eq("enabled", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def get_public_link(
    supabase: Client, assessment_id: str
) -> PublicLinkView | None:
    """Active link for an assessment, or None if none is enabled."""

    row = _active_link_row(supabase, assessment_id)
    return _to_view(row) if row else None


def create_public_link(
    supabase: Client,
    principal: AdminPrincipal,
    assessment_id: str,
    payload: PublicLinkCreateRequest,
) -> PublicLinkView:
    """Create the assessment's public link, or return the existing active
    one (idempotent enable). Rotate via rotate_public_link."""

    ensure_role(principal, "admin")
    # 404s if the assessment doesn't exist.
    get_assessment_detail(supabase, assessment_id)

    existing = _active_link_row(supabase, assessment_id)
    if existing:
        return _to_view(existing)

    inserted = (
        supabase.table(_TABLE)
        .insert(
            {
                "id": str(uuid.uuid4()),
                "assessment_id": assessment_id,
                "token": secrets.token_urlsafe(24),
                "enabled": True,
                "expires_at": (
                    payload.expires_at.isoformat()
                    if payload.expires_at
                    else None
                ),
                "assignment_expires_in_days": payload.assignment_expires_in_days,
                "max_uses": payload.max_uses,
                "created_by": principal.user_id,
            }
        )
        .execute()
    )
    if not inserted.data:
        raise HTTPException(
            status_code=500, detail="Failed to create public link."
        )
    return _to_view(inserted.data[0])


def disable_public_link(
    supabase: Client, principal: AdminPrincipal, assessment_id: str
) -> None:
    """Revoke the assessment's public link(s). Outstanding assignments
    already minted through it keep working; only new enrollments stop."""

    ensure_role(principal, "admin")
    supabase.table(_TABLE).update(
        {"enabled": False, "updated_at": datetime.now(UTC).isoformat()}
    ).eq("assessment_id", assessment_id).eq("enabled", True).execute()


def rotate_public_link(
    supabase: Client,
    principal: AdminPrincipal,
    assessment_id: str,
    payload: PublicLinkCreateRequest,
) -> PublicLinkView:
    """Disable the current link and mint a fresh one, invalidating the old
    URL. Use when a link leaks."""

    ensure_role(principal, "admin")
    disable_public_link(supabase, principal, assessment_id)
    # _active_link_row now returns None, so create makes a new one.
    return create_public_link(supabase, principal, assessment_id, payload)


# -- Public (unauthenticated) enrollment -------------------------------------


def _resolve_open_link(supabase: Client, link_token: str) -> dict[str, Any]:
    """Load a usable link by token. Always raises a generic 404 on any
    closed/missing path so the endpoint never reveals why a link is
    unavailable."""

    res = (
        supabase.table(_TABLE)
        .select("*")
        .eq("token", link_token)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(
            status_code=404, detail="This enrollment link is not available."
        )
    link = rows[0]
    now = datetime.now(UTC)
    if not link["enabled"]:
        raise HTTPException(
            status_code=404, detail="This enrollment link is no longer active."
        )
    expires_at = _parse_ts(link.get("expires_at"))
    if expires_at is not None and expires_at <= now:
        raise HTTPException(
            status_code=404, detail="This enrollment link has expired."
        )
    if link.get("max_uses") is not None and link["uses_count"] >= link["max_uses"]:
        raise HTTPException(
            status_code=404,
            detail="This enrollment link has reached its limit.",
        )
    return link


def get_public_assessment(
    supabase: Client, link_token: str
) -> PublicAssessmentView:
    """Intro shown on the enrollment landing page."""

    link = _resolve_open_link(supabase, link_token)
    detail = get_assessment_detail(supabase, link["assessment_id"])
    if detail.status != "published":
        # Treat an unpublished assessment as a closed link; don't leak that
        # it exists in draft.
        raise HTTPException(
            status_code=404, detail="This assessment is not currently open."
        )
    return PublicAssessmentView(
        title=detail.title,
        description=detail.description,
        module_count=detail.module_count,
        question_count=detail.question_count,
        total_duration_minutes=detail.total_duration_minutes,
    )


def register_via_public_link(
    supabase: Client,
    link_token: str,
    payload: PublicRegisterRequest,
    *,
    ip_hash: str | None = None,
) -> PublicRegisterResponse:
    """Self-provision a subject + assignment for a candidate and return a
    magic-link token. Dedupes by email: blocks a second attempt once
    completed, resumes an open one, otherwise mints a new assignment."""

    if not payload.consent:
        raise HTTPException(
            status_code=400,
            detail="You must agree to begin the assessment.",
        )

    link = _resolve_open_link(supabase, link_token)
    assessment_id = link["assessment_id"]

    # Freeze the assessment now (also enforces published; surface a closed
    # link rather than the admin-facing 409 if it isn't).
    try:
        snapshot = _assessment_snapshot(supabase, assessment_id)
    except HTTPException as exc:
        if exc.status_code == 409:
            raise HTTPException(
                status_code=404,
                detail="This assessment is not currently open.",
            ) from exc
        raise

    email = payload.email.strip().lower()
    full_name = payload.full_name.strip()

    # Upsert subject keyed by (email, candidate) per the subjects unique
    # constraint. Keep the latest name they provide.
    subj_q = (
        supabase.table("subjects")
        .select("id, full_name")
        .eq("email", email)
        .eq("type", "candidate")
        .limit(1)
        .execute()
    )
    if subj_q.data:
        subject_id = subj_q.data[0]["id"]
        if full_name and subj_q.data[0].get("full_name") != full_name:
            supabase.table("subjects").update({"full_name": full_name}).eq(
                "id", subject_id
            ).execute()
    else:
        subj_ins = (
            supabase.table("subjects")
            .insert(
                {
                    "type": "candidate",
                    "full_name": full_name,
                    "email": email,
                    "metadata": {
                        "source": "public_link",
                        "public_link_id": link["id"],
                    },
                }
            )
            .execute()
        )
        if not subj_ins.data:
            raise HTTPException(status_code=500, detail="Failed to register.")
        subject_id = subj_ins.data[0]["id"]

    now = datetime.now(UTC)

    # Dedupe against the candidate's most recent assignment for this
    # assessment.
    prior_q = (
        supabase.table("assignments")
        .select("id, status, expires_at")
        .eq("subject_id", subject_id)
        .eq("assessment_id", assessment_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if prior_q.data:
        prior = prior_q.data[0]
        if prior["status"] == "completed":
            raise HTTPException(
                status_code=409,
                detail="You have already completed this assessment.",
            )
        prior_expiry = _parse_ts(prior["expires_at"])
        if prior["status"] in ("pending", "in_progress") and (
            prior_expiry is None or prior_expiry > now
        ):
            # Resume: re-issue a token bound to the same assignment, which
            # rotates token_hash and invalidates any earlier link.
            resume_expiry = prior_expiry or (
                now + timedelta(days=link["assignment_expires_in_days"])
            )
            token = issue_candidate_token(
                assignment_id=prior["id"],
                subject_id=subject_id,
                expires_at=resume_expiry,
            )
            supabase.table("assignments").update(
                {"token_hash": hash_token(token)}
            ).eq("id", prior["id"]).execute()
            return PublicRegisterResponse(
                token=token,
                redirect_path=f"/a/{token}",
                resumed=True,
            )

    # Mint a fresh assignment (mirrors services.admin.create_assignment).
    expires_at = now + timedelta(days=link["assignment_expires_in_days"])
    assignment_id = str(uuid.uuid4())
    token = issue_candidate_token(
        assignment_id=assignment_id,
        subject_id=subject_id,
        expires_at=expires_at,
    )
    metadata: dict[str, Any] = {"public_link_id": link["id"]}
    if ip_hash:
        metadata["registration_ip_hash"] = ip_hash
    supabase.table("assignments").insert(
        {
            "id": assignment_id,
            "subject_id": subject_id,
            "created_by": link.get("created_by"),
            "assessment_id": assessment_id,
            "assessment_snapshot": snapshot,
            "token_hash": hash_token(token),
            "expires_at": expires_at.isoformat(),
            "status": "pending",
            "random_seed": secrets.randbits(63),
            "metadata": metadata,
        }
    ).execute()

    # Best-effort usage counter (not atomic, fine at this volume).
    supabase.table(_TABLE).update({"uses_count": link["uses_count"] + 1}).eq(
        "id", link["id"]
    ).execute()

    # Best-effort: email the link so they can resume from their inbox. The
    # candidate is redirected immediately regardless of delivery.
    try:
        from .email import send_magic_link

        send_magic_link(
            to_email=email,
            subject_full_name=full_name or "there",
            module_title=snapshot.get("title", "Assessment"),
            magic_link_url=candidate_token_url(
                get_settings().next_public_candidate_url, token
            ),
            expires_at=expires_at,
        )
    except Exception:  # pragma: no cover - delivery is non-blocking
        log.exception("public-link magic-link email failed")

    return PublicRegisterResponse(
        token=token,
        redirect_path=f"/a/{token}",
        resumed=False,
    )
