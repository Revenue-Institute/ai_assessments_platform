"""Attempt lifecycle: lazy creation on first view, idempotent submit,
deadline enforcement, and final completion (spec §10.1, §13.1, §14.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from supabase import Client

from .code_runner import grade_code_attempt
from .diagram_runner import grade_diagram_attempt
from .n8n_runner import grade_n8n_attempt
from .notebook_runner import grade_notebook_attempt
from .randomizer import question_seed, render_prompt, sample_variables
from .sql_runner import grade_sql_attempt


def _parse_ts(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def session_deadline(assignment: dict[str, Any]) -> datetime | None:
    """The deadline the candidate timer should count down to.

    Once the candidate has consented (started_at is set), the session
    deadline is started_at + module_snapshot.target_duration_minutes,
    capped by the magic-link expiry. Before consent we just return the
    link expiry so the consent screen can show "Link expires" without
    pretending the assessment has started."""

    expires_at = _parse_ts(assignment.get("expires_at"))
    started_at = _parse_ts(assignment.get("started_at"))
    if not started_at:
        return expires_at
    snapshot = assignment.get("module_snapshot") or {}
    minutes = int(snapshot.get("target_duration_minutes") or 0)
    if minutes <= 0:
        return expires_at
    session_end = started_at + timedelta(minutes=minutes)
    if expires_at and expires_at < session_end:
        return expires_at
    return session_end


def _ensure_in_progress(assignment: dict[str, Any]) -> None:
    if assignment["status"] != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Assessment is {assignment['status']}, not in progress.",
        )
    deadline = session_deadline(assignment)
    if deadline and deadline <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Assessment time limit has elapsed.",
        )


def _question_at(assignment: dict[str, Any], index: int) -> dict[str, Any]:
    snapshot = assignment.get("module_snapshot") or {}
    questions: list[dict[str, Any]] = snapshot.get("questions") or []
    if index < 0 or index >= len(questions):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question index out of range.",
        )
    return questions[index]


def _sanitize_interactive_config(
    qtype: str, config: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Strip answer fields the candidate must not see (spec §13.2)."""

    if not config:
        return None
    cfg = dict(config)
    if qtype == "mcq" or qtype == "multi_select":
        cfg.pop("correct_index", None)
        cfg.pop("correct_indices", None)
    if qtype == "code":
        cfg.pop("hidden_tests", None)
    if qtype == "n8n":
        cfg.pop("reference_workflow", None)
    if qtype == "diagram":
        cfg.pop("reference_structure", None)
    if qtype == "sql":
        cfg.pop("expected_query_result", None)
        cfg.pop("expected_sql_patterns", None)
    if qtype == "notebook":
        cfg.pop("validation_script", None)
    return cfg


def get_assignment_for_token(supabase: Client, raw_token: str) -> dict[str, Any]:
    """Look up the full assignment row for a candidate token."""

    from .tokens import hash_token

    res = (
        supabase.table("assignments")
        .select(
            "id, status, expires_at, started_at, completed_at, "
            "random_seed, module_snapshot"
        )
        .eq("token_hash", hash_token(raw_token))
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found.",
        )
    return rows[0]


def _existing_attempt(
    supabase: Client, assignment_id: str, question_template_id: str
) -> dict[str, Any] | None:
    res = (
        supabase.table("attempts")
        .select(
            "id, raw_answer, started_at, submitted_at, rendered_prompt, "
            "variables_used, expected_answer, metadata"
        )
        .eq("assignment_id", assignment_id)
        .eq("question_template_id", question_template_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def _create_attempt(
    supabase: Client,
    *,
    assignment_id: str,
    random_seed: int,
    question: dict[str, Any],
) -> dict[str, Any]:
    qid = question["id"]
    variables = sample_variables(
        question.get("variable_schema") or {},
        question_seed(random_seed, qid),
    )
    rendered = render_prompt(question["prompt_template"], variables)

    # Spec §8.3: run the solver at attempt-creation time and cache its
    # output on the row. Fails soft when E2B is offline; admin rescore
    # picks it up later.
    expected_answer = None
    solver_code = question.get("solver_code")
    if isinstance(solver_code, str) and solver_code.strip():
        from .solver_runner import execute_solver

        expected_answer = execute_solver(
            solver_code=solver_code,
            variables=variables,
        )

    payload = {
        "assignment_id": assignment_id,
        "question_template_id": qid,
        "rendered_prompt": rendered,
        "variables_used": variables,
        "expected_answer": expected_answer,
        "started_at": datetime.now(UTC).isoformat(),
        "max_score": float(question.get("max_points") or 10),
    }
    inserted = supabase.table("attempts").insert(payload).execute()
    if not inserted.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create attempt.",
        )
    return inserted.data[0]


def get_or_create_attempt_view(
    supabase: Client,
    raw_token: str,
    index: int,
) -> dict[str, Any]:
    """Returns a candidate-safe view of the attempt at `index`. Lazily
    creates the row on first view (samples vars, renders prompt)."""

    assignment = get_assignment_for_token(supabase, raw_token)
    _ensure_in_progress(assignment)
    question = _question_at(assignment, index)

    attempt = _existing_attempt(supabase, assignment["id"], question["id"])
    if attempt is None:
        attempt = _create_attempt(
            supabase,
            assignment_id=assignment["id"],
            random_seed=int(assignment["random_seed"]),
            question=question,
        )

    questions = assignment["module_snapshot"]["questions"]
    deadline = session_deadline(assignment)
    return {
        "assignment_id": assignment["id"],
        "index": index,
        "total": len(questions),
        "question_template_id": question["id"],
        "type": question["type"],
        "rendered_prompt": attempt["rendered_prompt"],
        "max_points": float(question.get("max_points") or 10),
        "time_limit_seconds": question.get("time_limit_seconds"),
        "competency_tags": question.get("competency_tags") or [],
        "interactive_config": _sanitize_interactive_config(
            question["type"], question.get("interactive_config")
        ),
        "raw_answer": attempt.get("raw_answer"),
        "submitted_at": attempt.get("submitted_at"),
        "expires_at": (deadline or _parse_ts(assignment["expires_at"])),
    }


def save_draft_answer(
    supabase: Client,
    raw_token: str,
    index: int,
    answer: dict[str, Any] | list[Any] | str | int | float | bool | None,
) -> dict[str, Any]:
    """Autosave the in-progress answer for a question without scoring or
    advancing. `submitted_at` stays null so the attempt remains editable."""

    assignment = get_assignment_for_token(supabase, raw_token)
    _ensure_in_progress(assignment)
    question = _question_at(assignment, index)

    attempt = _existing_attempt(supabase, assignment["id"], question["id"])
    if attempt is None:
        attempt = _create_attempt(
            supabase,
            assignment_id=assignment["id"],
            random_seed=int(assignment["random_seed"]),
            question=question,
        )

    supabase.table("attempts").update(
        {"raw_answer": {"value": answer}}
    ).eq("id", attempt["id"]).execute()
    return {"ok": True, "saved_at": datetime.now(UTC).isoformat()}


def submit_answer(
    supabase: Client,
    raw_token: str,
    index: int,
    answer: dict[str, Any] | list[Any] | str | int | float | bool | None,
) -> dict[str, Any]:
    """Saves the candidate answer for a question. Idempotent overwrite
    until the assignment is completed."""

    assignment = get_assignment_for_token(supabase, raw_token)
    _ensure_in_progress(assignment)
    question = _question_at(assignment, index)

    attempt = _existing_attempt(supabase, assignment["id"], question["id"])
    if attempt is None:
        # Submit before view should not happen, but heal gracefully.
        attempt = _create_attempt(
            supabase,
            assignment_id=assignment["id"],
            random_seed=int(assignment["random_seed"]),
            question=question,
        )

    update: dict[str, Any] = {
        "raw_answer": {"value": answer},
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    # Synchronous grading on submit for the runner-backed types we can
    # score deterministically. Everything else (rubric_ai, structural_match
    # for n8n) lands later via score_assignment when the candidate completes.
    rubric = question.get("rubric") or {}
    qtype = question["type"]
    config = question.get("interactive_config") or {}
    max_points = float(question.get("max_points") or 10)

    if (
        qtype == "code"
        and rubric.get("scoring_mode") == "test_cases"
        and isinstance(answer, dict)
    ):
        candidate_code = answer.get("code")
        if isinstance(candidate_code, str) and candidate_code.strip():
            try:
                update.update(
                    grade_code_attempt(
                        code=candidate_code,
                        config=config,
                        max_points=max_points,
                    )
                )
                if update.get("score_rationale"):
                    update["rubric_version"] = rubric.get("version", "1")
            except HTTPException:
                # Sandbox is unavailable; keep the answer but leave score null.
                # An admin rescore picks this up later (spec §9.3).
                pass

    if qtype == "sql" and isinstance(answer, dict):
        candidate_sql = answer.get("sql") or answer.get("text")
        if isinstance(candidate_sql, str) and candidate_sql.strip():
            try:
                update.update(
                    grade_sql_attempt(
                        query_sql=candidate_sql,
                        config=config,
                        max_points=max_points,
                    )
                )
                if update.get("score_rationale"):
                    update["rubric_version"] = rubric.get("version", "1")
            except HTTPException:
                pass

    if (
        qtype == "diagram"
        and rubric.get("scoring_mode") in ("structural_match", "test_cases")
        and isinstance(answer, dict)
    ):
        diagram_payload = answer.get("diagram")
        if isinstance(diagram_payload, dict):
            try:
                update.update(
                    grade_diagram_attempt(
                        submission=diagram_payload,
                        config=config,
                        max_points=max_points,
                    )
                )
                if update.get("score_rationale"):
                    update["rubric_version"] = rubric.get("version", "1")
            except HTTPException:
                pass

    if qtype == "notebook" and isinstance(answer, dict):
        notebook_cells = answer.get("cells")
        if isinstance(notebook_cells, list) and notebook_cells:
            from .notebook_export import export_notebook_ipynb

            ipynb_path = export_notebook_ipynb(
                supabase,
                attempt_id=attempt["id"],
                cells=notebook_cells,
            )
            if ipynb_path:
                existing_meta = attempt.get("metadata") or {}
                update["metadata"] = {**existing_meta, "ipynb_path": ipynb_path}
            if rubric.get("scoring_mode") == "test_cases":
                try:
                    update.update(
                        grade_notebook_attempt(
                            cells=notebook_cells,
                            config=config,
                            max_points=max_points,
                        )
                    )
                    if update.get("score_rationale"):
                        update["rubric_version"] = rubric.get("version", "1")
                except HTTPException:
                    pass

    if (
        qtype == "n8n"
        and rubric.get("scoring_mode") in ("structural_match", "test_cases")
        and isinstance(answer, dict)
    ):
        workflow_payload = answer.get("workflow")
        if isinstance(workflow_payload, dict):
            try:
                update.update(
                    grade_n8n_attempt(
                        submission=workflow_payload,
                        config=config,
                        max_points=max_points,
                    )
                )
                if update.get("score_rationale"):
                    update["rubric_version"] = rubric.get("version", "1")
            except HTTPException:
                pass

    supabase.table("attempts").update(update).eq("id", attempt["id"]).execute()

    questions = assignment["module_snapshot"]["questions"]
    next_index = index + 1 if index + 1 < len(questions) else None
    return {
        "ok": True,
        "next_index": next_index,
        "total": len(questions),
    }


def complete_assignment(
    supabase: Client,
    raw_token: str,
) -> dict[str, Any]:
    """Marks the assignment completed. Computes total_time_seconds from the
    started_at + now diff (a coarse fallback; the proper number is the sum
    of attempt.active_time_seconds, computed once heartbeats land in v1)."""

    assignment = get_assignment_for_token(supabase, raw_token)
    if assignment["status"] == "completed":
        return {
            "assignment_id": assignment["id"],
            "status": "completed",
            "completed_at": assignment.get("completed_at"),
        }
    _ensure_in_progress(assignment)

    now = datetime.now(UTC)
    started_at = _parse_ts(assignment.get("started_at"))
    total_seconds = int((now - started_at).total_seconds()) if started_at else None

    update = {
        "status": "completed",
        "completed_at": now.isoformat(),
    }
    if total_seconds is not None:
        update["total_time_seconds"] = total_seconds

    supabase.table("assignments").update(update).eq("id", assignment["id"]).execute()

    # Try to enqueue async. Falls back to inline scoring when Redis is
    # offline so a stack without the worker still produces scores. A
    # background worker (apps/api/src/ri_assessments_api/worker.py) pulls
    # the job and runs the same score_assignment path.
    import logging

    log = logging.getLogger(__name__)

    from .queue import enqueue_score_assignment

    enqueued = enqueue_score_assignment(assignment["id"])
    if not enqueued:
        log.warning(
            "redis unavailable; running inline scoring for %s",
            assignment["id"],
        )
        try:
            from .scoring import score_assignment

            score_assignment(supabase, assignment["id"])
        except Exception:
            log.exception(
                "scoring failed for assignment %s; admin rescore will retry",
                assignment["id"],
            )

    return {
        "assignment_id": assignment["id"],
        "status": "completed",
        "completed_at": now.isoformat(),
        "scoring": "queued" if enqueued else "inline",
    }
