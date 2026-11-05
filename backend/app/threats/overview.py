"""The Threats page's numbers: how many reports it took to make the incidents that are going on,
and how they divide into threats, suspects and background; and the kinds of incident (families)
those are made of.

Each step of the funnel is one of the ways AresGate keeps a real attack from being lost: the same
alert reported by two programs counts once (``Event.twin_of``), the same alert again and again
counts once for a stretch of time (``app/dashboard.py``), and what is left is grouped into
incidents, which are told apart by how sure it is that they are real
(``app/incidents/attention.py``).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app import dashboard
from app.events.event import Severity
from app.incidents import attention
from app.incidents.attention import ACTIVE, Lane
from app.models import Incident, IncidentFamily
from app.threats.settings import Tuning


@dataclass(frozen=True)
class Funnel:
    """From what programs reported to what needs a person, over a window."""

    # How many alerts programs reported.
    reports: int
    # How many of those another program had already reported.
    duplicates: int
    # How many were an alert said again in the same stretch of time.
    repeats: int
    # What is left: each alert once.
    alerts: int
    # The incidents they make that were going on, and the kinds of those incidents.
    incidents: int
    families: int
    # Where they stand: threats, suspects and background (unsure, or set aside by an AI), and those
    # the owner called not suspicious or low priority, and those that are over.
    threats: int
    suspects: int
    background: int
    muted: int
    handled: int


@dataclass(frozen=True)
class Coverage:
    """How much of the kinds of incident the AI has judged."""

    # Kinds with an incident going on, and how many of them an AI has judged, the owner has called,
    # or are waiting to be judged.
    families: int
    judged: int
    owned: int
    waiting: int


def funnel(db: Session, win: dashboard.Window, floor: int, tuning: Tuning) -> Funnel:
    found = dashboard.alerts(db, win)
    standing = dashboard.attention(db, win, floor, tuning)
    kinds = (
        db.scalar(
            select(func.count(Incident.family_id.distinct())).where(
                Incident.first_seen_at < win.end,
                Incident.last_seen_at >= win.start,
                Incident.status.in_(ACTIVE),
            )
        )
        or 0
    )
    return Funnel(
        reports=found.reports,
        duplicates=found.duplicates,
        repeats=max(found.reports - found.duplicates - found.total, 0),
        alerts=found.total,
        incidents=standing.incidents,
        families=kinds,
        threats=standing.urgent,
        suspects=standing.needs_you - standing.urgent,
        background=standing.unsure + standing.cleared,
        muted=standing.muted,
        handled=standing.handled,
    )


def coverage(db: Session) -> Coverage:
    """How many of the kinds that are going on have been judged."""
    going = select(Incident.family_id).where(
        Incident.status.in_(ACTIVE), Incident.family_id.is_not(None)
    )
    row = db.execute(
        select(
            func.count(),
            func.count().filter(
                IncidentFamily.owner_call.is_(None), IncidentFamily.judged_at.is_not(None)
            ),
            func.count().filter(IncidentFamily.owner_call.is_not(None)),
            func.count().filter(
                IncidentFamily.owner_call.is_(None), IncidentFamily.judged_at.is_(None)
            ),
        ).where(IncidentFamily.id.in_(going))
    ).one()
    return Coverage(*row)


@dataclass(frozen=True)
class Kind:
    """A family and what its incidents that are going on come to."""

    family: IncidentFamily
    incidents: int
    alerts: int
    actors: int
    worst: Severity
    first_at: datetime
    last_at: datetime
    threats: int
    suspects: int
    background: int


@dataclass(frozen=True)
class Kinds:
    total: int
    items: list[Kind]


def kinds(
    db: Session,
    floor: int,
    tuning: Tuning,
    *,
    lane: Lane | None = None,
    judged: str | None = None,
    text: str = "",
    limit: int = 20,
    offset: int = 0,
    family_id: int | None = None,
) -> Kinds:
    """The families that have an incident going on: those with one in the lane, or that the AI has
    judged, or the owner has called, or neither, or whose words contain the text. The ones with
    threats first, then suspects, then the biggest."""
    by = attention.lane_clauses(floor, tuning)
    threats = func.count().filter(by[Lane.THREAT])
    suspects = func.count().filter(by[Lane.SUSPECT])
    background = func.count().filter(by[Lane.BACKGROUND])
    counted = (
        select(
            IncidentFamily,
            func.count().label("incidents"),
            func.coalesce(func.sum(Incident.signal_count), 0).label("alerts"),
            func.count(Incident.subject.distinct()).label("actors"),
            func.max(Incident.severity).label("worst"),
            func.min(Incident.first_seen_at).label("first_at"),
            func.max(Incident.last_seen_at).label("last_at"),
            threats.label("threats"),
            suspects.label("suspects"),
            background.label("background"),
        )
        .join(Incident, Incident.family_id == IncidentFamily.id)
        .where(Incident.status.in_(ACTIVE))
        .group_by(IncidentFamily.id)
    )
    after: list[ColumnElement[bool]] = []
    if family_id is not None:
        counted = counted.where(IncidentFamily.id == family_id)
    if text:
        counted = counted.where(IncidentFamily.label.icontains(text, autoescape=True))
    if judged == "ai":
        counted = counted.where(IncidentFamily.judged_at.is_not(None))
    elif judged == "owner":
        counted = counted.where(IncidentFamily.owner_call.is_not(None))
    elif judged == "waiting":
        counted = counted.where(
            IncidentFamily.judged_at.is_(None), IncidentFamily.owner_call.is_(None)
        )
    if lane is Lane.THREAT:
        after.append(threats > 0)
    elif lane is Lane.SUSPECT:
        after.append(suspects > 0)
    elif lane is Lane.BACKGROUND:
        after.append(background > 0)
    for condition in after:
        counted = counted.having(condition)
    total = db.scalar(select(func.count()).select_from(counted.subquery())) or 0
    rows = db.execute(
        counted.order_by(threats.desc(), suspects.desc(), func.count().desc(), IncidentFamily.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return Kinds(
        total=total,
        items=[
            Kind(
                family=row[0],
                incidents=row.incidents,
                alerts=row.alerts,
                actors=row.actors,
                worst=Severity(row.worst),
                first_at=row.first_at,
                last_at=row.last_at,
                threats=row.threats,
                suspects=row.suspects,
                background=row.background,
            )
            for row in rows
        ],
    )
