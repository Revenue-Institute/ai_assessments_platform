import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .logging_config import install_pii_filter
from .routers import (
    admin,
    benchmarks,
    candidate,
    debug,
    generator,
    health,
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

        sentry_sdk.init(
            dsn=settings.sentry_dsn_api,
            environment=settings.app_env,
            traces_sample_rate=0.1 if settings.app_env == "production" else 1.0,
            send_default_pii=False,
            attach_stacktrace=True,
        )
        log.info("Sentry initialized (env=%s)", settings.app_env)
    except Exception:
        log.exception("Sentry init failed; continuing without it")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


def create_app() -> FastAPI:
    install_pii_filter()
    _init_sentry()
    settings = get_settings()
    app = FastAPI(
        title="RI Assessments API",
        version="0.1.0",
        description="Backend for the Revenue Institute Assessments Platform.",
        lifespan=lifespan,
    )

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
    app.include_router(webhooks.router)

    return app


app = create_app()
