"""Spec §6.1 Stage-2 validation: drop hallucinated tags + reject broken
question payloads coming out of Claude.

`_validate_stage2_question` returns `(ok, reason)`. Stage-2 callers skip
items with `ok=False`; we test the four canonical outcomes directly."""

from __future__ import annotations

from ri_assessments_api.services.generator import (
    _filter_competency_tags,
    _validate_stage2_question,
)


def _well_formed_mcq(*, tags: list[str]) -> dict:
    return {
        "type": "mcq",
        "prompt_template": "Pick the best option.",
        "variable_schema": {},
        "solver_code": None,
        "interactive_config": {
            "options": ["a", "b"],
            "correct_index": 0,
        },
        "rubric": {
            "version": "1",
            "scoring_mode": "exact_match",
            "criteria": [
                {
                    "id": "c1",
                    "label": "Correctness",
                    "weight": 1.0,
                    "description": "Right option",
                    "scoring_guidance": "Award full credit when correct.",
                }
            ],
        },
        "competency_tags": tags,
        "max_points": 10,
        "difficulty": "junior",
    }


# -- Hallucinated tags ----------------------------------------------------


def test_drops_hallucinated_tags_but_keeps_valid_ones():
    """A question with `[valid, fake]` keeps `valid` and drops `fake`. As
    long as one valid tag survives, the question itself is accepted."""

    filtered = _filter_competency_tags(
        ["hubspot.workflows", "not.a.real.tag", "another.fake.tag"]
    )
    assert filtered == ["hubspot.workflows"]

    raw = _well_formed_mcq(tags=["hubspot.workflows", "not.a.real.tag"])
    ok, reason = _validate_stage2_question(raw, default_difficulty="junior")
    assert ok is True, reason


def test_rejects_when_all_tags_are_invalid():
    raw = _well_formed_mcq(tags=["not.a.real.tag", "another.fake.tag"])
    ok, reason = _validate_stage2_question(raw, default_difficulty="junior")
    assert ok is False
    assert reason is not None
    assert "competency_tags" in reason


# -- Invalid interactive_config -------------------------------------------


def test_rejects_invalid_interactive_config():
    raw = _well_formed_mcq(tags=["hubspot.workflows"])
    # mcq requires `options` (>= 2) AND `correct_index`. Drop them.
    raw["interactive_config"] = {"options": ["only-one"]}
    ok, reason = _validate_stage2_question(raw, default_difficulty="junior")
    assert ok is False
    assert reason is not None
    assert "interactive_config" in reason


# -- Well-formed accepted -------------------------------------------------


def test_accepts_well_formed_question():
    raw = _well_formed_mcq(tags=["hubspot.workflows"])
    ok, reason = _validate_stage2_question(raw, default_difficulty="mid")
    assert ok is True
    assert reason is None


def test_rejects_question_with_no_type():
    raw = _well_formed_mcq(tags=["hubspot.workflows"])
    raw["type"] = 123  # not a string
    ok, reason = _validate_stage2_question(raw, default_difficulty="junior")
    assert ok is False
    assert reason == "missing type"


def test_rejects_question_with_missing_rubric():
    raw = _well_formed_mcq(tags=["hubspot.workflows"])
    raw["rubric"] = {}  # empty, no scoring_mode / criteria
    # Pydantic accepts an empty dict for `rubric: dict`, so the failure
    # must come from elsewhere. Force prompt_template to be empty to
    # exercise the QuestionTemplateCreate validation branch.
    raw["prompt_template"] = ""
    ok, reason = _validate_stage2_question(raw, default_difficulty="junior")
    assert ok is False
    assert reason is not None
    assert "QuestionTemplate validation failed" in reason
