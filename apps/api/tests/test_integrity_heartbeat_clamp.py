"""Tests for the service-layer integrity heartbeat clamp.

Spec §10.4 + remediation memo 2026-05-26: a malicious candidate that
POSTs `{"focused_seconds_since_last": 999}` once per second should not
inflate active_time_seconds. Two clamps run in series:

  1. The service layer caps the client delta to
     `_HEARTBEAT_MAX_DELTA_SECONDS` (30s) BEFORE the RPC sees it.
  2. The Postgres RPC (migration 0018) re-clamps the delta against
     wall-clock elapsed since `attempts.last_heartbeat_at`.

This file tests layer 1 (Python). Layer 2 lives in the migration and
is covered by integration tests that run against a real Postgres."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from ri_assessments_api.auth import issue_candidate_token
from ri_assessments_api.services import integrity as svc
from ri_assessments_api.services.tokens import hash_token

from .conftest import MockSupabase


def _seed_in_progress(mock: MockSupabase) -> str:
    """Seed an assignment + attempt that record_heartbeat can resolve.
    Returns the raw token."""

    started = datetime.now(UTC) - timedelta(minutes=2)
    expires = datetime.now(UTC) + timedelta(days=1)
    raw_token = issue_candidate_token(
        assignment_id="a-hb-1",
        subject_id="s-1",
        expires_at=expires,
    )
    assignment_row: dict[str, Any] = {
        "id": "a-hb-1",
        "status": "in_progress",
        "expires_at": expires.isoformat(),
        "started_at": started.isoformat(),
        "completed_at": None,
        "random_seed": 0,
        "module_snapshot": {"target_duration_minutes": 60, "questions": []},
        "assessment_snapshot": None,
        "metadata": None,
        "token_hash": hash_token(raw_token),
    }
    # get_assignment_for_token reads once.
    mock.queue(("assignments", "select"), [assignment_row])
    # _current_attempt_id picks the latest attempt for this assignment.
    mock.queue(("attempts", "select"), [{"id": "att-1"}])
    return raw_token


def test_zero_delta_returns_applied_zero():
    mock = MockSupabase()
    token = _seed_in_progress(mock)
    out = svc.record_heartbeat(mock, token, 0.0)
    assert out["applied"] == 0
    assert out["attempt_id"] == "att-1"
    # No RPC call was issued.
    assert all(c.table != "_rpc" for c in mock.captured)


def test_normal_cadence_passes_through(monkeypatch):
    mock = MockSupabase()
    token = _seed_in_progress(mock)

    calls: list[dict[str, Any]] = []

    def fake_rpc(name, params):
        calls.append({"name": name, "params": params})

        class _R:
            data = (params.get("p_delta") or 0)

        class _Builder:
            def execute(self):
                return _R()

        return _Builder()

    monkeypatch.setattr(mock, "rpc", fake_rpc, raising=False)

    out = svc.record_heartbeat(mock, token, 11.0)
    assert out["applied"] == 11
    assert calls[-1]["params"]["p_delta"] == 11


def test_oversize_delta_clamped_to_cap(monkeypatch, caplog):
    """A client claiming 999s in one heartbeat must be clamped to the
    service-layer cap and the over-cadence event logged for ops."""

    mock = MockSupabase()
    token = _seed_in_progress(mock)

    captured_delta: dict[str, int] = {}

    def fake_rpc(name, params):
        captured_delta["p_delta"] = params["p_delta"]

        class _R:
            data = params["p_delta"]

        class _Builder:
            def execute(self):
                return _R()

        return _Builder()

    monkeypatch.setattr(mock, "rpc", fake_rpc, raising=False)

    import logging

    with caplog.at_level(logging.WARNING):
        out = svc.record_heartbeat(mock, token, 999.0)

    assert captured_delta["p_delta"] == svc._HEARTBEAT_MAX_DELTA_SECONDS
    assert out["applied"] == svc._HEARTBEAT_MAX_DELTA_SECONDS
    assert any(
        "over cadence" in record.getMessage() for record in caplog.records
    )


def test_negative_delta_floored_to_zero(monkeypatch):
    mock = MockSupabase()
    token = _seed_in_progress(mock)

    def fake_rpc(name, params):
        pytest.fail("RPC should not be invoked for a zero/negative delta")

    monkeypatch.setattr(mock, "rpc", fake_rpc, raising=False)

    out = svc.record_heartbeat(mock, token, -100.0)
    assert out["applied"] == 0
