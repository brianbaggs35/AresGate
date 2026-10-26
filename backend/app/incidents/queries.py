"""Reading incidents: what the API lists and shows."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Final

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.events.event import Severity
from app.models import INCIDENT_STATUSES, Device, DeviceAddress, Event, Incident, IncidentSignal

# How far either side of an incident the firewall's blocks of its address still count as part of
# the picture: it often turns the address away before anything else notices it.
CONTEXT: Final = timedelta(hours=1)


@dataclass(frozen=True)
class Page:
    """One page of a search, and how many incidents it found in all."""

    total: int
    incidents: list[Incident]


def search(
    db: Session,
    *,
    statuses: list[str],
    min_severity: Severity | None,
    min_confidence: int,
    address: IPv4Address | IPv6Address | None,
    since: datetime | None,
    limit: int,
    offset: int,
) -> Page:
    """Incidents that match, the ones that were going most recently first. Nothing given
    matches everything."""
    conditions: list[ColumnElement[bool]] = []
    if statuses:
        conditions.append(Incident.status.in_(statuses))
    if min_severity is not None:
        conditions.append(Incident.severity >= min_severity)
    if min_confidence:
        conditions.append(Incident.confidence >= min_confidence)
    if address is not None:
        conditions.append(Incident.addresses.contains([address]))
    if since is not None:
        conditions.append(Incident.last_seen_at >= since)
    total = db.scalar(select(func.count()).select_from(Incident).where(*conditions)) or 0
    found = db.scalars(
        select(Incident)
        .where(*conditions)
        .order_by(Incident.last_seen_at.desc(), Incident.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return Page(total=total, incidents=list(found))


def counts(db: Session) -> dict[str, int]:
    """How many incidents there are in each status, whatever a search is for."""
    rows = db.execute(select(Incident.status, func.count()).group_by(Incident.status)).all()
    found = dict(rows)
    return {status: found.get(status, 0) for status in INCIDENT_STATUSES}


def get(db: Session, incident_id: int) -> Incident | None:
    return db.get(Incident, incident_id)


def signals(db: Session, incident: Incident) -> list[IncidentSignal]:
    """The timeline: the signals that were kept, oldest first."""
    return list(
        db.scalars(
            select(IncidentSignal)
            .where(IncidentSignal.incident_id == incident.id)
            .order_by(IncidentSignal.occurred_at, IncidentSignal.id)
        )
    )


def devices(db: Session, incident: Incident) -> list[tuple[IPv4Address | IPv6Address, Device]]:
    """The devices on the network behind the incident's addresses, the subject's first. An
    address a device no longer has is the device it was last seen with."""
    if not incident.addresses:
        return []
    rows = db.execute(
        select(DeviceAddress.address, Device)
        .join(Device, Device.id == DeviceAddress.device_id)
        .where(DeviceAddress.address.in_(incident.addresses))
        .order_by(DeviceAddress.last_seen_at.desc(), Device.id)
    ).all()
    latest: dict[IPv4Address | IPv6Address, Device] = {}
    for address, device in rows:
        latest.setdefault(address, device)
    return [(address, latest[address]) for address in incident.addresses if address in latest]


def blocks(db: Session, incident: Incident) -> int | None:
    """How many times the firewall turned the incident's address away around the time of it, or
    None for an incident about a rule rather than an address. They aren't part of it, because
    the internet knocks all day, but they say how persistent it was."""
    if incident.subject.startswith("rule:"):
        return None
    return db.scalar(
        select(func.count()).where(
            Event.kind == "firewall",
            Event.severity >= Severity.LOW,
            Event.src_address == ip_address(incident.subject),
            Event.occurred_at >= incident.first_seen_at - CONTEXT,
            Event.occurred_at <= incident.last_seen_at + CONTEXT,
        )
    )
