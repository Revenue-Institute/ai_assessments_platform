"""Admin endpoints (spec §14.1). All routes require a valid Supabase JWT
linked to a public.users row."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from supabase import Client

from ..auth import AdminPrincipal, require_admin_jwt
from ..db import get_supabase
from ..models.admin import (
    AssignmentBulkCreateRequest,
    AssignmentBulkCreateResult,
    AssignmentCreateRequest,
    AssignmentDetail,
    AssignmentMagicLink,
    AssignmentSummary,
    ModuleCreateRequest,
    ModuleDetail,
    ModulePatchRequest,
    ModuleSummary,
    SubjectCreateRequest,
    SubjectSummary,
)
from ..services import admin as admin_service

router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin_jwt)])


@router.get("/me")
def me(
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
) -> dict[str, str | None]:
    return {
        "user_id": principal.user_id,
        "email": principal.email,
        "full_name": principal.full_name,
        "role": principal.role,
    }


# Modules --------------------------------------------------------------------


@router.get("/modules", response_model=list[ModuleSummary])
def list_modules(
    supabase: Annotated[Client, Depends(get_supabase)],
) -> list[ModuleSummary]:
    return admin_service.list_modules(supabase)


@router.post("/modules", response_model=ModuleSummary, status_code=201)
def create_module(
    payload: ModuleCreateRequest,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ModuleSummary:
    return admin_service.create_module(supabase, principal, payload)


@router.get("/modules/{module_id}", response_model=ModuleDetail)
def get_module(
    module_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ModuleDetail:
    return admin_service.get_module(supabase, module_id)


@router.patch("/modules/{module_id}", response_model=ModuleSummary)
def patch_module(
    module_id: str,
    payload: ModulePatchRequest,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ModuleSummary:
    return admin_service.patch_module(supabase, principal, module_id, payload)


@router.post("/modules/{module_id}/questions", status_code=201)
def create_question(
    module_id: str,
    payload: dict,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> dict:
    return admin_service.create_question(
        supabase, principal, module_id=module_id, payload=payload
    )


@router.patch("/modules/{module_id}/questions/{question_id}")
def patch_question(
    module_id: str,
    question_id: str,
    payload: dict,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> dict:
    return admin_service.patch_question(
        supabase,
        principal,
        module_id=module_id,
        question_id=question_id,
        payload=payload,
    )


@router.delete(
    "/modules/{module_id}/questions/{question_id}", status_code=204
)
def delete_question(
    module_id: str,
    question_id: str,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> None:
    admin_service.delete_question(
        supabase, principal, module_id=module_id, question_id=question_id
    )


@router.post("/modules/{module_id}/publish", response_model=ModuleSummary)
def publish_module(
    module_id: str,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ModuleSummary:
    return admin_service.publish_module(supabase, principal, module_id)


@router.get("/modules/{module_id}/preview")
def preview_module(
    module_id: str,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> dict:
    return admin_service.preview_module(supabase, principal, module_id)


@router.post("/modules/{module_id}/archive", response_model=ModuleSummary)
def archive_module(
    module_id: str,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ModuleSummary:
    return admin_service.archive_module(supabase, principal, module_id)


# Subjects -------------------------------------------------------------------


@router.get("/subjects", response_model=list[SubjectSummary])
def list_subjects(
    supabase: Annotated[Client, Depends(get_supabase)],
) -> list[SubjectSummary]:
    return admin_service.list_subjects(supabase)


@router.post("/subjects", response_model=SubjectSummary, status_code=201)
def create_subject(
    payload: SubjectCreateRequest,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> SubjectSummary:
    return admin_service.create_subject(supabase, principal, payload)


# Assignments ----------------------------------------------------------------


@router.get("/assignments", response_model=list[AssignmentSummary])
def list_assignments(
    supabase: Annotated[Client, Depends(get_supabase)],
) -> list[AssignmentSummary]:
    return admin_service.list_assignments(supabase)


@router.post(
    "/assignments",
    response_model=AssignmentMagicLink,
    status_code=201,
)
def create_assignment(
    payload: AssignmentCreateRequest,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> AssignmentMagicLink:
    return admin_service.create_assignment(
        supabase, principal, payload, send_email=payload.send_email
    )


@router.post(
    "/assignments/bulk",
    response_model=AssignmentBulkCreateResult,
    status_code=201,
)
def bulk_create_assignments(
    payload: AssignmentBulkCreateRequest,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> AssignmentBulkCreateResult:
    result = admin_service.bulk_create_assignments(
        supabase,
        principal,
        module_id=payload.module_id,
        subject_ids=payload.subject_ids,
        expires_in_days=payload.expires_in_days,
        send_email=payload.send_email,
    )
    return AssignmentBulkCreateResult(**result)


@router.get(
    "/assignments/{assignment_id}", response_model=AssignmentDetail
)
def get_assignment(
    assignment_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> AssignmentDetail:
    return admin_service.get_assignment_detail(supabase, assignment_id)


@router.get("/assignments/{assignment_id}/events")
def get_assignment_events(
    assignment_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
    limit: int = 1000,
) -> list[dict]:
    return admin_service.list_attempt_events(
        supabase, assignment_id, limit=limit
    )


@router.post(
    "/assignments/{assignment_id}/cancel", response_model=AssignmentDetail
)
def cancel_assignment(
    assignment_id: str,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> AssignmentDetail:
    return admin_service.cancel_assignment(supabase, principal, assignment_id)


@router.post(
    "/assignments/{assignment_id}/rescore", response_model=AssignmentDetail
)
def rescore_assignment(
    assignment_id: str,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> AssignmentDetail:
    """Re-runs scoring across every attempt on the assignment. Each attempt's
    current score is snapshotted to attempt_scores_history first."""

    from ..services import scoring as scoring_service

    current = (
        supabase.table("attempts")
        .select(
            "id, score, max_score, score_rationale, scorer_model, "
            "scorer_version, rubric_version, scorer_confidence"
        )
        .eq("assignment_id", assignment_id)
        .execute()
    ).data or []
    history_rows = [
        {
            "attempt_id": row["id"],
            "score": row.get("score"),
            "max_score": row.get("max_score"),
            "score_rationale": row.get("score_rationale"),
            "scorer_model": row.get("scorer_model"),
            "scorer_version": row.get("scorer_version"),
            "rubric_version": row.get("rubric_version"),
            "scorer_confidence": row.get("scorer_confidence"),
            "recorded_by": principal.user_id,
        }
        for row in current
        if row.get("score") is not None
    ]
    if history_rows:
        supabase.table("attempt_scores_history").insert(history_rows).execute()

    scoring_service.score_assignment(supabase, assignment_id)
    return admin_service.get_assignment_detail(supabase, assignment_id)


@router.post("/attempts/{attempt_id}/rescore", response_model=AssignmentDetail)
def rescore_attempt(
    attempt_id: str,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> AssignmentDetail:
    """Rescore a single attempt and re-derive assignment-level rollups."""

    from ..services import scoring as scoring_service

    aggregate = scoring_service.rescore_attempt(
        supabase, attempt_id=attempt_id, recorded_by=principal.user_id
    )
    return admin_service.get_assignment_detail(supabase, aggregate["assignment_id"])
