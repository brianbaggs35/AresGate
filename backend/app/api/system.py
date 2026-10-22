"""What the install says about itself, for someone signed in."""

import time
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import Db, SettingsDep, signed_in

# The public health check says nothing but whether AresGate is up. This one says more, so it
# needs a sign-in.
router = APIRouter(tags=["system"], dependencies=[Depends(signed_in)])


class DatabaseInfo(BaseModel):
    status: Literal["ok", "unavailable"]
    # PostgreSQL's own version, e.g. 18.1.
    version: str | None


class SystemInfo(BaseModel):
    version: str
    started_at: datetime
    uptime_seconds: int
    database: DatabaseInfo


@router.get("/system")
def system(request: Request, db: Db, settings: SettingsDep) -> SystemInfo:
    try:
        # Some builds add their packaging to it, as in "18.1 (Debian 18.1-1)".
        version = db.scalar(text("SELECT split_part(current_setting('server_version'), ' ', 1)"))
        database = DatabaseInfo(status="ok", version=version)
    except SQLAlchemyError:
        database = DatabaseInfo(status="unavailable", version=None)
    return SystemInfo(
        version=settings.version,
        started_at=request.app.state.started_at,
        uptime_seconds=int(time.monotonic() - request.app.state.started_monotonic),
        database=database,
    )
