"""Debug-only endpoints. Intentionally narrow surface; refuse to do
anything outside `local` / `staging` to avoid accidental prod misuse."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..config import get_settings

router = APIRouter(tags=["debug"])


@router.get("/debug/sentry")
def sentry_smoke() -> dict[str, str]:
    """Raises a controlled error so the operator can confirm SENTRY_DSN_API
    is wired and breadcrumbs land in the project. Disabled in production."""

    settings = get_settings()
    if settings.app_env == "production":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
        )
    raise RuntimeError(
        "Intentional error from /debug/sentry to verify the Sentry integration."
    )


@router.get("/debug/observability")
def observability_status() -> dict[str, object]:
    """Reports which observability env vars are populated. Helps spot a
    missing DSN before chasing a non-event. Returns booleans only; never
    leaks the secret values themselves."""

    settings = get_settings()
    return {
        "app_env": settings.app_env,
        "sentry_dsn_api_set": bool(settings.sentry_dsn_api),
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
