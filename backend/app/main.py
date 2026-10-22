"""FastAPI application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router
from app.config import Settings, get_settings
from app.secret_key import load_secret_key


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    docs = settings.enable_docs

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # Checked when the server starts, so a missing or short key stops it with a clear
        # message instead of failing later, the first time something is encrypted.
        app.state.secret_key = load_secret_key(settings)
        yield

    app = FastAPI(
        title="AresGate API",
        version=settings.version,
        lifespan=lifespan,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    app.include_router(api_router, prefix="/api")
    app.dependency_overrides[get_settings] = lambda: settings
    return app


app = create_app()
