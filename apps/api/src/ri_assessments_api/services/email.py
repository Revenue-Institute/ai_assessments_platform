"""Resend email delivery (spec §11.4, §14.4, §15).

Fails soft when RESEND_API_KEY is unset, callers get back ok=False and
log the reason. The candidate flow still works without email; admins
just have to copy the magic-link URL out of the create-assignment
response themselves.

Hardening (Phase 5):
- Each send is wrapped in tenacity retry with exponential backoff on
  transient network errors (httpx HTTPError, ConnectionError,
  TimeoutError). If tenacity is not installed, we degrade gracefully to
  a single attempt.
- Templates are brand-aligned dark-emerald (Forest Green #0A8F5D on Deep
  Navy #020617) and ship matched text + HTML alternatives.
- No em or en dashes anywhere (CLAUDE.md style rule, enforced in CI).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)


# Brand palette (spec §13.3 dark-emerald). Used inline because Resend
# bodies are not allowed external stylesheets.
BRAND_PRIMARY = "#0A8F5D"  # Forest Green
BRAND_BG = "#020617"       # Deep Navy
BRAND_TEXT = "#E2E8F0"     # Slate-200 on dark
BRAND_MUTED = "#94A3B8"    # Slate-400


# tenacity is listed in pyproject.toml but we guard the import so the
# module still loads in environments where it has not been pinned yet.
try:  # pragma: no cover, exercised by both branches in CI
    from tenacity import (
        RetryError,
        before_sleep_log,
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential,
    )

    _HAS_TENACITY = True
except ImportError:  # pragma: no cover
    _HAS_TENACITY = False


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


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _wrap_html(body_inner: str) -> str:
    """Wrap a section of HTML body content with the brand frame.

    Inline styles only; clients strip <style> blocks. Dark-on-dark
    background with the emerald CTA stands in for revenueinstitute.com.
    """

    return (
        f'<div style="background:{BRAND_BG};padding:32px 0;font-family:'
        '-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,'
        'sans-serif;">'
        f'<div style="max-width:560px;margin:0 auto;background:{BRAND_BG};'
        f'color:{BRAND_TEXT};padding:32px 28px;border:1px solid #0F172A;'
        'border-radius:10px;">'
        f'<div style="font-size:18px;font-weight:600;color:{BRAND_PRIMARY};'
        'margin-bottom:18px;letter-spacing:0.3px;">Revenue Institute</div>'
        f"{body_inner}"
        f'<p style="color:{BRAND_MUTED};font-size:12px;margin-top:32px;">'
        "If you did not expect this email, you can ignore it.</p>"
        "</div></div>"
    )


def _cta_button(label: str, url: str) -> str:
    return (
        f'<p style="margin:22px 0;"><a href="{url}" '
        f'style="background:{BRAND_PRIMARY};color:#031b12;padding:12px 22px;'
        'border-radius:6px;text-decoration:none;display:inline-block;'
        f'font-weight:600;">{label}</a></p>'
    )


def _send_via_resend(payload: dict[str, Any]) -> Any:
    """Inner send call. Pulled out so tenacity can wrap it.

    Raised exceptions trigger retry; the outer caller converts the final
    failure into an `EmailResult(ok=False, ...)`."""

    resend_mod, reason = _resend_or_skip()
    if resend_mod is None:
        raise RuntimeError(reason)
    return resend_mod.Emails.send(payload)


if _HAS_TENACITY:
    _send_with_retry: Callable[[dict[str, Any]], Any] = retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(
            (httpx.HTTPError, ConnectionError, TimeoutError)
        ),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )(_send_via_resend)
else:  # pragma: no cover, fallback path
    _send_with_retry = _send_via_resend


def _send_email(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str,
    op: str,
) -> EmailResult:
    """Single chokepoint that every template function flows through.

    Returns an EmailResult instead of raising so callers can swallow
    delivery failures without aborting the request. The Resend API
    response's `id` field becomes our `message_id`; we persist it on
    `assignments.metadata.message_id` for webhook reconciliation."""

    resend_mod, reason = _resend_or_skip()
    if resend_mod is None:
        return EmailResult(ok=False, message_id=None, detail=reason)

    settings = get_settings()
    payload: dict[str, Any] = {
        "from": settings.resend_from_email,
        "to": [to_email],
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }
    try:
        result = _send_with_retry(payload)
    except Exception as exc:
        if _HAS_TENACITY and isinstance(exc, RetryError):
            exc = exc.last_attempt.exception() or exc  # type: ignore[assignment]
        log.exception("resend %s failed", op)
        return EmailResult(ok=False, message_id=None, detail=str(exc))

    message_id = (
        result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
    )
    return EmailResult(ok=True, message_id=message_id, detail="sent")


def send_magic_link(
    *,
    to_email: str,
    subject_full_name: str,
    module_title: str,
    magic_link_url: str,
    expires_at: datetime,
) -> EmailResult:
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
    inner = (
        f"<p>Hi {_escape(subject_full_name)},</p>"
        f"<p>You've been assigned the <strong>{_escape(module_title)}</strong> "
        "assessment by Revenue Institute.</p>"
        f"{_cta_button('Begin assessment', magic_link_url)}"
        f"<p>This link expires <strong>{_format_dt(expires_at)}</strong>.</p>"
        "<p>Notes:</p><ul>"
        "<li>Plan a quiet block of time. The assessment is timed and runs in fullscreen.</li>"
        "<li>Tab focus, copy/paste outside the editor, and similar events are logged.</li>"
        "<li>Raw answers are stored permanently. AI scores them against a rubric and a "
        "human reviewer may re-score before final results are issued.</li>"
        "</ul>"
    )
    return _send_email(
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=_wrap_html(inner),
        op="send_magic_link",
    )


def send_resend_notification(
    *,
    to_email: str,
    subject_full_name: str,
    module_title: str,
    magic_link_url: str,
    expires_at: datetime,
) -> EmailResult:
    """Variant of `send_magic_link` for the admin-triggered resend flow.

    Body honestly says the link was reissued and that any prior link no
    longer works. Used by `services/admin.py:resend_assignment_email`."""

    subject = "Resent: Your Revenue Institute assessment link"
    text_body = (
        f"Hi {subject_full_name},\n\n"
        f"We re-sent your link to the {module_title} assessment. Any earlier link "
        "from us no longer works.\n\n"
        f"Open the new link below to begin. It expires {_format_dt(expires_at)}:\n\n"
        f"{magic_link_url}\n\n"
        "If you did not request a resend, you can ignore this email.\n"
    )
    inner = (
        f"<p>Hi {_escape(subject_full_name)},</p>"
        f"<p>We re-sent your link to the <strong>{_escape(module_title)}</strong> "
        "assessment. Any earlier link from us no longer works.</p>"
        f"{_cta_button('Open new link', magic_link_url)}"
        f"<p>This link expires <strong>{_format_dt(expires_at)}</strong>.</p>"
        "<p>If you did not request a resend, you can ignore this email.</p>"
    )
    return _send_email(
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=_wrap_html(inner),
        op="send_resend_notification",
    )


def send_series_due_notification(
    *,
    to_email: str,
    subject_full_name: str,
    series_name: str,
    sequence_number: int,
    magic_link_url: str,
    expires_at: datetime,
) -> EmailResult:
    """Retest cycle invite (spec §11.4). Replaces the generic invite for
    series-issued assignments so the recipient understands this is a
    follow-up round, not a brand-new assessment."""

    subject = (
        f"Your {series_name} retest is ready (Round {sequence_number})"
    )
    text_body = (
        f"Hi {subject_full_name},\n\n"
        f"This is your Round {sequence_number} follow-up for the {series_name} series.\n\n"
        f"Open the link below to begin. It expires {_format_dt(expires_at)}:\n\n"
        f"{magic_link_url}\n\n"
        "Notes:\n"
        " - The questions are randomized variants, so prior answers will not match.\n"
        " - The assessment is timed and runs in fullscreen, same as before.\n"
        " - Raw answers are stored permanently and AI-scored against the rubric.\n\n"
        "If you did not expect this email, ignore it.\n"
    )
    inner = (
        f"<p>Hi {_escape(subject_full_name)},</p>"
        f"<p>This is your <strong>Round {sequence_number}</strong> follow-up for the "
        f"<strong>{_escape(series_name)}</strong> series.</p>"
        f"{_cta_button('Begin retest', magic_link_url)}"
        f"<p>This link expires <strong>{_format_dt(expires_at)}</strong>.</p>"
        "<p>Notes:</p><ul>"
        "<li>The questions are randomized variants, so prior answers will not match.</li>"
        "<li>The assessment is timed and runs in fullscreen, same as before.</li>"
        "<li>Raw answers are stored permanently and AI-scored against the rubric.</li>"
        "</ul>"
    )
    return _send_email(
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=_wrap_html(inner),
        op="send_series_due_notification",
    )


def send_cancellation_notification(
    *,
    to_email: str,
    subject_full_name: str,
    module_title: str,
) -> EmailResult:
    """Tell the candidate the assignment has been cancelled. No magic
    link; the row is now terminal."""

    subject = "Your assessment has been cancelled"
    text_body = (
        f"Hi {subject_full_name},\n\n"
        f"Your {module_title} assessment with Revenue Institute has been cancelled. "
        "You no longer need to take it.\n\n"
        "If you have questions, reply to this email and our team will follow up.\n"
    )
    inner = (
        f"<p>Hi {_escape(subject_full_name)},</p>"
        f"<p>Your <strong>{_escape(module_title)}</strong> assessment with Revenue "
        "Institute has been cancelled. You no longer need to take it.</p>"
        "<p>If you have questions, reply to this email and our team will follow up.</p>"
    )
    return _send_email(
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=_wrap_html(inner),
        op="send_cancellation_notification",
    )


def send_result_notification(
    *,
    to_email: str,
    admin_full_name: str | None,
    subject_full_name: str,
    module_title: str,
    final_score_pct: float | None,
    integrity_score: float | None,
    assignment_id: str,
) -> EmailResult:
    """Admin-internal summary fired when scoring completes (spec §11.4 +
    §9). Sent to the admin who created the assignment. Score and
    integrity are best-effort; either may be None if scoring is still
    running or the worker did not produce an integrity number."""

    settings = get_settings()
    admin_link = (
        f"{settings.next_public_admin_url.rstrip('/')}"
        f"/assignments/{assignment_id}"
    )
    score_text = (
        f"{final_score_pct:.1f}%" if isinstance(final_score_pct, (int, float))
        else "pending"
    )
    integrity_text = (
        f"{integrity_score:.0f}/100"
        if isinstance(integrity_score, (int, float))
        else "pending"
    )
    greeting = admin_full_name or "team"

    subject = f"Scoring complete for {subject_full_name} ({module_title})"
    text_body = (
        f"Hi {greeting},\n\n"
        f"Scoring just completed for {subject_full_name} on the {module_title} assessment.\n\n"
        f"Score: {score_text}\n"
        f"Integrity: {integrity_text}\n\n"
        f"Open the assignment in the admin app:\n{admin_link}\n\n"
        "Per-question rationale and the full integrity event timeline are available "
        "on that page. Rescore is one click away if the rubric needs adjustment.\n"
    )
    inner = (
        f"<p>Hi {_escape(greeting)},</p>"
        f"<p>Scoring just completed for <strong>{_escape(subject_full_name)}</strong> "
        f"on the <strong>{_escape(module_title)}</strong> assessment.</p>"
        '<table cellpadding="0" cellspacing="0" style="margin:18px 0;">'
        f'<tr><td style="padding:6px 16px 6px 0;color:{BRAND_MUTED};">Score</td>'
        f'<td style="padding:6px 0;color:{BRAND_TEXT};font-weight:600;">'
        f"{_escape(score_text)}</td></tr>"
        f'<tr><td style="padding:6px 16px 6px 0;color:{BRAND_MUTED};">Integrity</td>'
        f'<td style="padding:6px 0;color:{BRAND_TEXT};font-weight:600;">'
        f"{_escape(integrity_text)}</td></tr>"
        "</table>"
        f"{_cta_button('Open assignment', admin_link)}"
        "<p>Per-question rationale and the full integrity event timeline are available "
        "on that page. Rescore is one click away if the rubric needs adjustment.</p>"
    )
    return _send_email(
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=_wrap_html(inner),
        op="send_result_notification",
    )
