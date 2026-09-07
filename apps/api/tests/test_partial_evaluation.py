"""Unit tests for partial-attempt candidate evaluation helpers.

Covers gating, 1-10 quality normalization, timing flags, gaming-risk
summary shape, and assignment evaluation_report persistence shape.
Does not call Anthropic or Supabase.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from ri_assessments_api.services.scoring import (
    _assert_can_evaluate,
    _enrich_attempt_evaluation,
    _has_submitted_answer,
    build_gaming_risk_summary,
    build_strengths_weaknesses,
    classify_timing,
    normalize_quality_score,
)

# -- gating / answer presence ----------------------------------------------


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [
        ({"raw_answer": None}, False),
        ({"raw_answer": {"value": None}}, False),
        ({"raw_answer": {"value": ""}}, False),
        ({"raw_answer": {"value": {}}}, False),
        ({"raw_answer": {"value": []}}, False),
        ({"raw_answer": {"value": {"selected_index": 1}}}, True),
        ({"raw_answer": {"value": "hello"}}, True),
        ({"raw_answer": {"value": 0}}, True),
    ],
)
def test_has_submitted_answer(attempt, expected):
    assert _has_submitted_answer(attempt) is expected


def test_assert_can_evaluate_partial_requires_answers():
    with pytest.raises(HTTPException) as exc:
        _assert_can_evaluate(
            assignment={"status": "in_progress"},
            attempts=[{"id": "a1", "raw_answer": None}],
            allow_partial=True,
        )
    assert exc.value.status_code == 409


def test_assert_can_evaluate_partial_returns_only_answered():
    attempts = [
        {"id": "a1", "raw_answer": None},
        {"id": "a2", "raw_answer": {"value": "x"}},
        {"id": "a3", "raw_answer": {"value": ""}},
    ]
    out = _assert_can_evaluate(
        assignment={"status": "in_progress"},
        attempts=attempts,
        allow_partial=True,
    )
    assert [a["id"] for a in out] == ["a2"]


def test_assert_can_evaluate_completed_path_keeps_all_rows():
    attempts = [
        {"id": "a1", "raw_answer": None},
        {"id": "a2", "raw_answer": {"value": "x"}},
    ]
    out = _assert_can_evaluate(
        assignment={"status": "completed"},
        attempts=attempts,
        allow_partial=False,
    )
    assert [a["id"] for a in out] == ["a1", "a2"]


# -- 1-10 normalization ----------------------------------------------------


def test_normalize_quality_score_endpoints():
    assert normalize_quality_score(0, 10) == 1.0
    assert normalize_quality_score(10, 10) == 10.0
    assert normalize_quality_score(5, 10) == 5.5


def test_normalize_quality_score_clamps_and_nulls():
    assert normalize_quality_score(20, 10) == 10.0
    assert normalize_quality_score(-5, 10) == 1.0
    assert normalize_quality_score(None, 10) is None
    assert normalize_quality_score(5, None) is None
    assert normalize_quality_score(5, 0) is None


# -- timing ----------------------------------------------------------------


def test_classify_timing_bands():
    assert classify_timing(active_time_seconds=10, time_limit_seconds=100)[
        "flag"
    ] == "rushed"
    assert classify_timing(active_time_seconds=50, time_limit_seconds=100)[
        "flag"
    ] == "normal"
    assert classify_timing(active_time_seconds=95, time_limit_seconds=100)[
        "flag"
    ] == "slow"
    assert classify_timing(active_time_seconds=None, time_limit_seconds=100)[
        "flag"
    ] == "unknown"


# -- gaming summary --------------------------------------------------------


def test_gaming_summary_shape_and_flags():
    events = [
        {"event_type": "paste_attempted", "payload": {"allowed": False}},
        {"event_type": "paste_attempted", "payload": {"allowed": True}},
        {"event_type": "devtools_opened", "payload": {}},
        {"event_type": "visibility_hidden", "payload": {}},
        {"event_type": "visibility_hidden", "payload": {}},
        {"event_type": "visibility_hidden", "payload": {}},
        {"event_type": "visibility_hidden", "payload": {}},
        {"event_type": "copy_attempted", "payload": {}},
        {"event_type": "fullscreen_exited", "payload": {}},
    ]
    summary = build_gaming_risk_summary(
        events=events,
        active_time_seconds=10,
        total_time_seconds=100,
        integrity_score=42.0,
    )
    assert set(summary.keys()) >= {
        "integrity_score",
        "risk_level",
        "flags",
        "counts",
        "active_time_seconds",
        "total_time_seconds",
        "active_time_ratio",
    }
    codes = {f["code"] for f in summary["flags"]}
    assert "paste_disallowed" in codes
    assert "devtools_opened" in codes
    assert "visibility_hidden" in codes
    assert "fullscreen_exited" in codes
    assert "low_active_time_ratio" in codes
    assert summary["counts"]["paste_disallowed"] == 1
    assert summary["risk_level"] == "high"
    for flag in summary["flags"]:
        assert set(flag.keys()) == {"code", "severity", "count", "detail"}
        assert flag["severity"] in {"low", "medium", "high"}


def test_gaming_summary_clean_session_is_low_risk():
    summary = build_gaming_risk_summary(
        events=[{"event_type": "focus_gained", "payload": {}}],
        active_time_seconds=80,
        total_time_seconds=100,
        integrity_score=100.0,
    )
    assert summary["risk_level"] == "low"
    assert summary["flags"] == []


# -- strengths / weaknesses + attempt report -------------------------------


def test_strengths_weaknesses_from_rollups_and_rationales():
    snapshot = {
        "questions": [
            {
                "id": "q1",
                "type": "mcq",
                "competency_tags": ["hubspot.workflows"],
                "max_points": 10,
            },
            {
                "id": "q2",
                "type": "text",
                "competency_tags": ["sql.joins"],
                "max_points": 10,
            },
        ]
    }
    attempts = [
        {
            "question_template_id": "q1",
            "score": 9,
            "max_score": 10,
            "score_rationale": "Correct option selected.",
            "needs_review": False,
        },
        {
            "question_template_id": "q2",
            "score": 2,
            "max_score": 10,
            "score_rationale": "Missed join condition.",
            "needs_review": True,
        },
    ]
    rollups = [
        {
            "competency_id": "hubspot.workflows",
            "score_pct": 90.0,
            "point_total": 9.0,
            "point_possible": 10.0,
        },
        {
            "competency_id": "sql.joins",
            "score_pct": 20.0,
            "point_total": 2.0,
            "point_possible": 10.0,
        },
    ]
    out = build_strengths_weaknesses(
        attempts=attempts, snapshot=snapshot, rollups=rollups
    )
    assert out["strengths"]
    assert out["weaknesses"]
    assert any("hubspot.workflows" in s for s in out["strengths"])
    assert any("sql.joins" in s for s in out["weaknesses"])


def test_enrich_attempt_evaluation_persists_report_shape():
    attempt = {"active_time_seconds": 30}
    question = {"time_limit_seconds": 120, "max_points": 10}
    out = _enrich_attempt_evaluation(
        attempt=attempt,
        question=question,
        score=8.0,
        max_score=10.0,
        rationale="Solid answer with minor gaps.",
    )
    assert out["quality_score"] == 8.2
    report = out["evaluation_report"]
    assert report["analysis"] == "Solid answer with minor gaps."
    assert report["quality_score"] == 8.2
    assert report["timing"]["flag"] == "normal"
    assert report["timing"]["ratio"] == 0.25
