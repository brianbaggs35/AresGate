"""Trends: how things have been going over the last hours and days, for the pages that list the
present. For someone signed in."""

from ipaddress import ip_address
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AwareDatetime, BaseModel, Field

from app import trends
from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.api.deps import Db, signed_in
from app.models import utcnow
from app.trends import HourState, Step

router = APIRouter(prefix="/trends", tags=["trends"], dependencies=[Depends(signed_in)])

MOST_HOURS = trends.MOST_BUCKETS
MOST_ADDRESSES = 50
KindId = Annotated[int, Field(ge=1, le=2**63 - 1)]
Count = Annotated[int, Query(ge=2, le=MOST_HOURS)]


class DeliveryTrend(BaseModel):
    """Messages made in each bucket, by how serious what they were about."""

    times: list[AwareDatetime]
    step: Step
    severities: dict[SeverityName, list[int]]


class AddressTrend(BaseModel):
    incoming: list[int]
    outgoing: list[int]


class AddressTrends(BaseModel):
    """The events each address was in, in each bucket: the connections to it and from it."""

    times: list[AwareDatetime]
    step: Step
    items: dict[str, AddressTrend]


class KindTrends(BaseModel):
    """The incidents of each kind that began in each bucket."""

    times: list[AwareDatetime]
    step: Step
    items: dict[int, list[int]]


class IntegrationTrends(BaseModel):
    """How each integration's calls went in each bucket."""

    times: list[AwareDatetime]
    step: Step
    items: dict[str, list[HourState]]


@router.get("/deliveries")
def delivery_trend(
    db: Db,
    destination_id: Annotated[int | None, Query(ge=1, le=2**63 - 1)] = None,
    state: Annotated[str | None, Query(max_length=12)] = None,
    hours: Count = 48,
) -> DeliveryTrend:
    """Messages made per hour, by severity, for what the Alerts page is looking at."""
    starting = trends.starts(utcnow(), "hour", hours)
    found = trends.deliveries(db, starting, "hour", destination_id, state)
    return DeliveryTrend(
        times=starting,
        step="hour",
        severities={
            name: found.get(level, [0] * len(starting)) for level, name in SEVERITY_NAMES.items()
        },
    )


@router.get("/addresses")
def address_trends(
    db: Db,
    address: Annotated[list[str], Query(min_length=1, max_length=MOST_ADDRESSES)],
    step: Step = "day",
    count: Count = 7,
) -> AddressTrends:
    """The events each address was in, per hour or per day."""
    try:
        names = sorted({str(ip_address(one)) for one in address})
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "That is not an address."
        ) from None
    starting = trends.starts(utcnow(), step, count if step == "hour" else min(count, 90))
    found = trends.traffic(db, starting, step, names)
    return AddressTrends(
        times=starting,
        step=step,
        items={
            name: AddressTrend(incoming=incoming, outgoing=outgoing)
            for name, (incoming, outgoing) in found.items()
        },
    )


@router.get("/kinds")
def kind_trends(
    db: Db,
    id: Annotated[list[KindId], Query(min_length=1, max_length=MOST_ADDRESSES)],
    days: Annotated[int, Query(ge=2, le=90)] = 7,
) -> KindTrends:
    """Incidents of each kind that began per day."""
    starting = trends.starts(utcnow(), "day", days)
    return KindTrends(
        times=starting, step="day", items=trends.kinds(db, starting, "day", sorted(set(id)))
    )


@router.get("/integrations")
def integration_trends(db: Db, hours: Count = 24) -> IntegrationTrends:
    """How each integration's calls went, per hour."""
    starting = trends.starts(utcnow(), "hour", hours)
    return IntegrationTrends(
        times=starting, step="hour", items=trends.integrations(db, starting, "hour")
    )
