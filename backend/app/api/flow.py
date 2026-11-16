"""Network flow: where the traffic goes, as the firewall's log tells it. Read-only, for someone
signed in. The paths are put together in app/flows.py."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AwareDatetime, BaseModel

from app.api.deps import Db, signed_in
from app.flows import HOURS, Column, Direction, Scope, build
from app.models import utcnow

router = APIRouter(prefix="/flow", tags=["flow"], dependencies=[Depends(signed_in)])


class NodeOut(BaseModel):
    """A block in one of the three columns: an address that connected, a service, or an address
    that was reached. "Others" folds the ones that were too small to draw."""

    id: str
    column: Column
    label: str
    # What an address on the internet is called, when its reverse lookup is kept.
    name: str | None
    scope: Scope | None
    protocol: str | None
    port: int | None
    events: int
    blocked: int
    # How many nodes an "others" holds.
    folded: int


class LinkOut(BaseModel):
    source: str
    target: str
    events: int
    blocked: int


class BarOut(BaseModel):
    at: AwareDatetime
    allowed: int
    blocked: int


class FlowOut(BaseModel):
    hours: int
    direction: Direction
    since: AwareDatetime
    until: AwareDatetime
    # How wide each bar of the timeline is.
    stride_seconds: int
    events: int
    blocked: int
    nodes: list[NodeOut]
    links: list[LinkOut]
    timeline: list[BarOut]
    # Whether there were more paths than are read, so this is the busiest of them.
    capped: bool


@router.get("")
def get_flow(
    db: Db,
    hours: Annotated[int, Query(description="1, 6, 24 or 168")] = 24,
    direction: Annotated[Direction, Query()] = "all",
) -> FlowOut:
    """The connections the firewall wrote down in the last hour, six hours, day or week, as paths
    from the address that connected through the service to the address it reached."""
    if hours not in HOURS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Ask for the last 1, 6, 24 or 168 hours.",
        )
    flow = build(db, utcnow(), hours, direction)
    return FlowOut(
        hours=flow.hours,
        direction=flow.direction,
        since=flow.since,
        until=flow.until,
        stride_seconds=flow.stride_seconds,
        events=flow.events,
        blocked=flow.blocked,
        nodes=[NodeOut(**node.__dict__) for node in flow.nodes],
        links=[LinkOut(**link.__dict__) for link in flow.links],
        timeline=[BarOut(**bar.__dict__) for bar in flow.timeline],
        capped=flow.capped,
    )
