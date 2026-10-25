"""How long each integration's samples are kept, and how many there are. For someone signed in.
The samples themselves are read by the pages that chart them."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import AwareDatetime, BaseModel
from sqlalchemy.orm import Session

from app.api.deps import Db, SettingsDep, SignedIn, record_audit, signed_in
from app.api.events import Key, RetentionIn
from app.audit import Action, Outcome
from app.config import Settings
from app.integrations import registry
from app.metrics import retention

router = APIRouter(prefix="/metrics", tags=["metrics"], dependencies=[Depends(signed_in)])


class MetricSourceOut(BaseModel):
    """What is kept of one integration's samples."""

    source: str
    name: str
    # The days set for this integration, or None while it keeps them for the default.
    days: int | None
    # How many days its samples are kept for, whichever of the two that comes from.
    effective_days: int
    samples: int
    oldest_at: AwareDatetime | None


class MetricStorageOut(BaseModel):
    default_days: int
    sources: list[MetricSourceOut]


def _source(
    key: str, loaded: retention.Retention, stored: dict[str, retention.Stored]
) -> MetricSourceOut:
    found = stored.get(key)
    return MetricSourceOut(
        source=key,
        name=registry.INTEGRATIONS[key].name,
        days=loaded.own.get(key),
        effective_days=loaded.days(key),
        samples=found.rows if found else 0,
        oldest_at=found.oldest if found else None,
    )


def _storage(db: Session, settings: Settings) -> MetricStorageOut:
    loaded = retention.load(db, settings)
    stored = retention.stored(db)
    return MetricStorageOut(
        default_days=loaded.default,
        sources=[_source(key, loaded, stored) for key in registry.INTEGRATIONS],
    )


@router.get("/storage")
def get_storage(db: Db, settings: SettingsDep) -> MetricStorageOut:
    """Each integration's samples: how many are kept, how old the oldest is and for how long they
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
) -> MetricSourceOut:
    """Sets how many days an integration's samples are kept, or goes back to the default. The
    next clean-up removes what is older, which happens every few hours."""
    if key not in registry.INTEGRATIONS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no such integration.")
    retention.set_days(db, key, body.days)
    record_audit(
        db,
        request,
        Action.METRIC_RETENTION_CHANGED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"source": key, "days": "default" if body.days is None else body.days},
    )
    db.commit()
    loaded = retention.load(db, settings)
    return _source(key, loaded, retention.stored(db))
