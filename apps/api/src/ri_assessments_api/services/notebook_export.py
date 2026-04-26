"""Convert a candidate's notebook submission into an .ipynb file and upload
it to Supabase Storage so admins can download it post-submission (spec §6.5).

We keep this best-effort: storage failures don't block submit, since the
raw cells already live on attempts.raw_answer."""

from __future__ import annotations

import json
import logging
from typing import Any

from supabase import Client

from ..config import get_settings

log = logging.getLogger(__name__)


def _build_ipynb(cells: list[dict[str, Any]]) -> dict[str, Any]:
    nb_cells: list[dict[str, Any]] = []
    for cell in cells:
        ctype = cell.get("type") or "code"
        source = cell.get("source") or cell.get("code") or ""
        if not isinstance(source, str):
            source = json.dumps(source)
        if ctype == "markdown":
            nb_cells.append(
                {
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": source.splitlines(keepends=True),
                }
            )
        else:
            nb_cells.append(
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": source.splitlines(keepends=True),
                }
            )
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
        },
        "cells": nb_cells,
    }


def export_notebook_ipynb(
    supabase: Client,
    *,
    attempt_id: str,
    cells: list[dict[str, Any]],
) -> str | None:
    """Upload a candidate's notebook to artifacts/<attempt_id>.ipynb.
    Returns the storage path or None if upload failed."""

    settings = get_settings()
    bucket = settings.supabase_storage_bucket_artifacts
    nb = _build_ipynb(cells)
    body = json.dumps(nb).encode("utf-8")
    path = f"notebooks/{attempt_id}.ipynb"
    try:
        supabase.storage.from_(bucket).upload(
            path,
            body,
            file_options={
                "content-type": "application/x-ipynb+json",
                "upsert": "true",
            },
        )
        return path
    except Exception as exc:
        log.warning("notebook ipynb upload failed for %s: %s", attempt_id, exc)
        return None


def signed_notebook_url(
    supabase: Client,
    *,
    path: str,
    expires_in_seconds: int = 3600,
) -> str | None:
    settings = get_settings()
    bucket = settings.supabase_storage_bucket_artifacts
    try:
        res = supabase.storage.from_(bucket).create_signed_url(
            path, expires_in_seconds
        )
        return res.get("signedURL") or res.get("signed_url")
    except Exception as exc:
        log.warning("notebook signed url failed for %s: %s", path, exc)
        return None
