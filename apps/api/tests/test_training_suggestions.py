"""Spec §11.5 training-loop hook.

`_maybe_insert_training_suggestions` is the wired-but-not-auto-populated
v1 hook that surfaces competencies below 60% for employee subjects only.
Candidates never get suggestions, and undismissed rows for the same
(subject, competency) pair are deduped."""

from __future__ import annotations

from ri_assessments_api.services.scoring import (
    _maybe_insert_training_suggestions,
)

from .conftest import MockSupabase


def _rollups(*pairs: tuple[str, float]) -> list[dict]:
    return [
        {
            "competency_id": cid,
            "score_pct": pct,
            "point_total": 0,
            "point_possible": 0,
        }
        for cid, pct in pairs
    ]


def test_inserts_for_employee_below_60():
    mock = MockSupabase()
    mock.queue(
        ("subjects", "select"), [{"id": "s1", "type": "employee"}]
    )
    # No existing rows.
    mock.queue(("training_suggestions", "select"), [])

    _maybe_insert_training_suggestions(
        mock,
        subject_id="s1",
        rollups=_rollups(("hubspot.workflows", 45.0)),
    )

    inserts = mock.calls_for("training_suggestions", "insert")
    assert inserts, "expected an insert for low employee score"
    payload = inserts[0].payload
    assert isinstance(payload, list)
    assert payload[0]["competency_id"] == "hubspot.workflows"
    assert payload[0]["subject_id"] == "s1"


def test_skipped_for_candidate_subject():
    mock = MockSupabase()
    mock.queue(
        ("subjects", "select"), [{"id": "s2", "type": "candidate"}]
    )
    _maybe_insert_training_suggestions(
        mock,
        subject_id="s2",
        rollups=_rollups(("hubspot.workflows", 30.0)),
    )
    assert mock.calls_for("training_suggestions", "insert") == []


def test_skipped_when_pct_at_or_above_60():
    mock = MockSupabase()
    mock.queue(
        ("subjects", "select"), [{"id": "s1", "type": "employee"}]
    )
    _maybe_insert_training_suggestions(
        mock,
        subject_id="s1",
        rollups=_rollups(("hubspot.workflows", 60.0)),
    )
    assert mock.calls_for("training_suggestions", "insert") == []


def test_deduplicates_existing_undismissed_suggestion():
    mock = MockSupabase()
    mock.queue(
        ("subjects", "select"), [{"id": "s1", "type": "employee"}]
    )
    mock.queue(
        ("training_suggestions", "select"),
        [
            {
                "competency_id": "hubspot.workflows",
                "dismissed_at": None,  # undismissed -> held
            }
        ],
    )

    _maybe_insert_training_suggestions(
        mock,
        subject_id="s1",
        rollups=_rollups(
            ("hubspot.workflows", 40.0),  # held by existing row
            ("data.sql", 35.0),           # fresh, should insert
        ),
    )

    inserts = mock.calls_for("training_suggestions", "insert")
    assert inserts, "expected at least one insert for the un-held competency"
    payload = inserts[0].payload
    assert isinstance(payload, list)
    assert [r["competency_id"] for r in payload] == ["data.sql"]


def test_dismissed_existing_row_does_not_block_new_insert():
    """An existing row with dismissed_at NOT NULL is treated as resolved;
    a fresh suggestion may be inserted for the same competency."""

    mock = MockSupabase()
    mock.queue(
        ("subjects", "select"), [{"id": "s1", "type": "employee"}]
    )
    mock.queue(
        ("training_suggestions", "select"),
        [
            {
                "competency_id": "hubspot.workflows",
                "dismissed_at": "2026-05-01T00:00:00+00:00",
            }
        ],
    )

    _maybe_insert_training_suggestions(
        mock,
        subject_id="s1",
        rollups=_rollups(("hubspot.workflows", 40.0)),
    )

    inserts = mock.calls_for("training_suggestions", "insert")
    assert inserts
    assert inserts[0].payload[0]["competency_id"] == "hubspot.workflows"
