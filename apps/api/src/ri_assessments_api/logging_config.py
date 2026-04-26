"""PII-scrubbing log configuration (spec §11.3).

We expose `install_pii_filter()` which mounts a logging.Filter on the root
logger that masks email addresses, phone numbers, candidate magic-link
tokens, and credit-card-shaped strings before any record is emitted.

The filter applies to both `record.msg` and any string args, so f-strings
*and* % formatting are covered. Bound integers, floats, and dataclasses
pass through unchanged.

Why a filter rather than per-call sanitization? Because we have ~30
log sites and adding a sanitize call to each one would rot. A filter at
the root makes the policy enforceable centrally and immune to drift.
"""

from __future__ import annotations

import logging
import re

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)
PHONE_RE = re.compile(
    r"(?:(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})(?!\d)"
)
# Candidate magic-link tokens are JWTs; mask anything that looks like a JWT.
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")
# 13-19 digit credit-card-ish runs (with optional separators).
CC_RE = re.compile(r"(?<!\d)(?:\d[ \-]?){13,19}(?!\d)")


def _scrub(text: str) -> str:
    text = EMAIL_RE.sub("<email>", text)
    text = JWT_RE.sub("<jwt>", text)
    text = PHONE_RE.sub("<phone>", text)
    text = CC_RE.sub("<cc>", text)
    return text


class PIIScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _scrub(record.msg)
        if record.args:
            scrubbed_args: list[object] = []
            for arg in record.args if isinstance(record.args, tuple) else (record.args,):
                if isinstance(arg, str):
                    scrubbed_args.append(_scrub(arg))
                else:
                    scrubbed_args.append(arg)
            record.args = (
                tuple(scrubbed_args)
                if isinstance(record.args, tuple)
                else scrubbed_args[0]
            )
        return True


def install_pii_filter() -> None:
    """Attach the filter to the root logger and to known noisy children
    (uvicorn/httpx/anthropic) so their access-log lines also get scrubbed."""

    pii = PIIScrubFilter()
    for name in ("", "uvicorn", "uvicorn.access", "httpx", "anthropic"):
        logging.getLogger(name).addFilter(pii)
