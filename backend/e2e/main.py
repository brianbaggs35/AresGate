"""The API with the end-to-end test harness mounted.

The e2e image and CI serve it with ``uvicorn e2e.main:create_e2e_app --factory``.
"""

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.integrations import netguard
from app.main import create_app
from e2e.api import router


def create_e2e_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    # The harness can wipe the database, so it refuses to run anywhere but a test server.
    if settings.environment != "test":
        raise RuntimeError(
            "The end-to-end test harness only runs with ARESGATE_ENVIRONMENT=test, because it "
            "can erase all the data."
        )
    app = create_app(settings)
    # Stand-ins for the integrations run on the test server's own machine.
    app.state.address_policy = netguard.HOME_NETWORK_AND_LOOPBACK
    app.state.ai_policy = netguard.PUBLIC_INTERNET_AND_LOOPBACK
    app.include_router(router, prefix="/api")
    return app
