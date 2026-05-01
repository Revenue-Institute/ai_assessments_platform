import threading

from supabase import Client, create_client
from supabase.client import ClientOptions

from .config import get_settings

# httpx HTTP/2 connections inside the supabase SDK aren't safe to share
# across worker threads, long-lived h2 streams occasionally raise
# RemoteProtocolError when the server closes them. We give each thread
# its own client so concurrent FastAPI handlers don't trample each
# other.
_thread_local = threading.local()


def get_supabase() -> Client:
    """Service-role Supabase client. Bypasses RLS; use only on the server."""

    client = getattr(_thread_local, "client", None)
    if client is not None:
        return client

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set before using the Supabase client."
        )

    client = create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options=ClientOptions(postgrest_client_timeout=30),
    )
    _thread_local.client = client
    return client
