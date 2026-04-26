from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import admin, candidate, generator, health, references


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


def create_app() -> FastAPI:
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
    app.include_router(candidate.router, prefix="/a")

    return app


app = create_app()
