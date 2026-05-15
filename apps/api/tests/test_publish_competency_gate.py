"""Spec §11.1: every question_template must tag at least one competency
from the canonical taxonomy. `publish_module` rejects with 409 when any
question violates this rule, listing the offending positions.

These tests stub out the fairness check (which requires E2B) so the
competency gate is the only thing under test."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from ri_assessments_api.auth import AdminPrincipal
from ri_assessments_api.services import admin as admin_service
from ri_assessments_api.services import solver_runner as solver_runner_module

from .conftest import MockSupabase

MODULE_ID = "module-1"


def _admin() -> AdminPrincipal:
    return AdminPrincipal(
        user_id="admin-uid",
        email="admin@example.com",
        full_name="Admin",
        role="admin",
    )


def _seed_module(mock: MockSupabase, *, tag_rows: list[dict]) -> None:
    """Wire mock responses for:
      get_module() -> a single module row + N question_templates,
      then the publish_module helpers (taxonomy tag check, fairness).
    """

    questions_inner = [
        {
            "id": r["id"],
            "position": r["position"],
            "type": "short_answer",
            "prompt_template": "?",
            "variable_schema": {},
            "solver_code": None,
            "interactive_config": None,
            "rubric": {"scoring_mode": "exact_match", "criteria": []},
            "competency_tags": r["competency_tags"],
            "max_points": 10,
            "time_limit_seconds": None,
        }
        for r in tag_rows
    ]
    module_row = {
        "id": MODULE_ID,
        "slug": "m1",
        "title": "M1",
        "description": "",
        "domain": "ops",
        "target_duration_minutes": 30,
        "difficulty": "junior",
        "status": "draft",
        "version": 1,
        "created_at": "2026-05-13T00:00:00+00:00",
        "published_at": None,
        "question_templates": questions_inner,
    }
    mock.queue(("modules", "select"), [module_row])
    # publish_module reads question_templates again for the tag-validation
    # loop:
    mock.queue(
        ("question_templates", "select"),
        [
            {
                "id": r["id"],
                "position": r["position"],
                "competency_tags": r["competency_tags"],
            }
            for r in tag_rows
        ],
    )
    # Fairness pull (id, variable_schema, solver_code) returns empty so
    # fairness_check_module reports passed=True.
    mock.queue(("question_templates", "select"), [])


def _patch_fairness_pass(monkeypatch) -> None:
    """Skip E2B by short-circuiting fairness_check_module to a passing
    report. We patch via the module that publish_module imports inside its
    body (see services/admin.py)."""

    monkeypatch.setattr(
        solver_runner_module,
        "fairness_check_module",
        lambda **_kwargs: {"passed": True, "per_question": []},
    )
    monkeypatch.setattr(
        solver_runner_module,
        "assert_publishable",
        lambda report: None,
    )


# -- empty competency_tags ------------------------------------------------


def test_rejects_when_question_has_empty_competency_tags(monkeypatch):
    mock = MockSupabase()
    _seed_module(
        mock,
        tag_rows=[
            {
                "id": "q1",
                "position": 0,
                "competency_tags": ["hubspot.workflows"],
            },
            {"id": "q2", "position": 1, "competency_tags": []},
        ],
    )
    _patch_fairness_pass(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        admin_service.publish_module(mock, _admin(), MODULE_ID)
    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert isinstance(detail, dict)
    positions = [
        item["position"] for item in detail["offending_questions"]
    ]
    assert 1 in positions
    # Module must NOT have been flipped to published.
    assert not any(
        c.payload.get("status") == "published"
        for c in mock.calls_for("modules", "update")
    )


# -- out-of-taxonomy tag --------------------------------------------------


def test_rejects_when_tag_is_outside_taxonomy(monkeypatch):
    mock = MockSupabase()
    _seed_module(
        mock,
        tag_rows=[
            {
                "id": "q1",
                "position": 0,
                "competency_tags": ["totally.fake.tag"],
            },
        ],
    )
    _patch_fairness_pass(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        admin_service.publish_module(mock, _admin(), MODULE_ID)
    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert isinstance(detail, dict)
    bad = detail["offending_questions"][0]
    assert bad["position"] == 0
    assert "totally.fake.tag" in bad.get("tags", [])


# -- happy path -----------------------------------------------------------


def test_publishes_when_all_tags_valid(monkeypatch):
    mock = MockSupabase()
    # The third get_module call (publish_module returns get_module(...))
    # needs another module row.
    module_row_factory = lambda: {
        "id": MODULE_ID,
        "slug": "m1",
        "title": "M1",
        "description": "",
        "domain": "ops",
        "target_duration_minutes": 30,
        "difficulty": "junior",
        "status": "draft",
        "version": 1,
        "created_at": "2026-05-13T00:00:00+00:00",
        "published_at": None,
        "question_templates": [
            {
                "id": "q1",
                "position": 0,
                "type": "short_answer",
                "prompt_template": "?",
                "variable_schema": {},
                "solver_code": None,
                "interactive_config": None,
                "rubric": {"scoring_mode": "exact_match", "criteria": []},
                "competency_tags": ["hubspot.workflows"],
                "max_points": 10,
                "time_limit_seconds": None,
            }
        ],
    }
    # First select: get_module() called at the top of publish_module.
    mock.queue(("modules", "select"), [module_row_factory()])
    # Then tag-validation select:
    mock.queue(
        ("question_templates", "select"),
        [
            {
                "id": "q1",
                "position": 0,
                "competency_tags": ["hubspot.workflows"],
            }
        ],
    )
    # Fairness select returns []:
    mock.queue(("question_templates", "select"), [])
    # The final get_module() at the bottom of publish_module returns a
    # module row reflecting the new published state.
    mock.queue(("modules", "select"), [module_row_factory()])

    _patch_fairness_pass(monkeypatch)

    summary = admin_service.publish_module(mock, _admin(), MODULE_ID)
    assert summary.id == MODULE_ID
    # The update must have set status=published.
    updates = mock.calls_for("modules", "update")
    assert any(u.payload.get("status") == "published" for u in updates)
