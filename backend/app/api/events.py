"""How long each integration's events are kept, and how many there are. For someone signed in.
The events themselves are read by the pages that show them."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import Db, SettingsDep, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.config import Settings
from app.events import retention
from app.events.retention import MAX_DAYS, MIN_DAYS
from app.integrations import registry
from app.security.credential_store import NAME_PATTERN

router = APIRouter(prefix="/events", tags=["events"], dependencies=[Depends(signed_in)])

Key = Annotated[str, Path(pattern=NAME_PATTERN, description="An integration, such as wazuh.")]


class SourceOut(BaseModel):
    """What is kept of one integration's events."""

    source: str
    name: str
    # The days set for this integration, or None while it keeps them for the default.
    days: int | None
    # How many days its events are kept for, whichever of the two that comes from.
    effective_days: int
    events: int
    oldest_at: AwareDatetime | None


class StorageOut(BaseModel):
    default_days: int
    sources: list[SourceOut]


class RetentionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # None goes back to the default.
    days: int | None = Field(strict=True, ge=MIN_DAYS, le=MAX_DAYS)


def _source(
    key: str, loaded: retention.Retention, stored: dict[str, retention.Stored]
) -> SourceOut:
    found = stored.get(key)
    return SourceOut(
        source=key,
        name=registry.INTEGRATIONS[key].name,
        days=loaded.own.get(key),
        effective_days=loaded.days(key),
        events=found.rows if found else 0,
        oldest_at=found.oldest if found else None,
    )


def _storage(db: Session, settings: Settings) -> StorageOut:
    loaded = retention.load(db, settings)
    stored = retention.stored(db)
    return StorageOut(
        default_days=loaded.default,
        sources=[_source(key, loaded, stored) for key in registry.INTEGRATIONS],
    )


@router.get("/storage")
def get_storage(db: Db, settings: SettingsDep) -> StorageOut:
    """Each integration's events: how many are kept, how old the oldest is and for how long they
    are kept."""
    return _storage(db, settings)


@router.put("/storage/{key}")
def set_retention(
    key: Key,
    body: RetentionIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
) -> SourceOut:
    """Sets how many days an integration's events are kept, or goes back to the default. The
    next clean-up removes what is older, which happens every few hours."""
    if key not in registry.INTEGRATIONS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no such integration.")
    retention.set_days(db, key, body.days)
    record_audit(
        db,
        request,
        Action.EVENT_RETENTION_CHANGED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"source": key, "days": "default" if body.days is None else body.days},
    )
    db.commit()
    loaded = retention.load(db, settings)
    return _source(key, loaded, retention.stored(db))
