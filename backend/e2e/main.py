"""The API with the end-to-end test harness mounted.

The e2e image and CI serve it with ``uvicorn e2e.main:create_e2e_app --factory``.
"""

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.incidents import names
from app.integrations import netguard
from app.main import create_app
from e2e.api import router

# What the test server's reverse lookups answer, so that no test asks the internet: a few of the
# addresses the harness's factories use have a name, the rest have none.
STAND_IN_NAMES = {
    "93.184.216.34": "scanner-17.example.net",
    "8.8.8.8": "dns.example.net",
    "198.51.100.20": "edge-20.example.net",
}


def create_e2e_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    # The harness can wipe the database, so it refuses to run anywhere but a test server.
    if settings.environment != "test":
        raise RuntimeError(
            "The end-to-end test harness only runs with ARESGATE_ENVIRONMENT=test, because it "
            "can erase all the data."
        )
    app = create_app(settings)
    names.resolver = STAND_IN_NAMES.get
    # Stand-ins for the integrations run on the test server's own machine.
    app.state.address_policy = netguard.HOME_NETWORK_AND_LOOPBACK
    app.state.local_ai_policy = netguard.HOME_NETWORK_AND_LOOPBACK
    app.state.ai_policy = netguard.PUBLIC_INTERNET_AND_LOOPBACK
    app.state.alert_policy = netguard.PUBLIC_INTERNET_AND_LOOPBACK
    app.include_router(router, prefix="/api")
    return app
