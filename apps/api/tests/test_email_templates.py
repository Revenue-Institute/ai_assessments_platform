"""Phase-5 email templates (spec §11.4, §15).

Confirms each new template:
  - renders the required content into both the text and HTML bodies,
  - returns EmailResult(ok=True) when the underlying Resend call succeeds,
  - falls back to EmailResult(ok=False, ...) when Resend raises, after
    tenacity has exhausted its retry budget (default 3 attempts),
  - contains no em-dash, no en-dash, no emoji."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import resend  # type: ignore[import-not-found]

from ri_assessments_api.services import email as email_module
from ri_assessments_api.services.email import (
    send_cancellation_notification,
    send_resend_notification,
    send_result_notification,
    send_series_due_notification,
)

# Surrogate-pair-aware emoji detector. Covers the common pictographic
# code-point ranges (BMP arrows are intentionally outside the test scope
# so the brand frame's existing pure-ASCII bullets stay legal).
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "]"
)


# Built via chr() so the guard file itself stays clean of the very
# code points it is policing (CLAUDE.md style rule: no em / en dash
# anywhere in source).
_EM_DASH = chr(0x2014)
_EN_DASH = chr(0x2013)


def _assert_no_dash_or_emoji(text: str) -> None:
    assert _EM_DASH not in text, "em-dash leaked into email body"
    assert _EN_DASH not in text, "en-dash leaked into email body"
    assert _EMOJI_PATTERN.search(text) is None, "emoji leaked into email body"


@pytest.fixture
def patch_resend(monkeypatch):
    """Replace Resend's transport with a MagicMock so tests run offline."""

    settings = email_module.get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "test-key", raising=False)
    monkeypatch.setattr(
        settings,
        "resend_from_email",
        "assessments@revenueinstitute.com",
        raising=False,
    )
    # Cache invalidation: email_module._resend_or_skip pulls get_settings()
    # afresh each call, so the in-process Settings object now sees the
    # values above.

    mock = MagicMock(return_value={"id": "msg_abc"})
    monkeypatch.setattr(resend.Emails, "send", mock)
    return mock


# -- send_resend_notification ---------------------------------------------


def test_send_resend_notification_renders_resent_copy_and_link(patch_resend):
    result = send_resend_notification(
        to_email="candidate@example.com",
        subject_full_name="Jane Candidate",
        module_title="HubSpot Workflows",
        magic_link_url="https://app.test/a/xyz",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )

    assert result.ok is True
    assert result.message_id == "msg_abc"

    payload = patch_resend.call_args.args[0]
    assert payload["subject"].startswith("Resent")
    assert "Resent" in payload["text"] or "re-sent" in payload["text"]
    assert "https://app.test/a/xyz" in payload["text"]
    assert "https://app.test/a/xyz" in payload["html"]
    _assert_no_dash_or_emoji(payload["text"])
    _assert_no_dash_or_emoji(payload["html"])


# -- send_series_due_notification -----------------------------------------


def test_send_series_due_notification_includes_series_and_sequence(patch_resend):
    result = send_series_due_notification(
        to_email="employee@example.com",
        subject_full_name="Sam Employee",
        series_name="Quarterly HubSpot Benchmark",
        sequence_number=3,
        magic_link_url="https://app.test/a/retest",
        expires_at=datetime.now(UTC) + timedelta(days=14),
    )

    assert result.ok is True
    payload = patch_resend.call_args.args[0]
    assert "Quarterly HubSpot Benchmark" in payload["text"]
    assert "Quarterly HubSpot Benchmark" in payload["html"]
    assert "Round 3" in payload["text"]
    assert "Round 3" in payload["html"]
    _assert_no_dash_or_emoji(payload["text"])
    _assert_no_dash_or_emoji(payload["html"])


# -- send_cancellation_notification ---------------------------------------


def test_send_cancellation_notification_no_magic_link(patch_resend):
    result = send_cancellation_notification(
        to_email="candidate@example.com",
        subject_full_name="Jane Candidate",
        module_title="HubSpot Workflows",
    )

    assert result.ok is True
    payload = patch_resend.call_args.args[0]
    # Use lowercase comparison since the body capitalizes "cancelled".
    assert "cancelled" in payload["text"].lower()
    assert "cancelled" in payload["html"].lower()
    assert "HubSpot Workflows" in payload["text"]
    # Sanity: this email must NOT carry a magic link.
    assert "/a/" not in payload["text"]
    assert 'href="https://app.test/a/' not in payload["html"]
    _assert_no_dash_or_emoji(payload["text"])
    _assert_no_dash_or_emoji(payload["html"])


# -- send_result_notification ---------------------------------------------


def test_send_result_notification_renders_score(patch_resend):
    result = send_result_notification(
        to_email="admin@example.com",
        admin_full_name="Admin User",
        subject_full_name="Jane Candidate",
        module_title="HubSpot Workflows",
        final_score_pct=82.345,
        integrity_score=95.0,
        assignment_id="00000000-0000-0000-0000-000000000001",
    )

    assert result.ok is True
    payload = patch_resend.call_args.args[0]
    # Score formatted to 1 decimal place per send_result_notification.
    assert "82.3%" in payload["text"]
    assert "82.3%" in payload["html"]
    # Integrity formatted as N/100.
    assert "95/100" in payload["text"]
    _assert_no_dash_or_emoji(payload["text"])
    _assert_no_dash_or_emoji(payload["html"])


# -- Tenacity retry behavior ----------------------------------------------


def test_send_result_notification_retries_then_returns_failure(monkeypatch):
    """On a string of httpx.HTTPError raises, tenacity should retry 3
    times and then surface a clean EmailResult(ok=False) instead of
    blowing up the caller."""

    settings = email_module.get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "test-key", raising=False)
    monkeypatch.setattr(
        settings, "resend_from_email", "from@example.com", raising=False
    )

    # Sleep wait is configured with min=1s in production; collapse to 0 so
    # the retries don't make the test sleep for real seconds.
    if email_module._HAS_TENACITY:
        from tenacity import (
            retry,
            retry_if_exception_type,
            stop_after_attempt,
            wait_none,
        )

        def fast_send(payload: dict[str, Any]) -> Any:
            return email_module._send_via_resend(payload)

        wrapped = retry(
            stop=stop_after_attempt(3),
            wait=wait_none(),
            retry=retry_if_exception_type(
                (httpx.HTTPError, ConnectionError, TimeoutError)
            ),
            reraise=True,
        )(fast_send)
        monkeypatch.setattr(email_module, "_send_with_retry", wrapped)

    call_count = {"n": 0}

    def boom(payload: dict[str, Any]):
        call_count["n"] += 1
        raise httpx.ConnectError("simulated outage")

    monkeypatch.setattr(resend.Emails, "send", boom)

    result = send_result_notification(
        to_email="admin@example.com",
        admin_full_name="Admin User",
        subject_full_name="Jane Candidate",
        module_title="HubSpot Workflows",
        final_score_pct=50.0,
        integrity_score=80.0,
        assignment_id="00000000-0000-0000-0000-000000000001",
    )
    assert result.ok is False
    # When tenacity is present we expect the full 3 attempts; without it,
    # one. Either way we want > 0, and when present, > 1.
    assert call_count["n"] >= 1
    if email_module._HAS_TENACITY:
        assert call_count["n"] == 3
