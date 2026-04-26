"""Scoring orchestrator (spec §9). Routes by rubric.scoring_mode and writes
back to attempts. Synchronous for v1 (BullMQ async lands later).

Modes:
- exact_match: mcq correct_index, multi_select correct_indices, or text/number
  equality against attempts.expected_answer.
- numeric_tolerance: abs diff against attempts.expected_answer with rubric.tolerance.
- rubric_ai: Claude tool-use with submit_score (breakdown + rationale + confidence).
- test_cases: handled at submit time by code_runner.grade_code_attempt.
- structural_match: delegated to per-runner grade (n8n / diagram); landing in
  the next slice. For now we leave the score null and flag for review."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from anthropic import Anthropic
from fastapi import HTTPException, status
from supabase import Client

from ..config import get_settings
from ..prompts.scoring import SCORING_SYSTEM_PROMPT, SUBMIT_SCORE_TOOL

log = logging.getLogger(__name__)

SCORING_MODEL = "claude-sonnet-4-6"
SCORER_VERSION = "1"
LOW_CONFIDENCE_THRESHOLD = 0.6


def _client() -> Anthropic:
    settings = get_settings()
    if not settings.anthropic_api_key_scoring:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY_SCORING is not configured.",
        )
    return Anthropic(api_key=settings.anthropic_api_key_scoring)


# -- Helpers ----------------------------------------------------------------


def _question_from_snapshot(
    module_snapshot: dict[str, Any], question_template_id: str
) -> dict[str, Any] | None:
    for q in (module_snapshot or {}).get("questions") or []:
        if q.get("id") == question_template_id:
            return q
    return None


def _value(answer: Any) -> Any:
    """attempts.raw_answer is stored as {"value": <whatever>}. Extract."""
    if isinstance(answer, dict) and "value" in answer:
        return answer["value"]
    return answer


def _normalize_text(s: str) -> str:
    return s.strip().lower()


# -- Scoring modes ----------------------------------------------------------


def _score_exact_match(
    *, raw_answer: Any, expected: Any, question: dict[str, Any]
) -> tuple[float, str]:
    """exact_match: mcq selected_index vs interactive_config.correct_index,
    multi_select selected_indices vs correct_indices, or text/number equality
    against expected (typically populated by solver)."""

    max_points = float(question.get("max_points") or 10)
    qtype = question.get("type")
    config = question.get("interactive_config") or {}
    value = _value(raw_answer)

    if qtype == "mcq":
        correct = config.get("correct_index")
        selected = (value or {}).get("selected_index") if isinstance(value, dict) else None
        if correct is None:
            return 0.0, "No correct_index defined; cannot exact-match."
        if selected == correct:
            return max_points, f"Selected option {selected} matches correct_index {correct}."
        return 0.0, f"Selected {selected}, correct was {correct}."

    if qtype == "multi_select":
        correct = set(config.get("correct_indices") or [])
        selected = (
            set((value or {}).get("selected_indices") or [])
            if isinstance(value, dict)
            else set()
        )
        if not correct:
            return 0.0, "No correct_indices defined; cannot exact-match."
        if selected == correct:
            return max_points, "Selected indices match exactly."
        # Partial credit: precision * recall * max
        true_positives = len(selected & correct)
        precision = true_positives / len(selected) if selected else 0
        recall = true_positives / len(correct)
        score = round(precision * recall * max_points, 2)
        return score, (
            f"Selected {sorted(selected)}, correct {sorted(correct)}. "
            f"precision={precision:.2f} recall={recall:.2f}."
        )

    # Text / numeric equality against solver-provided expected
    if expected is None:
        return 0.0, "No expected answer available; cannot exact-match."
    submitted = (value or {}).get("text") if isinstance(value, dict) else value
    if submitted is None:
        return 0.0, "No answer submitted."
    if isinstance(expected, str) and isinstance(submitted, str):
        if _normalize_text(submitted) == _normalize_text(expected):
            return max_points, "Exact text match (case-insensitive)."
        return 0.0, "Submitted text did not match expected."
    try:
        if float(submitted) == float(expected):
            return max_points, "Numeric exact match."
    except (TypeError, ValueError):
        pass
    return 0.0, "Submitted value did not equal expected."


def _score_numeric_tolerance(
    *, raw_answer: Any, expected: Any, tolerance: float, question: dict[str, Any]
) -> tuple[float, str]:
    max_points = float(question.get("max_points") or 10)
    value = _value(raw_answer)
    submitted = (value or {}).get("text") if isinstance(value, dict) else value
    if submitted is None or expected is None:
        return 0.0, "No answer or expected value to compare."
    try:
        diff = abs(float(submitted) - float(expected))
    except (TypeError, ValueError):
        return 0.0, "Could not coerce submitted/expected to numeric."
    if diff <= tolerance:
        return max_points, f"Within tolerance ({diff:.4g} <= {tolerance})."
    return 0.0, f"Out of tolerance ({diff:.4g} > {tolerance})."


def _score_rubric_ai(
    *, attempt: dict[str, Any], question: dict[str, Any]
) -> dict[str, Any]:
    """Claude tool-use scoring (spec §9.2)."""

    rubric = question.get("rubric") or {}
    max_points = float(question.get("max_points") or 10)
    rendered_prompt = attempt.get("rendered_prompt") or question.get("prompt_template", "")
    expected_answer = attempt.get("expected_answer")
    raw_answer = _value(attempt.get("raw_answer"))

    user_prompt = (
        "Score the following candidate answer against the rubric. Use the "
        "submit_score tool exactly once.\n\n"
        f"<question>\n{rendered_prompt}\n</question>\n\n"
        "<rubric>\n"
        f"{json.dumps(rubric, indent=2)}\n"
        "</rubric>\n\n"
        "<expected_answer>\n"
        f"{json.dumps(expected_answer, indent=2) if expected_answer is not None else '(none provided)'}\n"
        "</expected_answer>\n\n"
        "<candidate_answer>\n"
        f"{json.dumps(raw_answer, indent=2)}\n"
        "</candidate_answer>\n\n"
        f"This question is worth {max_points} max points. The criterion `max` "
        "fields are local caps — your final score is computed by us as a "
        "weighted average of (criterion.score / criterion.max) * weight scaled "
        f"to {max_points}, so populate every criterion."
    )

    started = time.monotonic()
    client = _client()
    response = client.messages.create(
        model=SCORING_MODEL,
        max_tokens=4_000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=[
            {
                "type": "text",
                "text": SCORING_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[SUBMIT_SCORE_TOOL],
        tool_choice={"type": "tool", "name": "submit_score"},
        messages=[{"role": "user", "content": user_prompt}],
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    payload: dict[str, Any] | None = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_score":
            payload = dict(block.input or {})
            break
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Scoring model did not call submit_score.",
        )

    breakdown = payload.get("breakdown") or []
    weighted_fraction = 0.0
    weight_total = 0.0
    criteria_index = {c["id"]: c for c in (rubric.get("criteria") or [])}
    for entry in breakdown:
        criterion = criteria_index.get(entry.get("criterion_id"))
        if not criterion:
            continue
        max_local = float(entry.get("max") or 0) or 1.0
        fraction = max(0.0, min(1.0, float(entry.get("score") or 0) / max_local))
        weight = float(criterion.get("weight") or 0)
        weighted_fraction += fraction * weight
        weight_total += weight

    # Even-weighted fallback so a malformed rubric still yields a score.
    if weight_total == 0 and breakdown:
        weighted_fraction = sum(
            max(0.0, min(1.0, float(b.get("score") or 0) / float(b.get("max") or 1)))
            for b in breakdown
        ) / len(breakdown)
        weight_total = 1.0

    score = round(weighted_fraction * max_points, 2) if weight_total else 0.0
    confidence = float(payload.get("confidence") or 0)

    return {
        "score": score,
        "score_rationale": payload.get("overall_rationale") or "",
        "scorer_model": SCORING_MODEL,
        "scorer_version": SCORER_VERSION,
        "scorer_confidence": round(confidence, 3),
        "needs_review": confidence < LOW_CONFIDENCE_THRESHOLD,
        "rubric_version": rubric.get("version", "1"),
        "_breakdown": breakdown,
        "_latency_ms": latency_ms,
        "_tokens_in": response.usage.input_tokens,
        "_tokens_out": response.usage.output_tokens,
    }


# -- Orchestration ----------------------------------------------------------


def score_attempt(
    supabase: Client,
    *,
    attempt: dict[str, Any],
    module_snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    """Score a single attempt, write the result back, return the update payload.
    Returns None if the attempt was skipped (e.g. structural_match awaiting a
    runner)."""

    question = _question_from_snapshot(
        module_snapshot, attempt["question_template_id"]
    )
    if question is None:
        log.warning(
            "attempt %s references question_template_id not in snapshot",
            attempt["id"],
        )
        return None

    rubric = question.get("rubric") or {}
    mode = rubric.get("scoring_mode")
    rubric_version = rubric.get("version", "1")

    update: dict[str, Any] = {
        "rubric_version": rubric_version,
    }

    if mode == "test_cases":
        # Already scored at submit time by code_runner.grade_code_attempt.
        # If for some reason the score is missing (e.g. E2B was offline at
        # submit), leave it for an admin rescore.
        if attempt.get("score") is None:
            return None
        return None

    if mode == "exact_match":
        score, rationale = _score_exact_match(
            raw_answer=attempt.get("raw_answer"),
            expected=attempt.get("expected_answer"),
            question=question,
        )
        update.update(
            {
                "score": score,
                "score_rationale": rationale,
                "scorer_model": "deterministic-exact",
                "scorer_version": SCORER_VERSION,
            }
        )

    elif mode == "numeric_tolerance":
        tolerance = float(rubric.get("tolerance") or 0.0)
        score, rationale = _score_numeric_tolerance(
            raw_answer=attempt.get("raw_answer"),
            expected=attempt.get("expected_answer"),
            tolerance=tolerance,
            question=question,
        )
        update.update(
            {
                "score": score,
                "score_rationale": rationale,
                "scorer_model": "deterministic-numeric",
                "scorer_version": SCORER_VERSION,
            }
        )

    elif mode == "rubric_ai":
        ai = _score_rubric_ai(attempt=attempt, question=question)
        update.update(
            {
                "score": ai["score"],
                "score_rationale": ai["score_rationale"],
                "scorer_model": ai["scorer_model"],
                "scorer_version": ai["scorer_version"],
                "scorer_confidence": ai["scorer_confidence"],
                "needs_review": ai["needs_review"],
                "rubric_version": ai["rubric_version"],
            }
        )

    elif mode == "structural_match":
        # n8n / diagram runners land in the next slice.
        update["needs_review"] = True
        update["score_rationale"] = (
            "structural_match scoring is not yet wired; awaiting runner integration."
        )
    else:
        update["needs_review"] = True
        update["score_rationale"] = f"Unknown scoring_mode: {mode!r}"

    update["updated_at"] = datetime.now(UTC).isoformat()
    supabase.table("attempts").update(update).eq("id", attempt["id"]).execute()
    return update


def _attempts_for_assignment(
    supabase: Client, assignment_id: str
) -> list[dict[str, Any]]:
    res = (
        supabase.table("attempts")
        .select(
            "id, question_template_id, raw_answer, expected_answer, "
            "rendered_prompt, score, max_score, score_rationale, "
            "scorer_model, scorer_version, scorer_confidence, needs_review, "
            "active_time_seconds"
        )
        .eq("assignment_id", assignment_id)
        .execute()
    )
    return list(res.data or [])


def _assignment_row(supabase: Client, assignment_id: str) -> dict[str, Any]:
    res = (
        supabase.table("assignments")
        .select(
            "id, subject_id, module_snapshot, started_at, completed_at, "
            "expires_at, status, total_time_seconds"
        )
        .eq("id", assignment_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    return rows[0]


# -- Aggregate rollups ------------------------------------------------------


def _compute_competency_rollups(
    *,
    attempts: list[dict[str, Any]],
    module_snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """For each competency tag referenced by any question, sum the points
    earned and possible across attempts that map to that tag (questions can
    carry multiple tags — we attribute the full attempt to each tag, per
    spec §11.2 read pattern)."""

    questions_by_id = {
        q["id"]: q for q in (module_snapshot or {}).get("questions") or []
    }
    rollups: dict[str, dict[str, float]] = {}
    for a in attempts:
        question = questions_by_id.get(a["question_template_id"])
        if not question:
            continue
        tags = question.get("competency_tags") or []
        score = float(a.get("score") or 0)
        max_score = float(a.get("max_score") or 0)
        for tag in tags:
            bucket = rollups.setdefault(tag, {"point_total": 0.0, "point_possible": 0.0})
            bucket["point_total"] += score
            bucket["point_possible"] += max_score
    out = []
    for tag, bucket in rollups.items():
        if bucket["point_possible"] <= 0:
            continue
        out.append(
            {
                "competency_id": tag,
                "point_total": round(bucket["point_total"], 2),
                "point_possible": round(bucket["point_possible"], 2),
                "score_pct": round(
                    bucket["point_total"] / bucket["point_possible"] * 100, 2
                ),
            }
        )
    return out


def _compute_integrity_score(
    *,
    events: list[dict[str, Any]],
    active_time_seconds: int | None,
    total_time_seconds: int | None,
) -> float:
    """Spec §10.4 formula: base 100, deductions per event class, floor 0."""

    counts: dict[str, int] = {}
    for ev in events:
        counts[ev.get("event_type", "")] = counts.get(ev.get("event_type", ""), 0) + 1

    score = 100.0
    visibility_hidden = counts.get("visibility_hidden", 0)
    if visibility_hidden > 3:
        score -= (visibility_hidden - 3) * 3
    focus_lost = counts.get("focus_lost", 0)
    if focus_lost > 5:
        score -= (focus_lost - 5) * 2
    score -= counts.get("fullscreen_exited", 0) * 8
    score -= counts.get("paste_attempted", 0) * 5
    score -= counts.get("copy_attempted", 0) * 2
    if counts.get("devtools_opened", 0) > 0:
        score -= 15
    score -= counts.get("window_resized", 0) * 3
    if (
        total_time_seconds
        and total_time_seconds > 0
        and active_time_seconds is not None
        and active_time_seconds / total_time_seconds < 0.3
    ):
        score -= 20
    return max(0.0, round(score, 2))


def _replace_competency_scores(
    supabase: Client,
    *,
    subject_id: str,
    assignment_id: str,
    rollups: list[dict[str, Any]],
) -> None:
    """Replace existing rollups for this assignment, then insert fresh rows.
    Keeps history simple — we re-derive on every (re)score."""

    supabase.table("competency_scores").delete().eq(
        "assignment_id", assignment_id
    ).execute()
    if not rollups:
        return
    rows = [
        {
            "id": str(uuid.uuid4()),
            "subject_id": subject_id,
            "competency_id": r["competency_id"],
            "assignment_id": assignment_id,
            "score_pct": r["score_pct"],
            "point_total": r["point_total"],
            "point_possible": r["point_possible"],
        }
        for r in rollups
    ]
    supabase.table("competency_scores").insert(rows).execute()


def score_assignment(
    supabase: Client, assignment_id: str
) -> dict[str, Any]:
    """Scores every unscored attempt, writes assignment-level rollups,
    computes integrity score from attempt_events, and upserts
    competency_scores. Returns the aggregate payload."""

    assignment = _assignment_row(supabase, assignment_id)
    snapshot = assignment.get("module_snapshot") or {}

    attempts = _attempts_for_assignment(supabase, assignment_id)
    for a in attempts:
        # Re-fetch isn't needed; we score from the in-memory attempt.
        score_attempt(supabase, attempt=a, module_snapshot=snapshot)

    # Re-read attempts now that scores are written.
    attempts = _attempts_for_assignment(supabase, assignment_id)

    final_score = round(sum(float(a.get("score") or 0) for a in attempts), 2)
    max_possible_score = round(sum(float(a.get("max_score") or 0) for a in attempts), 2)
    active_time = sum(int(a.get("active_time_seconds") or 0) for a in attempts) or None

    events = (
        supabase.table("attempt_events")
        .select("event_type")
        .eq("assignment_id", assignment_id)
        .execute()
    ).data or []
    integrity = _compute_integrity_score(
        events=events,
        active_time_seconds=active_time,
        total_time_seconds=assignment.get("total_time_seconds"),
    )

    supabase.table("assignments").update(
        {
            "final_score": final_score,
            "max_possible_score": max_possible_score,
            "integrity_score": integrity,
            "updated_at": datetime.now(UTC).isoformat(),
        }
    ).eq("id", assignment_id).execute()

    rollups = _compute_competency_rollups(
        attempts=attempts, module_snapshot=snapshot
    )
    _replace_competency_scores(
        supabase,
        subject_id=assignment["subject_id"],
        assignment_id=assignment_id,
        rollups=rollups,
    )

    return {
        "assignment_id": assignment_id,
        "final_score": final_score,
        "max_possible_score": max_possible_score,
        "integrity_score": integrity,
        "competency_rollups": rollups,
    }


# -- Rescore + audit -------------------------------------------------------


def rescore_attempt(
    supabase: Client,
    *,
    attempt_id: str,
    recorded_by: str | None,
) -> dict[str, Any]:
    """Snapshot the current score into attempt_scores_history, then re-score
    just this attempt and re-derive assignment rollups."""

    res = (
        supabase.table("attempts")
        .select(
            "id, assignment_id, question_template_id, raw_answer, "
            "expected_answer, rendered_prompt, score, max_score, "
            "score_rationale, scorer_model, scorer_version, "
            "scorer_confidence, rubric_version, needs_review, "
            "active_time_seconds"
        )
        .eq("id", attempt_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Attempt not found.")
    attempt = rows[0]

    supabase.table("attempt_scores_history").insert(
        {
            "attempt_id": attempt_id,
            "score": attempt.get("score"),
            "max_score": attempt.get("max_score"),
            "score_rationale": attempt.get("score_rationale"),
            "scorer_model": attempt.get("scorer_model"),
            "scorer_version": attempt.get("scorer_version"),
            "rubric_version": attempt.get("rubric_version"),
            "scorer_confidence": attempt.get("scorer_confidence"),
            "recorded_by": recorded_by,
        }
    ).execute()

    assignment = _assignment_row(supabase, attempt["assignment_id"])
    snapshot = assignment.get("module_snapshot") or {}

    score_attempt(supabase, attempt=attempt, module_snapshot=snapshot)

    aggregate = score_assignment(supabase, attempt["assignment_id"])
    return aggregate
