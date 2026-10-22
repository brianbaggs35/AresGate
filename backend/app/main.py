"""FastAPI application factory."""

from fastapi import FastAPI

from app.api import api_router
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    docs = settings.enable_docs
    app = FastAPI(
        title="AresGate API",
        version=settings.version,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    app.include_router(api_router, prefix="/api")
    app.dependency_overrides[get_settings] = lambda: settings
    return app


app = create_app()
