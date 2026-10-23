"""The API's routes, all served under ``/api``."""

from fastapi import APIRouter, Depends

from app.api import (
    account,
    audit,
    auth,
    credentials,
    health,
    integrations,
    passkeys,
    setup,
    system,
    two_factor,
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
api_router.include_router(audit.router)
api_router.include_router(system.router)
