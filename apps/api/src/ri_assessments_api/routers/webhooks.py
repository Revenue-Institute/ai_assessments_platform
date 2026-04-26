"""Inbound webhooks (spec §14.4).

- POST /webhooks/resend: delivery/bounce/complaint signals from Resend.
  Records the event on the assignment row's metadata so admins can see
  why a magic-link email never arrived.
- POST /webhooks/scoring-complete: optional callback used when scoring is
  moved to a background worker (BullMQ in v2). Records the timestamp so
  the admin UI can stop showing the "scoring..." state.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from supabase import Client

from ..config import get_settings
from ..db import get_supabase

router = APIRouter(tags=["webhooks"])


def _verify_resend_signature(raw_body: bytes, signature: str | None) -> bool:
    settings = get_settings()
    secret = settings.resend_webhook_secret
    if not secret:
        # Webhook secret not configured: accept (local dev). Production
        # deployments should set RESEND_WEBHOOK_SECRET.
        return True
    if not signature:
        return False
    expected = hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhooks/resend")
async def resend_webhook(
    request: Request,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> dict[str, Any]:
    raw = await request.body()
    sig = request.headers.get("svix-signature") or request.headers.get(
        "resend-signature"
    )
    if not _verify_resend_signature(raw, sig):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )

    payload = await request.json()
    event_type = payload.get("type") or payload.get("event")
    data = payload.get("data") or {}
    to_field = data.get("to")
    recipient = (
        to_field[0]
        if isinstance(to_field, list) and to_field
        else (to_field if isinstance(to_field, str) else None)
    )

    if not recipient:
        return {"ok": True, "stored": False}

    # Find the latest pending/in_progress assignment for this email.
    res = (
        supabase.table("subjects")
        .select("id")
        .eq("email", recipient)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return {"ok": True, "stored": False}
    subject_id = rows[0]["id"]

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
            "raw": data,
        }
    )
    new_meta = {**existing_meta, "email_delivery": delivery_log[-50:]}
    supabase.table("assignments").update({"metadata": new_meta}).eq(
        "id", assignment_id
    ).execute()
    return {"ok": True, "stored": True, "assignment_id": assignment_id}


@router.post("/webhooks/scoring-complete")
async def scoring_complete_webhook(
    request: Request,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> dict[str, Any]:
    """Internal callback from a background scoring worker. The worker is
    responsible for HMAC-signing the body with `n8n_webhook_secret`
    (reused as the shared secret for cross-service callbacks). When the
    secret is unset (local dev) the endpoint is open."""

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

    payload = await request.json()
    assignment_id = payload.get("assignment_id")
    if not isinstance(assignment_id, str) or not assignment_id:
        raise HTTPException(
            status_code=400, detail="assignment_id is required."
        )

    supabase.table("assignments").update(
        {"scored_at": datetime.now(UTC).isoformat()}
    ).eq("id", assignment_id).execute()
    return {"ok": True}
