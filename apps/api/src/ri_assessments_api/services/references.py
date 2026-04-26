"""Reference library: ingest text/markdown/URL/PDF, chunk, embed via
Voyage, store, retrieve top-k by cosine similarity (spec §6.4)."""

from __future__ import annotations

import io
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from supabase import Client

from ..auth import AdminPrincipal
from ..config import get_settings

log = logging.getLogger(__name__)

# Spec §6.4: chunk at 800 tokens with 100 token overlap. We approximate
# 1 token ~= 4 chars (English) so 800 tokens ~= 3200 chars and 100 tokens
# ~= 400 chars. Cheap and good enough for retrieval; if cross-language
# accuracy ever matters, swap in voyageai.tokenize() here.
CHUNK_CHAR_TARGET = 3_200
CHUNK_CHAR_OVERLAP = 400
EMBEDDING_MODEL = "voyage-3"
EMBEDDING_DIMS = 1024


def _ensure_role(principal: AdminPrincipal, *allowed: str) -> None:
    if principal.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{principal.role}' is not permitted for this action.",
        )


def _voyage_client():
    settings = get_settings()
    if not settings.voyage_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VOYAGE_API_KEY is not configured.",
        )
    try:
        import voyageai  # type: ignore[import-not-found]
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="voyageai is not installed on the server.",
        ) from exc
    return voyageai.Client(api_key=settings.voyage_api_key)


# -- Chunking ---------------------------------------------------------------


def chunk_text(content: str) -> list[str]:
    """Paragraph-aware sliding-window chunker. Keeps natural breaks intact
    when possible and falls back to fixed-size splits for very long
    paragraphs (e.g., minified code, single-line scrapes)."""

    text = content.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buffer = ""

    def flush(buf: str) -> None:
        if buf.strip():
            chunks.append(buf.strip())

    for paragraph in paragraphs:
        # Hard split paragraphs that exceed the target by themselves.
        if len(paragraph) > CHUNK_CHAR_TARGET:
            if buffer:
                flush(buffer)
                buffer = ""
            for i in range(0, len(paragraph), CHUNK_CHAR_TARGET - CHUNK_CHAR_OVERLAP):
                chunks.append(paragraph[i : i + CHUNK_CHAR_TARGET])
            continue

        if len(buffer) + len(paragraph) + 2 > CHUNK_CHAR_TARGET and buffer:
            flush(buffer)
            buffer = buffer[-CHUNK_CHAR_OVERLAP:] if CHUNK_CHAR_OVERLAP > 0 else ""
            buffer = (buffer + "\n\n" + paragraph).strip() if buffer else paragraph
        else:
            buffer = (buffer + "\n\n" + paragraph).strip() if buffer else paragraph

    flush(buffer)
    return chunks


def embed_chunks(chunks: list[str], *, input_type: str = "document") -> list[list[float]]:
    """Voyage-3 embeddings, batched. `input_type` is `document` for ingestion
    and `query` for retrieval (Voyage embeds them in distinct spaces)."""

    client = _voyage_client()
    if not chunks:
        return []
    result = client.embed(
        texts=chunks,
        model=EMBEDDING_MODEL,
        input_type=input_type,
    )
    embeddings = list(result.embeddings)
    if any(len(v) != EMBEDDING_DIMS for v in embeddings):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Voyage returned vectors of unexpected dimension; "
                f"expected {EMBEDDING_DIMS}."
            ),
        )
    return embeddings


# -- Ingestion --------------------------------------------------------------


def _insert_document(
    supabase: Client,
    *,
    title: str,
    content: str,
    domain: str | None,
    source_url: str | None,
    uploaded_by: str | None,
) -> dict[str, Any]:
    res = (
        supabase.table("reference_documents")
        .insert(
            {
                "id": str(uuid.uuid4()),
                "title": title,
                "source_url": source_url,
                "content": content,
                "uploaded_by": uploaded_by,
                "domain": domain,
            }
        )
        .execute()
    )
    if not res.data:
        raise HTTPException(
            status_code=500, detail="Failed to insert reference document."
        )
    return res.data[0]


def _insert_chunks(
    supabase: Client,
    *,
    document_id: str,
    chunks: list[str],
    embeddings: list[list[float]],
) -> int:
    rows = [
        {
            "id": str(uuid.uuid4()),
            "document_id": document_id,
            "content": chunks[i],
            "position": i,
            "embedding": embeddings[i],
        }
        for i in range(len(chunks))
    ]
    if not rows:
        return 0
    # supabase-py serializes embeddings as JSON; pgvector accepts the
    # bracketed string form natively.
    supabase.table("reference_chunks").insert(rows).execute()
    return len(rows)


def upload_text(
    supabase: Client,
    principal: AdminPrincipal,
    *,
    title: str,
    content: str,
    domain: str | None,
    source_url: str | None,
) -> dict[str, Any]:
    _ensure_role(principal, "admin", "reviewer")
    chunks = chunk_text(content)
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content is empty after normalization.",
        )

    embeddings = embed_chunks(chunks, input_type="document")
    document = _insert_document(
        supabase,
        title=title,
        content=content,
        domain=domain,
        source_url=source_url,
        uploaded_by=principal.user_id,
    )
    inserted = _insert_chunks(
        supabase,
        document_id=document["id"],
        chunks=chunks,
        embeddings=embeddings,
    )
    return {
        "document": _summarize(document, chunk_count=inserted),
        "chunks_inserted": inserted,
    }


def upload_url(
    supabase: Client,
    principal: AdminPrincipal,
    *,
    url: str,
    title: str | None,
    domain: str | None,
) -> dict[str, Any]:
    try:
        import trafilatura  # type: ignore[import-not-found]
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="trafilatura is not installed on the server.",
        ) from exc

    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not fetch URL {url!r}.",
        )
    extracted = trafilatura.extract(
        downloaded,
        include_links=False,
        include_images=False,
        include_tables=True,
    )
    if not extracted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract readable text from URL.",
        )

    return upload_text(
        supabase,
        principal,
        title=title or _title_from_url(url),
        content=extracted,
        domain=domain,
        source_url=url,
    )


def upload_pdf(
    supabase: Client,
    principal: AdminPrincipal,
    *,
    pdf_bytes: bytes,
    title: str,
    domain: str | None,
    source_url: str | None,
) -> dict[str, Any]:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="pypdf is not installed on the server.",
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not parse PDF: {exc}",
        ) from exc

    content = "\n\n".join(p.strip() for p in pages if p.strip())
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF contained no extractable text.",
        )
    return upload_text(
        supabase,
        principal,
        title=title,
        content=content,
        domain=domain,
        source_url=source_url,
    )


# -- Listing ----------------------------------------------------------------


def list_documents(supabase: Client) -> list[dict[str, Any]]:
    res = (
        supabase.table("reference_documents")
        .select(
            "id, title, source_url, domain, created_at, "
            "reference_chunks(id)"
        )
        .order("created_at", desc=True)
        .execute()
    )
    return [
        _summarize(row, chunk_count=len(row.get("reference_chunks") or []))
        for row in res.data or []
    ]


def delete_document(supabase: Client, principal: AdminPrincipal, doc_id: str) -> None:
    _ensure_role(principal, "admin")
    supabase.table("reference_documents").delete().eq("id", doc_id).execute()


# -- Retrieval --------------------------------------------------------------


def retrieve_top_k(
    supabase: Client,
    *,
    query: str,
    document_ids: list[str] | None = None,
    k: int = 10,
) -> list[dict[str, Any]]:
    """Embeds the query then calls match_reference_chunks() RPC for the
    top-k chunks (spec §6.4)."""

    if not query.strip():
        return []
    if not document_ids:
        return []  # Spec §6.4 retrieval is opt-in via brief.reference_document_ids.

    [embedding] = embed_chunks([query], input_type="query")
    res = supabase.rpc(
        "match_reference_chunks",
        {
            "query_embedding": embedding,
            "match_count": k,
            "document_ids": document_ids,
        },
    ).execute()
    return list(res.data or [])


# -- Helpers ----------------------------------------------------------------


def _title_from_url(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").rstrip("/")[:200]


def _summarize(row: dict[str, Any], *, chunk_count: int) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "source_url": row.get("source_url"),
        "domain": row.get("domain"),
        "chunk_count": chunk_count,
        "created_at": _ensure_iso(row.get("created_at")),
    }


def _ensure_iso(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return datetime.now(UTC).isoformat()
