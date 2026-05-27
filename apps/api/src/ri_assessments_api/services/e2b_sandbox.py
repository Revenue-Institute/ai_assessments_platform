"""Shared E2B sandbox bootstrap (spec §14.3).

Four runner modules (code, sql, notebook, plus solver in soft mode) all
need the same "resolve E2B API key, import Sandbox, fail with a clean
503 or return None" boilerplate. This file is the single owner.

`get_sandbox()` raises HTTPException(503) on missing key or import
failure; runners that must serve the candidate flow use this. The
`maybe_get_sandbox()` variant returns None instead so the solver runner
(which is best-effort during attempt creation, spec §8.3) can skip
without breaking attempt creation."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from ..config import get_settings


def get_sandbox() -> tuple[Any, str]:
    """Returns (Sandbox class, e2b_api_key). Raises HTTPException(503)
    if E2B is not configured or the SDK is missing on the server."""

    settings = get_settings()
    if not settings.e2b_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Code runner is not configured (E2B_API_KEY missing).",
        )
    try:
        from e2b_code_interpreter import Sandbox  # type: ignore[import-not-found]
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="e2b-code-interpreter is not installed on the server.",
        ) from exc
    return Sandbox, settings.e2b_api_key


def maybe_get_sandbox() -> tuple[Any, str] | None:
    """Soft variant for fail-open callers. Returns None if E2B is not
    available; never raises. Used by the solver runner, which is allowed
    to skip solver execution when E2B is offline (spec §8.3 caches the
    solver output, but attempt creation must not fail when it can't)."""

    settings = get_settings()
    if not settings.e2b_api_key:
        return None
    try:
        from e2b_code_interpreter import Sandbox  # type: ignore[import-not-found]
    except ImportError:
        return None
    return Sandbox, settings.e2b_api_key
