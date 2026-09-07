"""Scoring orchestrator (spec §9). Routes by rubric.scoring_mode and
writes back to attempts.

Submission no longer scores synchronously: the candidate's submit_answer
just persists raw_answer and returns. Scoring is queued (services.queue,
worker.py) when the assignment flips to completed, with an inline
fallback when Redis is unavailable.

Partial evaluation: admins can also score assignments that still have
status in_progress / expired / cancelled whenever at least one attempt
has a submitted `raw_answer`. That path reuses the same modes, then
normalizes each answered attempt to a 1-10 quality_score, stamps a
per-attempt evaluation_report (analysis + timing), and writes an
assignment-level evaluation_report (gaming-risk summary, strengths /
weaknesses, partial progress).

Modes:
- exact_match: mcq correct_index, multi_select correct_indices, or
  text/number equality against attempts.expected_answer.
- numeric_tolerance: abs diff against attempts.expected_answer with
  rubric.tolerance.
- rubric_ai: Claude tool-use with submit_score (breakdown + rationale +
  confidence).
- test_cases: code grading runs through code_runner.grade_code_attempt
  inside this orchestrator (no synchronous path at submit time).
- structural_match: delegated to per-runner grade (n8n / diagram)."""

from __future__ import annotations

import json
import logging
import os
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
# Scorer version blends a manual schema tag with the short git sha so a
# rescore after a code change is distinguishable in attempt_scores_history.
# GIT_SHA is set by CI / docker build; falls back to "dev" locally.
SCORER_VERSION = f"1+{os.environ.get('GIT_SHA', 'dev')[:8]}"
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
    snapshot: dict[str, Any], question_template_id: str
) -> dict[str, Any] | None:
    for q in (snapshot or {}).get("questions") or []:
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


def _has_submitted_answer(attempt: dict[str, Any]) -> bool:
    """True when the attempt carries a real submitted raw_answer.

    Attempts are created lazily on question view, so many rows exist with
    raw_answer IS NULL. Empty wrappers ({}, {"value": null}, {"value": ""})
    also count as unanswered so partial evaluate does not invent scores.
    """

    raw = attempt.get("raw_answer")
    if raw is None:
        return False
    value = _value(raw)
    if value is None or value == "":
        return False
    return not (isinstance(value, (dict, list)) and len(value) == 0)


def normalize_quality_score(
    score: float | None, max_score: float | None
) -> float | None:
    """Map a raw points score onto a closed 1.0-10.0 quality scale.

    0% -> 1.0, 100% -> 10.0, linear in between. Returns None when the
    attempt has no numeric score or max_score is missing/zero so callers
    can leave quality_score null for unanswered / unscored rows.
    """

    if score is None or max_score is None:
        return None
    try:
        max_f = float(max_score)
        score_f = float(score)
    except (TypeError, ValueError):
        return None
    if max_f <= 0:
        return None
    fraction = max(0.0, min(1.0, score_f / max_f))
    return round(1.0 + fraction * 9.0, 1)


# Timing bands relative to the question's time_limit_seconds (snapshot).
# Rushed: finished in under 25% of the allotted window. Slow: used more
# than 90%. Everything else is normal. Unknown when either side is missing.
TIMING_RUSHED_RATIO = 0.25
TIMING_SLOW_RATIO = 0.90


def classify_timing(
    *,
    active_time_seconds: int | None,
    time_limit_seconds: int | None,
) -> dict[str, Any]:
    """Return {flag, ratio, active_time_seconds, time_limit_seconds}."""

    payload: dict[str, Any] = {
        "flag": "unknown",
        "ratio": None,
        "active_time_seconds": active_time_seconds,
        "time_limit_seconds": time_limit_seconds,
    }
    if (
        active_time_seconds is None
        or time_limit_seconds is None
        or time_limit_seconds <= 0
    ):
        return payload
    ratio = float(active_time_seconds) / float(time_limit_seconds)
    payload["ratio"] = round(ratio, 3)
    if ratio < TIMING_RUSHED_RATIO:
        payload["flag"] = "rushed"
    elif ratio > TIMING_SLOW_RATIO:
        payload["flag"] = "slow"
    else:
        payload["flag"] = "normal"
    return payload


def _question_time_limit(question: dict[str, Any] | None) -> int | None:
    if not question:
        return None
    raw = question.get("time_limit_seconds")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _enrich_attempt_evaluation(
    *,
    attempt: dict[str, Any],
    question: dict[str, Any] | None,
    score: float | None,
    max_score: float | None,
    rationale: str | None,
) -> dict[str, Any]:
    """Build quality_score + evaluation_report fields for an attempt update."""

    quality = normalize_quality_score(score, max_score)
    timing = classify_timing(
        active_time_seconds=attempt.get("active_time_seconds"),
        time_limit_seconds=_question_time_limit(question),
    )
    analysis = (rationale or "").strip()
    if not analysis and quality is not None:
        analysis = f"Quality score {quality}/10 from existing scoring mode."
    report = {
        "analysis": analysis[:600] if analysis else None,
        "quality_score": quality,
        "timing": timing,
    }
    out: dict[str, Any] = {"evaluation_report": report}
    if quality is not None:
        out["quality_score"] = quality
    return out


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
        "fields are local caps, your final score is computed by us as a "
        "weighted average of (criterion.score / criterion.max) * weight scaled "
        f"to {max_points}, so populate every criterion."
    )

    started = time.monotonic()
    client = _client()
    response = client.messages.create(
        model=SCORING_MODEL,
        # 4k was tight for multi-criterion rubrics with detailed notes;
        # 8k gives the model headroom on long rubric breakdowns without
        # forcing truncation that would trip submit_score schema validation.
        max_tokens=8_000,
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
    snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    """Score a single attempt, write the result back, return the update payload.
    Returns None if the attempt was skipped (e.g. structural_match awaiting a
    runner).

    `snapshot` is the assignment's resolved snapshot (either
    assessment_snapshot or module_snapshot; see services.attempts.
    resolve_snapshot). Callers do not need to know which one."""

    question = _question_from_snapshot(
        snapshot, attempt["question_template_id"]
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
        # Code grading runs through code_runner.grade_code_attempt at
        # candidate-runtime (POST /a/{token}/code/test). The orchestrator
        # does not re-grade here because re-execution requires E2B and
        # the candidate's submitted code+packages, which the assignment
        # snapshot does not carry. If a code attempt arrives at scoring
        # with no `score`, leave it null so an admin can rescore via the
        # explicit rescore endpoint.
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
                # Deterministic scorers don't carry residual uncertainty:
                # confidence is 1.0, needs_review is cleared so a rescore
                # after a previous low-confidence AI pass clears the flag.
                "scorer_confidence": 1.0,
                "needs_review": False,
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
                "scorer_confidence": 1.0,
                "needs_review": False,
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
        # Spec §9.2: persist the per-criterion breakdown so reviewers can
        # audit which criteria drove the score. Column lives at
        # `attempts.score_breakdown` (migration 0017).
        breakdown = ai.get("_breakdown")
        if breakdown is not None:
            update["score_breakdown"] = breakdown

    elif mode == "structural_match":
        # diagram + n8n submissions are graded synchronously at submit
        # time by their respective runners (grade_diagram_attempt /
        # grade_n8n_attempt). If a score is already set we leave it; if
        # it's missing the runner was unavailable and an admin rescore
        # picks it up later.
        if attempt.get("score") is None:
            update["needs_review"] = True
            update["score_rationale"] = (
                "structural_match runner did not produce a score at submit "
                "time. Admin rescore will retry."
            )
        else:
            return None
    else:
        update["needs_review"] = True
        update["score_rationale"] = f"Unknown scoring_mode: {mode!r}"

    # Attach 1-10 quality + short analysis/timing whenever we produced a
    # numeric score. Reuses score_rationale as the analysis text so we do
    # not invent a second model call per answer.
    if "score" in update and update.get("score") is not None:
        max_for_quality = float(
            attempt.get("max_score") or question.get("max_points") or 0
        )
        update.update(
            _enrich_attempt_evaluation(
                attempt=attempt,
                question=question,
                score=float(update["score"]),
                max_score=max_for_quality,
                rationale=update.get("score_rationale"),
            )
        )

    update["updated_at"] = datetime.now(UTC).isoformat()
    supabase.table("attempts").update(update).eq("id", attempt["id"]).execute()

    # Spec §9.1, §14.4: fan out a per-attempt event so admins watching
    # the assignment detail page see the score flip the moment each
    # attempt lands, instead of waiting for the assignment-level
    # scoring_completed event at the end. Best-effort; failures are
    # swallowed inside queue_service.publish_scoring_event.
    try:
        from . import queue as queue_service

        assignment_id = attempt.get("assignment_id")
        if assignment_id and "score" in update:
            queue_service.publish_scoring_event(
                {
                    "type": "scoring_attempt",
                    "assignment_id": assignment_id,
                    "attempt_id": attempt["id"],
                    "score": update.get("score"),
                    "max": float(attempt.get("max_score") or 0),
                    "needs_review": bool(update.get("needs_review", False)),
                }
            )
    except Exception:  # pragma: no cover, defensive
        log.debug("scoring_attempt event publish failed", exc_info=True)

    return update


def _attempts_for_assignment(
    supabase: Client, assignment_id: str
) -> list[dict[str, Any]]:
    res = (
        supabase.table("attempts")
        .select(
            "id, assignment_id, question_template_id, raw_answer, "
            "expected_answer, rendered_prompt, score, max_score, "
            "score_rationale, scorer_model, scorer_version, "
            "scorer_confidence, needs_review, active_time_seconds, "
            "quality_score, evaluation_report"
        )
        .eq("assignment_id", assignment_id)
        .execute()
    )
    return list(res.data or [])


def _assignment_row(supabase: Client, assignment_id: str) -> dict[str, Any]:
    res = (
        supabase.table("assignments")
        .select(
            "id, subject_id, module_snapshot, assessment_snapshot, "
            "started_at, completed_at, expires_at, status, "
            "total_time_seconds, evaluation_report, scored_at"
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
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """For each competency tag referenced by any question, sum the points
    earned and possible across attempts that map to that tag (questions can
    carry multiple tags, we attribute the full attempt to each tag, per
    spec §11.2 read pattern)."""

    questions_by_id = {
        q["id"]: q for q in (snapshot or {}).get("questions") or []
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


# Integrity-score deductions per spec §10.4. Tuning lives here; the
# function below is just arithmetic. Keep this block in lockstep with
# packages/integrity/src/score.ts on the candidate side.
INTEGRITY_BASE_SCORE = 100.0
VISIBILITY_HIDDEN_GRACE = 3
VISIBILITY_HIDDEN_PENALTY = 3
FOCUS_LOST_GRACE = 5
FOCUS_LOST_PENALTY = 2
FULLSCREEN_EXIT_PENALTY = 8
PASTE_DISALLOWED_PENALTY = 5
COPY_PENALTY = 2
DEVTOOLS_PENALTY = 15
WINDOW_RESIZED_PENALTY = 3
ACTIVE_TIME_FLOOR = 0.3
INACTIVE_TIME_PENALTY = 20


def _compute_integrity_score(
    *,
    events: list[dict[str, Any]],
    active_time_seconds: int | None,
    total_time_seconds: int | None,
) -> float:
    """Spec §10.4 formula: base 100, deductions per event class, floor 0.

    Pastes only count when the browser monitor flagged them as
    disallowed (payload.allowed === false). Pastes inside Monaco /
    other code editors carry payload.allowed === true and are excluded.
    Window resizes only count for shrink events (the monitor only
    emits when the new width drops below 70 percent of the previous
    width). Other events have no payload-dependent gating."""

    counts: dict[str, int] = {}
    paste_disallowed = 0
    for ev in events:
        evt = ev.get("event_type", "")
        counts[evt] = counts.get(evt, 0) + 1
        if evt == "paste_attempted":
            payload = ev.get("payload") or {}
            if payload.get("allowed") is False:
                paste_disallowed += 1

    score = INTEGRITY_BASE_SCORE
    visibility_hidden = counts.get("visibility_hidden", 0)
    if visibility_hidden > VISIBILITY_HIDDEN_GRACE:
        score -= (visibility_hidden - VISIBILITY_HIDDEN_GRACE) * VISIBILITY_HIDDEN_PENALTY
    focus_lost = counts.get("focus_lost", 0)
    if focus_lost > FOCUS_LOST_GRACE:
        score -= (focus_lost - FOCUS_LOST_GRACE) * FOCUS_LOST_PENALTY
    score -= counts.get("fullscreen_exited", 0) * FULLSCREEN_EXIT_PENALTY
    score -= paste_disallowed * PASTE_DISALLOWED_PENALTY
    score -= counts.get("copy_attempted", 0) * COPY_PENALTY
    if counts.get("devtools_opened", 0) > 0:
        score -= DEVTOOLS_PENALTY
    score -= counts.get("window_resized", 0) * WINDOW_RESIZED_PENALTY
    if (
        total_time_seconds
        and total_time_seconds > 0
        and active_time_seconds is not None
        and active_time_seconds / total_time_seconds < ACTIVE_TIME_FLOOR
    ):
        score -= INACTIVE_TIME_PENALTY
    return max(0.0, round(score, 2))


def build_gaming_risk_summary(
    *,
    events: list[dict[str, Any]],
    active_time_seconds: int | None,
    total_time_seconds: int | None,
    integrity_score: float | None = None,
) -> dict[str, Any]:
    """Human-readable gaming / trust summary derived from attempt_events
    and the §10.4 integrity formula inputs. Surfaces concrete flags rather
    than a single opaque number (the number is still included)."""

    counts: dict[str, int] = {}
    paste_disallowed = 0
    for ev in events:
        evt = ev.get("event_type", "")
        counts[evt] = counts.get(evt, 0) + 1
        if evt == "paste_attempted":
            payload = ev.get("payload") or {}
            if payload.get("allowed") is False:
                paste_disallowed += 1

    visibility_hidden = counts.get("visibility_hidden", 0)
    focus_lost = counts.get("focus_lost", 0)
    fullscreen_exited = counts.get("fullscreen_exited", 0)
    copy_attempted = counts.get("copy_attempted", 0)
    devtools_opened = counts.get("devtools_opened", 0)
    window_resized = counts.get("window_resized", 0)

    active_ratio: float | None = None
    low_active_time = False
    if (
        total_time_seconds
        and total_time_seconds > 0
        and active_time_seconds is not None
    ):
        active_ratio = round(
            float(active_time_seconds) / float(total_time_seconds), 3
        )
        low_active_time = active_ratio < ACTIVE_TIME_FLOOR

    flags: list[dict[str, Any]] = []
    if paste_disallowed > 0:
        flags.append(
            {
                "code": "paste_disallowed",
                "severity": "medium",
                "count": paste_disallowed,
                "detail": (
                    f"{paste_disallowed} paste attempt(s) blocked outside "
                    "allowed editors."
                ),
            }
        )
    if copy_attempted > 0:
        flags.append(
            {
                "code": "copy_attempted",
                "severity": "low",
                "count": copy_attempted,
                "detail": f"{copy_attempted} copy attempt(s) recorded.",
            }
        )
    if visibility_hidden > VISIBILITY_HIDDEN_GRACE:
        flags.append(
            {
                "code": "visibility_hidden",
                "severity": "medium",
                "count": visibility_hidden,
                "detail": (
                    f"Tab hidden {visibility_hidden} time(s) "
                    f"(grace {VISIBILITY_HIDDEN_GRACE})."
                ),
            }
        )
    if focus_lost > FOCUS_LOST_GRACE:
        flags.append(
            {
                "code": "focus_lost",
                "severity": "medium",
                "count": focus_lost,
                "detail": (
                    f"Window focus lost {focus_lost} time(s) "
                    f"(grace {FOCUS_LOST_GRACE})."
                ),
            }
        )
    if fullscreen_exited > 0:
        flags.append(
            {
                "code": "fullscreen_exited",
                "severity": "high",
                "count": fullscreen_exited,
                "detail": f"Fullscreen exited {fullscreen_exited} time(s).",
            }
        )
    if devtools_opened > 0:
        flags.append(
            {
                "code": "devtools_opened",
                "severity": "high",
                "count": devtools_opened,
                "detail": "Developer tools open event detected.",
            }
        )
    if window_resized > 0:
        flags.append(
            {
                "code": "window_resized",
                "severity": "low",
                "count": window_resized,
                "detail": f"{window_resized} shrink resize event(s).",
            }
        )
    if low_active_time:
        flags.append(
            {
                "code": "low_active_time_ratio",
                "severity": "high",
                "count": 1,
                "detail": (
                    f"Active/total time ratio {active_ratio} is below "
                    f"floor {ACTIVE_TIME_FLOOR}."
                ),
            }
        )

    severity_rank = {"low": 1, "medium": 2, "high": 3}
    max_sev = max((severity_rank[f["severity"]] for f in flags), default=0)
    if max_sev >= 3 or len(flags) >= 3:
        risk_level = "high"
    elif max_sev >= 2 or len(flags) >= 1:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "integrity_score": integrity_score,
        "risk_level": risk_level,
        "flags": flags,
        "counts": {
            "visibility_hidden": visibility_hidden,
            "focus_lost": focus_lost,
            "fullscreen_exited": fullscreen_exited,
            "paste_disallowed": paste_disallowed,
            "copy_attempted": copy_attempted,
            "devtools_opened": devtools_opened,
            "window_resized": window_resized,
        },
        "active_time_seconds": active_time_seconds,
        "total_time_seconds": total_time_seconds,
        "active_time_ratio": active_ratio,
    }


def build_strengths_weaknesses(
    *,
    attempts: list[dict[str, Any]],
    snapshot: dict[str, Any],
    rollups: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Assignment-level strengths / weaknesses from scored answers +
    competency tags. Deterministic (no extra model call): high-scoring
    competency buckets and rationales become strengths; low-scoring
    buckets and needs_review rationales become weaknesses."""

    questions_by_id = {
        q["id"]: q for q in (snapshot or {}).get("questions") or []
    }
    strengths: list[str] = []
    weaknesses: list[str] = []

    for r in sorted(
        rollups, key=lambda x: float(x.get("score_pct") or 0), reverse=True
    ):
        pct = float(r.get("score_pct") or 0)
        cid = r.get("competency_id") or "unknown"
        if pct >= 75:
            strengths.append(
                f"Strong on {cid} ({pct:.0f}% of available points)."
            )
        elif pct < 50:
            weaknesses.append(
                f"Needs work on {cid} ({pct:.0f}% of available points)."
            )

    for a in attempts:
        if a.get("score") is None:
            continue
        q = questions_by_id.get(a.get("question_template_id") or "")
        max_score = float(
            a.get("max_score") or (q or {}).get("max_points") or 0
        )
        score = float(a.get("score") or 0)
        rationale = (a.get("score_rationale") or "").strip()
        label = (
            (q or {}).get("type")
            or a.get("question_template_id")
            or "question"
        )
        if max_score > 0 and score / max_score >= 0.85 and rationale:
            strengths.append(f"{label}: {rationale[:180]}")
        elif (
            (max_score > 0 and score / max_score < 0.4) or a.get("needs_review")
        ) and rationale:
            weaknesses.append(f"{label}: {rationale[:180]}")

    return {
        "strengths": strengths[:8],
        "weaknesses": weaknesses[:8],
    }


def _replace_competency_scores(
    supabase: Client,
    *,
    subject_id: str,
    assignment_id: str,
    rollups: list[dict[str, Any]],
) -> None:
    """Replace existing rollups for this assignment, then insert fresh rows.
    Keeps history simple, we re-derive on every (re)score."""

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


def _maybe_insert_training_suggestions(
    supabase: Client,
    *,
    subject_id: str,
    rollups: list[dict[str, Any]],
) -> None:
    """Spec §11.5 training-loop hook. For each competency rollup below 60%,
    insert a row into `training_suggestions` so the panel can surface it.
    Only fires for employee subjects; candidates don't get suggestions.

    Idempotent: skips when an undismissed row already exists for the
    (subject_id, competency_id) pair. Wrapped in try/except so a missing
    column / table / FK never blocks scoring."""

    try:
        subj_q = (
            supabase.table("subjects")
            .select("id, type")
            .eq("id", subject_id)
            .limit(1)
            .execute()
        )
        subj_rows = subj_q.data or []
        if not subj_rows or subj_rows[0].get("type") != "employee":
            return

        low_rollups = [r for r in rollups if float(r.get("score_pct") or 0) < 60]
        if not low_rollups:
            return

        # Dedup against existing undismissed suggestions.
        comp_ids = [r["competency_id"] for r in low_rollups]
        existing_q = (
            supabase.table("training_suggestions")
            .select("competency_id, dismissed_at")
            .eq("subject_id", subject_id)
            .in_("competency_id", comp_ids)
            .execute()
        )
        held = {
            row["competency_id"]
            for row in (existing_q.data or [])
            if row.get("dismissed_at") is None
        }
        now = datetime.now(UTC).isoformat()
        new_rows = [
            {
                "id": str(uuid.uuid4()),
                "subject_id": subject_id,
                "competency_id": r["competency_id"],
                "suggested_at": now,
            }
            for r in low_rollups
            if r["competency_id"] not in held
        ]
        if new_rows:
            supabase.table("training_suggestions").insert(new_rows).execute()
    except Exception as exc:  # pragma: no cover, defensive
        log.warning("training_suggestions insert skipped: %s", exc)


def _recompute_assignment_aggregates(
    supabase: Client, assignment_id: str
) -> dict[str, Any]:
    """Re-derive assignment-level rollups (final_score, max_possible_score,
    integrity_score, competency_scores) from the current attempt rows.
    Extracted from `score_assignment` so `rescore_attempt` can call it
    without re-running Claude across every sibling attempt."""

    assignment = _assignment_row(supabase, assignment_id)
    from .attempts import resolve_snapshot

    snapshot = resolve_snapshot(assignment)

    attempts = _attempts_for_assignment(supabase, assignment_id)

    final_score = round(sum(float(a.get("score") or 0) for a in attempts), 2)
    max_possible_score = round(
        sum(float(a.get("max_score") or 0) for a in attempts), 2
    )
    active_time = (
        sum(int(a.get("active_time_seconds") or 0) for a in attempts) or None
    )

    events = (
        supabase.table("attempt_events")
        .select("event_type, payload")
        .eq("assignment_id", assignment_id)
        .execute()
    ).data or []
    integrity = _compute_integrity_score(
        events=events,
        active_time_seconds=active_time,
        total_time_seconds=assignment.get("total_time_seconds"),
    )

    rollups = _compute_competency_rollups(
        attempts=attempts, snapshot=snapshot
    )
    _replace_competency_scores(
        supabase,
        subject_id=assignment["subject_id"],
        assignment_id=assignment_id,
        rollups=rollups,
    )

    # Spec §11.5 training-loop hook (v1.1 wired, not auto-populated):
    # insert training_suggestions for employee subjects whose rollups
    # land below 60 percent. Failures here never break scoring.
    _maybe_insert_training_suggestions(
        supabase, subject_id=assignment["subject_id"], rollups=rollups
    )

    answered = [a for a in attempts if _has_submitted_answer(a)]
    total_questions = len((snapshot or {}).get("questions") or [])
    gaming = build_gaming_risk_summary(
        events=events,
        active_time_seconds=active_time,
        total_time_seconds=assignment.get("total_time_seconds"),
        integrity_score=integrity,
    )
    narrative = build_strengths_weaknesses(
        attempts=attempts, snapshot=snapshot, rollups=rollups
    )
    evaluation_report = {
        "partial": assignment.get("status") != "completed"
        or len(answered) < total_questions,
        "answered_count": len(answered),
        "total_questions": total_questions,
        "scored_count": sum(1 for a in attempts if a.get("score") is not None),
        "gaming_risk": gaming,
        "strengths": narrative["strengths"],
        "weaknesses": narrative["weaknesses"],
        "evaluated_at": datetime.now(UTC).isoformat(),
    }

    supabase.table("assignments").update(
        {
            "final_score": final_score,
            "max_possible_score": max_possible_score,
            "integrity_score": integrity,
            "evaluation_report": evaluation_report,
            "scored_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    ).eq("id", assignment_id).execute()

    return {
        "assignment_id": assignment_id,
        "final_score": final_score,
        "max_possible_score": max_possible_score,
        "integrity_score": integrity,
        "competency_rollups": rollups,
        "evaluation_report": evaluation_report,
    }


def _assert_can_evaluate(
    *,
    assignment: dict[str, Any],
    attempts: list[dict[str, Any]],
    allow_partial: bool,
) -> list[dict[str, Any]]:
    """Return the attempts that should be scored for this run.

    Completed-flow (allow_partial=False): score every attempt row, same
    as before (unanswered rows still flow through deterministic scorers
    and land as 0). Partial-flow: require >=1 submitted answer and only
    score those answered rows, regardless of assignment status.
    """

    answered = [a for a in attempts if _has_submitted_answer(a)]
    if allow_partial:
        if not answered:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "No submitted answers to evaluate. At least one attempt "
                    "must have a raw_answer."
                ),
            )
        return answered

    # Legacy completed-path callers may still invoke this on non-completed
    # rows (inline fallback / rescore). Keep scoring every row so behavior
    # stays identical to pre-partial releases.
    return attempts


def score_assignment(
    supabase: Client,
    assignment_id: str,
    *,
    allow_partial: bool = False,
) -> dict[str, Any]:
    """Scores attempts, writes assignment-level rollups, computes integrity
    score from attempt_events, upserts competency_scores, and persists
    evaluation_report (gaming + strengths/weaknesses). Returns aggregates.

    When allow_partial=True, only attempts with a submitted raw_answer are
    scored and the assignment may be in_progress / expired / cancelled.
    Completed-flow callers leave allow_partial=False (default).
    """

    assignment = _assignment_row(supabase, assignment_id)
    from .attempts import resolve_snapshot

    snapshot = resolve_snapshot(assignment)

    attempts = _attempts_for_assignment(supabase, assignment_id)
    to_score = _assert_can_evaluate(
        assignment=assignment,
        attempts=attempts,
        allow_partial=allow_partial,
    )
    for a in to_score:
        # Re-fetch isn't needed; we score from the in-memory attempt.
        score_attempt(supabase, attempt=a, snapshot=snapshot)

    return _recompute_assignment_aggregates(supabase, assignment_id)


def evaluate_assignment(
    supabase: Client,
    assignment_id: str,
    *,
    recorded_by: str | None = None,
) -> dict[str, Any]:
    """Admin "Evaluate now" entrypoint for partial or completed work.

    Idempotent: re-running overwrites quality_score / evaluation_report
    and re-derives rollups. Does not change assignment.status.
    """

    aggregate = score_assignment(
        supabase, assignment_id, allow_partial=True
    )
    if recorded_by:
        attempts = _attempts_for_assignment(supabase, assignment_id)
        for a in attempts:
            if a.get("score") is not None:
                _stamp_history_recorded_by(supabase, a["id"], recorded_by)
    return aggregate


def list_partial_assignments_for_backfill(
    supabase: Client,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Assignments that have submitted answers but are not completed, or
    completed rows that somehow never received an evaluation_report.
    Used by the admin backfill endpoint / script."""

    statuses = ["in_progress", "expired", "cancelled", "completed"]
    res = (
        supabase.table("assignments")
        .select(
            "id, status, evaluation_report, "
            "attempts(id, raw_answer, score)"
        )
        .in_("status", statuses)
        .order("updated_at", desc=True)
        .limit(max(1, min(limit * 5, 500)))
        .execute()
    )
    out: list[dict[str, Any]] = []
    for row in res.data or []:
        attempts = row.get("attempts") or []
        answered = [a for a in attempts if _has_submitted_answer(a)]
        if not answered:
            continue
        report = row.get("evaluation_report")
        needs = report is None or row.get("status") != "completed"
        # Also pick completed rows that still have unanswered scoring gaps.
        unscored_answered = [
            a for a in answered if a.get("score") is None
        ]
        if needs or unscored_answered:
            out.append(
                {
                    "id": row["id"],
                    "status": row["status"],
                    "answered_count": len(answered),
                    "unscored_answered_count": len(unscored_answered),
                }
            )
        if len(out) >= limit:
            break
    return out


# -- Rescore + audit -------------------------------------------------------


def rescore_attempt(
    supabase: Client,
    *,
    attempt_id: str,
    recorded_by: str | None,
) -> dict[str, Any]:
    """Re-score just this attempt and re-derive assignment rollups.

    The prior score is snapshotted into attempt_scores_history automatically
    by the BEFORE UPDATE trigger installed in migration 0011. We do a
    follow-up UPDATE on the freshest history row to stamp recorded_by so
    audit attribution is preserved.
    """

    res = (
        supabase.table("attempts")
        .select(
            "id, assignment_id, question_template_id, raw_answer, "
            "expected_answer, rendered_prompt, score, max_score, "
            "score_rationale, scorer_model, scorer_version, "
            "scorer_confidence, rubric_version, needs_review, "
            "active_time_seconds, quality_score, evaluation_report"
        )
        .eq("id", attempt_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Attempt not found.")
    attempt = rows[0]

    assignment = _assignment_row(supabase, attempt["assignment_id"])
    from .attempts import resolve_snapshot

    snapshot = resolve_snapshot(assignment)

    # Only the target attempt gets re-scored. Iterating score_assignment
    # would re-bill Claude across every sibling attempt for what is
    # supposed to be a single-attempt rescore (spec §9.3 explicitly
    # frames rescore_attempt as a one-shot audit retry). Aggregates land
    # via _recompute_assignment_aggregates below.
    score_attempt(supabase, attempt=attempt, snapshot=snapshot)

    if recorded_by:
        _stamp_history_recorded_by(supabase, attempt_id, recorded_by)

    aggregate = _recompute_assignment_aggregates(
        supabase, attempt["assignment_id"]
    )
    return aggregate


def _stamp_history_recorded_by(
    supabase: Client, attempt_id: str, recorded_by: str
) -> None:
    """Tag the freshest attempt_scores_history row for this attempt with
    recorded_by. The trigger writes recorded_by = NULL; this follow-up
    UPDATE preserves admin attribution without re-snapshotting the row."""

    try:
        latest = (
            supabase.table("attempt_scores_history")
            .select("id")
            .eq("attempt_id", attempt_id)
            .is_("recorded_by", "null")
            .order("recorded_at", desc=True)
            .limit(1)
            .execute()
        ).data or []
        if latest:
            supabase.table("attempt_scores_history").update(
                {"recorded_by": recorded_by}
            ).eq("id", latest[0]["id"]).execute()
    except Exception:
        log.exception(
            "Failed to stamp recorded_by on history row for attempt %s",
            attempt_id,
        )
