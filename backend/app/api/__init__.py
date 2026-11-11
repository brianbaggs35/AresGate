"""The API's routes, all served under ``/api``."""

from fastapi import APIRouter, Depends

from app.api import (
    account,
    agents,
    ai,
    ai_chat,
    ai_usage,
    alerts,
    assets,
    audit,
    auth,
    chains,
    collectors,
    credentials,
    dashboard,
    events,
    health,
    incidents,
    integrations,
    interfaces,
    logs,
    metrics,
    noise,
    passkeys,
    searches,
    setup,
    status,
    system,
    threat_intel,
    threat_settings,
    threats,
    two_factor,
    verdicts,
)
from app.api.deps import require_same_origin

api_router = APIRouter(dependencies=[Depends(require_same_origin)])
api_router.include_router(health.router)
api_router.include_router(setup.router)
api_router.include_router(auth.router)
api_router.include_router(account.router)
api_router.include_router(two_factor.router)
api_router.include_router(passkeys.router)
api_router.include_router(credentials.router)
api_router.include_router(integrations.router)
api_router.include_router(interfaces.router)
api_router.include_router(assets.router)
api_router.include_router(agents.router)
api_router.include_router(ai.router)
api_router.include_router(ai_chat.router)
api_router.include_router(ai_usage.router)
api_router.include_router(alerts.router)
api_router.include_router(collectors.router)
api_router.include_router(dashboard.router)
api_router.include_router(events.router)
api_router.include_router(incidents.router)
api_router.include_router(logs.router)
api_router.include_router(searches.router)
api_router.include_router(verdicts.router)
api_router.include_router(noise.router)
api_router.include_router(chains.router)
api_router.include_router(threats.router)
api_router.include_router(threat_intel.router)
api_router.include_router(threat_settings.router)
api_router.include_router(metrics.router)
api_router.include_router(audit.router)
api_router.include_router(status.router)
api_router.include_router(system.router)
