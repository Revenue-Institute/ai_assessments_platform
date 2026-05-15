"""AI generation endpoints (spec §6, §14.1)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from supabase import Client

from ..auth import AdminPrincipal, ensure_role, require_admin_jwt
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
    ReviseQuestionRequest,
    ReviseQuestionResponse,
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


async def _generation_events_stream(run_id: str) -> AsyncGenerator[bytes, None]:
    """Bridge the per-run Redis pub/sub channel into an SSE stream.

    Event payloads (spec §12.2 step 4):
      - {"type": "started", "topics": [..names], "total_topics": N, "ts": iso}
      - {"type": "topic_completed", "topic_name": str,
         "status": "success"|"failed", "questions_count": int,
         "error": str|None, "completed": k, "total_topics": N, "ts": iso}
      - {"type": "finished", "module_id": uuid, "total_questions": int, "ts": iso}

    Mirrors the scoring SSE in routers/admin.py: pubsub get_message
    polled on a thread executor; comment heartbeats every 15s keep the
    connection open through proxies; pubsub torn down in finally."""

    from ..services import queue as queue_service

    if not queue_service.is_configured():
        yield b'retry: 30000\nevent: unavailable\ndata: {"reason":"redis-unavailable"}\n\n'
        return

    pubsub = queue_service.subscribe_generation_events(run_id)
    loop = asyncio.get_running_loop()
    yield b": connected\n\n"
    try:
        while True:
            message = await loop.run_in_executor(
                None, lambda: pubsub.get_message(timeout=15.0)
            )
            if message is None:
                # Heartbeat comment line keeps proxies from idling out
                # the connection between sparse generation events.
                yield b": keepalive\n\n"
                continue
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")
            if not isinstance(data, str):
                continue
            # Best-effort: emit the type as the SSE event name so the
            # browser can hook addEventListener('topic_completed', ...).
            event_name = "generation"
            try:
                parsed = json.loads(data)
                if isinstance(parsed, dict) and isinstance(parsed.get("type"), str):
                    event_name = parsed["type"]
            except json.JSONDecodeError:
                pass
            yield f"event: {event_name}\ndata: {data}\n\n".encode()
            # Close the stream once the run is done so the client
            # disconnects cleanly without a stale subscription.
            if event_name == "finished":
                break
    finally:
        try:
            pubsub.unsubscribe()
            pubsub.close()
        except Exception:
            pass


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: str,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
) -> StreamingResponse:
    """Server-Sent Events stream of per-topic generation progress
    (spec §12.2 step 4, §14.1). Admin-only.

    Wire from the wizard with EventSource on this URL after POSTing to
    /api/generator/questions. The stream closes itself after the
    `finished` event; the client should treat any reconnect after that
    as a no-op."""

    # Spec §6.1: outline + question authoring is admin+reviewer; the
    # progress feed mirrors that so reviewers can shadow a run.
    ensure_role(principal, "admin", "reviewer")
    return StreamingResponse(
        _generation_events_stream(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/question/{question_id}/revise",
    response_model=ReviseQuestionResponse,
)
def revise_question(
    question_id: str,
    payload: ReviseQuestionRequest,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ReviseQuestionResponse:
    result = generator_service.revise_question(
        supabase,
        principal,
        question_id=question_id,
        instruction=payload.instruction,
        preserve=payload.preserve,
    )
    return ReviseQuestionResponse(**result)


@router.post("/preview-variants", response_model=PreviewVariantsResponse)
def preview_variants(
    payload: PreviewVariantsRequest,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
) -> PreviewVariantsResponse:
    # Spec §6.6: preview is part of the authoring loop, so admin and
    # reviewer roles are allowed (viewer is not). Mirrors the outline
    # endpoint's role gate in services/generator.generate_outline.
    ensure_role(principal, "admin", "reviewer")
    rows = generator_service.preview_variants(
        payload.variable_schema, payload.prompt_template, payload.seed_count
    )
    return PreviewVariantsResponse(
        variants=[PreviewVariant(**row) for row in rows]
    )
