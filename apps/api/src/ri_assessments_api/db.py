from functools import lru_cache

from supabase import Client, create_client

from .config import get_settings


@lru_cache
def get_supabase() -> Client:
    """Service-role Supabase client. Bypasses RLS; use only on the server."""

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set before using the Supabase client."
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
