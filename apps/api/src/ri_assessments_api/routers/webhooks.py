"""Inbound webhooks (spec §14.4).

- POST /webhooks/resend: delivery/bounce/complaint signals from Resend.
  Verifies Svix-style signing (newer Resend scheme) and falls back to
  the legacy raw-HMAC `resend-signature` for compatibility. Records the
  event on the assignment row's metadata so admins can see why a
  magic-link email never arrived. The assignment is preferred-matched
  by the `message_id` captured at send time (persisted in
  `assignments.metadata.message_id`); we only fall back to "latest by
  subject email" when the payload does not carry an id we know.
- POST /webhooks/scoring-complete: optional callback used when scoring
  is moved to a background worker (BullMQ in v2). Records the timestamp
  so the admin UI can stop showing the "scoring..." state.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from supabase import Client

from ..config import get_settings
from ..db import get_supabase

router = APIRouter(tags=["webhooks"])
log = logging.getLogger(__name__)

# Svix's replay window. Resend follows the canonical 5-minute clock skew
# tolerance documented at https://docs.svix.com/receiving/verifying-payloads.
_SVIX_TOLERANCE_SECONDS = 5 * 60


def _decode_resend_secret(secret: str) -> bytes:
    """Resend's signing secrets look like `whsec_<base64>`. Older HMAC
    deployments used the raw string. We accept both: strip the prefix +
    base64-decode when present, otherwise treat as utf-8 bytes."""

    if secret.startswith("whsec_"):
        body = secret[len("whsec_"):]
        try:
            return base64.b64decode(body)
        except (ValueError, base64.binascii.Error):
            return secret.encode("utf-8")
    return secret.encode("utf-8")


def _verify_resend_signature(
    raw_body: bytes, headers: dict[str, str]
) -> bool:
    """Verify the inbound Resend webhook signature.

    Order of preference:
    1. Svix headers (`svix-id`, `svix-timestamp`, `svix-signature`).
       Canonical signed payload is `{id}.{timestamp}.{raw_body}` per
       https://docs.svix.com/receiving/verifying-payloads. The signature
       header is space-separated `v1,<base64>` entries; any match wins.
       Reject when the timestamp is outside the 5 minute tolerance to
       prevent replay.
    2. Legacy raw-HMAC `resend-signature` (sha256 hex over the body).
    3. Local-env bypass when no secret is configured (so first-boot
       contributors are not blocked).

    Fails closed in any non-local environment when no recognized header
    set matches.
    """

    settings = get_settings()
    secret = settings.resend_webhook_secret
    if not secret:
        # Fail-closed in any non-local environment so a missing env var in
        # staging / production cannot silently accept unsigned webhooks.
        return settings.app_env == "local"

    svix_id = headers.get("svix-id")
    svix_ts = headers.get("svix-timestamp")
    svix_sig = headers.get("svix-signature")

    if svix_id and svix_ts and svix_sig:
        # Replay protection.
        try:
            sent_at = int(svix_ts)
        except (TypeError, ValueError):
            return False
        if abs(time.time() - sent_at) > _SVIX_TOLERANCE_SECONDS:
            return False

        secret_bytes = _decode_resend_secret(secret)
        signed_payload = (
            f"{svix_id}.{svix_ts}.".encode() + raw_body
        )
        expected = base64.b64encode(
            hmac.new(secret_bytes, signed_payload, hashlib.sha256).digest()
        ).decode("ascii")

        # Header form: "v1,<sig1> v1,<sig2> ..." space-separated.
        for entry in svix_sig.split(" "):
            entry = entry.strip()
            if not entry:
                continue
            if "," not in entry:
                continue
            version, value = entry.split(",", 1)
            if version != "v1":
                continue
            if hmac.compare_digest(value, expected):
                return True
        return False

    # Legacy raw-HMAC fallback. Resend's pre-Svix scheme.
    legacy = headers.get("resend-signature")
    if legacy:
        expected = hmac.new(
            secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, legacy)

    return False


def _normalize_headers(request: Request) -> dict[str, str]:
    return {k.lower(): v for k, v in request.headers.items()}


def _extract_resend_email_id(data: dict[str, Any]) -> str | None:
    """Resend wraps the actual email payload under `data`. Newer events
    expose `email_id`; older shapes use `id`. We accept either."""

    raw = data.get("email_id") or data.get("id")
    return str(raw) if isinstance(raw, (str, int)) and raw else None


@router.post("/webhooks/resend")
async def resend_webhook(
    request: Request,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> dict[str, Any]:
    raw = await request.body()
    headers = _normalize_headers(request)
    if not _verify_resend_signature(raw, headers):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )

    payload = await request.json()
    event_type = payload.get("type") or payload.get("event")
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    message_id = _extract_resend_email_id(data)
    assignment_id: str | None = None
    existing_meta: dict[str, Any] = {}

    # Prefer message_id join when available; precise per-send mapping
    # captured by services/admin.py at send time.
    if message_id:
        res = (
            supabase.table("assignments")
            .select("id, metadata")
            .filter("metadata->>message_id", "eq", message_id)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if rows:
            assignment_id = rows[0]["id"]
            existing_meta = rows[0].get("metadata") or {}

    if not assignment_id:
        to_field = data.get("to")
        recipient = (
            to_field[0]
            if isinstance(to_field, list) and to_field
            else (to_field if isinstance(to_field, str) else None)
        )
        if not recipient:
            return {"ok": True, "stored": False}

        # Find the latest assignment for this email.
        subj_res = (
            supabase.table("subjects")
            .select("id")
            .eq("email", recipient)
            .limit(1)
            .execute()
        )
        subj_rows = subj_res.data or []
        if not subj_rows:
            return {"ok": True, "stored": False}
        subject_id = subj_rows[0]["id"]

        assn = (
            supabase.table("assignments")
            .select("id, metadata")
            .eq("subject_id", subject_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not assn.data:
            return {"ok": True, "stored": False}
        assignment_id = assn.data[0]["id"]
        existing_meta = assn.data[0].get("metadata") or {}

    delivery_log = list(existing_meta.get("email_delivery") or [])
    delivery_log.append(
        {
            "type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "message_id": message_id,
            "raw": data,
        }
    )
    new_meta = {**existing_meta, "email_delivery": delivery_log[-50:]}
    supabase.table("assignments").update({"metadata": new_meta}).eq(
        "id", assignment_id
    ).execute()
    return {
        "ok": True,
        "stored": True,
        "assignment_id": assignment_id,
        "matched_by": "message_id" if message_id else "recipient",
    }


@router.post("/webhooks/scoring-complete")
async def scoring_complete_webhook(
    request: Request,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> dict[str, Any]:
    """Internal callback from a background scoring worker. The worker is
    responsible for HMAC-signing the body with `n8n_webhook_secret`
    (reused as the shared secret for cross-service callbacks). The
    endpoint fails closed in any non-local environment so a misconfigured
    deployment cannot silently accept unsigned mutations."""

    raw = await request.body()
    sig = request.headers.get("x-ri-signature")
    settings = get_settings()
    secret = settings.n8n_webhook_secret
    if secret:
        if not sig:
            raise HTTPException(status_code=401, detail="Signature missing.")
        expected = hmac.new(
            secret.encode("utf-8"), raw, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise HTTPException(
                status_code=401, detail="Invalid signature."
            )
    elif settings.app_env != "local":
        raise HTTPException(
            status_code=503,
            detail="N8N_WEBHOOK_SECRET is not configured.",
        )

    payload = await request.json()
    assignment_id = payload.get("assignment_id")
    if not isinstance(assignment_id, str) or not assignment_id:
        raise HTTPException(
            status_code=400, detail="assignment_id is required."
        )

    supabase.table("assignments").update(
        {"scored_at": datetime.now(UTC).isoformat()}
    ).eq("id", assignment_id).execute()

    # Fan out to the SSE channel so any admin watching the assignment
    # detail page sees the score flip without polling.
    from ..services import queue as queue_service

    queue_service.publish_scoring_event(
        {"type": "scoring_completed", "assignment_id": assignment_id}
    )
    return {"ok": True}
