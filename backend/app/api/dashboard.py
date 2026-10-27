"""What the dashboard shows. For someone signed in."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel

from app import dashboard
from app.api.deps import Db, signed_in
from app.events.event import Severity
from app.integrations import registry
from app.models import Event, Incident, utcnow

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(signed_in)])

SeverityName = Literal["info", "low", "medium", "high", "critical"]
# The words the web app uses for each severity.
SEVERITY_NAMES: dict[Severity, SeverityName] = {
    Severity.INFO: "info",
    Severity.LOW: "low",
    Severity.MEDIUM: "medium",
    Severity.HIGH: "high",
    Severity.CRITICAL: "critical",
}


class WindowOut(BaseModel):
    """The stretch of time the numbers are for, and when each bucket of it starts."""

    key: str
    start: AwareDatetime
    end: AwareDatetime
    # The counts have a number for each of these, and the traffic for each of its own.
    buckets: list[AwareDatetime]
    traffic_buckets: list[AwareDatetime]


class CountOut(BaseModel):
    """How many in the window and in the one before, and how many in each bucket."""

    total: int
    previous: int
    per_bucket: list[int]


class AlertsOut(BaseModel):
    total: int
    previous: int
    # The most serious alert there was, or None when there were none.
    highest: SeverityName | None
    # How many of each severity in each bucket.
    by_severity: dict[SeverityName, list[int]]


class AlertOut(BaseModel):
    id: int
    occurred_at: AwareDatetime
    # The integration that reported it, such as wazuh, and what it is called.
    source: str
    source_name: str
    severity: SeverityName
    summary: str
    signature: str | None
    src_address: str | None
    dst_address: str | None


class SourceOut(BaseModel):
    address: str
    count: int


class BlockedOut(CountOut):
    top_sources: list[SourceOut]


class InterfaceOut(BaseModel):
    """How fast one interface went in each bucket, in bits a second, and None where it can't be
    told."""

    interface: str
    received: list[float | None]
    sent: list[float | None]


class DevicesOut(BaseModel):
    total: int
    new: int


class IncidentMarkOut(BaseModel):
    """An incident that was going on in the window, for a flag on the charts."""

    id: int
    title: str
    # What it is about: an address, or a rule when it names none.
    subject: str
    severity: SeverityName
    confidence: int
    status: str
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime
    banned: bool


class DashboardOut(BaseModel):
    window: WindowOut
    alerts: AlertsOut
    recent_alerts: list[AlertOut]
    blocked: BlockedOut
    traffic: list[InterfaceOut]
    devices: DevicesOut
    # The incidents to flag on the charts, in the order they began.
    marks: list[IncidentMarkOut]


def _mark(incident: Incident) -> IncidentMarkOut:
    return IncidentMarkOut(
        id=incident.id,
        title=incident.title,
        subject=incident.subject,
        severity=SEVERITY_NAMES[Severity(incident.severity)],
        confidence=incident.confidence,
        status=incident.status,
        first_seen_at=incident.first_seen_at,
        last_seen_at=incident.last_seen_at,
        banned=incident.banned,
    )


def _alert(event: Event) -> AlertOut:
    integration = registry.INTEGRATIONS.get(event.source)
    return AlertOut(
        id=event.id,
        occurred_at=event.occurred_at,
        source=event.source,
        source_name=integration.name if integration else event.source,
        severity=SEVERITY_NAMES[Severity(event.severity)],
        summary=event.summary,
        signature=event.signature,
        src_address=str(event.src_address) if event.src_address else None,
        dst_address=str(event.dst_address) if event.dst_address else None,
    )


def build(db: Db, key: str, now: datetime) -> DashboardOut:
    win = dashboard.window(key, now)
    found = dashboard.alerts(db, win)
    refused = dashboard.blocked(db, win)
    people = dashboard.devices(db, win)
    return DashboardOut(
        window=WindowOut(
            key=win.key,
            start=win.start,
            end=win.end,
            buckets=win.buckets(),
            traffic_buckets=win.buckets(win.traffic_bucket),
        ),
        alerts=AlertsOut(
            total=found.total,
            previous=found.previous,
            highest=SEVERITY_NAMES[found.highest] if found.highest is not None else None,
            by_severity={
                SEVERITY_NAMES[level]: counts for level, counts in found.by_severity.items()
            },
        ),
        recent_alerts=[_alert(event) for event in dashboard.recent_alerts(db, win)],
        blocked=BlockedOut(
            total=refused.total,
            previous=refused.previous,
            per_bucket=refused.per_bucket,
            top_sources=[
                SourceOut(address=str(source.address), count=source.count)
                for source in dashboard.top_blocked_sources(db, win)
            ],
        ),
        traffic=[
            InterfaceOut(interface=item.interface, received=item.received, sent=item.sent)
            for item in dashboard.traffic(db, win)
        ],
        devices=DevicesOut(total=people.total, new=people.new),
        marks=[_mark(incident) for incident in dashboard.marked_incidents(db, win)],
    )


@router.get("")
def get_dashboard(
    db: Db,
    window: Annotated[Literal["24h", "7d"], Query(description="How far back to look.")] = "24h",
) -> DashboardOut:
    """The numbers and charts on the dashboard for the last 24 hours or 7 days, each against the
    stretch of time before it."""
    return build(db, window, utcnow())
