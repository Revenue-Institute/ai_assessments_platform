"""Admin-side business logic: modules, subjects, assignments (spec §14.1)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from supabase import Client

from ..auth import AdminPrincipal, issue_candidate_token
from ..config import get_settings
from ..models.admin import (
    AssignmentCreateRequest,
    AssignmentDetail,
    AssignmentMagicLink,
    AssignmentSummary,
    AttemptSummary,
    ModuleCreateRequest,
    ModuleDetail,
    ModulePatchRequest,
    ModuleSummary,
    SubjectCreateRequest,
    SubjectSummary,
)
from .tokens import candidate_token_url, hash_token


def _ensure_role(principal: AdminPrincipal, *allowed: str) -> None:
    if principal.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{principal.role}' is not permitted for this action.",
        )


def _module_summary(row: dict[str, Any]) -> ModuleSummary:
    snapshot_questions = (row.get("module_snapshot") or {}).get("questions", [])
    questions = row.get("questions") or snapshot_questions
    return ModuleSummary(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        description=row.get("description"),
        domain=row["domain"],
        target_duration_minutes=row["target_duration_minutes"],
        difficulty=row["difficulty"],
        status=row["status"],
        version=row["version"],
        question_count=len(questions),
        created_at=row["created_at"],
        published_at=row.get("published_at"),
    )


def list_modules(supabase: Client) -> list[ModuleSummary]:
    res = (
        supabase.table("modules")
        .select(
            "id, slug, title, description, domain, target_duration_minutes, "
            "difficulty, status, version, created_at, published_at, "
            "question_templates(id)"
        )
        .order("created_at", desc=True)
        .execute()
    )
    summaries: list[ModuleSummary] = []
    for row in res.data or []:
        question_count = len(row.get("question_templates") or [])
        summaries.append(
            ModuleSummary(
                id=row["id"],
                slug=row["slug"],
                title=row["title"],
                description=row.get("description"),
                domain=row["domain"],
                target_duration_minutes=row["target_duration_minutes"],
                difficulty=row["difficulty"],
                status=row["status"],
                version=row["version"],
                question_count=question_count,
                created_at=row["created_at"],
                published_at=row.get("published_at"),
            )
        )
    return summaries


def get_module(supabase: Client, module_id: str) -> ModuleDetail:
    res = (
        supabase.table("modules")
        .select(
            "id, slug, title, description, domain, target_duration_minutes, "
            "difficulty, status, version, created_at, published_at, "
            "question_templates(id, position, type, prompt_template, "
            "competency_tags, max_points, time_limit_seconds)"
        )
        .eq("id", module_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Module not found.")
    row = rows[0]
    questions = sorted(
        row.get("question_templates") or [], key=lambda q: q.get("position", 0)
    )
    return ModuleDetail(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        description=row.get("description"),
        domain=row["domain"],
        target_duration_minutes=row["target_duration_minutes"],
        difficulty=row["difficulty"],
        status=row["status"],
        version=row["version"],
        question_count=len(questions),
        created_at=row["created_at"],
        published_at=row.get("published_at"),
        questions=questions,
    )


def create_module(
    supabase: Client,
    principal: AdminPrincipal,
    payload: ModuleCreateRequest,
) -> ModuleSummary:
    _ensure_role(principal, "admin")
    inserted = (
        supabase.table("modules")
        .insert(
            {
                "slug": payload.slug,
                "title": payload.title,
                "description": payload.description,
                "domain": payload.domain,
                "target_duration_minutes": payload.target_duration_minutes,
                "difficulty": payload.difficulty,
                "status": "draft",
                "version": 1,
                "created_by": principal.user_id,
            }
        )
        .execute()
    )
    if not inserted.data:
        raise HTTPException(
            status_code=500, detail="Failed to create module."
        )
    return _module_summary({**inserted.data[0], "question_templates": []})


def patch_module(
    supabase: Client,
    principal: AdminPrincipal,
    module_id: str,
    payload: ModulePatchRequest,
) -> ModuleSummary:
    _ensure_role(principal, "admin")
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update:
        return get_module(supabase, module_id)
    update["updated_at"] = datetime.now(UTC).isoformat()
    res = (
        supabase.table("modules").update(update).eq("id", module_id).execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Module not found.")
    return get_module(supabase, module_id)


def publish_module(
    supabase: Client, principal: AdminPrincipal, module_id: str
) -> ModuleSummary:
    _ensure_role(principal, "admin")
    detail = get_module(supabase, module_id)
    if detail.question_count == 0:
        raise HTTPException(
            status_code=409,
            detail="Cannot publish a module with zero questions.",
        )

    # Spec §8.4 fairness validation: pull every question's full template,
    # sample 50 variable sets per question, run any solver, fail publish
    # on errors. Skips when E2B is offline (so local dev still works).
    question_rows = (
        supabase.table("question_templates")
        .select("id, variable_schema, solver_code")
        .eq("module_id", module_id)
        .execute()
    ).data or []
    from .solver_runner import assert_publishable, fairness_check_module

    fairness = fairness_check_module(
        questions=question_rows, sample_count=50
    )
    assert_publishable(fairness)

    now = datetime.now(UTC).isoformat()
    supabase.table("modules").update(
        {"status": "published", "published_at": now, "updated_at": now}
    ).eq("id", module_id).execute()
    return get_module(supabase, module_id)


def archive_module(
    supabase: Client, principal: AdminPrincipal, module_id: str
) -> ModuleSummary:
    _ensure_role(principal, "admin")
    supabase.table("modules").update(
        {"status": "archived", "updated_at": datetime.now(UTC).isoformat()}
    ).eq("id", module_id).execute()
    return get_module(supabase, module_id)


# Subjects -------------------------------------------------------------------


def list_subjects(supabase: Client) -> list[SubjectSummary]:
    res = (
        supabase.table("subjects")
        .select("id, type, full_name, email, metadata, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return [
        SubjectSummary(
            id=row["id"],
            type=row["type"],
            full_name=row["full_name"],
            email=row["email"],
            metadata=row.get("metadata") or {},
            created_at=row["created_at"],
        )
        for row in res.data or []
    ]


def create_subject(
    supabase: Client,
    principal: AdminPrincipal,
    payload: SubjectCreateRequest,
) -> SubjectSummary:
    _ensure_role(principal, "admin", "reviewer")
    inserted = (
        supabase.table("subjects")
        .insert(
            {
                "type": payload.type,
                "full_name": payload.full_name,
                "email": payload.email,
                "metadata": payload.metadata or {},
            }
        )
        .execute()
    )
    if not inserted.data:
        raise HTTPException(
            status_code=500, detail="Failed to create subject."
        )
    row = inserted.data[0]
    return SubjectSummary(
        id=row["id"],
        type=row["type"],
        full_name=row["full_name"],
        email=row["email"],
        metadata=row.get("metadata") or {},
        created_at=row["created_at"],
    )


# Assignments ----------------------------------------------------------------


def _module_snapshot(supabase: Client, module_id: str) -> dict[str, Any]:
    """Build the frozen module+questions snapshot for an assignment."""

    module_q = (
        supabase.table("modules")
        .select(
            "id, slug, title, description, domain, target_duration_minutes, "
            "difficulty, status"
        )
        .eq("id", module_id)
        .limit(1)
        .execute()
    )
    module_rows = module_q.data or []
    if not module_rows:
        raise HTTPException(status_code=404, detail="Module not found.")
    module = module_rows[0]
    if module["status"] != "published":
        raise HTTPException(
            status_code=409,
            detail="Cannot assign a module that is not published.",
        )

    qres = (
        supabase.table("question_templates")
        .select(
            "id, position, type, prompt_template, variable_schema, "
            "solver_code, solver_language, interactive_config, rubric, "
            "competency_tags, time_limit_seconds, max_points, metadata"
        )
        .eq("module_id", module_id)
        .order("position")
        .execute()
    )
    questions = qres.data or []
    if not questions:
        raise HTTPException(
            status_code=409,
            detail="Cannot assign a module with no questions.",
        )

    return {
        "slug": module["slug"],
        "title": module["title"],
        "description": module.get("description") or "",
        "domain": module["domain"],
        "target_duration_minutes": module["target_duration_minutes"],
        "difficulty": module["difficulty"],
        "questions": questions,
    }


def list_assignments(supabase: Client) -> list[AssignmentSummary]:
    res = (
        supabase.table("assignments")
        .select(
            "id, subject_id, module_id, status, expires_at, started_at, "
            "completed_at, integrity_score, final_score, max_possible_score, "
            "created_at, subjects(full_name, email), modules(title)"
        )
        .order("created_at", desc=True)
        .limit(200)
        .execute()
    )
    out: list[AssignmentSummary] = []
    for row in res.data or []:
        subject = row.get("subjects") or {}
        module = row.get("modules") or {}
        out.append(
            AssignmentSummary(
                id=row["id"],
                subject_id=row["subject_id"],
                subject_full_name=subject.get("full_name"),
                subject_email=subject.get("email"),
                module_id=row.get("module_id"),
                module_title=module.get("title"),
                status=row["status"],
                expires_at=row["expires_at"],
                started_at=row.get("started_at"),
                completed_at=row.get("completed_at"),
                integrity_score=row.get("integrity_score"),
                final_score=row.get("final_score"),
                max_possible_score=row.get("max_possible_score"),
                created_at=row["created_at"],
            )
        )
    return out


def get_assignment_detail(
    supabase: Client, assignment_id: str
) -> AssignmentDetail:
    res = (
        supabase.table("assignments")
        .select(
            "id, subject_id, module_id, status, expires_at, started_at, "
            "completed_at, consent_at, total_time_seconds, integrity_score, "
            "final_score, max_possible_score, created_at, "
            "subjects(full_name, email), modules(title), "
            "attempts(id, question_template_id, rendered_prompt, raw_answer, "
            "submitted_at, score, max_score, score_rationale, scorer_model, "
            "scorer_confidence, needs_review, active_time_seconds)"
        )
        .eq("id", assignment_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    row = rows[0]
    subject = row.get("subjects") or {}
    module = row.get("modules") or {}
    attempts_raw = row.get("attempts") or []
    attempts = [
        AttemptSummary(
            id=a["id"],
            question_template_id=a["question_template_id"],
            rendered_prompt=a["rendered_prompt"],
            raw_answer=a.get("raw_answer"),
            submitted_at=a.get("submitted_at"),
            score=a.get("score"),
            max_score=a["max_score"],
            score_rationale=a.get("score_rationale"),
            scorer_model=a.get("scorer_model"),
            scorer_confidence=a.get("scorer_confidence"),
            needs_review=bool(a.get("needs_review")),
            active_time_seconds=a.get("active_time_seconds"),
        )
        for a in attempts_raw
    ]
    return AssignmentDetail(
        id=row["id"],
        subject_id=row["subject_id"],
        subject_full_name=subject.get("full_name"),
        subject_email=subject.get("email"),
        module_id=row.get("module_id"),
        module_title=module.get("title"),
        status=row["status"],
        expires_at=row["expires_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        consent_at=row.get("consent_at"),
        total_time_seconds=row.get("total_time_seconds"),
        integrity_score=row.get("integrity_score"),
        final_score=row.get("final_score"),
        max_possible_score=row.get("max_possible_score"),
        created_at=row["created_at"],
        attempts=attempts,
    )


def create_assignment(
    supabase: Client,
    principal: AdminPrincipal,
    payload: AssignmentCreateRequest,
    *,
    send_email: bool = True,
) -> AssignmentMagicLink:
    _ensure_role(principal, "admin", "reviewer")
    settings = get_settings()
    snapshot = _module_snapshot(supabase, payload.module_id)

    subject_q = (
        supabase.table("subjects")
        .select("id, full_name, email")
        .eq("id", payload.subject_id)
        .limit(1)
        .execute()
    )
    if not subject_q.data:
        raise HTTPException(status_code=404, detail="Subject not found.")
    subject_row = subject_q.data[0]

    expires_at = datetime.now(UTC) + timedelta(days=payload.expires_in_days)
    assignment_id = str(uuid.uuid4())
    token = issue_candidate_token(
        assignment_id=assignment_id,
        subject_id=payload.subject_id,
        expires_at=expires_at,
    )
    token_hash = hash_token(token)

    supabase.table("assignments").insert(
        {
            "id": assignment_id,
            "subject_id": payload.subject_id,
            "module_id": payload.module_id,
            "module_snapshot": snapshot,
            "created_by": principal.user_id,
            "token_hash": token_hash,
            "expires_at": expires_at.isoformat(),
            "status": "pending",
            "random_seed": secrets.randbits(63),
        }
    ).execute()

    magic_link_url = candidate_token_url(
        settings.next_public_candidate_url, token
    )

    if send_email and subject_row.get("email"):
        # Best-effort. Failures are logged inside the email service; we don't
        # block the API response since the admin can always copy the URL.
        from .email import send_magic_link

        send_magic_link(
            to_email=subject_row["email"],
            subject_full_name=subject_row.get("full_name") or "there",
            module_title=snapshot.get("title", "Assessment"),
            magic_link_url=magic_link_url,
            expires_at=expires_at,
        )

    return AssignmentMagicLink(
        assignment_id=assignment_id,
        subject_id=payload.subject_id,
        module_id=payload.module_id,
        expires_at=expires_at,
        token=token,
        magic_link_url=magic_link_url,
    )


def bulk_create_assignments(
    supabase: Client,
    principal: AdminPrincipal,
    *,
    module_id: str,
    subject_ids: list[str],
    expires_in_days: int,
    send_email: bool,
) -> dict[str, Any]:
    """Issue one magic link per subject. Failures on individual subjects do
    not abort the batch — admin sees the per-subject outcome list."""

    _ensure_role(principal, "admin", "reviewer")
    created: list[AssignmentMagicLink] = []
    failed: list[dict[str, str]] = []
    for subject_id in subject_ids:
        try:
            link = create_assignment(
                supabase,
                principal,
                AssignmentCreateRequest(
                    module_id=module_id,
                    subject_id=subject_id,
                    expires_in_days=expires_in_days,
                    send_email=send_email,
                ),
                send_email=send_email,
            )
            created.append(link)
        except HTTPException as exc:
            failed.append({"subject_id": subject_id, "detail": str(exc.detail)})
        except Exception as exc:
            failed.append({"subject_id": subject_id, "detail": str(exc)})
    return {"created": created, "failed": failed}


def cancel_assignment(
    supabase: Client, principal: AdminPrincipal, assignment_id: str
) -> AssignmentDetail:
    _ensure_role(principal, "admin")
    supabase.table("assignments").update({"status": "cancelled"}).eq(
        "id", assignment_id
    ).execute()
    return get_assignment_detail(supabase, assignment_id)
