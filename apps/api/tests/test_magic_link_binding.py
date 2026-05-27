"""Tests for the magic-link consumption binding (migration 0019).

The binding stamps `consumed_at` / `consumed_user_agent` /
`consumed_ip_hash` on the assignments row at first consent. Subsequent
calls must match at least one of (user_agent, ip_hash) or the service
returns 409. This is the load-bearing defense against a leaked magic
link being replayed from a second device.

The test exercises the service layer directly via the MockSupabase
fixture; it deliberately does not spin up the FastAPI router because
the binding contract lives in `services.assignments.record_consent`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import HTTPException

from ri_assessments_api.auth import issue_candidate_token
from ri_assessments_api.services import assignments as svc
from ri_assessments_api.services.tokens import hash_token

from .conftest import MockSupabase


def _seed_pending_assignment(
    mock: MockSupabase,
    *,
    consumed_at: str | None = None,
    consumed_ua: str | None = None,
    consumed_ip: str | None = None,
) -> tuple[str, str]:
    """Set up a single pending assignment + the matching subject row.
    Returns (raw_token, assignment_id)."""

    assignment_id = "a-bind-1"
    subject_id = "s-1"
    expires_at = datetime.now(UTC) + timedelta(days=7)
    raw_token = issue_candidate_token(
        assignment_id=assignment_id,
        subject_id=subject_id,
        expires_at=expires_at,
    )
    snapshot = {
        "title": "Test Module",
        "description": "",
        "target_duration_minutes": 30,
        "questions": [],
    }
    row: dict[str, Any] = {
        "id": assignment_id,
        "status": "pending",
        "expires_at": expires_at.isoformat(),
        "started_at": None,
        "consent_at": None,
        "module_snapshot": snapshot,
        "assessment_snapshot": None,
        "subject_id": subject_id,
        "consumed_at": consumed_at,
        "consumed_user_agent": consumed_ua,
        "consumed_ip_hash": consumed_ip,
        "token_hash": hash_token(raw_token),
    }
    # resolve_token's read of the assignment.
    mock.queue(("assignments", "select"), [row])
    mock.queue(("subjects", "select"), [{"full_name": "Cand", "type": "candidate"}])
    # record_consent's raw fingerprint re-read.
    mock.queue(
        ("assignments", "select"),
        [
            {
                "id": assignment_id,
                "consumed_at": consumed_at,
                "consumed_user_agent": consumed_ua,
                "consumed_ip_hash": consumed_ip,
            }
        ],
    )
    return raw_token, assignment_id


def test_first_consent_stamps_fingerprint():
    mock = MockSupabase()
    token, assignment_id = _seed_pending_assignment(mock)

    result = svc.record_consent(
        mock,
        token,
        ip_hash="ip-aaaa",
        user_agent="Mozilla/Browser-A",
    )

    assert result.assignment_id == assignment_id
    assert result.status == "in_progress"

    updates = mock.calls_for("assignments", "update")
    assert updates, "expected an update on first consent"
    payload = updates[-1].payload
    assert payload["status"] == "in_progress"
    assert payload["consumed_at"] is not None
    assert payload["consumed_user_agent"] == "Mozilla/Browser-A"
    assert payload["consumed_ip_hash"] == "ip-aaaa"


def test_second_consent_same_ua_passes():
    """Same browser, IP rotated (mobile network switch): admit."""

    mock = MockSupabase()
    token, _ = _seed_pending_assignment(
        mock,
        consumed_at="2026-05-27T00:00:00+00:00",
        consumed_ua="Mozilla/Browser-A",
        consumed_ip="ip-aaaa",
    )
    # Pending status means record_consent flips to in_progress; for this
    # test we want the "already in_progress, just re-confirm" path.
    # Trick: feed the same row twice, but the second resolve_token call
    # sees status=in_progress with started_at set.
    # The MockSupabase queue is already primed; we just need the
    # service to dispatch through it. record_consent reads twice
    # internally (resolve_token + the binding fingerprint re-read);
    # both are queued by _seed_pending_assignment.
    result = svc.record_consent(
        mock,
        token,
        ip_hash="ip-bbbb-different-network",
        user_agent="Mozilla/Browser-A",
    )
    assert result.status == "in_progress"


def test_second_consent_same_ip_passes():
    """Same network, UA stripped (privacy extension): admit."""

    mock = MockSupabase()
    token, _ = _seed_pending_assignment(
        mock,
        consumed_at="2026-05-27T00:00:00+00:00",
        consumed_ua="Mozilla/Browser-A",
        consumed_ip="ip-aaaa",
    )
    result = svc.record_consent(
        mock,
        token,
        ip_hash="ip-aaaa",
        user_agent=None,
    )
    assert result.status == "in_progress"


def test_second_consent_both_differ_rejected_409():
    """Different UA AND different IP: this is the replay-from-another-
    device shape. Reject with 409."""

    mock = MockSupabase()
    token, _ = _seed_pending_assignment(
        mock,
        consumed_at="2026-05-27T00:00:00+00:00",
        consumed_ua="Mozilla/Browser-A",
        consumed_ip="ip-aaaa",
    )
    with pytest.raises(HTTPException) as exc:
        svc.record_consent(
            mock,
            token,
            ip_hash="ip-attacker",
            user_agent="curl/8.0",
        )
    assert exc.value.status_code == 409
    assert "different device" in exc.value.detail


def test_already_consumed_with_no_request_fingerprint_rejects():
    """A request with neither UA nor IP can never match a stored
    fingerprint. Must 409 rather than fail-open."""

    mock = MockSupabase()
    token, _ = _seed_pending_assignment(
        mock,
        consumed_at="2026-05-27T00:00:00+00:00",
        consumed_ua="Mozilla/Browser-A",
        consumed_ip="ip-aaaa",
    )
    with pytest.raises(HTTPException) as exc:
        svc.record_consent(mock, token, ip_hash=None, user_agent=None)
    assert exc.value.status_code == 409


def test_client_binding_matches_helper_directly():
    """Direct coverage of the matcher so future regressions show the
    bug at the helper layer rather than buried in record_consent."""

    row = {
        "consumed_user_agent": "Mozilla/X",
        "consumed_ip_hash": "ip-1",
    }
    # both match
    assert svc._client_binding_matches(row, ip_hash="ip-1", user_agent="Mozilla/X")
    # ua match, ip drift
    assert svc._client_binding_matches(row, ip_hash="ip-2", user_agent="Mozilla/X")
    # ip match, ua drift
    assert svc._client_binding_matches(row, ip_hash="ip-1", user_agent="curl")
    # both differ
    assert not svc._client_binding_matches(
        row, ip_hash="ip-2", user_agent="curl"
    )
    # one side missing on request
    assert svc._client_binding_matches(row, ip_hash="ip-1", user_agent=None)
    assert not svc._client_binding_matches(row, ip_hash=None, user_agent=None)
    # missing stored side: never matches
    empty = {"consumed_user_agent": None, "consumed_ip_hash": None}
    assert not svc._client_binding_matches(
        empty, ip_hash="ip-1", user_agent="Mozilla/X"
    )
