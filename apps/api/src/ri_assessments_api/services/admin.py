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
    AssessmentCreateRequest,
    AssessmentDetail,
    AssessmentModuleAddRequest,
    AssessmentModuleEntry,
    AssessmentPatchRequest,
    AssessmentReorderRequest,
    AssessmentSummary,
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


def create_question(
    supabase: Client,
    principal: AdminPrincipal,
    *,
    module_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Append a question to a module. Position defaults to the next free
    slot. Caller supplies the full QuestionTemplate shape (typically
    JSON-edited in the admin UI)."""

    _ensure_role(principal, "admin")
    # Confirm the module exists and grab the next position.
    existing = (
        supabase.table("question_templates")
        .select("position")
        .eq("module_id", module_id)
        .execute()
    ).data or []
    next_position = (
        max((int(r.get("position") or 0) for r in existing), default=-1) + 1
    )

    row = {
        "id": payload.get("id") or str(uuid.uuid4()),
        "module_id": module_id,
        "position": int(payload.get("position") or next_position),
        "type": payload["type"],
        "prompt_template": payload["prompt_template"],
        "variable_schema": payload.get("variable_schema") or {},
        "solver_code": payload.get("solver_code"),
        "solver_language": payload.get("solver_language") or "python",
        "interactive_config": payload.get("interactive_config"),
        "rubric": payload["rubric"],
        "competency_tags": payload.get("competency_tags") or [],
        "time_limit_seconds": payload.get("time_limit_seconds"),
        "max_points": float(payload.get("max_points") or 10),
        "metadata": payload.get("metadata") or {},
    }
    inserted = supabase.table("question_templates").insert(row).execute()
    if not inserted.data:
        raise HTTPException(status_code=500, detail="Failed to create question.")
    return inserted.data[0]


def patch_question(
    supabase: Client,
    principal: AdminPrincipal,
    *,
    module_id: str,
    question_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    _ensure_role(principal, "admin")

    allowed_keys = {
        "position",
        "type",
        "prompt_template",
        "variable_schema",
        "solver_code",
        "solver_language",
        "interactive_config",
        "rubric",
        "competency_tags",
        "time_limit_seconds",
        "max_points",
        "metadata",
    }
    update = {k: v for k, v in payload.items() if k in allowed_keys}
    if not update:
        raise HTTPException(
            status_code=400, detail="No editable fields supplied."
        )
    update["updated_at"] = datetime.now(UTC).isoformat()

    res = (
        supabase.table("question_templates")
        .update(update)
        .eq("id", question_id)
        .eq("module_id", module_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Question not found.")
    return res.data[0]


def delete_question(
    supabase: Client,
    principal: AdminPrincipal,
    *,
    module_id: str,
    question_id: str,
) -> None:
    _ensure_role(principal, "admin")
    supabase.table("question_templates").delete().eq("id", question_id).eq(
        "module_id", module_id
    ).execute()


def preview_module(
    supabase: Client,
    principal: AdminPrincipal,
    module_id: str,
) -> dict[str, Any]:
    """Render every question in `module_id` with sampled variables and
    return a candidate-shaped view. Used by the admin /preview page so
    reviewers can walk the assessment exactly as a candidate would, with
    answer-revealing fields stripped (spec §13.2)."""

    _ensure_role(principal, "admin")

    from .attempts import _sanitize_interactive_config
    from .randomizer import question_seed, render_prompt, sample_variables

    res = (
        supabase.table("question_templates")
        .select(
            "id, position, type, prompt_template, variable_schema, "
            "interactive_config, competency_tags, max_points, "
            "time_limit_seconds, rubric"
        )
        .eq("module_id", module_id)
        .order("position")
        .execute()
    )
    rows = list(res.data or [])
    seed = 1
    questions = []
    for q in rows:
        variables = sample_variables(
            q.get("variable_schema") or {},
            question_seed(seed, q["id"]),
        )
        questions.append(
            {
                "question_template_id": q["id"],
                "position": q["position"],
                "type": q["type"],
                "rendered_prompt": render_prompt(
                    q["prompt_template"], variables
                ),
                "max_points": float(q.get("max_points") or 10),
                "time_limit_seconds": q.get("time_limit_seconds"),
                "competency_tags": q.get("competency_tags") or [],
                "interactive_config": _sanitize_interactive_config(
                    q["type"], q.get("interactive_config")
                ),
            }
        )
    return {"module_id": module_id, "questions": questions}


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


def get_subject(supabase: Client, subject_id: str) -> SubjectSummary:
    res = (
        supabase.table("subjects")
        .select("id, type, full_name, email, metadata, created_at")
        .eq("id", subject_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Subject not found.")
    row = rows[0]
    return SubjectSummary(
        id=row["id"],
        type=row["type"],
        full_name=row["full_name"],
        email=row["email"],
        metadata=row.get("metadata") or {},
        created_at=row["created_at"],
    )


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


# Assessments ----------------------------------------------------------------


def _assessment_module_rows(
    supabase: Client, assessment_id: str
) -> list[dict[str, Any]]:
    """Inner-join assessment_modules with modules + question counts. Sorted
    by position so the candidate sees questions in the curated order."""

    res = (
        supabase.table("assessment_modules")
        .select(
            "position, module_id, "
            "modules(id, slug, title, description, domain, "
            "target_duration_minutes, difficulty, status, "
            "question_templates(id))"
        )
        .eq("assessment_id", assessment_id)
        .order("position")
        .execute()
    )
    out: list[dict[str, Any]] = []
    for row in res.data or []:
        module = row.get("modules") or {}
        question_count = len(module.get("question_templates") or [])
        out.append(
            {
                "position": row["position"],
                "module_id": row["module_id"],
                "title": module.get("title", ""),
                "slug": module.get("slug"),
                "description": module.get("description"),
                "domain": module.get("domain", "ops"),
                "difficulty": module.get("difficulty", "junior"),
                "target_duration_minutes": module.get(
                    "target_duration_minutes", 0
                ),
                "status": module.get("status"),
                "question_count": question_count,
            }
        )
    return out


def _assessment_summary(
    row: dict[str, Any], modules: list[dict[str, Any]]
) -> AssessmentSummary:
    return AssessmentSummary(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        description=row.get("description"),
        status=row["status"],
        version=row["version"],
        module_count=len(modules),
        question_count=sum(m["question_count"] for m in modules),
        total_duration_minutes=sum(
            m["target_duration_minutes"] for m in modules
        ),
        created_at=row["created_at"],
        published_at=row.get("published_at"),
    )


def list_assessments(supabase: Client) -> list[AssessmentSummary]:
    res = (
        supabase.table("assessments")
        .select(
            "id, slug, title, description, status, version, "
            "created_at, published_at"
        )
        .order("created_at", desc=True)
        .execute()
    )
    out: list[AssessmentSummary] = []
    for row in res.data or []:
        modules = _assessment_module_rows(supabase, row["id"])
        out.append(_assessment_summary(row, modules))
    return out


def get_assessment_detail(
    supabase: Client, assessment_id: str
) -> AssessmentDetail:
    res = (
        supabase.table("assessments")
        .select(
            "id, slug, title, description, status, version, "
            "created_at, published_at"
        )
        .eq("id", assessment_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    row = rows[0]
    modules = _assessment_module_rows(supabase, assessment_id)
    summary = _assessment_summary(row, modules)
    return AssessmentDetail(
        **summary.model_dump(),
        modules=[
            AssessmentModuleEntry(
                module_id=m["module_id"],
                position=m["position"],
                title=m["title"],
                domain=m["domain"],
                difficulty=m["difficulty"],
                target_duration_minutes=m["target_duration_minutes"],
                question_count=m["question_count"],
            )
            for m in modules
        ],
    )


def create_assessment(
    supabase: Client,
    principal: AdminPrincipal,
    payload: AssessmentCreateRequest,
) -> AssessmentSummary:
    _ensure_role(principal, "admin")

    # slug uniqueness across published versions; for v1 we simply require
    # the slug to be unused. Versioning lands when we publish updated copies.
    existing = (
        supabase.table("assessments")
        .select("id")
        .eq("slug", payload.slug)
        .limit(1)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail=f"Assessment slug '{payload.slug}' is already in use.",
        )

    inserted = (
        supabase.table("assessments")
        .insert(
            {
                "slug": payload.slug,
                "title": payload.title,
                "description": payload.description,
                "status": "draft",
                "version": 1,
                "created_by": principal.user_id,
            }
        )
        .execute()
    )
    if not inserted.data:
        raise HTTPException(status_code=500, detail="Failed to create assessment.")
    assessment_id = inserted.data[0]["id"]

    if payload.module_ids:
        rows = [
            {
                "assessment_id": assessment_id,
                "module_id": module_id,
                "position": position,
            }
            for position, module_id in enumerate(payload.module_ids)
        ]
        supabase.table("assessment_modules").insert(rows).execute()

    detail = get_assessment_detail(supabase, assessment_id)
    return AssessmentSummary(**detail.model_dump(exclude={"modules"}))


def patch_assessment(
    supabase: Client,
    principal: AdminPrincipal,
    assessment_id: str,
    payload: AssessmentPatchRequest,
) -> AssessmentSummary:
    _ensure_role(principal, "admin")
    update: dict[str, Any] = {}
    if payload.title is not None:
        update["title"] = payload.title
    if payload.description is not None:
        update["description"] = payload.description
    if update:
        update["updated_at"] = datetime.now(UTC).isoformat()
        supabase.table("assessments").update(update).eq(
            "id", assessment_id
        ).execute()
    return AssessmentSummary(
        **get_assessment_detail(supabase, assessment_id).model_dump(
            exclude={"modules"}
        )
    )


def add_assessment_module(
    supabase: Client,
    principal: AdminPrincipal,
    assessment_id: str,
    payload: AssessmentModuleAddRequest,
) -> AssessmentDetail:
    _ensure_role(principal, "admin")

    # Confirm both rows exist.
    a_check = (
        supabase.table("assessments")
        .select("id, status")
        .eq("id", assessment_id)
        .limit(1)
        .execute()
    )
    if not a_check.data:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    if a_check.data[0]["status"] == "archived":
        raise HTTPException(
            status_code=409,
            detail="Cannot edit an archived assessment.",
        )

    m_check = (
        supabase.table("modules")
        .select("id, status")
        .eq("id", payload.module_id)
        .limit(1)
        .execute()
    )
    if not m_check.data:
        raise HTTPException(status_code=404, detail="Module not found.")

    existing = _assessment_module_rows(supabase, assessment_id)
    if any(m["module_id"] == payload.module_id for m in existing):
        raise HTTPException(
            status_code=409,
            detail="Module is already in this assessment.",
        )

    position = (
        payload.position
        if payload.position is not None
        else len(existing)
    )

    # Shift later positions if inserting in the middle.
    for m in existing:
        if m["position"] >= position:
            supabase.table("assessment_modules").update(
                {"position": m["position"] + 1}
            ).eq("assessment_id", assessment_id).eq(
                "module_id", m["module_id"]
            ).execute()

    supabase.table("assessment_modules").insert(
        {
            "assessment_id": assessment_id,
            "module_id": payload.module_id,
            "position": position,
        }
    ).execute()

    return get_assessment_detail(supabase, assessment_id)


def remove_assessment_module(
    supabase: Client,
    principal: AdminPrincipal,
    assessment_id: str,
    module_id: str,
) -> AssessmentDetail:
    _ensure_role(principal, "admin")

    a_check = (
        supabase.table("assessments")
        .select("id, status")
        .eq("id", assessment_id)
        .limit(1)
        .execute()
    )
    if not a_check.data:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    if a_check.data[0]["status"] == "archived":
        raise HTTPException(
            status_code=409,
            detail="Cannot edit an archived assessment.",
        )

    supabase.table("assessment_modules").delete().eq(
        "assessment_id", assessment_id
    ).eq("module_id", module_id).execute()

    # Compact positions (0..N-1) after removal.
    remaining = _assessment_module_rows(supabase, assessment_id)
    for new_pos, m in enumerate(remaining):
        if m["position"] != new_pos:
            supabase.table("assessment_modules").update(
                {"position": new_pos}
            ).eq("assessment_id", assessment_id).eq(
                "module_id", m["module_id"]
            ).execute()

    return get_assessment_detail(supabase, assessment_id)


def reorder_assessment_modules(
    supabase: Client,
    principal: AdminPrincipal,
    assessment_id: str,
    payload: AssessmentReorderRequest,
) -> AssessmentDetail:
    _ensure_role(principal, "admin")

    existing = _assessment_module_rows(supabase, assessment_id)
    existing_ids = {m["module_id"] for m in existing}
    if set(payload.module_ids) != existing_ids:
        raise HTTPException(
            status_code=400,
            detail="Reorder must include exactly the existing modules.",
        )

    # Two-phase reorder so we don't trip the unique (assessment_id, position)
    # constraint mid-update: bump every position by 1000 first, then assign
    # the final positions.
    for m in existing:
        supabase.table("assessment_modules").update(
            {"position": m["position"] + 1000}
        ).eq("assessment_id", assessment_id).eq(
            "module_id", m["module_id"]
        ).execute()
    for new_pos, module_id in enumerate(payload.module_ids):
        supabase.table("assessment_modules").update(
            {"position": new_pos}
        ).eq("assessment_id", assessment_id).eq(
            "module_id", module_id
        ).execute()

    return get_assessment_detail(supabase, assessment_id)


def publish_assessment(
    supabase: Client, principal: AdminPrincipal, assessment_id: str
) -> AssessmentSummary:
    _ensure_role(principal, "admin")

    modules = _assessment_module_rows(supabase, assessment_id)
    if not modules:
        raise HTTPException(
            status_code=409,
            detail="Cannot publish an assessment with no modules.",
        )
    for m in modules:
        if m["status"] != "published":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Module '{m['title']}' must be published before the "
                    "assessment can be published."
                ),
            )
        if m["question_count"] == 0:
            raise HTTPException(
                status_code=409,
                detail=f"Module '{m['title']}' has no questions.",
            )

    supabase.table("assessments").update(
        {
            "status": "published",
            "published_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    ).eq("id", assessment_id).execute()
    return AssessmentSummary(
        **get_assessment_detail(supabase, assessment_id).model_dump(
            exclude={"modules"}
        )
    )


def archive_assessment(
    supabase: Client, principal: AdminPrincipal, assessment_id: str
) -> AssessmentSummary:
    _ensure_role(principal, "admin")
    supabase.table("assessments").update(
        {
            "status": "archived",
            "updated_at": datetime.now(UTC).isoformat(),
        }
    ).eq("id", assessment_id).execute()
    return AssessmentSummary(
        **get_assessment_detail(supabase, assessment_id).model_dump(
            exclude={"modules"}
        )
    )


# Assignments ----------------------------------------------------------------


def _assessment_snapshot(
    supabase: Client, assessment_id: str
) -> dict[str, Any]:
    """Build the frozen assessment + modules + questions snapshot."""

    a_q = (
        supabase.table("assessments")
        .select("id, slug, title, description, status")
        .eq("id", assessment_id)
        .limit(1)
        .execute()
    )
    a_rows = a_q.data or []
    if not a_rows:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    assessment = a_rows[0]
    if assessment["status"] != "published":
        raise HTTPException(
            status_code=409,
            detail="Cannot assign an assessment that is not published.",
        )

    am_q = (
        supabase.table("assessment_modules")
        .select("position, module_id")
        .eq("assessment_id", assessment_id)
        .order("position")
        .execute()
    )
    am_rows = am_q.data or []
    if not am_rows:
        raise HTTPException(
            status_code=409,
            detail="Cannot assign an assessment with no modules.",
        )

    modules: list[dict[str, Any]] = []
    flat_questions: list[dict[str, Any]] = []
    total_duration = 0
    for am in am_rows:
        module_id = am["module_id"]
        m_q = (
            supabase.table("modules")
            .select(
                "id, slug, title, description, domain, "
                "target_duration_minutes, difficulty, status"
            )
            .eq("id", module_id)
            .limit(1)
            .execute()
        )
        if not m_q.data:
            continue
        module = m_q.data[0]
        if module["status"] != "published":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Module '{module['title']}' must be published before the "
                    "assessment can be assigned."
                ),
            )
        total_duration += int(module.get("target_duration_minutes") or 0)

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
                detail=f"Module '{module['title']}' has no questions.",
            )
        modules.append(
            {
                "module_id": module_id,
                "slug": module["slug"],
                "title": module["title"],
                "description": module.get("description") or "",
                "domain": module["domain"],
                "difficulty": module["difficulty"],
                "target_duration_minutes": module["target_duration_minutes"],
                "position": am["position"],
            }
        )
        # Tag each question with its source module so admin/UI can rollup
        # scores per-module without re-joining.
        for q in questions:
            q_with_module = {**q, "module_id": module_id}
            flat_questions.append(q_with_module)

    return {
        "slug": assessment["slug"],
        "title": assessment["title"],
        "description": assessment.get("description") or "",
        "target_duration_minutes": total_duration,
        "modules": modules,
        "questions": flat_questions,
    }


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


def list_assignments(
    supabase: Client, *, needs_review: bool | None = None
) -> list[AssignmentSummary]:
    res = (
        supabase.table("assignments")
        .select(
            "id, subject_id, module_id, assessment_id, status, expires_at, "
            "started_at, completed_at, integrity_score, final_score, "
            "max_possible_score, created_at, "
            "subjects(full_name, email), modules(title), assessments(title), "
            "attempts(needs_review)"
        )
        .order("created_at", desc=True)
        .limit(200)
        .execute()
    )
    out: list[AssignmentSummary] = []
    for row in res.data or []:
        subject = row.get("subjects") or {}
        module = row.get("modules") or {}
        assessment = row.get("assessments") or {}
        attempts = row.get("attempts") or []
        has_review_flag = any(
            bool(a.get("needs_review")) for a in attempts
        )
        if needs_review is True and not has_review_flag:
            continue
        if needs_review is False and has_review_flag:
            continue
        out.append(
            AssignmentSummary(
                id=row["id"],
                subject_id=row["subject_id"],
                subject_full_name=subject.get("full_name"),
                subject_email=subject.get("email"),
                assessment_id=row.get("assessment_id"),
                assessment_title=assessment.get("title"),
                module_id=row.get("module_id"),
                module_title=module.get("title"),
                status=row["status"],
                expires_at=row["expires_at"],
                started_at=row.get("started_at"),
                completed_at=row.get("completed_at"),
                integrity_score=row.get("integrity_score"),
                final_score=row.get("final_score"),
                max_possible_score=row.get("max_possible_score"),
                needs_review=has_review_flag,
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
            "id, subject_id, module_id, assessment_id, status, expires_at, "
            "started_at, completed_at, consent_at, total_time_seconds, "
            "integrity_score, final_score, max_possible_score, created_at, "
            "subjects(full_name, email), modules(title), assessments(title), "
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
    assessment = row.get("assessments") or {}
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
        assessment_id=row.get("assessment_id"),
        assessment_title=assessment.get("title"),
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

    if not payload.assessment_id and not payload.module_id:
        raise HTTPException(
            status_code=400,
            detail="Either assessment_id or module_id is required.",
        )

    assessment_id: str | None = None
    module_id: str | None = None
    snapshot: dict[str, Any]
    if payload.assessment_id:
        assessment_id = payload.assessment_id
        snapshot = _assessment_snapshot(supabase, assessment_id)
    else:
        module_id = payload.module_id
        snapshot = _module_snapshot(supabase, module_id)

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
    assignment_id_new = str(uuid.uuid4())
    token = issue_candidate_token(
        assignment_id=assignment_id_new,
        subject_id=payload.subject_id,
        expires_at=expires_at,
    )
    token_hash = hash_token(token)

    insert_row: dict[str, Any] = {
        "id": assignment_id_new,
        "subject_id": payload.subject_id,
        "created_by": principal.user_id,
        "token_hash": token_hash,
        "expires_at": expires_at.isoformat(),
        "status": "pending",
        "random_seed": secrets.randbits(63),
    }
    if assessment_id:
        insert_row["assessment_id"] = assessment_id
        insert_row["assessment_snapshot"] = snapshot
        # Keep module_snapshot populated for legacy code paths that read
        # questions from there. The snapshot's questions list is the same
        # flat array either way.
        insert_row["module_snapshot"] = snapshot
    else:
        insert_row["module_id"] = module_id
        insert_row["module_snapshot"] = snapshot

    supabase.table("assignments").insert(insert_row).execute()

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
        assignment_id=assignment_id_new,
        subject_id=payload.subject_id,
        assessment_id=assessment_id,
        module_id=module_id,
        expires_at=expires_at,
        token=token,
        magic_link_url=magic_link_url,
    )


def bulk_create_assignments(
    supabase: Client,
    principal: AdminPrincipal,
    *,
    assessment_id: str | None = None,
    module_id: str | None = None,
    subject_ids: list[str],
    expires_in_days: int,
    send_email: bool,
) -> dict[str, Any]:
    """Issue one magic link per subject. Failures on individual subjects do
    not abort the batch; admin sees the per-subject outcome list."""

    _ensure_role(principal, "admin", "reviewer")
    if not assessment_id and not module_id:
        raise HTTPException(
            status_code=400,
            detail="Either assessment_id or module_id is required.",
        )
    created: list[AssignmentMagicLink] = []
    failed: list[dict[str, str]] = []
    for subject_id in subject_ids:
        try:
            link = create_assignment(
                supabase,
                principal,
                AssignmentCreateRequest(
                    assessment_id=assessment_id,
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


def resend_assignment_email(
    supabase: Client,
    principal: AdminPrincipal,
    assignment_id: str,
    *,
    expires_in_days: int | None = None,
) -> AssignmentMagicLink:
    """Issue a fresh magic link for an existing assignment and email it
    again. The previous token's hash is replaced, invalidating any stale
    link the candidate may have. Refuses to resend on completed or
    cancelled assignments."""

    _ensure_role(principal, "admin", "reviewer")
    settings = get_settings()
    res = (
        supabase.table("assignments")
        .select(
            "id, subject_id, module_id, assessment_id, module_snapshot, "
            "assessment_snapshot, status, expires_at"
        )
        .eq("id", assignment_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    row = rows[0]
    if row["status"] in ("completed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot resend a {row['status']} assignment.",
        )

    if expires_in_days is not None:
        new_expiry = datetime.now(UTC) + timedelta(days=expires_in_days)
    else:
        new_expiry = datetime.fromisoformat(
            row["expires_at"].replace("Z", "+00:00")
        )
        if new_expiry <= datetime.now(UTC):
            new_expiry = datetime.now(UTC) + timedelta(days=7)

    token = issue_candidate_token(
        assignment_id=assignment_id,
        subject_id=row["subject_id"],
        expires_at=new_expiry,
    )
    supabase.table("assignments").update(
        {
            "token_hash": hash_token(token),
            "expires_at": new_expiry.isoformat(),
        }
    ).eq("id", assignment_id).execute()

    magic_link_url = candidate_token_url(
        settings.next_public_candidate_url, token
    )

    subj = (
        supabase.table("subjects")
        .select("full_name, email")
        .eq("id", row["subject_id"])
        .limit(1)
        .execute()
    )
    subject_row = (subj.data or [{}])[0]
    if subject_row.get("email"):
        from .email import send_magic_link

        snapshot = row.get("assessment_snapshot") or row.get("module_snapshot") or {}
        send_magic_link(
            to_email=subject_row["email"],
            subject_full_name=subject_row.get("full_name") or "there",
            module_title=snapshot.get("title", "Assessment"),
            magic_link_url=magic_link_url,
            expires_at=new_expiry,
        )

    return AssignmentMagicLink(
        assignment_id=assignment_id,
        subject_id=row["subject_id"],
        assessment_id=row.get("assessment_id"),
        module_id=row.get("module_id"),
        expires_at=new_expiry,
        token=token,
        magic_link_url=magic_link_url,
    )


def get_attempt(supabase: Client, attempt_id: str) -> dict[str, Any]:
    res = (
        supabase.table("attempts")
        .select(
            "id, assignment_id, question_template_id, rendered_prompt, "
            "raw_answer, expected_answer, started_at, submitted_at, "
            "score, max_score, score_rationale, scorer_model, "
            "scorer_confidence, needs_review, active_time_seconds, "
            "rubric_version, metadata"
        )
        .eq("id", attempt_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Attempt not found.")
    return rows[0]


def attempt_notebook_download_url(
    supabase: Client, attempt_id: str
) -> dict[str, Any]:
    """Return a short-lived signed URL for the .ipynb artifact bound to
    this attempt. 404s when the attempt has no exported notebook."""

    attempt = get_attempt(supabase, attempt_id)
    metadata = attempt.get("metadata") or {}
    path = metadata.get("ipynb_path")
    if not path:
        raise HTTPException(
            status_code=404, detail="No notebook export found for attempt."
        )
    from .notebook_export import signed_notebook_url

    url = signed_notebook_url(supabase, path=path)
    if not url:
        raise HTTPException(
            status_code=502, detail="Storage service rejected signing request."
        )
    return {"signed_url": url, "path": path}


def list_competencies(supabase: Client) -> list[dict[str, Any]]:
    """Return the canonical competency catalog. Falls back to an empty list
    if the table doesn't exist yet on a fresh database."""

    try:
        res = (
            supabase.table("competencies")
            .select("id, name, domain, description")
            .order("domain")
            .order("name")
            .execute()
        )
        return list(res.data or [])
    except Exception:
        return []


def list_attempt_events(
    supabase: Client, assignment_id: str, *, limit: int = 1000
) -> list[dict[str, Any]]:
    """Integrity event log for an assignment, chronological. Used by the
    admin events timeline (spec §12.3)."""
    res = (
        supabase.table("attempt_events")
        .select(
            "id, attempt_id, event_type, payload, client_timestamp, "
            "server_timestamp, user_agent"
        )
        .eq("assignment_id", assignment_id)
        .order("server_timestamp")
        .limit(limit)
        .execute()
    )
    return list(res.data or [])


def cancel_assignment(
    supabase: Client, principal: AdminPrincipal, assignment_id: str
) -> AssignmentDetail:
    _ensure_role(principal, "admin")
    supabase.table("assignments").update({"status": "cancelled"}).eq(
        "id", assignment_id
    ).execute()
    return get_assignment_detail(supabase, assignment_id)
