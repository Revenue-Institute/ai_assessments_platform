"""Resend webhook signature verification (spec §14.4).

The endpoint accepts both Svix (current Resend scheme) and the legacy
raw-HMAC `resend-signature` header. These tests pin the four canonical
acceptance / rejection paths."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any

import pytest

from ri_assessments_api.config import get_settings
from ri_assessments_api.routers.webhooks import _verify_resend_signature

# A long-enough secret to satisfy `_MIN_SECRET_LEN`.
SECRET_PLAIN = "x" * 48


@pytest.fixture(autouse=True)
def _set_webhook_secret(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "resend_webhook_secret", SECRET_PLAIN, raising=False)
    monkeypatch.setattr(settings, "app_env", "staging", raising=False)
    yield


def _svix_sig(secret: str, svix_id: str, ts: str, body: bytes) -> str:
    signed_payload = f"{svix_id}.{ts}.".encode("utf-8") + body
    mac = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).digest()
    return "v1," + base64.b64encode(mac).decode("ascii")


def _legacy_sig(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


# -- Valid Svix signature -------------------------------------------------


def test_valid_svix_signature_accepted():
    body = b'{"event":"email.delivered"}'
    svix_id = "msg_test_1"
    ts = str(int(time.time()))
    sig = _svix_sig(SECRET_PLAIN, svix_id, ts, body)
    headers = {
        "svix-id": svix_id,
        "svix-timestamp": ts,
        "svix-signature": sig,
    }
    assert _verify_resend_signature(body, headers) is True


# -- Tampered body --------------------------------------------------------


def test_tampered_body_rejected():
    body = b'{"event":"email.delivered"}'
    svix_id = "msg_test_2"
    ts = str(int(time.time()))
    sig = _svix_sig(SECRET_PLAIN, svix_id, ts, body)
    headers = {
        "svix-id": svix_id,
        "svix-timestamp": ts,
        "svix-signature": sig,
    }
    # The signature was computed against `body`; pass a different body.
    assert _verify_resend_signature(b'{"event":"email.bounced"}', headers) is False


# -- Replay outside the 5-minute window -----------------------------------


def test_replayed_old_timestamp_rejected():
    body = b'{"event":"email.delivered"}'
    svix_id = "msg_test_3"
    # 10 minutes ago: well outside Svix's 5-minute tolerance.
    ts = str(int(time.time()) - 60 * 10)
    sig = _svix_sig(SECRET_PLAIN, svix_id, ts, body)
    headers = {
        "svix-id": svix_id,
        "svix-timestamp": ts,
        "svix-signature": sig,
    }
    assert _verify_resend_signature(body, headers) is False


# -- Multi-version signature header: any valid match wins -----------------


def test_multi_version_signature_any_match_wins():
    body = b'{"event":"email.delivered"}'
    svix_id = "msg_test_4"
    ts = str(int(time.time()))
    good = _svix_sig(SECRET_PLAIN, svix_id, ts, body)
    # The header form is space-separated; "bad" entry first, "good" second.
    headers = {
        "svix-id": svix_id,
        "svix-timestamp": ts,
        "svix-signature": "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= " + good,
    }
    assert _verify_resend_signature(body, headers) is True


# -- Legacy raw-HMAC fallback ---------------------------------------------


def test_legacy_resend_signature_accepted():
    body = b'{"event":"email.delivered"}'
    sig = _legacy_sig(SECRET_PLAIN, body)
    headers = {"resend-signature": sig}
    assert _verify_resend_signature(body, headers) is True


def test_legacy_resend_signature_wrong_value_rejected():
    body = b'{"event":"email.delivered"}'
    headers = {"resend-signature": "00" * 32}
    assert _verify_resend_signature(body, headers) is False


def test_no_headers_no_secret_local_only(monkeypatch):
    """When no secret is configured we accept iff app_env == 'local'."""
    settings = get_settings()
    monkeypatch.setattr(settings, "resend_webhook_secret", "", raising=False)
    monkeypatch.setattr(settings, "app_env", "production", raising=False)
    assert _verify_resend_signature(b"{}", {}) is False
    monkeypatch.setattr(settings, "app_env", "local", raising=False)
    assert _verify_resend_signature(b"{}", {}) is True
