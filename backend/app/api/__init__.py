"""The API's routes, all served under ``/api``."""

from fastapi import APIRouter, Depends

from app.api import auth, health, setup
from app.api.deps import require_same_origin

api_router = APIRouter(dependencies=[Depends(require_same_origin)])
api_router.include_router(health.router)
api_router.include_router(setup.router)
api_router.include_router(auth.router)
