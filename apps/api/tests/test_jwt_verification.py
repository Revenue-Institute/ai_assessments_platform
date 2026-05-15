"""Magic-link token security (spec §13, §14.2, §18).

`get_assignment_for_token` is the single chokepoint every candidate /
runner endpoint funnels through. These tests pin down the four ways a
token may be rejected (bad signature, wrong audience, expired, mismatched
assignment_id claim) and confirm the happy path still resolves."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from jose import jwt

from ri_assessments_api.auth import (
    ALGORITHM,
    CANDIDATE_TOKEN_AUDIENCE,
    issue_candidate_token,
)
from ri_assessments_api.config import get_settings
from ri_assessments_api.services.attempts import get_assignment_for_token
from ri_assessments_api.services.tokens import hash_token

from .conftest import MockSupabase


# -- Fixtures --------------------------------------------------------------


@pytest.fixture
def assignment_id() -> str:
    return "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def subject_id() -> str:
    return "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def valid_token(assignment_id: str, subject_id: str) -> str:
    return issue_candidate_token(
        assignment_id=assignment_id,
        subject_id=subject_id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def _seed_assignment(mock: MockSupabase, token: str, assignment_id: str) -> None:
    """Register a single assignment row keyed by the token hash, so the
    `select(...).eq("token_hash", hash_token(...))` returns the row."""

    mock.queue(
        ("assignments", "select"),
        [
            {
                "id": assignment_id,
                "status": "in_progress",
                "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "started_at": datetime.now(UTC).isoformat(),
                "completed_at": None,
                "random_seed": 7,
                "module_snapshot": {"questions": []},
                "metadata": {},
            }
        ],
    )


# -- Happy path ------------------------------------------------------------


def test_valid_token_resolves_assignment(valid_token, assignment_id):
    mock = MockSupabase()
    _seed_assignment(mock, valid_token, assignment_id)

    row = get_assignment_for_token(mock, valid_token)
    assert row["id"] == assignment_id

    # The select must have been filtered by the SHA-256 hash of the token.
    capture = mock.calls_for("assignments", "select")[0]
    assert ("eq", ("token_hash", hash_token(valid_token))) in capture.filters


# -- Tampered signature ----------------------------------------------------


def test_tampered_signature_rejected(valid_token, assignment_id):
    mock = MockSupabase()
    _seed_assignment(mock, valid_token, assignment_id)

    # Flip the last character of the signature segment; this corrupts the
    # MAC without altering the visible payload.
    header, payload, sig = valid_token.split(".")
    flipped = sig[:-1] + ("A" if sig[-1] != "A" else "B")
    tampered = ".".join([header, payload, flipped])

    with pytest.raises(HTTPException) as exc:
        get_assignment_for_token(mock, tampered)
    assert exc.value.status_code == 401


# -- Wrong audience --------------------------------------------------------


def test_wrong_audience_rejected(assignment_id, subject_id):
    mock = MockSupabase()
    _seed_assignment(mock, "ignored", assignment_id)

    settings = get_settings()
    bad_aud = jwt.encode(
        {
            "sub": subject_id,
            "assignment_id": assignment_id,
            "aud": "some-other-audience",
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
        settings.jwt_signing_secret,
        algorithm=ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc:
        get_assignment_for_token(mock, bad_aud)
    assert exc.value.status_code == 401


# -- Expired exp -----------------------------------------------------------


def test_expired_token_rejected(assignment_id, subject_id):
    mock = MockSupabase()
    _seed_assignment(mock, "ignored", assignment_id)

    expired = issue_candidate_token(
        assignment_id=assignment_id,
        subject_id=subject_id,
        expires_at=datetime.now(UTC) - timedelta(seconds=5),
    )

    with pytest.raises(HTTPException) as exc:
        get_assignment_for_token(mock, expired)
    assert exc.value.status_code == 401


# -- Claim mismatch --------------------------------------------------------


def test_assignment_id_claim_mismatch_rejected(subject_id):
    """If the JWT's `assignment_id` claim disagrees with the row resolved
    by token_hash, refuse the request even though the row exists. Defense
    in depth against a leaked token_hash being paired with a re-signed
    JWT pointing at another assignment."""

    mock = MockSupabase()
    real_assignment_id = "33333333-3333-3333-3333-333333333333"
    claim_assignment_id = "44444444-4444-4444-4444-444444444444"
    mock.queue(
        ("assignments", "select"),
        [
            {
                "id": real_assignment_id,
                "status": "in_progress",
                "expires_at": (
                    datetime.now(UTC) + timedelta(days=1)
                ).isoformat(),
                "started_at": datetime.now(UTC).isoformat(),
                "completed_at": None,
                "random_seed": 7,
                "module_snapshot": {"questions": []},
                "metadata": {},
            }
        ],
    )

    token = issue_candidate_token(
        assignment_id=claim_assignment_id,
        subject_id=subject_id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    with pytest.raises(HTTPException) as exc:
        get_assignment_for_token(mock, token)
    assert exc.value.status_code == 401


# -- Token missing assignment_id claim ------------------------------------


def test_missing_assignment_id_claim_rejected(subject_id):
    settings = get_settings()
    no_assign = jwt.encode(
        {
            "sub": subject_id,
            "aud": CANDIDATE_TOKEN_AUDIENCE,
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
        settings.jwt_signing_secret,
        algorithm=ALGORITHM,
    )
    mock = MockSupabase()
    with pytest.raises(HTTPException) as exc:
        get_assignment_for_token(mock, no_assign)
    assert exc.value.status_code == 401
