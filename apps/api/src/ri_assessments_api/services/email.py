"""Resend email delivery (spec §15).

Fails soft when RESEND_API_KEY is unset, callers get back ok=False and
log the reason. The candidate flow still works without email; admins
just have to copy the magic-link URL out of the create-assignment
response themselves."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class EmailResult:
    ok: bool
    message_id: str | None
    detail: str


def _resend_or_skip() -> tuple[Any | None, str]:
    settings = get_settings()
    if not settings.resend_api_key:
        return None, "RESEND_API_KEY missing"
    if not settings.resend_from_email:
        return None, "RESEND_FROM_EMAIL missing"
    try:
        import resend  # type: ignore[import-not-found]
    except ImportError:
        return None, "resend package not installed"
    resend.api_key = settings.resend_api_key
    return resend, ""


def _format_dt(value: datetime) -> str:
    # Plain-English-ish UTC; we deliberately don't localize since admin
    # email lists span time zones.
    return value.strftime("%Y-%m-%d %H:%M UTC")


def send_magic_link(
    *,
    to_email: str,
    subject_full_name: str,
    module_title: str,
    magic_link_url: str,
    expires_at: datetime,
) -> EmailResult:
    resend, reason = _resend_or_skip()
    if resend is None:
        return EmailResult(ok=False, message_id=None, detail=reason)

    settings = get_settings()
    subject = f"Your Revenue Institute assessment: {module_title}"
    text_body = (
        f"Hi {subject_full_name},\n\n"
        f"You've been assigned the {module_title} assessment by Revenue Institute.\n\n"
        f"Open the link below to begin. The link expires {_format_dt(expires_at)}:\n\n"
        f"{magic_link_url}\n\n"
        "Notes:\n"
        " - Plan a quiet block of time. The assessment is timed and runs in fullscreen.\n"
        " - Tab focus, copy/paste outside the editor, and similar events are logged.\n"
        " - Your raw answers are stored permanently. AI scores them against a rubric and a "
        "human reviewer may re-score before final results are issued.\n\n"
        "If you did not expect this email, ignore it.\n"
    )
    html_body = (
        f"<p>Hi {_escape(subject_full_name)},</p>"
        f"<p>You've been assigned the <strong>{_escape(module_title)}</strong> "
        "assessment by Revenue Institute.</p>"
        f'<p><a href="{magic_link_url}" style="background:#10b981;color:#022c22;'
        'padding:10px 16px;border-radius:6px;text-decoration:none;display:inline-block;">'
        "Begin assessment</a></p>"
        f"<p>This link expires <strong>{_format_dt(expires_at)}</strong>.</p>"
        "<p>Notes:</p><ul>"
        "<li>Plan a quiet block of time. The assessment is timed and runs in fullscreen.</li>"
        "<li>Tab focus, copy/paste outside the editor, and similar events are logged.</li>"
        "<li>Raw answers are stored permanently. AI scores them against a rubric and a "
        "human reviewer may re-score before final results are issued.</li>"
        "</ul>"
        "<p style=\"color:#6b7280;font-size:12px\">If you did not expect this email, ignore it.</p>"
    )

    try:
        result = resend.Emails.send(
            {
                "from": settings.resend_from_email,
                "to": [to_email],
                "subject": subject,
                "text": text_body,
                "html": html_body,
            }
        )
    except Exception as exc:
        log.exception("resend send_magic_link failed")
        return EmailResult(ok=False, message_id=None, detail=str(exc))

    message_id = (
        result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
    )
    return EmailResult(ok=True, message_id=message_id, detail="sent")


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
