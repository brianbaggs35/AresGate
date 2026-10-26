"""Correlation: turning the events the integrations stored into incidents.

Each run reads the signals that arrived since the last one and gives each to the incident it
belongs to, or starts one. A signal belongs to the incident about the same subject (see
``subject.py``) that is still going: not resolved, and not longer than ``GAP`` since its last
signal. The program that saw it doesn't matter, which is the point: Suricata's alert, Wazuh's
log line, the firewall's block and CrowdSec's ban of one address are one incident, and each
program that agrees makes it more certain (see ``rules.py``).

What is a signal is deliberately narrow. Alerts and bans of at least low severity are; the
firewall's blocks are not, because the internet knocks all day and a block says the firewall
worked. Nothing here needs the analyst, which reads and extends incidents later.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.events.event import Severity
from app.incidents import rules
from app.incidents.subject import Address, addresses_of, subject_of
from app.models import Event, Incident, IncidentSignal, SystemInfo

# The kinds of event that can be part of an incident, and how serious one has to be.
KINDS: Final = ("alert", "decision")
MIN_SEVERITY: Final = Severity.LOW
# An incident that has been quiet this long is over, and the next signal about the same subject
# starts another: a scan on Monday and another on Friday are two.
GAP: Final = timedelta(hours=6)
# An event is read once it has been stored this long, so one that was written by a slow run
# can't be passed over by a run that began after it in time but numbered before it.
SETTLE: Final = timedelta(seconds=30)
# How far back an event may have happened and still be read, which is also how far back the
# first run looks.
LOOKBACK: Final = timedelta(hours=24)
# How many events one run reads: a run that reads this many has more to do.
BATCH: Final = 1000
# How many signals an incident lists. More are counted, and still change its severity, its
# programs and its end.
MAX_SIGNALS: Final = 1000
MAX_ADDRESSES: Final = 50

# The id of the last event that was read, so the next run begins after it.
CURSOR: Final = "incidents.cursor"
# Held while a run is under way, so that two never are; the same lock key as the partitions'
# (0x41524553) with its last digit changed.
LOCK: Final = 0x41524554


@dataclass(frozen=True)
class Result:
    """What a run did."""

    events: int = 0
    created: int = 0
    updated: int = 0
    # There were more waiting than one run reads.
    behind: bool = False
    # Another run had the lock.
    skipped: bool = False


def _cursor(db: Session) -> int:
    row = db.get(SystemInfo, CURSOR)
    return int(row.value) if row else 0


def _move_cursor(db: Session, event_id: int) -> None:
    row = db.get(SystemInfo, CURSOR)
    if row is None:
        db.add(SystemInfo(key=CURSOR, value=str(event_id)))
    else:
        row.value = str(event_id)


def _current(db: Session, subject: str, when: datetime) -> Incident | None:
    """The incident about the subject that a signal at that time belongs to."""
    return db.scalars(
        select(Incident)
        .where(
            Incident.subject == subject,
            Incident.status != "resolved",
            Incident.last_seen_at >= when - GAP,
            Incident.first_seen_at <= when + GAP,
        )
        .order_by(Incident.last_seen_at.desc())
        .limit(1)
    ).first()


def _start(db: Session, event: Event, subject: str) -> Incident:
    incident = Incident(
        subject=subject,
        title=subject,
        severity=event.severity,
        confidence=0,
        first_seen_at=event.occurred_at,
        last_seen_at=event.occurred_at,
        top_source=event.source,
        top_summary=event.signature or event.summary,
        signal_count=0,
        sources=[],
        addresses=[],
        banned=False,
    )
    db.add(incident)
    # Its id is needed for its signals.
    db.flush()
    return incident


def _join(db: Session, incident: Incident, event: Event, subject: str) -> None:
    """Adds a signal to an incident, and what it changes in the summary."""
    if incident.signal_count < MAX_SIGNALS:
        db.add(
            IncidentSignal(
                incident_id=incident.id,
                event_id=event.id,
                occurred_at=event.occurred_at,
                source=event.source,
                kind=event.kind,
                severity=event.severity,
                summary=event.summary,
                signature=event.signature,
                src_address=event.src_address,
                src_port=event.src_port,
                dst_address=event.dst_address,
                dst_port=event.dst_port,
                protocol=event.protocol,
            )
        )
    incident.signal_count += 1
    incident.first_seen_at = min(incident.first_seen_at, event.occurred_at)
    incident.last_seen_at = max(incident.last_seen_at, event.occurred_at)
    if event.severity > incident.severity:
        incident.severity = event.severity
        incident.top_source = event.source
        incident.top_summary = event.signature or event.summary
    if event.source not in incident.sources:
        incident.sources = sorted({*incident.sources, event.source})
    incident.addresses = _with(incident.addresses, addresses_of(event), subject)
    incident.banned = incident.banned or event.kind == "decision"


def _with(known: list[Address], new: list[Address], subject: str) -> list[Address]:
    """The addresses an incident names, with the new ones added, the subject first."""
    wanted = [address for address in new if address not in known]
    if not wanted or len(known) >= MAX_ADDRESSES:
        return known
    return sorted([*known, *wanted], key=lambda address: str(address) != subject)[:MAX_ADDRESSES]


def _score(incident: Incident) -> None:
    others = [address for address in incident.addresses if str(address) != incident.subject]
    facts = rules.Facts(
        subject=incident.subject,
        severity=Severity(incident.severity),
        top_source=incident.top_source,
        top_summary=incident.top_summary,
        sources=incident.sources,
        signal_count=incident.signal_count,
        banned=incident.banned,
        others=len(others),
    )
    assessment = rules.assess(facts)
    incident.confidence = assessment.confidence
    incident.reasons = assessment.as_json()
    incident.title = rules.title_of(facts)


def correlate(db: Session, now: datetime) -> Result:
    """One run: reads the signals stored since the last, and files them. The caller commits, so
    that the incidents and the place the run got to are saved together or not at all."""
    if not db.scalar(select(func.pg_try_advisory_xact_lock(LOCK))):
        return Result(skipped=True)
    events = db.scalars(
        select(Event)
        .where(
            Event.id > _cursor(db),
            Event.occurred_at >= now - LOOKBACK,
            Event.received_at <= now - SETTLE,
            Event.kind.in_(KINDS),
            Event.severity >= MIN_SEVERITY,
        )
        .order_by(Event.id)
        .limit(BATCH)
    ).all()
    if not events:
        return Result()
    last = events[-1].id
    touched: dict[int, Incident] = {}
    created = 0
    # In the order they happened, so a signal that was stored late still lands in place.
    for event in sorted(events, key=lambda item: (item.occurred_at, item.id)):
        subject = subject_of(event)
        incident = _current(db, subject, event.occurred_at)
        if incident is None:
            incident = _start(db, event, subject)
            created += 1
        _join(db, incident, event, subject)
        touched[incident.id] = incident
    for incident in touched.values():
        _score(incident)
    _move_cursor(db, last)
    return Result(
        events=len(events),
        created=created,
        updated=len(touched) - created,
        behind=len(events) == BATCH,
    )
