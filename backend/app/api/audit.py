"""Reading the audit log."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints

from app import audit
from app.api.deps import Db, signed_in
from app.audit import DEFAULT_PAGE, MAX_PAGE, Outcome

# Everything here is for someone who is signed in.
router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(signed_in)])


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    action: str
    outcome: Outcome
    user_id: UUID | None
    username: str | None
    client_address: str | None
    user_agent: str | None
    detail: dict[str, str | int | bool] | None


class AuditPage(BaseModel):
    events: list[AuditEventOut]
    # Pass it back as ``before`` for the next page of older events. Missing on the last page.
    next_before: int | None


@router.get("/events")
def list_events(
    db: Db,
    action: Annotated[
        list[Annotated[str, StringConstraints(max_length=64)]] | None,
        Query(description="Only these actions, e.g. auth.login_failed. Repeat it for several."),
    ] = None,
    outcome: Outcome | None = None,
    username: Annotated[str | None, Query(max_length=64)] = None,
    since: Annotated[AwareDatetime | None, Query(description="From this time on.")] = None,
    until: Annotated[AwareDatetime | None, Query(description="Before this time.")] = None,
    before: Annotated[int | None, Query(ge=1, description="Older than this event id.")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = DEFAULT_PAGE,
) -> AuditPage:
    """The audit log, newest first."""
    page = audit.list_events(
        db,
        actions=action or (),
        outcome=outcome,
        username=username,
        since=since,
        until=until,
        before=before,
        limit=limit,
    )
    return AuditPage(
        events=[AuditEventOut.model_validate(event) for event in page.events],
        next_before=page.next_before,
    )
