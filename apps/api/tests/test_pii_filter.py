"""Spec §11.3 PII scrubbing — verify the log filter masks email, phone,
JWTs, and credit-card-shaped strings before records are emitted."""

from __future__ import annotations

import logging

from ri_assessments_api.logging_config import PIIScrubFilter


def _make_record(msg: str, args: tuple = ()) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )
    return record


def test_email_is_scrubbed() -> None:
    f = PIIScrubFilter()
    record = _make_record("login from candidate@example.com worked")
    f.filter(record)
    assert "candidate@example.com" not in record.getMessage()
    assert "<email>" in record.getMessage()


def test_phone_is_scrubbed() -> None:
    f = PIIScrubFilter()
    record = _make_record("called +1 (415) 555-0142")
    f.filter(record)
    assert "<phone>" in record.getMessage()


def test_jwt_is_scrubbed() -> None:
    f = PIIScrubFilter()
    fake_jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.abcdef1234"
    record = _make_record(f"token={fake_jwt}")
    f.filter(record)
    assert fake_jwt not in record.getMessage()
    assert "<jwt>" in record.getMessage()


def test_credit_card_is_scrubbed() -> None:
    f = PIIScrubFilter()
    record = _make_record("card 4111-1111-1111-1111 charged")
    f.filter(record)
    assert "<cc>" in record.getMessage()


def test_args_are_scrubbed() -> None:
    f = PIIScrubFilter()
    record = _make_record("user %s opened module", args=("a@b.co",))
    f.filter(record)
    assert "<email>" in record.getMessage()
