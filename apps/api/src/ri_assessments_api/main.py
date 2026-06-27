import contextlib
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .logging_config import (
    install_axiom_shipping,
    install_pii_filter,
    install_request_id_filter,
    request_id_var,
)
from .routers import (
    admin,
    benchmarks,
    candidate,
    debug,
    generator,
    health,
    public,
    references,
    webhooks,
)

log = logging.getLogger(__name__)


def _init_sentry() -> None:
    """Initialize Sentry once when SENTRY_DSN_API is set. Spec §11.3
    says we send breadcrumbs to Sentry and structured logs to Axiom; the
    Axiom side is just stdout JSON in v1 (the docker host runs vector or
    similar to ship it on)."""

    settings = get_settings()
    if not settings.sentry_dsn_api:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn_api,
            environment=settings.app_env,
            traces_sample_rate=0.1 if settings.app_env == "production" else 1.0,
            send_default_pii=False,
            attach_stacktrace=True,
            disabled_integrations=[FastApiIntegration()],
        )
        log.info("Sentry initialized (env=%s)", settings.app_env)
    except Exception:
        log.exception("Sentry init failed; continuing without it")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application-wide lifecycle hooks.

    Startup: nothing dynamic; settings, Sentry, and logging are wired
    inside create_app() so the module-level `app` object is fully
    configured at import time (uvicorn `--factory` is not required).

    Shutdown: close the Redis client used by the scoring queue so pooled
    connections release cleanly. In-flight requests are drained by
    starlette before the lifespan exit runs, so this finally block fires
    only after the last request returns."""

    try:
        yield
    finally:
        from .services import queue as scoring_queue

        with contextlib.suppress(Exception):
            scoring_queue.close_client()


# -- Rate limiting -------------------------------------------------------

# Per-token key function. Each candidate magic-link token is one
# logical bucket (one candidate = one rate-limit ceiling). Falling back
# to remote IP would punish multiple candidates behind a corporate NAT
# and would be trivially bypassable from a residential connection;
# keying by token is the natural unit of abuse here. Admin endpoints
# never see a `token` path param so they fall through to the IP-based
# default which is fine for an internal user surface.
def _rate_limit_key(request: Request) -> str:
    token = request.path_params.get("token") if hasattr(request, "path_params") else None
    if token:
        return f"candidate:{token}"
    return get_remote_address(request)


# Single source of truth: this Limiter instance is the one attached to
# `app.state.limiter` AND the one the candidate router's `_rate_limit`
# decorators call. They share `_route_limits`, which is how
# SlowAPIMiddleware finds per-endpoint configuration at request time.
# We deliberately reuse the candidate router's existing limiter rather
# than instantiating a second one: a duplicate Limiter would silently
# ignore the @_rate_limit decorations registered against the first.
limiter = candidate._limiter  # type: ignore[assignment]


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Stamps every request with a UUID4 correlation id, exposes it on
    the response as `X-Request-ID`, and stores it in a contextvar so
    every log line emitted during the request carries the same id.

    The contextvar survives `await` boundaries inside the same asyncio
    task, so handlers don't need to thread the id around manually. The
    middleware also publishes the id to `request.state.request_id` for
    code paths (Sentry scope, exception handlers) that prefer reading
    from request state instead of the contextvar."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id")
        rid = incoming if incoming and len(incoming) <= 128 else str(uuid4())
        token = request_id_var.set(rid)
        request.state.request_id = rid
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = rid
        return response


class SentryContextMiddleware(BaseHTTPMiddleware):
    """Best-effort: stamp Sentry scope tags so an event captured during
    the request carries enough breadcrumbs to find it.

    * `request_id`: always set from request.state.
    * `assignment_id`: decoded (without signature verification) from the
      candidate token when the path matches /a/{token}/*. The token is
      already untrusted input at this point in the request flow; we are
      only borrowing the payload claim for breadcrumbs, never for
      authorization, so unverified decode is acceptable here.
    * `principal.role`: read from request.state if the auth dependency
      already populated it (admin routes set this after JWT validation).

    Every operation is wrapped so a failure to set a tag never breaks
    the request itself. Tagging is observability, not control flow."""

    async def dispatch(self, request: Request, call_next):
        try:
            import sentry_sdk

            # sentry-sdk 2.x uses the global scope API; configure_scope
            # is deprecated. `set_tag` on the module is the supported way
            # to attach metadata to whatever scope the SDK currently
            # considers active (which is per-request when the FastAPI
            # integration is enabled).
            with contextlib.suppress(Exception):
                sentry_sdk.set_tag(
                    "request_id", getattr(request.state, "request_id", "-")
                )
            with contextlib.suppress(Exception):
                token = request.path_params.get("token") if hasattr(request, "path_params") else None
                if token and request.url.path.startswith("/a/"):
                    assignment_id = _maybe_decode_assignment_id(token)
                    if assignment_id:
                        sentry_sdk.set_tag("assignment_id", assignment_id)
            with contextlib.suppress(Exception):
                principal = getattr(request.state, "principal", None)
                role = getattr(principal, "role", None) if principal else None
                if role:
                    sentry_sdk.set_tag("principal.role", role)
        except Exception:
            # Sentry SDK not installed or not initialized: skip silently.
            pass
        return await call_next(request)


def _maybe_decode_assignment_id(token: str) -> str | None:
    """Pull the `assignment_id` claim out of a candidate JWT without
    verifying the signature. We never use this for auth; it exists only
    so a Sentry breadcrumb can carry the assignment id for a request
    that ultimately failed signature verification or expired. Returns
    None on any failure."""

    try:
        import jwt

        # Sentry breadcrumb only; never used for auth. PyJWT does not
        # expose a `get_unverified_claims` helper, so we decode with
        # signature verification disabled instead.
        claims = jwt.decode(
            token, options={"verify_signature": False, "verify_aud": False}
        )
        value = claims.get("assignment_id") or claims.get("sub")
        return str(value) if value else None
    except Exception:
        return None


def create_app() -> FastAPI:
    install_pii_filter()
    install_request_id_filter()
    settings = get_settings()
    install_axiom_shipping(
        token=settings.axiom_token,
        dataset=settings.axiom_dataset,
        env=settings.app_env,
    )
    _init_sentry()
    app = FastAPI(
        title="RI Assessments API",
        version="0.1.0",
        description="Backend for the Revenue Institute Assessments Platform.",
        lifespan=lifespan,
    )

    # Rate limiter wiring. `app.state.limiter` is read by
    # SlowAPIMiddleware on every request; the same limiter instance
    # owns the per-route `_route_limits` registered by the candidate
    # router's @_rate_limit decorators. Without this binding, the
    # decorators register limits against a dangling instance and
    # SlowAPIMiddleware no-ops.
    if limiter is not None:
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(SentryContextMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.resolve_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    if settings.app_env != "production":
        app.include_router(debug.router)
    app.include_router(admin.router, prefix="/api")
    app.include_router(generator.router, prefix="/api")
    app.include_router(references.router, prefix="/api")
    app.include_router(benchmarks.router)
    app.include_router(candidate.router, prefix="/a")
    # Unauthenticated public enrollment (shareable assessment links). The
    # candidate Next app calls these server-side via INTERNAL_API_URL; the
    # enrollment page itself lives under /a/enroll/* so prod nginx routes
    # it to the candidate app without a new location block.
    app.include_router(public.router, prefix="/p")
    app.include_router(webhooks.router)

    return app


app = create_app()
