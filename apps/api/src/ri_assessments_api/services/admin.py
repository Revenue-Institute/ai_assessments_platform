"""Admin-side business logic: modules, subjects, assignments (spec §14.1)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from supabase import Client

from ..auth import AdminPrincipal, ensure_role, issue_candidate_token
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
    ModuleQuestion,
    ModuleSummary,
    SubjectCreateRequest,
    SubjectSummary,
    UserListItem,
    UserListResponse,
)
from ..models.interactive import validate_interactive_config
from .tokens import candidate_token_url, hash_token


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
    # Admin module-detail endpoint (spec §14.1 `GET /api/modules/{id}`).
    # Returns the full question_templates payload including rubric,
    # variable_schema, solver_code, and interactive_config so the admin UI
    # can edit / preview without firing extra round-trips. The candidate
    # path (services/attempts.py) is where sanitization happens, not here.
    res = (
        supabase.table("modules")
        .select(
            "id, slug, title, description, domain, target_duration_minutes, "
            "difficulty, status, version, created_at, published_at, "
            "question_templates(id, position, type, prompt_template, "
            "variable_schema, solver_code, interactive_config, rubric, "
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
    raw_questions = sorted(
        row.get("question_templates") or [], key=lambda q: q.get("position", 0)
    )
    questions = [
        ModuleQuestion(
            id=q["id"],
            position=int(q.get("position") or 0),
            type=q["type"],
            prompt_template=q.get("prompt_template") or "",
            variable_schema=q.get("variable_schema") or {},
            solver_code=q.get("solver_code"),
            interactive_config=q.get("interactive_config"),
            rubric=q.get("rubric") or {},
            competency_tags=list(q.get("competency_tags") or []),
            time_limit_seconds=q.get("time_limit_seconds"),
            max_points=float(q.get("max_points") or 10),
        )
        for q in raw_questions
    ]
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
    ensure_role(principal, "admin")
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
    ensure_role(principal, "admin")
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
    ensure_role(principal, "admin")
    detail = get_module(supabase, module_id)
    if detail.question_count == 0:
        raise HTTPException(
            status_code=409,
            detail="Cannot publish a module with zero questions.",
        )

    # Spec §11.1: every question_template must tag at least one valid
    # competency. Load the canonical taxonomy and reject publish with a
    # 409 listing offending question positions when any question carries
    # zero tags or tags that aren't in the taxonomy.
    from .generator import _taxonomy_ids

    tag_rows = (
        supabase.table("question_templates")
        .select("id, position, competency_tags")
        .eq("module_id", module_id)
        .order("position")
        .execute()
    ).data or []
    valid_ids = _taxonomy_ids()
    invalid_positions: list[dict[str, Any]] = []
    for row in tag_rows:
        tags = [t for t in (row.get("competency_tags") or []) if isinstance(t, str)]
        if not tags:
            invalid_positions.append(
                {"position": row.get("position"), "reason": "no tags"}
            )
            continue
        out_of_taxonomy = [t for t in tags if t not in valid_ids]
        if out_of_taxonomy:
            invalid_positions.append(
                {
                    "position": row.get("position"),
                    "reason": "tags not in taxonomy",
                    "tags": out_of_taxonomy,
                }
            )
    if invalid_positions:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Module cannot be published: one or more questions carry "
                    "missing or out-of-taxonomy competency_tags."
                ),
                "offending_questions": invalid_positions,
            },
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

    ensure_role(principal, "admin")
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
        "interactive_config": validate_interactive_config(
            payload["type"], payload.get("interactive_config")
        ),
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
    ensure_role(principal, "admin")

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

    if "interactive_config" in update:
        # Resolve the effective type (the patch may be changing it). Falls
        # back to the existing row when the patch leaves type unset.
        new_type = update.get("type")
        if not new_type:
            existing = (
                supabase.table("question_templates")
                .select("type")
                .eq("id", question_id)
                .eq("module_id", module_id)
                .limit(1)
                .execute()
            )
            if not existing.data:
                raise HTTPException(status_code=404, detail="Question not found.")
            new_type = existing.data[0]["type"]
        update["interactive_config"] = validate_interactive_config(
            new_type, update["interactive_config"]
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
    ensure_role(principal, "admin")
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

    ensure_role(principal, "admin")

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
    ensure_role(principal, "admin")
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
    ensure_role(principal, "admin", "reviewer")
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
    rows = res.data or []
    if not rows:
        return []

    # Batch the per-assessment module aggregates into a single query, instead
    # of looping _assessment_module_rows N times. We only need module_count,
    # question_count, and total_duration_minutes for the summary; no need to
    # fetch the full module detail or sort by position.
    am_res = (
        supabase.table("assessment_modules")
        .select(
            "assessment_id, "
            "modules(target_duration_minutes, question_templates(id))"
        )
        .in_("assessment_id", [r["id"] for r in rows])
        .execute()
    )
    by_assessment: dict[str, list[dict[str, Any]]] = {}
    for am in am_res.data or []:
        module = am.get("modules") or {}
        by_assessment.setdefault(am["assessment_id"], []).append(
            {
                "target_duration_minutes": module.get(
                    "target_duration_minutes", 0
                ),
                "question_count": len(module.get("question_templates") or []),
            }
        )
    return [
        _assessment_summary(row, by_assessment.get(row["id"], []))
        for row in rows
    ]


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
    ensure_role(principal, "admin")

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
    ensure_role(principal, "admin")
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
    ensure_role(principal, "admin")

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

    # Two-phase shift so we don't trip the unique (assessment_id, position)
    # constraint mid-update. Walking `existing` ascending and bumping each
    # by 1 collides on the very first row when inserting at the head, since
    # `_assessment_module_rows` returns rows ordered by position. Mirror the
    # pattern used by reorder_assessment_modules: bump every shifted row to
    # an out-of-band band first, then assign the final positions.
    to_shift = [m for m in existing if m["position"] >= position]
    for m in to_shift:
        supabase.table("assessment_modules").update(
            {"position": m["position"] + 1000}
        ).eq("assessment_id", assessment_id).eq(
            "module_id", m["module_id"]
        ).execute()
    for m in to_shift:
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
    ensure_role(principal, "admin")

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
    ensure_role(principal, "admin")

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
    ensure_role(principal, "admin")

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
    ensure_role(principal, "admin")
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
    supabase: Client,
    assessment_id: str,
    *,
    allow_unpublished: bool = False,
) -> dict[str, Any]:
    """Build the frozen assessment + modules + questions snapshot.

    `allow_unpublished` is used by the admin preview flow ("Open as
    candidate" on a draft) so reviewers can validate authoring end-to-end
    without flipping the assessment to published first.
    """

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
    if not allow_unpublished and assessment["status"] != "published":
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


def _module_snapshot(
    supabase: Client,
    module_id: str,
    *,
    allow_unpublished: bool = False,
) -> dict[str, Any]:
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
    if not allow_unpublished and module["status"] != "published":
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
    preview: bool = False,
) -> AssignmentMagicLink:
    # Spec §13: only admins can mint magic links to real candidates. The
    # frontend mirrors this in role-policy.ts (/assignments/new is admin-
    # gated). The admin preview flow ("Open as candidate" on a draft)
    # routes through here with preview=True so reviewers + admins can
    # validate authoring on drafts without publishing first.
    if preview:
        ensure_role(principal, "admin", "reviewer")
    else:
        ensure_role(principal, "admin")
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
        snapshot = _assessment_snapshot(
            supabase, assessment_id, allow_unpublished=preview
        )
    else:
        module_id = payload.module_id
        snapshot = _module_snapshot(
            supabase, module_id, allow_unpublished=preview
        )

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
        # The Resend message id (when delivery succeeds) is persisted on
        # assignments.metadata.message_id so the resend webhook can join
        # delivery events precisely instead of fuzzy-matching by recipient.
        from .email import send_magic_link

        result = send_magic_link(
            to_email=subject_row["email"],
            subject_full_name=subject_row.get("full_name") or "there",
            module_title=snapshot.get("title", "Assessment"),
            magic_link_url=magic_link_url,
            expires_at=expires_at,
        )
        if result.ok and result.message_id:
            supabase.table("assignments").update(
                {"metadata": {"message_id": result.message_id}}
            ).eq("id", assignment_id_new).execute()

    return AssignmentMagicLink(
        assignment_id=assignment_id_new,
        subject_id=payload.subject_id,
        assessment_id=assessment_id,
        module_id=module_id,
        expires_at=expires_at,
        token=token,
        magic_link_url=magic_link_url,
    )


def create_preview_magic_link(
    supabase: Client,
    principal: AdminPrincipal,
    *,
    module_id: str | None = None,
    assessment_id: str | None = None,
) -> AssignmentMagicLink:
    """Mint a one-hour candidate magic link pointed at the admin's own
    `Admin Preview` subject. The admin clicks "Open as candidate" on a
    module / assessment preview page, the FE calls this, and the URL
    returned drops them straight into the live candidate UI (Monaco,
    Run / Test, timer, integrity monitor).

    The preview subject is a real `subjects` row keyed on the admin's
    user id so each reviewer gets their own. Re-using the row across
    sessions keeps the assignment list tidy."""

    ensure_role(principal, "admin", "reviewer")
    if not module_id and not assessment_id:
        raise HTTPException(
            status_code=400,
            detail="Either module_id or assessment_id is required.",
        )

    preview_email = f"preview+{principal.user_id}@admin.local"
    full_name = principal.full_name or principal.email or "Admin Preview"

    existing = (
        supabase.table("subjects")
        .select("id, full_name, email, type")
        .eq("email", preview_email)
        .eq("type", "candidate")
        .limit(1)
        .execute()
    )
    if existing.data:
        subject_id = existing.data[0]["id"]
    else:
        inserted = (
            supabase.table("subjects")
            .insert(
                {
                    "type": "candidate",
                    "full_name": f"{full_name} (preview)",
                    "email": preview_email,
                    "metadata": {"preview_for_admin_user_id": principal.user_id},
                }
            )
            .execute()
        )
        if not inserted.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to create preview subject.",
            )
        subject_id = inserted.data[0]["id"]

    payload = AssignmentCreateRequest(
        subject_id=subject_id,
        module_id=module_id,
        assessment_id=assessment_id,
        # 1 hour is enough to walk the assessment; expires_in_days is the
        # only knob the API exposes today, so we pass the equivalent.
        expires_in_days=1,
        send_email=False,
    )
    return create_assignment(
        supabase, principal, payload, send_email=False, preview=True
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

    ensure_role(principal, "admin")
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

    # Resending mints a fresh token; same authority as create_assignment,
    # so admin only.
    ensure_role(principal, "admin")
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
        # Use the dedicated "we resent your link" template so the body is
        # honest about being a reissue and existing recipients aren't
        # confused by a duplicate first-time invite.
        from .email import send_resend_notification

        snapshot = row.get("assessment_snapshot") or row.get("module_snapshot") or {}
        result = send_resend_notification(
            to_email=subject_row["email"],
            subject_full_name=subject_row.get("full_name") or "there",
            module_title=snapshot.get("title", "Assessment"),
            magic_link_url=magic_link_url,
            expires_at=new_expiry,
        )
        if result.ok and result.message_id:
            # Merge into existing metadata so we don't blow away the
            # delivery log accumulated by the resend webhook.
            existing_meta = (
                supabase.table("assignments")
                .select("metadata")
                .eq("id", assignment_id)
                .limit(1)
                .execute()
            )
            current = (existing_meta.data or [{}])[0].get("metadata") or {}
            current["message_id"] = result.message_id
            supabase.table("assignments").update(
                {"metadata": current}
            ).eq("id", assignment_id).execute()

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
    ensure_role(principal, "admin")
    supabase.table("assignments").update({"status": "cancelled"}).eq(
        "id", assignment_id
    ).execute()

    # Notify the candidate (best-effort). Lookup the email + snapshot
    # title; skip silently when the subject has no email on file. Email
    # failures never block the cancel response since the DB state has
    # already flipped to `cancelled`.
    try:
        ctx = (
            supabase.table("assignments")
            .select(
                "subject_id, module_snapshot, assessment_snapshot, "
                "subjects(full_name, email)"
            )
            .eq("id", assignment_id)
            .limit(1)
            .execute()
        )
        row = (ctx.data or [{}])[0]
        subject = row.get("subjects") or {}
        if subject.get("email"):
            snapshot = (
                row.get("assessment_snapshot")
                or row.get("module_snapshot")
                or {}
            )
            from .email import send_cancellation_notification

            send_cancellation_notification(
                to_email=subject["email"],
                subject_full_name=subject.get("full_name") or "there",
                module_title=snapshot.get("title", "Assessment"),
            )
    except Exception:  # pragma: no cover, defensive
        import logging

        logging.getLogger(__name__).exception(
            "cancel_assignment notification failed for %s", assignment_id
        )

    return get_assignment_detail(supabase, assignment_id)


# Settings / users management (spec §12.1 /settings/users) ------------------


_VALID_ROLES: tuple[str, ...] = ("admin", "reviewer", "viewer")


def list_users(
    supabase: Client, principal: AdminPrincipal
) -> UserListResponse:
    """List every row in public.users for the admin /settings/users page.

    Admin-only: viewers and reviewers should not see the team roster (spec
    §12.1 places user management under /settings/users, an admin-only
    surface). The signed-in admin's row is marked with `is_self=True` so
    the UI can grey-out destructive self-actions client-side; the
    self-demotion guard is still enforced server-side in
    update_user_role()."""

    ensure_role(principal, "admin")
    res = (
        supabase.table("users")
        .select("id, email, full_name, role")
        .order("email")
        .execute()
    )
    rows = res.data or []
    users: list[UserListItem] = []
    for row in rows:
        role = row.get("role")
        if role not in _VALID_ROLES:
            # Defensive: a row with an unrecognized role would otherwise
            # break the response_model validation. Skip rather than 500.
            continue
        users.append(
            UserListItem(
                id=row["id"],
                email=row.get("email") or "",
                full_name=row.get("full_name"),
                role=role,  # type: ignore[arg-type]
                is_self=row["id"] == principal.user_id,
            )
        )
    return UserListResponse(users=users)


def update_user_role(
    supabase: Client,
    principal: AdminPrincipal,
    *,
    target_user_id: str,
    new_role: str,
) -> UserListItem:
    """Update the role on public.users for `target_user_id`. Admin-only.

    Refuses self-demotion: an admin cannot strip their own admin role,
    which would otherwise let the last admin lock the org out of the
    /settings/users surface. The Supabase Dashboard remains the recovery
    path (operators with the service role can override directly)."""

    ensure_role(principal, "admin")
    if new_role not in _VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid role '{new_role}'. Allowed: "
                + ", ".join(_VALID_ROLES)
            ),
        )

    if target_user_id == principal.user_id and new_role != "admin":
        raise HTTPException(
            status_code=409,
            detail=(
                "You cannot remove your own admin role. Ask another admin "
                "to demote you, or use the Supabase Dashboard."
            ),
        )

    existing = (
        supabase.table("users")
        .select("id, email, full_name, role")
        .eq("id", target_user_id)
        .limit(1)
        .execute()
    )
    rows = existing.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="User not found.")

    updated = (
        supabase.table("users")
        .update(
            {"role": new_role, "updated_at": datetime.now(UTC).isoformat()}
        )
        .eq("id", target_user_id)
        .execute()
    )
    row = (updated.data or rows)[0]
    return UserListItem(
        id=row["id"],
        email=row.get("email") or "",
        full_name=row.get("full_name"),
        role=new_role,  # type: ignore[arg-type]
        is_self=row["id"] == principal.user_id,
    )
