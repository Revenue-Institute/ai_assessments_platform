"""Debug-only endpoints. Intentionally narrow surface; refuse to do
anything outside `local` / `staging` to avoid accidental prod misuse.

Defense in depth: `main.py` already declines to include this router
when APP_ENV=production, but we also gate every handler with
`_require_non_production` so a future routing change can never silently
expose these in prod. Belt and braces.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..config import get_settings

router = APIRouter(tags=["debug"])


def _require_non_production() -> None:
    """Return 404 (not 403) when in production so the surface looks
    identical to a missing route. Probes shouldn't be able to fingerprint
    that these handlers exist at all."""

    if get_settings().app_env == "production":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
        )


@router.get("/debug/observability")
def observability_status() -> dict[str, object]:
    """Reports which observability env vars are populated. Returns
    booleans only; never leaks the secret values themselves."""

    _require_non_production()
    settings = get_settings()
    return {
        "app_env": settings.app_env,
        "axiom_token_set": bool(settings.axiom_token),
        "axiom_dataset_set": bool(settings.axiom_dataset),
        "supabase_url_set": bool(settings.supabase_url),
        "anthropic_keys_set": bool(
            settings.anthropic_api_key_generation
            and settings.anthropic_api_key_scoring
        ),
        "e2b_key_set": bool(settings.e2b_api_key),
        "resend_key_set": bool(settings.resend_api_key),
        "redis_url_set": bool(settings.upstash_redis_url),
    }
