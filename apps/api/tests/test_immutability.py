"""Spec §9.3 raw-answer immutability.

The second `submit_answer` for the same attempt is rejected with 409 so
admin rescore stays the only path to a new score. The never-submitted
path still accepts the write."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from ri_assessments_api.auth import issue_candidate_token
from ri_assessments_api.services.attempts import submit_answer

from .conftest import MockSupabase

ASSIGNMENT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SUBJECT_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
QUESTION_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
ATTEMPT_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"


def _token() -> str:
    return issue_candidate_token(
        assignment_id=ASSIGNMENT_ID,
        subject_id=SUBJECT_ID,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def _question() -> dict:
    return {
        "id": QUESTION_ID,
        "position": 0,
        "type": "short_answer",
        "prompt_template": "What is 2 + 2?",
        "variable_schema": {},
        "interactive_config": {},
        "rubric": {"scoring_mode": "exact_match", "criteria": []},
        "competency_tags": ["data.python_analysis"],
        "max_points": 10,
    }


def _assignment_row(started: bool = True) -> dict:
    return {
        "id": ASSIGNMENT_ID,
        "status": "in_progress",
        "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "started_at": datetime.now(UTC).isoformat() if started else None,
        "completed_at": None,
        "random_seed": 7,
        "module_snapshot": {
            "target_duration_minutes": 30,
            "questions": [_question()],
        },
        "metadata": {},
    }


def test_first_submit_accepts_answer():
    mock = MockSupabase()
    mock.queue(("assignments", "select"), [_assignment_row()])
    # No existing attempt: returns []
    mock.queue(("attempts", "select"), [])
    # Insert echoes back the new attempt (auto-default in MockSupabase)
    # so _create_attempt has a row to read.
    mock.queue(
        ("attempts", "insert"),
        [
            {
                "id": ATTEMPT_ID,
                "raw_answer": None,
                "started_at": datetime.now(UTC).isoformat(),
                "submitted_at": None,
                "rendered_prompt": "What is 2 + 2?",
                "variables_used": {},
                "expected_answer": None,
                "metadata": None,
            }
        ],
    )

    out = submit_answer(mock, _token(), 0, {"text": "4"})
    assert out["ok"] is True
    # An update against attempts must have happened with raw_answer set
    # and submitted_at populated.
    updates = mock.calls_for("attempts", "update")
    assert any(
        isinstance(u.payload, dict)
        and u.payload.get("raw_answer") == {"value": {"text": "4"}}
        and u.payload.get("submitted_at") is not None
        for u in updates
    )


def test_second_submit_rejected_with_409():
    mock = MockSupabase()
    mock.queue(("assignments", "select"), [_assignment_row()])
    # Existing attempt that was already submitted.
    mock.queue(
        ("attempts", "select"),
        [
            {
                "id": ATTEMPT_ID,
                "raw_answer": {"value": {"text": "4"}},
                "started_at": datetime.now(UTC).isoformat(),
                "submitted_at": datetime.now(UTC).isoformat(),
                "rendered_prompt": "What is 2 + 2?",
                "variables_used": {},
                "expected_answer": None,
                "metadata": None,
            }
        ],
    )

    with pytest.raises(HTTPException) as exc:
        submit_answer(mock, _token(), 0, {"text": "five"})
    assert exc.value.status_code == 409
    assert "Answer already submitted" in str(exc.value.detail)


def test_unsubmitted_existing_attempt_accepts_answer():
    """Edge case: a row exists (from /save or /view) but submitted_at is
    still null. The first submit should still be accepted."""

    mock = MockSupabase()
    mock.queue(("assignments", "select"), [_assignment_row()])
    mock.queue(
        ("attempts", "select"),
        [
            {
                "id": ATTEMPT_ID,
                "raw_answer": None,
                "started_at": datetime.now(UTC).isoformat(),
                "submitted_at": None,
                "rendered_prompt": "What is 2 + 2?",
                "variables_used": {},
                "expected_answer": None,
                "metadata": None,
            }
        ],
    )

    out = submit_answer(mock, _token(), 0, {"text": "4"})
    assert out["ok"] is True
