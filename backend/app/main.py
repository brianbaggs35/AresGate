"""FastAPI application factory."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app import retention
from app.api import api_router
from app.config import Settings, get_settings
from app.db import get_sessionmaker
from app.secret_key import load_secret_key


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    docs = settings.enable_docs

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # Checked when the server starts, so a missing or short key stops it with a clear
        # message instead of failing later, the first time something is encrypted.
        app.state.secret_key = load_secret_key(settings)
        # The tests and the end-to-end harness decide for themselves when the log is purged.
        purging = (
            None
            if settings.environment == "test"
            else asyncio.create_task(retention.run(settings, get_sessionmaker()))
        )
        try:
            yield
        finally:
            if purging:
                purging.cancel()
                with suppress(asyncio.CancelledError):
                    await purging

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
