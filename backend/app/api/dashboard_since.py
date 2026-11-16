"""What is new since the owner last looked at the dashboard, and the word that they have now."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import AwareDatetime, BaseModel

from app import since as news
from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.api.deps import Db, SignedIn, signed_in
from app.models import utcnow

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(signed_in)])


class SinceOut(BaseModel):
    # When this account last looked, or None on its first visit.
    since: AwareDatetime | None
    # Incidents that began since, by how serious, which the incident list shows by default.
    incidents: dict[SeverityName, int]
    cleared_by_ai: int
    new_devices: int
    # How many things there are in all, so a page can say nothing at 0.
    total: int


@router.get("/since")
def get_since(db: Db, auth: Annotated[SignedIn, Depends(signed_in)]) -> SinceOut:
    """What began, what the AI cleared and which devices appeared since this account last looked
    at the dashboard. The first visit says nothing, and starts the count."""
    found = news.of(db, auth.user.id, utcnow())
    db.commit()
    return SinceOut(
        since=found.after,
        incidents={name: found.incidents.get(level, 0) for level, name in SEVERITY_NAMES.items()},
        cleared_by_ai=found.cleared_by_ai,
        new_devices=found.new_devices,
        total=found.total,
    )


@router.post("/seen", status_code=status.HTTP_204_NO_CONTENT)
def mark_seen(db: Db, auth: Annotated[SignedIn, Depends(signed_in)]) -> Response:
    """Says the account has now looked, so the next visit is compared with this one."""
    news.seen(db, auth.user.id, utcnow())
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
