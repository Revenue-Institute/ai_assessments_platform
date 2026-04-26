"""Candidate magic-link endpoints (spec §14.2)."""

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ..db import get_supabase
from ..models.candidate import CandidateAssignmentView, ConsentResponse
from ..services.assignments import record_consent, resolve_token

router = APIRouter(tags=["candidate"])


def _ip_hash_from_request(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    raw_ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else None
    )
    if not raw_ip:
        return None
    return hashlib.sha256(raw_ip.encode("utf-8")).hexdigest()


@router.get("/{token}/resolve", response_model=CandidateAssignmentView)
def resolve(
    token: str,
    supabase: Annotated[object, Depends(get_supabase)],
) -> CandidateAssignmentView:
    return resolve_token(supabase, token)  # type: ignore[arg-type]


@router.post("/{token}/consent", response_model=ConsentResponse)
def consent(
    token: str,
    request: Request,
    supabase: Annotated[object, Depends(get_supabase)],
) -> ConsentResponse:
    return record_consent(  # type: ignore[arg-type]
        supabase,
        token,
        ip_hash=_ip_hash_from_request(request),
    )
