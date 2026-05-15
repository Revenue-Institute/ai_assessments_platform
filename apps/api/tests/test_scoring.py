"""Unit tests for the deterministic scorers in services/scoring.

The rubric-AI scorer is not covered here (calls Anthropic). This file
covers exact-match (mcq/multi_select/text/numeric), numeric-tolerance,
the answer unwrap helper, and the competency rollup aggregator. These
are the parts a regression in the formula would silently break."""

from __future__ import annotations

from ri_assessments_api.services.scoring import (
    _compute_competency_rollups,
    _normalize_text,
    _score_exact_match,
    _score_numeric_tolerance,
    _value,
)

# -- _value ----------------------------------------------------------------


def test_value_unwraps_value_dict():
    assert _value({"value": 42}) == 42


def test_value_passes_through_when_not_wrapped():
    assert _value(42) == 42
    assert _value({"other": 1}) == {"other": 1}
    assert _value(None) is None


# -- _normalize_text -------------------------------------------------------


def test_normalize_text_lowercases_and_strips():
    assert _normalize_text("  Hello WORLD  ") == "hello world"


# -- _score_exact_match: mcq -----------------------------------------------


def _mcq(correct_index: int, max_points: int = 10):
    return {
        "type": "mcq",
        "max_points": max_points,
        "interactive_config": {"correct_index": correct_index},
    }


def test_mcq_correct_selection_full_credit():
    score, _ = _score_exact_match(
        raw_answer={"value": {"selected_index": 2}},
        expected=None,
        question=_mcq(correct_index=2),
    )
    assert score == 10.0


def test_mcq_wrong_selection_zero():
    score, _ = _score_exact_match(
        raw_answer={"value": {"selected_index": 0}},
        expected=None,
        question=_mcq(correct_index=2),
    )
    assert score == 0.0


def test_mcq_no_correct_index_returns_zero():
    score, msg = _score_exact_match(
        raw_answer={"value": {"selected_index": 0}},
        expected=None,
        question={"type": "mcq", "max_points": 10, "interactive_config": {}},
    )
    assert score == 0.0
    assert "correct_index" in msg


# -- _score_exact_match: multi_select --------------------------------------


def _multi(correct_indices: list[int], max_points: int = 10):
    return {
        "type": "multi_select",
        "max_points": max_points,
        "interactive_config": {"correct_indices": correct_indices},
    }


def test_multi_select_exact_match_full_credit():
    score, _ = _score_exact_match(
        raw_answer={"value": {"selected_indices": [1, 3, 5]}},
        expected=None,
        question=_multi(correct_indices=[1, 3, 5]),
    )
    assert score == 10.0


def test_multi_select_partial_credit_uses_precision_recall():
    # selected {1,2}, correct {1,3} -> tp=1, prec=0.5, recall=0.5 -> 0.25 * 10 = 2.5
    score, msg = _score_exact_match(
        raw_answer={"value": {"selected_indices": [1, 2]}},
        expected=None,
        question=_multi(correct_indices=[1, 3]),
    )
    assert score == 2.5
    assert "precision=0.50" in msg
    assert "recall=0.50" in msg


def test_multi_select_no_overlap_zero():
    score, _ = _score_exact_match(
        raw_answer={"value": {"selected_indices": [4, 5]}},
        expected=None,
        question=_multi(correct_indices=[1, 2]),
    )
    assert score == 0.0


def test_multi_select_empty_selection_zero():
    score, _ = _score_exact_match(
        raw_answer={"value": {"selected_indices": []}},
        expected=None,
        question=_multi(correct_indices=[1, 2]),
    )
    assert score == 0.0


# -- _score_exact_match: text / numeric ------------------------------------


def _text_q(max_points: int = 10):
    return {"type": "short_answer", "max_points": max_points}


def test_text_match_is_case_and_whitespace_insensitive():
    score, _ = _score_exact_match(
        raw_answer={"value": {"text": "  Hubspot  "}},
        expected="hubspot",
        question=_text_q(),
    )
    assert score == 10.0


def test_text_mismatch_zero():
    score, _ = _score_exact_match(
        raw_answer={"value": {"text": "wrong"}},
        expected="right",
        question=_text_q(),
    )
    assert score == 0.0


def test_numeric_equality_when_expected_is_not_string():
    # Numeric fallback only fires when the string-match path doesn't apply,
    # ie. when at least one side is not a string (typical solver outputs are
    # numbers, not strings).
    score, _ = _score_exact_match(
        raw_answer={"value": {"text": "42.0"}},
        expected=42,
        question=_text_q(),
    )
    assert score == 10.0


def test_text_strings_never_fall_back_to_numeric():
    # When both sides are strings, "42.0" and "42" are intentionally treated
    # as different text rather than collapsed numerically; otherwise users
    # would be surprised by formatting variance equating answers.
    score, _ = _score_exact_match(
        raw_answer={"value": {"text": "42.0"}},
        expected="42",
        question=_text_q(),
    )
    assert score == 0.0


def test_no_expected_returns_zero():
    score, msg = _score_exact_match(
        raw_answer={"value": {"text": "anything"}},
        expected=None,
        question=_text_q(),
    )
    assert score == 0.0
    assert "expected" in msg.lower()


# -- _score_numeric_tolerance ---------------------------------------------


def test_numeric_tolerance_within_full_credit():
    score, _ = _score_numeric_tolerance(
        raw_answer={"value": {"text": "100.05"}},
        expected=100,
        tolerance=0.1,
        question=_text_q(),
    )
    assert score == 10.0


def test_numeric_tolerance_outside_zero():
    score, _ = _score_numeric_tolerance(
        raw_answer={"value": {"text": "105"}},
        expected=100,
        tolerance=0.1,
        question=_text_q(),
    )
    assert score == 0.0


def test_numeric_tolerance_uncoerceable_zero():
    score, _ = _score_numeric_tolerance(
        raw_answer={"value": {"text": "abc"}},
        expected=100,
        tolerance=0.1,
        question=_text_q(),
    )
    assert score == 0.0


# -- _compute_competency_rollups ------------------------------------------


def _attempt(qid: str, score: float, max_score: float):
    return {
        "question_template_id": qid,
        "score": score,
        "max_score": max_score,
    }


def _snapshot(questions: list[dict]):
    return {"questions": questions}


def test_rollup_attributes_to_each_tag_independently():
    snapshot = _snapshot(
        [
            {"id": "q1", "competency_tags": ["hubspot.workflows", "marketing.email"]},
            {"id": "q2", "competency_tags": ["hubspot.workflows"]},
        ]
    )
    attempts = [
        _attempt("q1", 8, 10),
        _attempt("q2", 6, 10),
    ]
    out = sorted(
        _compute_competency_rollups(attempts=attempts, module_snapshot=snapshot),
        key=lambda r: r["competency_id"],
    )
    assert out == [
        {
            "competency_id": "hubspot.workflows",
            "point_total": 14.0,
            "point_possible": 20.0,
            "score_pct": 70.0,
        },
        {
            "competency_id": "marketing.email",
            "point_total": 8.0,
            "point_possible": 10.0,
            "score_pct": 80.0,
        },
    ]


def test_rollup_skips_attempts_with_no_matching_question():
    snapshot = _snapshot([{"id": "q1", "competency_tags": ["a"]}])
    attempts = [_attempt("q1", 5, 10), _attempt("orphan", 100, 100)]
    out = _compute_competency_rollups(attempts=attempts, module_snapshot=snapshot)
    assert out == [
        {
            "competency_id": "a",
            "point_total": 5.0,
            "point_possible": 10.0,
            "score_pct": 50.0,
        }
    ]


def test_rollup_drops_zero_possible_buckets():
    snapshot = _snapshot([{"id": "q1", "competency_tags": ["a"]}])
    attempts = [_attempt("q1", 0, 0)]
    assert (
        _compute_competency_rollups(attempts=attempts, module_snapshot=snapshot) == []
    )


def test_rollup_handles_null_score():
    snapshot = _snapshot([{"id": "q1", "competency_tags": ["a"]}])
    attempts = [{"question_template_id": "q1", "score": None, "max_score": 10}]
    out = _compute_competency_rollups(attempts=attempts, module_snapshot=snapshot)
    assert out == [
        {
            "competency_id": "a",
            "point_total": 0.0,
            "point_possible": 10.0,
            "score_pct": 0.0,
        }
    ]
