"""FastAPI application factory."""

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import logs, retention
from app.api import api_router
from app.config import Settings, get_settings
from app.db import get_sessionmaker
from app.middleware import HEADER, RequestContext
from app.models import utcnow
from app.secret_key import load_secret_key


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    docs = settings.enable_docs

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # Checked when the server starts, so a missing or short key stops it with a clear
        # message instead of failing later, the first time something is encrypted.
        app.state.secret_key = load_secret_key(settings)
        # Tests and the end-to-end harness leave logging as it is, so pytest can capture it.
        if settings.environment != "test":
            logs.configure(settings, secrets=[app.state.secret_key.get_secret_value()])
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
                await asyncio.wait({purging})

    def server_error(request: Request, error: Exception) -> JSONResponse:
        # What ends a request that failed, so the person who sees it can quote its ID. The error
        # itself is logged, with the ID, after this.
        return JSONResponse(
            {"detail": "AresGate ran into a problem. Try again in a moment."},
            status_code=500,
            headers={HEADER: logs.request_id.get() or ""},
        )

    app = FastAPI(
        title="AresGate API",
        version=settings.version,
        lifespan=lifespan,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    app.state.started_at = utcnow()
    app.state.started_monotonic = time.monotonic()
    app.add_middleware(RequestContext)
    app.add_exception_handler(Exception, server_error)
    app.include_router(api_router, prefix="/api")
    app.dependency_overrides[get_settings] = lambda: settings
    return app


app = create_app()
