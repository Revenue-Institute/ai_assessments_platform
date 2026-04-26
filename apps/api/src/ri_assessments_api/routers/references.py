"""Reference library endpoints (spec §14.1, §6.4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from supabase import Client

from ..auth import AdminPrincipal, require_admin_jwt
from ..db import get_supabase
from ..models.generator import (
    ReferenceDocumentSummary,
    ReferenceTextUploadRequest,
    ReferenceUploadResponse,
    ReferenceUrlUploadRequest,
)
from ..services import references as references_service

router = APIRouter(
    tags=["references"],
    prefix="/references",
    dependencies=[Depends(require_admin_jwt)],
)


@router.get("", response_model=list[ReferenceDocumentSummary])
def list_documents(
    supabase: Annotated[Client, Depends(get_supabase)],
) -> list[ReferenceDocumentSummary]:
    rows = references_service.list_documents(supabase)
    return [ReferenceDocumentSummary(**row) for row in rows]


@router.post("", response_model=ReferenceUploadResponse, status_code=201)
def upload_text(
    payload: ReferenceTextUploadRequest,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ReferenceUploadResponse:
    result = references_service.upload_text(
        supabase,
        principal,
        title=payload.title,
        content=payload.content,
        domain=payload.domain,
        source_url=payload.source_url,
    )
    return ReferenceUploadResponse(**result)


@router.post("/url", response_model=ReferenceUploadResponse, status_code=201)
def upload_url(
    payload: ReferenceUrlUploadRequest,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ReferenceUploadResponse:
    result = references_service.upload_url(
        supabase,
        principal,
        url=payload.url,
        title=payload.title,
        domain=payload.domain,
    )
    return ReferenceUploadResponse(**result)


@router.post(
    "/pdf", response_model=ReferenceUploadResponse, status_code=201
)
async def upload_pdf(
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
    domain: Annotated[str | None, Form()] = None,
    source_url: Annotated[str | None, Form()] = None,
) -> ReferenceUploadResponse:
    pdf_bytes = await file.read()
    result = references_service.upload_pdf(
        supabase,
        principal,
        pdf_bytes=pdf_bytes,
        title=title,
        domain=domain,
        source_url=source_url,
    )
    return ReferenceUploadResponse(**result)


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    doc_id: str,
    principal: Annotated[AdminPrincipal, Depends(require_admin_jwt)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> None:
    references_service.delete_document(supabase, principal, doc_id)
