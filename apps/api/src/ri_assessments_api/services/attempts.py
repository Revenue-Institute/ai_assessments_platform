"""Attempt lifecycle: lazy creation on first view, idempotent submit,
deadline enforcement, and final completion (spec §10.1, §13.1, §14.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from supabase import Client

from .randomizer import question_seed, render_prompt, sample_variables


def _parse_ts(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def resolve_snapshot(assignment: dict[str, Any]) -> dict[str, Any]:
    """Return the active snapshot for an assignment row.

    Assignments bound to an assessment write `assessment_snapshot`;
    assignments bound to a single module (legacy v1 flow) write
    `module_snapshot`. Readers must always prefer the assessment
    snapshot. This helper is the one place that knows the precedence,
    so the cutover from `module_snapshot` is reversible from a single
    file when the legacy column is finally dropped.

    Returns {} when neither column is populated so callers can keep
    using `.get("questions", [])` without exploding."""

    return (
        assignment.get("assessment_snapshot")
        or assignment.get("module_snapshot")
        or {}
    )


def session_deadline(assignment: dict[str, Any]) -> datetime | None:
    """The deadline the candidate timer should count down to.

    Once the candidate has consented (started_at is set), the session
    deadline is started_at + snapshot.target_duration_minutes, capped
    by the magic-link expiry. Before consent we just return the link
    expiry so the consent screen can show "Link expires" without
    pretending the assessment has started."""

    expires_at = _parse_ts(assignment.get("expires_at"))
    started_at = _parse_ts(assignment.get("started_at"))
    if not started_at:
        return expires_at
    snapshot = resolve_snapshot(assignment)
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
        # Spec §10.1 + CLAUDE.md: submissions past the server-authoritative
        # deadline are rejected with 409 Conflict (resource is no longer in
        # a state that accepts the action), not 410 Gone (which would imply
        # the resource itself was removed).
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment time limit has elapsed.",
        )


def _question_at(assignment: dict[str, Any], index: int) -> dict[str, Any]:
    snapshot = resolve_snapshot(assignment)
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
    """Look up the full assignment row for a candidate token.

    Spec §13 + §14.2: every candidate / runner endpoint funnels through
    here, so this is the single chokepoint where we verify the JWT before
    touching the database. Validates signature, audience (`ri-assessments-
    candidate`), and exp; cross-checks the JWT's `assignment_id` claim
    against the row resolved by token_hash. Any mismatch or signature
    failure fails closed (401). Skipped only when JWT_SIGNING_SECRET is
    unset (local dev), which is also when config.py allows an empty
    secret."""

    from ..auth import decode_candidate_token
    from ..config import get_settings
    from .tokens import hash_token

    settings = get_settings()
    claim_assignment_id: str | None = None
    if settings.jwt_signing_secret:
        claims = decode_candidate_token(raw_token)
        claim_assignment_id = claims.get("assignment_id")
        if not claim_assignment_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing the assignment_id claim.",
            )

    res = (
        supabase.table("assignments")
        .select(
            "id, status, expires_at, started_at, completed_at, "
            "random_seed, module_snapshot, assessment_snapshot, metadata"
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
    row = rows[0]

    # Defense in depth: even though token_hash is the index key, refuse to
    # serve the row when the claim's assignment_id disagrees. A leaked
    # token_hash row with a re-signed JWT pointing at another assignment
    # would otherwise resolve.
    if claim_assignment_id is not None and str(row["id"]) != str(claim_assignment_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not match the resolved assignment.",
        )
    return row


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
    try:
        inserted = supabase.table("attempts").insert(payload).execute()
    except Exception as exc:
        # Race condition: concurrent request inserted the row between our
        # SELECT and this INSERT. Fall back to the existing row.
        if "23505" in str(exc):
            existing = _existing_attempt(supabase, assignment_id, qid)
            if existing is not None:
                return existing
        raise
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

    questions = resolve_snapshot(assignment).get("questions") or []
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
    """Saves the candidate answer for a question. Raw answers are immutable
    once submitted (spec §9.3): the second submission for the same attempt
    is rejected with 409 so an admin rescore is the only path to a new
    score."""

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
    elif attempt.get("submitted_at") is not None:
        # Spec §9.3: raw_answer is immutable once submitted. The admin
        # rescore endpoint is the supported path to revise scoring after
        # the fact; the candidate cannot overwrite their own submission.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Answer already submitted; rescore via admin if change needed.",
        )

    update: dict[str, Any] = {
        "raw_answer": {"value": answer},
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    # Notebook submissions still get their .ipynb exported on submit so the
    # artifact is preserved even if the worker queue stalls later. Scoring
    # itself (every type, every mode) is deferred to score_assignment via
    # the queue when the assignment flips to completed: spec §9.1 + spec
    # §13.1. Synchronous grading on submit used to make this handler block
    # 5-15s per interactive question while an E2B sandbox spun up; that
    # made the "Save and continue" button feel broken to candidates and
    # also double-counted work the scoring orchestrator does anyway.
    qtype = question["type"]
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

    supabase.table("attempts").update(update).eq("id", attempt["id"]).execute()

    questions = resolve_snapshot(assignment).get("questions") or []
    next_index = index + 1 if index + 1 < len(questions) else None
    return {
        "ok": True,
        "next_index": next_index,
        "total": len(questions),
    }


def record_n8n_workflow_id(
    supabase: Client,
    *,
    raw_token: str,
    question_index: int,
    workflow_id: str,
) -> None:
    """Spec §7.2 + §14.3 ownership: stash the n8n workflow_id on the
    attempt's metadata so /n8n/export can refuse any id the candidate
    did not provision through us. The router calls this immediately
    after a successful provision_workspace; subsequent provisions for
    the same question overwrite the value (the previous workflow is
    orphaned on the n8n side, which is the existing behavior)."""

    assignment = get_assignment_for_token(supabase, raw_token)
    _ensure_in_progress(assignment)
    question = _question_at(assignment, question_index)
    attempt = _existing_attempt(supabase, assignment["id"], question["id"])
    if attempt is None:
        attempt = _create_attempt(
            supabase,
            assignment_id=assignment["id"],
            random_seed=int(assignment["random_seed"]),
            question=question,
        )
    existing_meta = attempt.get("metadata") or {}
    new_meta = {**existing_meta, "n8n_workflow_id": str(workflow_id)}
    supabase.table("attempts").update({"metadata": new_meta}).eq(
        "id", attempt["id"]
    ).execute()


def verify_n8n_workflow_owner(
    supabase: Client,
    *,
    raw_token: str,
    question_index: int,
    workflow_id: str,
) -> None:
    """Reject export requests for workflows the candidate did not
    provision through their own attempt. Fail closed (404) if no
    workflow_id has been stored yet, so a candidate cannot scrape
    arbitrary workflows by guessing ids."""

    assignment = get_assignment_for_token(supabase, raw_token)
    question = _question_at(assignment, question_index)
    attempt = _existing_attempt(supabase, assignment["id"], question["id"])
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No attempt has been provisioned for this question.",
        )
    stored = (attempt.get("metadata") or {}).get("n8n_workflow_id")
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No n8n workflow has been provisioned for this attempt.",
        )
    if str(stored) != str(workflow_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workflow id does not belong to this attempt.",
        )


def complete_assignment(
    supabase: Client,
    raw_token: str,
) -> dict[str, Any]:
    """Marks the assignment completed. Computes total_time_seconds from
    the started_at + now diff (wall-clock elapsed). The per-attempt
    `active_time_seconds` series (heartbeat-clamped via migration 0018)
    is summed inside `_recompute_assignment_aggregates`, which is what
    the integrity score consumes; the wall-clock total here is just a
    coarse audit field for "how long did the candidate sit on this"."""

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

    import logging

    log = logging.getLogger(__name__)

    # n8n teardown (spec §7.2): iterate the assignment's attempts, find
    # any n8n questions whose attempt persisted a workflow_id, and call
    # cleanup_workflow for each. Failures are swallowed per attempt so
    # one stuck cleanup never blocks completion.
    try:
        from .n8n_runner import cleanup_workflow

        questions_by_id = {
            q.get("id"): q
            for q in resolve_snapshot(assignment).get("questions") or []
        }
        attempts_rows = (
            supabase.table("attempts")
            .select(
                "id, question_template_id, metadata, interactive_artifact_url"
            )
            .eq("assignment_id", assignment["id"])
            .execute()
        ).data or []
        for attempt in attempts_rows:
            question = questions_by_id.get(attempt.get("question_template_id"))
            if not question or question.get("type") != "n8n":
                continue
            workflow_id: str | None = None
            metadata = attempt.get("metadata") or {}
            if isinstance(metadata, dict):
                wf = metadata.get("n8n_workflow_id") or metadata.get(
                    "workflow_id"
                )
                if isinstance(wf, str) and wf:
                    workflow_id = wf
            if not workflow_id:
                artifact = attempt.get("interactive_artifact_url")
                if isinstance(artifact, str) and "/workflow/" in artifact:
                    workflow_id = (
                        artifact.rstrip("/").rsplit("/", 1)[-1] or None
                    )
            if workflow_id:
                try:
                    cleanup_workflow(workflow_id)
                except Exception as exc:  # pragma: no cover, defensive
                    log.warning(
                        "n8n cleanup failed for attempt %s: %s",
                        attempt.get("id"),
                        exc,
                    )
    except Exception as exc:  # pragma: no cover, defensive
        log.warning("n8n cleanup pass skipped: %s", exc)

    # Try to enqueue async. Falls back to inline scoring when Redis is
    # offline so a stack without the worker still produces scores. A
    # background worker (apps/api/src/ri_assessments_api/worker.py) pulls
    # the job and runs the same score_assignment path.
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

    # Notify the admin who created the assignment that scoring is in
    # flight / complete. Best-effort: scoring may still be running in
    # the worker, in which case score fields will be None and the email
    # surfaces a "pending" placeholder. Email failures never block the
    # candidate's completion response.
    try:
        meta = (
            supabase.table("assignments")
            .select(
                "created_by, final_score, max_possible_score, "
                "integrity_score, module_snapshot, assessment_snapshot, "
                "subjects(full_name, email)"
            )
            .eq("id", assignment["id"])
            .limit(1)
            .execute()
        )
        meta_row = (meta.data or [{}])[0]
        creator_id = meta_row.get("created_by")
        if creator_id:
            admin_q = (
                supabase.table("users")
                .select("email, full_name")
                .eq("id", creator_id)
                .limit(1)
                .execute()
            )
            admin_row = (admin_q.data or [{}])[0]
            admin_email = admin_row.get("email")
            if admin_email:
                snapshot = (
                    meta_row.get("assessment_snapshot")
                    or meta_row.get("module_snapshot")
                    or {}
                )
                subj_row = meta_row.get("subjects") or {}
                final = meta_row.get("final_score")
                possible = meta_row.get("max_possible_score")
                pct: float | None = None
                if (
                    isinstance(final, (int, float))
                    and isinstance(possible, (int, float))
                    and possible
                ):
                    pct = (float(final) / float(possible)) * 100.0
                from .email import send_result_notification

                send_result_notification(
                    to_email=admin_email,
                    admin_full_name=admin_row.get("full_name"),
                    subject_full_name=subj_row.get("full_name") or "candidate",
                    module_title=snapshot.get("title", "Assessment"),
                    final_score_pct=pct,
                    integrity_score=meta_row.get("integrity_score"),
                    assignment_id=assignment["id"],
                )
    except Exception:  # pragma: no cover, defensive
        log.exception(
            "result notification failed for assignment %s",
            assignment["id"],
        )

    return {
        "assignment_id": assignment["id"],
        "status": "completed",
        "completed_at": now.isoformat(),
        "scoring": "queued" if enqueued else "inline",
    }
