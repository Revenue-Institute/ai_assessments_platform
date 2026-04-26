from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .logging_config import install_pii_filter
from .routers import (
    admin,
    benchmarks,
    candidate,
    generator,
    health,
    references,
    webhooks,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


def create_app() -> FastAPI:
    install_pii_filter()
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
    app.include_router(admin.router, prefix="/api")
    app.include_router(generator.router, prefix="/api")
    app.include_router(references.router, prefix="/api")
    app.include_router(benchmarks.router)
    app.include_router(candidate.router, prefix="/a")
    app.include_router(webhooks.router)

    return app


app = create_app()
