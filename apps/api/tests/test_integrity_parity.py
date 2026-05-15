"""Parity test for the integrity score formula.

Loads the canonical fixtures from packages/integrity/test/fixtures.json
(also consumed by packages/integrity/test/score.test.ts) and asserts the
Python implementation matches expected_score. The TS implementation has
its own test against the same fixtures; if either side drifts, the
formula has to be updated in lockstep across both files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ri_assessments_api.services.scoring import _compute_integrity_score

FIXTURES_PATH = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "integrity"
    / "test"
    / "fixtures.json"
)


def _load_fixtures() -> list[dict]:
    with FIXTURES_PATH.open() as f:
        return json.load(f)["fixtures"]


@pytest.mark.parametrize("fixture", _load_fixtures(), ids=lambda fx: fx["name"])
def test_integrity_score_matches_fixture(fixture):
    score = _compute_integrity_score(
        events=fixture["events"],
        active_time_seconds=fixture["active_time_seconds"],
        total_time_seconds=fixture["total_time_seconds"],
    )
    assert score == fixture["expected_score"], (
        f"{fixture['name']}: expected {fixture['expected_score']}, got {score}"
    )
