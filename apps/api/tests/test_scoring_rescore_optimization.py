"""Spec §9.3 rescore: `rescore_attempt` re-scores only the target attempt
and re-derives assignment-level aggregates. The historic implementation
called `score_assignment`, which re-billed Claude across every sibling
rubric_ai attempt; we want to pin that today's path only invokes Claude
once per rescore.

We also confirm `_recompute_assignment_aggregates` writes the final
score / max possible / competency rollups using the in-memory attempt
rows after the targeted rescore."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from ri_assessments_api.services import scoring as scoring_module

from .conftest import MockSupabase

ASSIGNMENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SUBJECT_ID = "subject-1"

# Two rubric_ai attempts; the first is the rescore target, the second is a
# sibling that should NOT be re-evaluated.
ATTEMPT_TARGET = "attempt-target"
ATTEMPT_SIBLING = "attempt-sibling"
Q_TARGET = "q-target"
Q_SIBLING = "q-sibling"


def _rubric_ai_question(qid: str, tag: str) -> dict[str, Any]:
    return {
        "id": qid,
        "type": "long_answer",
        "prompt_template": "Explain your reasoning.",
        "rubric": {
            "version": "1",
            "scoring_mode": "rubric_ai",
            "criteria": [
                {
                    "id": "clarity",
                    "label": "Clarity",
                    "weight": 1.0,
                    "description": "Explanation is clear.",
                    "scoring_guidance": "Penalize hand-waving.",
                }
            ],
        },
        "competency_tags": [tag],
        "max_points": 10,
        "interactive_config": None,
    }


def _attempt_row(*, attempt_id: str, qid: str, score: float | None) -> dict:
    return {
        "id": attempt_id,
        "assignment_id": ASSIGNMENT_ID,
        "question_template_id": qid,
        "raw_answer": {"value": {"text": "an answer"}},
        "expected_answer": None,
        "rendered_prompt": "Explain your reasoning.",
        "score": score,
        "max_score": 10.0,
        "score_rationale": "prior pass" if score is not None else None,
        "scorer_model": "claude-sonnet-4-6" if score is not None else None,
        "scorer_version": "1+dev",
        "scorer_confidence": 0.8 if score is not None else None,
        "rubric_version": "1",
        "needs_review": False,
        "active_time_seconds": 60,
    }


def _module_snapshot() -> dict:
    return {
        "questions": [
            _rubric_ai_question(Q_TARGET, "data.python_analysis"),
            _rubric_ai_question(Q_SIBLING, "data.sql"),
        ]
    }


def _assignment_row() -> dict:
    return {
        "id": ASSIGNMENT_ID,
        "subject_id": SUBJECT_ID,
        "module_snapshot": _module_snapshot(),
        "started_at": "2026-05-13T00:00:00+00:00",
        "completed_at": "2026-05-13T00:30:00+00:00",
        "expires_at": "2026-05-20T00:00:00+00:00",
        "status": "completed",
        "total_time_seconds": 1800,
    }


def _fake_claude_response() -> Any:
    """Mimic an Anthropic Messages response with a single submit_score
    tool-use block."""

    block = MagicMock()
    block.type = "tool_use"
    block.name = "submit_score"
    block.input = {
        "breakdown": [
            {
                "criterion_id": "clarity",
                "score": 9,
                "max": 10,
                "note": "Strong, well-organized.",
            }
        ],
        "overall_rationale": "Clear and persuasive.",
        "confidence": 0.9,
    }
    response = MagicMock()
    response.content = [block]
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    return response


def test_rescore_attempt_only_invokes_claude_once(monkeypatch):
    """Spec §9.3 wants rescore_attempt to be a one-shot audit retry. The
    sibling rubric_ai attempt must NOT trigger a Claude call."""

    mock = MockSupabase()

    # 1) Fetch the target attempt row.
    mock.queue(
        ("attempts", "select"),
        [
            _attempt_row(
                attempt_id=ATTEMPT_TARGET, qid=Q_TARGET, score=5.0
            )
        ],
    )
    # 2) attempt_scores_history insert (echo).
    mock.queue(
        ("attempt_scores_history", "insert"),
        [{"id": "hist-1"}],
    )
    # 3) _assignment_row inside rescore_attempt.
    mock.queue(("assignments", "select"), [_assignment_row()])
    # 4) After the targeted score_attempt update, _recompute_assignment_aggregates:
    #    - _assignment_row again
    mock.queue(("assignments", "select"), [_assignment_row()])
    #    - _attempts_for_assignment returns both attempts so aggregates roll up correctly.
    mock.queue(
        ("attempts", "select"),
        [
            _attempt_row(
                attempt_id=ATTEMPT_TARGET, qid=Q_TARGET, score=9.0
            ),
            _attempt_row(
                attempt_id=ATTEMPT_SIBLING, qid=Q_SIBLING, score=7.0
            ),
        ],
    )
    #    - attempt_events for integrity score.
    mock.queue(("attempt_events", "select"), [])
    #    - subjects lookup inside _maybe_insert_training_suggestions.
    mock.queue(
        ("subjects", "select"),
        [{"id": SUBJECT_ID, "type": "candidate"}],
    )

    # Patch the Anthropic client so we can count calls.
    fake_anthropic = MagicMock()
    fake_anthropic.messages.create.return_value = _fake_claude_response()
    monkeypatch.setattr(scoring_module, "_client", lambda: fake_anthropic)

    # Run rescore.
    out = scoring_module.rescore_attempt(
        mock, attempt_id=ATTEMPT_TARGET, recorded_by="admin-uid"
    )

    # Exactly one Anthropic call for the target attempt; the sibling was
    # NOT re-scored.
    assert fake_anthropic.messages.create.call_count == 1

    # Aggregates persisted.
    assert out["assignment_id"] == ASSIGNMENT_ID
    # 9.0 (target rescored) + 7.0 (sibling untouched) = 16.0
    assert out["final_score"] == 16.0
    assert out["max_possible_score"] == 20.0

    # Assignment row update must have set final_score / max_possible_score.
    updates = mock.calls_for("assignments", "update")
    assert any(
        u.payload.get("final_score") == 16.0
        and u.payload.get("max_possible_score") == 20.0
        for u in updates
    )

    # competency_scores got replaced (delete + insert).
    assert mock.calls_for("competency_scores", "delete")
    inserts = mock.calls_for("competency_scores", "insert")
    assert inserts
    rollup_payload = inserts[0].payload
    assert isinstance(rollup_payload, list)
    tag_set = {row["competency_id"] for row in rollup_payload}
    assert tag_set == {"data.python_analysis", "data.sql"}


def test_recompute_aggregates_updates_assignment_row(monkeypatch):
    """Direct test of `_recompute_assignment_aggregates`: it must update
    final_score, max_possible_score, integrity_score, and rebuild the
    competency_scores rows from the current attempt set."""

    mock = MockSupabase()
    mock.queue(("assignments", "select"), [_assignment_row()])
    mock.queue(
        ("attempts", "select"),
        [
            _attempt_row(attempt_id="a1", qid=Q_TARGET, score=10.0),
            _attempt_row(attempt_id="a2", qid=Q_SIBLING, score=5.0),
        ],
    )
    mock.queue(("attempt_events", "select"), [])
    mock.queue(
        ("subjects", "select"),
        [{"id": SUBJECT_ID, "type": "candidate"}],
    )

    out = scoring_module._recompute_assignment_aggregates(
        mock, ASSIGNMENT_ID
    )

    assert out["final_score"] == 15.0
    assert out["max_possible_score"] == 20.0
    # rollups list contains a row per tag.
    tag_set = {r["competency_id"] for r in out["competency_rollups"]}
    assert tag_set == {"data.python_analysis", "data.sql"}
