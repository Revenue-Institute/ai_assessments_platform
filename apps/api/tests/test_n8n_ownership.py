"""Spec §7.2 + §14.3 n8n workflow ownership.

`verify_n8n_workflow_owner` is the export-side gate that refuses any
workflow_id the candidate did not provision through their own attempt.
It returns silently on a match, raises 403 on a mismatch, 409 when no
workflow id has been recorded yet, and 404 when no attempt exists."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from ri_assessments_api.auth import issue_candidate_token
from ri_assessments_api.services.attempts import verify_n8n_workflow_owner

from .conftest import MockSupabase

ASSIGNMENT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
SUBJECT_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
QUESTION_ID = "11112222-3333-4444-5555-666677778888"


def _token() -> str:
    return issue_candidate_token(
        assignment_id=ASSIGNMENT_ID,
        subject_id=SUBJECT_ID,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def _assignment_row() -> dict:
    return {
        "id": ASSIGNMENT_ID,
        "status": "in_progress",
        "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "started_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
        "random_seed": 7,
        "module_snapshot": {
            "target_duration_minutes": 30,
            "questions": [
                {
                    "id": QUESTION_ID,
                    "position": 0,
                    "type": "n8n",
                    "prompt_template": "Build the workflow.",
                    "variable_schema": {},
                    "interactive_config": {},
                    "rubric": {"scoring_mode": "structural_match", "criteria": []},
                    "competency_tags": ["automation.n8n"],
                    "max_points": 10,
                }
            ],
        },
        "metadata": {},
    }


def test_matching_workflow_id_passes():
    mock = MockSupabase()
    mock.queue(("assignments", "select"), [_assignment_row()])
    mock.queue(
        ("attempts", "select"),
        [
            {
                "id": "attempt-1",
                "raw_answer": None,
                "started_at": datetime.now(UTC).isoformat(),
                "submitted_at": None,
                "rendered_prompt": "Build the workflow.",
                "variables_used": {},
                "expected_answer": None,
                "metadata": {"n8n_workflow_id": "wf-42"},
            }
        ],
    )

    # No exception.
    verify_n8n_workflow_owner(
        mock,
        raw_token=_token(),
        question_index=0,
        workflow_id="wf-42",
    )


def test_mismatched_workflow_id_returns_403():
    mock = MockSupabase()
    mock.queue(("assignments", "select"), [_assignment_row()])
    mock.queue(
        ("attempts", "select"),
        [
            {
                "id": "attempt-1",
                "raw_answer": None,
                "started_at": datetime.now(UTC).isoformat(),
                "submitted_at": None,
                "rendered_prompt": "Build the workflow.",
                "variables_used": {},
                "expected_answer": None,
                "metadata": {"n8n_workflow_id": "wf-42"},
            }
        ],
    )

    with pytest.raises(HTTPException) as exc:
        verify_n8n_workflow_owner(
            mock,
            raw_token=_token(),
            question_index=0,
            workflow_id="wf-totally-different",
        )
    assert exc.value.status_code == 403


def test_no_workflow_recorded_returns_409():
    mock = MockSupabase()
    mock.queue(("assignments", "select"), [_assignment_row()])
    mock.queue(
        ("attempts", "select"),
        [
            {
                "id": "attempt-1",
                "raw_answer": None,
                "started_at": datetime.now(UTC).isoformat(),
                "submitted_at": None,
                "rendered_prompt": "Build the workflow.",
                "variables_used": {},
                "expected_answer": None,
                "metadata": {},  # no workflow_id yet
            }
        ],
    )

    with pytest.raises(HTTPException) as exc:
        verify_n8n_workflow_owner(
            mock,
            raw_token=_token(),
            question_index=0,
            workflow_id="wf-42",
        )
    assert exc.value.status_code == 409


def test_no_attempt_returns_404():
    mock = MockSupabase()
    mock.queue(("assignments", "select"), [_assignment_row()])
    mock.queue(("attempts", "select"), [])

    with pytest.raises(HTTPException) as exc:
        verify_n8n_workflow_owner(
            mock,
            raw_token=_token(),
            question_index=0,
            workflow_id="wf-42",
        )
    assert exc.value.status_code == 404
