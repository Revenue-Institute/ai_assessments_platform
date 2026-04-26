"""AI generation endpoints (spec §6, §14.1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from supabase import Client

from ..auth import AdminPrincipal, require_admin_jwt
from ..db import get_supabase
from ..models.generator import (
    GeneratedOutline,
    GenerationBriefIn,
    OutlineRunResponse,
    PreviewVariant,
    PreviewVariantsRequest,
    PreviewVariantsResponse,
    QuestionGenerationRequest,
    QuestionGenerationResponse,
)
from ..services import generator as generator_service

router = APIRouter(
    tags=["generator"],
    prefix="/generator",
    dependencies=[Depends(require_admin_jwt)],
)


@router.post("/outline", response_model=OutlineRunResponse)
def outline(
    payload: GenerationBriefIn,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> OutlineRunResponse:
    return generator_service.generate_outline(supabase, principal, payload)


@router.post("/questions", response_model=QuestionGenerationResponse)
def questions(
    payload: QuestionGenerationRequest,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> QuestionGenerationResponse:
    return generator_service.generate_questions(
        supabase,
        principal,
        outline_run_id=payload.outline_run_id,
        brief=payload.brief,
        outline=payload.outline,
        slug=payload.slug,
        domain=payload.domain,
    )


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> dict:
    """Return a generation_runs row. Used by the wizard to load an outline
    by run_id without re-passing the full payload through the URL."""

    row = generator_service.get_run(supabase, run_id)
    if row.get("stage") == "outline" and row.get("status") == "success":
        # Validate the cached outline so the UI gets a clean shape.
        try:
            outline = GeneratedOutline.model_validate(row["output"])
            row["outline"] = outline.model_dump()
        except Exception:
            pass
    return row


@router.post("/preview-variants", response_model=PreviewVariantsResponse)
def preview_variants(payload: PreviewVariantsRequest) -> PreviewVariantsResponse:
    rows = generator_service.preview_variants(
        payload.variable_schema, payload.prompt_template, payload.seed_count
    )
    return PreviewVariantsResponse(
        variants=[PreviewVariant(**row) for row in rows]
    )
