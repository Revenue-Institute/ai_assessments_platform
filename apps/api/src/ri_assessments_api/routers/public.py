"""Unauthenticated public enrollment endpoints (spec extension).

Powers the shareable assessment link. The opaque link token in the path is
the only capability required; there is no JWT. Per-IP rate limiting on the
register endpoint (shared limiter wired in main.py) bounds abuse, and the
service layer enforces the link's enabled / expiry / max_uses gates plus
per-email dedupe.

Mounted at /p in main.py, so the routes are GET /p/{link_token} and
POST /p/{link_token}/register.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from supabase import Client

from ..db import get_supabase
from ..models.public import (
    PublicAssessmentView,
    PublicRegisterRequest,
    PublicRegisterResponse,
)
from ..services import public_links
from .candidate import _ip_hash_from_request, _rate_limit

router = APIRouter(tags=["public"])


@router.get("/{link_token}", response_model=PublicAssessmentView)
def public_assessment(
    link_token: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> PublicAssessmentView:
    return public_links.get_public_assessment(supabase, link_token)


@router.post("/{link_token}/register", response_model=PublicRegisterResponse)
@_rate_limit("15/hour")
def public_register(
    link_token: str,
    payload: PublicRegisterRequest,
    request: Request,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> PublicRegisterResponse:
    return public_links.register_via_public_link(
        supabase,
        link_token,
        payload,
        ip_hash=_ip_hash_from_request(request),
    )
