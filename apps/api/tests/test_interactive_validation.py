"""validate_interactive_config: enforces required keys and types per
question type, passes unknown types through, and 422s on malformed input."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from ri_assessments_api.models.interactive import validate_interactive_config

# -- Pass-through cases ----------------------------------------------------


def test_none_returns_none():
    assert validate_interactive_config("mcq", None) is None


def test_unknown_type_passes_through_unchanged():
    cfg = {"anything": "goes", "nested": {"x": 1}}
    assert validate_interactive_config("scenario", cfg) == cfg


# -- mcq -------------------------------------------------------------------


def test_mcq_minimal_valid():
    out = validate_interactive_config(
        "mcq", {"options": ["a", "b"], "correct_index": 0}
    )
    assert out == {"options": ["a", "b"], "correct_index": 0}


def test_mcq_missing_correct_index_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_interactive_config("mcq", {"options": ["a", "b"]})
    assert exc.value.status_code == 422


def test_mcq_too_few_options_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_interactive_config(
            "mcq", {"options": ["only-one"], "correct_index": 0}
        )
    assert exc.value.status_code == 422


def test_mcq_extra_fields_preserved():
    out = validate_interactive_config(
        "mcq",
        {
            "options": ["a", "b", "c"],
            "correct_index": 1,
            "rationale": "because b",
        },
    )
    assert out["rationale"] == "because b"


# -- multi_select ----------------------------------------------------------


def test_multi_select_valid():
    out = validate_interactive_config(
        "multi_select",
        {"options": ["a", "b", "c"], "correct_indices": [0, 2]},
    )
    assert out == {"options": ["a", "b", "c"], "correct_indices": [0, 2]}


def test_multi_select_empty_correct_rejected():
    with pytest.raises(HTTPException):
        validate_interactive_config(
            "multi_select", {"options": ["a", "b"], "correct_indices": []}
        )


# -- code ------------------------------------------------------------------


def test_code_minimal_valid():
    out = validate_interactive_config(
        "code",
        {
            "language": "python",
            "starter_code": "def f(): pass",
            "hidden_tests": "assert True",
        },
    )
    assert out["language"] == "python"
    assert out["allow_internet"] is False
    assert out["packages"] == []
    assert out["time_limit_exec_ms"] == 10_000


def test_code_invalid_language_rejected():
    with pytest.raises(HTTPException):
        validate_interactive_config(
            "code",
            {
                "language": "ruby",
                "starter_code": "",
                "hidden_tests": "",
            },
        )


# -- sql -------------------------------------------------------------------


def test_sql_optional_expected_omitted_ok():
    out = validate_interactive_config(
        "sql", {"schema_sql": "create table t (id int);", "seed_sql": ""}
    )
    assert out["expected_query_result"] is None
    assert out["expected_sql_patterns"] is None


def test_sql_with_patterns():
    out = validate_interactive_config(
        "sql",
        {
            "schema_sql": "create table t(id int);",
            "seed_sql": "insert into t values(1);",
            "expected_sql_patterns": ["FROM t", "WHERE id"],
        },
    )
    assert out["expected_sql_patterns"] == ["FROM t", "WHERE id"]


# -- diagram ---------------------------------------------------------------


def test_diagram_grading_mode_validated():
    with pytest.raises(HTTPException):
        validate_interactive_config(
            "diagram",
            {
                "mode": "build",
                "starter_nodes": [],
                "reference_structure": {},
                "grading_mode": "freeform",
            },
        )


# -- n8n -------------------------------------------------------------------


def test_n8n_connection_uses_from_alias():
    out = validate_interactive_config(
        "n8n",
        {
            "mode": "build",
            "starter_workflow": {"nodes": []},
            "reference_workflow": {"nodes": []},
            "required_nodes": ["Webhook"],
            "required_connections": [{"from": "A", "to": "B"}],
            "test_payloads": [],
            "credentials_provided": [],
        },
    )
    # `from` must round-trip as `from` (not `from_`) since it's a Python kw
    # but the JSON contract uses the keyword.
    assert out["required_connections"][0]["from"] == "A"
    assert out["required_connections"][0]["to"] == "B"
