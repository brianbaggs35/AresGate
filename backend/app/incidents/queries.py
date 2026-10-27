"""Reading incidents: what the API lists and shows."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address
from typing import Any, Final, Literal

from sqlalchemy import ColumnElement, false, func, or_, select, true
from sqlalchemy.orm import Session

from app.events.event import Severity
from app.incidents.verdicts import MUTING
from app.models import INCIDENT_STATUSES, Device, DeviceAddress, Incident, IncidentSignal

# How far either side of an incident the firewall's blocks of its address still count as part of
# the picture: it often turns the address away before anything else notices it.
CONTEXT: Final = timedelta(hours=1)
# What to search for to find the incidents no verdict has been given to.
NO_VERDICT: Final = "none"

# The order a search comes in: what was going on most recently, or what most needs a decision.
Order = Literal["recent", "priority"]
_ORDERINGS: Final[dict[Order, tuple[ColumnElement[Any], ...]]] = {
    "recent": (Incident.last_seen_at.desc(), Incident.id.desc()),
    "priority": (
        Incident.severity.desc(),
        Incident.confidence.desc(),
        Incident.last_seen_at.desc(),
        Incident.id.desc(),
    ),
}


@dataclass(frozen=True)
class Facets:
    """How the incidents a search found are spread: how many are at each severity, and how many
    each integration reported part of (an incident several reported counts for each)."""

    severity: dict[int, int]
    source: dict[str, int]


@dataclass(frozen=True)
class Page:
    """One page of a search, and how many incidents it found in all."""

    total: int
    incidents: list[Incident]
    facets: Facets
    # How many more would have matched if the owner's verdicts weren't asked about: the ones they
    # said are not suspicious or low priority, which a search for anything else leaves out.
    quieted: int


def _verdict_condition(verdicts: list[str]) -> ColumnElement[bool]:
    """Incidents the owner said this of. A verdict of none is those they said nothing of."""
    wanted = [verdict for verdict in verdicts if verdict != NO_VERDICT]
    nothing = Incident.verdict.is_(None) if NO_VERDICT in verdicts else false()
    return or_(Incident.verdict.in_(wanted), nothing)


def conditions(
    *,
    statuses: list[str],
    min_severity: Severity | None,
    min_confidence: int,
    address: IPv4Address | IPv6Address | None,
    since: datetime | None,
    extra: Sequence[ColumnElement[bool]] = (),
) -> list[ColumnElement[bool]]:
    """What the incidents of a search have to be, except what the owner said of them. Nothing
    given matches everything. ``extra`` is what else has to be true (see search.py)."""
    found: list[ColumnElement[bool]] = list(extra)
    if statuses:
        found.append(Incident.status.in_(statuses))
    if min_severity is not None:
        found.append(Incident.severity >= min_severity)
    if min_confidence:
        found.append(Incident.confidence >= min_confidence)
    if address is not None:
        found.append(Incident.addresses.contains([address]))
    if since is not None:
        found.append(Incident.last_seen_at >= since)
    return found


def _asked(where: Sequence[ColumnElement[bool]], verdicts: list[str]) -> list[ColumnElement[bool]]:
    """The conditions with what the owner said of the incidents, if that was asked about."""
    return [*where, _verdict_condition(verdicts)] if verdicts else list(where)


def search(
    db: Session,
    *,
    verdicts: list[str],
    where: Sequence[ColumnElement[bool]],
    limit: int,
    offset: int,
    order: Order = "recent",
) -> Page:
    """Incidents that meet the conditions (see ``conditions``), the ones that were going most
    recently first, or the most serious and surest first. A verdict of none is the incidents the
    owner has said nothing of."""
    quieted = (
        db.scalar(
            select(func.count()).select_from(Incident).where(*where, Incident.verdict.in_(MUTING))
        )
        or 0
    )
    asked = _asked(where, verdicts)
    total = db.scalar(select(func.count()).select_from(Incident).where(*asked)) or 0
    found = db.scalars(
        select(Incident).where(*asked).order_by(*_ORDERINGS[order]).limit(limit).offset(offset)
    ).all()
    return Page(total=total, incidents=list(found), facets=facets(db, asked), quieted=quieted)


def selected(
    db: Session, *, verdicts: list[str], where: Sequence[ColumnElement[bool]], limit: int
) -> tuple[int, list[Incident]]:
    """How many incidents meet the conditions, and those of them, the lowest ids first, unless
    there are more than the limit: then none, since a change must not be made to some only."""
    asked = _asked(where, verdicts)
    total = db.scalar(select(func.count()).select_from(Incident).where(*asked)) or 0
    if total > limit:
        return total, []
    return total, list(db.scalars(select(Incident).where(*asked).order_by(Incident.id)))


def facets(db: Session, conditions: Sequence[ColumnElement[bool]]) -> Facets:
    """How many of the incidents that meet the conditions are at each severity, and how many
    each integration reported part of."""
    severity = db.execute(
        select(Incident.severity, func.count()).where(*conditions).group_by(Incident.severity)
    ).all()
    reporting = func.unnest(Incident.sources).table_valued("source").render_derived()
    sources = db.execute(
        select(reporting.c.source, func.count())
        .select_from(Incident)
        .join(reporting, true())
        .where(*conditions)
        .group_by(reporting.c.source)
    ).all()
    return Facets(severity=dict(severity), source=dict(sources))


def counts(db: Session, verdicts: list[str]) -> dict[str, int]:
    """How many incidents there are in each status, whatever else a search is for, among the
    ones the verdicts asked for (all of them if none were)."""
    query = select(Incident.status, func.count()).group_by(Incident.status)
    if verdicts:
        query = query.where(_verdict_condition(verdicts))
    found = dict(db.execute(query).all())
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
