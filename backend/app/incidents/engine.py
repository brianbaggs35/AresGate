"""Correlation: turning the events the integrations stored into incidents.

Each run reads the signals that arrived since the last one and gives each to the incident it
belongs to, or starts one. A signal belongs to the incident about the same subject (see
``subject.py``) that is still going: not resolved, and not longer than a gap since its last
signal. The program that saw it doesn't matter, which is the point: Suricata's alert, Wazuh's
log line, the firewall's block and CrowdSec's ban of one address are one incident, and each
program that agrees makes it more certain (see ``rules.py``).

A scan or a brute force also joins the incident that a neighbouring address of the same block
began, and an incident is not longer than a day, so what one bot does in an afternoon is one
incident, however many addresses and waves it takes, and tomorrow's is another (see
``episode.py``). Incidents that turn out to be one episode, such as ones from before this was
known, are merged.

What is a signal is deliberately narrow. Alerts and bans of at least low severity are; the
firewall's blocks are not, because the internet knocks all day and a block says the firewall
worked. Nothing here needs the analyst, which reads and extends incidents later.

The owner's verdicts (see ``verdicts.py``) are applied as each signal joins. One they have called
not suspicious or low priority is kept in the timeline and counted, but leaves everything the
incident says about itself to the signals that are not. ``reapply`` does it again for the
incidents that are not over after a verdict is given, changed or taken back.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.orm import Session

from app.events.event import Severity
from app.incidents import episode, rules, verdicts
from app.incidents.subject import Address, Signal, addresses_of, subject_of
from app.models import Event, Incident, IncidentSignal, SystemInfo, VerdictRule

# The kinds of event that can be part of an incident, and how serious one has to be.
KINDS: Final = ("alert", "decision")
MIN_SEVERITY: Final = Severity.LOW
# An incident that has been quiet this long is over, and the next signal about the same subject
# starts another: a scan on Monday and another on Friday are two. A scan is over sooner, a day
# of it is as long as an incident goes (see ``episode.py``).
GAP: Final = episode.DEFAULT_GAP
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
    # Incidents that were one episode and were merged into one.
    merged: int = 0
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


def _going(when: datetime, activity: str | None) -> ColumnElement[bool]:
    """Incidents a signal at that time can still join: not resolved, not quiet for longer than the
    gap for its activity, and not already a day long."""
    gap = episode.gap_of(activity)
    return and_(
        Incident.status != "resolved",
        Incident.last_seen_at >= when - gap,
        Incident.first_seen_at <= when + gap,
        Incident.first_seen_at > when - episode.MAX_SPAN,
    )


def _current(
    db: Session, subject: str, block: str | None, activity: str | None, when: datetime
) -> Incident | None:
    """The incident that a signal at that time belongs to: the one about the same subject that is
    still going, or failing that, one that an address of the same block began, for a scan or a
    brute force: botnets rent addresses next to each other."""
    going = _going(when, activity)
    same = db.scalars(
        select(Incident)
        .where(Incident.subject == subject, going)
        .order_by(Incident.last_seen_at.desc())
        .limit(1)
    ).first()
    if same is not None or block is None or activity not in episode.GROUPED:
        return same
    return db.scalars(
        select(Incident)
        .where(Incident.block == block, Incident.activities.contains([activity]), going)
        .order_by(Incident.last_seen_at.desc())
        .limit(1)
    ).first()


def _describe(incident: Incident, first: Signal) -> None:
    """Starts what an incident says about itself over, from the signal that opens it."""
    incident.severity = first.severity
    incident.top_source = first.source
    incident.top_summary = first.signature or first.summary
    incident.sources = []
    incident.addresses = []
    incident.activities = []
    incident.ports = []
    incident.banned = False


def _start(db: Session, event: Event, subject: str) -> Incident:
    incident = Incident(
        subject=subject,
        title=subject,
        confidence=0,
        first_seen_at=event.occurred_at,
        last_seen_at=event.occurred_at,
        signal_count=0,
        verdict_counts={},
        block=episode.block_of_subject(subject),
        waves=0,
    )
    _describe(incident, event)
    db.add(incident)
    # Its id is needed for its signals.
    db.flush()
    return incident


def _join(
    db: Session, incident: Incident, event: Event, verdict_rules: Sequence[VerdictRule]
) -> None:
    """Adds a signal to an incident, and what it changes in the summary."""
    previous = incident.last_seen_at if incident.signal_count else None
    rule = verdicts.judge(event, verdict_rules)
    verdict = rule.verdict if rule else None
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
                verdict=verdict,
                verdict_rule_id=rule.id if rule else None,
            )
        )
    _absorb(incident, event, verdict)
    incident.waves = episode.next_wave(incident.waves, previous, event.occurred_at)


def _absorb(incident: Incident, signal: Signal, verdict: str | None) -> None:
    """What a signal changes in an incident's summary. Every signal is counted and moves the
    times, but one the owner called not suspicious or low priority changes nothing else, unless
    every signal so far was such a one: then the incident is described by them, as it has to be
    by something, until a signal that counts turns up and takes over."""
    counting = incident.signal_count - verdicts.muted(incident.verdict_counts)
    muted = verdict in verdicts.MUTING
    incident.signal_count += 1
    incident.first_seen_at = min(incident.first_seen_at, signal.occurred_at)
    incident.last_seen_at = max(incident.last_seen_at, signal.occurred_at)
    if verdict is not None:
        incident.verdict_counts = {
            **incident.verdict_counts,
            verdict: incident.verdict_counts.get(verdict, 0) + 1,
        }
    if muted and counting:
        return
    if not muted and not counting and incident.signal_count > 1:
        _describe(incident, signal)
    if signal.severity > incident.severity:
        incident.severity = signal.severity
        incident.top_source = signal.source
        incident.top_summary = signal.signature or signal.summary
    if signal.source not in incident.sources:
        incident.sources = sorted({*incident.sources, signal.source})
    incident.addresses = _with(incident.addresses, addresses_of(signal), incident.subject)
    incident.banned = incident.banned or signal.kind == "decision"
    activity = episode.activity_of(signal)
    if activity is not None and activity not in incident.activities:
        incident.activities = sorted({*incident.activities, activity})
    incident.ports = episode.with_ports(incident.ports, signal.dst_port)


def _with(known: list[Address], new: list[Address], subject: str) -> list[Address]:
    """The addresses an incident names, with the new ones added, the subject first."""
    wanted = [address for address in new if address not in known]
    if not wanted or len(known) >= MAX_ADDRESSES:
        return known
    return sorted([*known, *wanted], key=lambda address: str(address) != subject)[:MAX_ADDRESSES]


def _score(incident: Incident) -> None:
    others = [address for address in incident.addresses if str(address) != incident.subject]
    muted = verdicts.muted(incident.verdict_counts)
    incident.verdict = verdicts.rollup(incident.verdict_counts, incident.signal_count)
    facts = rules.Facts(
        subject=incident.subject,
        severity=Severity(incident.severity),
        top_source=incident.top_source,
        top_summary=incident.top_summary,
        sources=incident.sources,
        signal_count=incident.signal_count - muted,
        banned=incident.banned,
        others=len(others),
        muted=muted,
        threats=incident.verdict_counts.get(verdicts.THREAT, 0),
        block=incident.block
        if episode.neighbours_of(incident.subject, incident.block, incident.addresses)
        else None,
    )
    assessment = rules.assess(facts)
    incident.confidence = assessment.confidence
    incident.reasons = assessment.as_json()
    incident.title = rules.title_of(facts)


def _shape(incident: Incident, signals: Sequence[IncidentSignal]) -> None:
    """Works out what an incident from before episodes were known has of them, from its signals
    as they were judged, and nothing else of it."""
    counting = [signal for signal in signals if signal.verdict not in verdicts.MUTING] or signals
    incident.block = episode.block_of_subject(incident.subject)
    # No signals at all can't happen, but a zero would have it looked at again for ever.
    incident.waves = episode.waves_of([signal.occurred_at for signal in signals]) if signals else 1
    incident.activities = sorted(
        {activity for signal in counting if (activity := episode.activity_of(signal))}
    )
    ports: list[int] = []
    for signal in counting:
        ports = episode.with_ports(ports, signal.dst_port)
    incident.ports = ports


def _signals_of(db: Session, incident: Incident) -> list[IncidentSignal]:
    return list(
        db.scalars(
            select(IncidentSignal)
            .where(IncidentSignal.incident_id == incident.id)
            .order_by(IncidentSignal.occurred_at, IncidentSignal.id)
        )
    )


def _backfill(db: Session) -> list[Incident]:
    """Gives the incidents from before episodes were known what they have of them, a batch at a
    time. Only the open ones are returned: they may be one episode with another."""
    old = db.scalars(
        select(Incident).where(Incident.waves == 0).order_by(Incident.id).limit(BATCH)
    ).all()
    for incident in old:
        _shape(incident, _signals_of(db, incident))
    return [incident for incident in old if incident.status != "resolved"]


def _fits(one: Incident, other: Incident) -> bool:
    """Whether two incidents are one episode: a scan or a brute force that both did, no further
    apart than the gap for it, and no longer together than an incident goes."""
    shared = next(
        (item for item in episode.GROUPED if item in one.activities and item in other.activities),
        None,
    )
    if shared is None:
        return False
    apart = max(one.first_seen_at, other.first_seen_at) - min(one.last_seen_at, other.last_seen_at)
    span = max(one.last_seen_at, other.last_seen_at) - min(one.first_seen_at, other.first_seen_at)
    return apart <= episode.gap_of(shared) and span < episode.MAX_SPAN


def _merge(
    db: Session, keep: Incident, drop: Incident, verdict_rules: Sequence[VerdictRule]
) -> None:
    """Folds one incident into the other: its signals (so their verdicts), its times and the last
    time its status was changed. Everything else is worked out again from the signals."""
    total = keep.signal_count + drop.signal_count
    for signal in _signals_of(db, drop):
        signal.incident_id = keep.id
    db.flush()
    keep.first_seen_at = min(keep.first_seen_at, drop.first_seen_at)
    keep.last_seen_at = max(keep.last_seen_at, drop.last_seen_at)
    keep.created_at = min(keep.created_at, drop.created_at)
    changed = [item for item in (keep.status_changed_at, drop.status_changed_at) if item]
    keep.status_changed_at = max(changed) if changed else None
    db.delete(drop)
    db.flush()
    _rebuild(db, keep, verdict_rules)
    # What an incident that outgrew its timeline saw is counted, if not listed.
    if keep.signal_count < total:
        keep.signal_count = total
        _score(keep)


def _consolidate(
    db: Session, touched: dict[int, Incident], verdict_rules: Sequence[VerdictRule]
) -> int:
    """Merges each incident that was touched with the ones of the same block and status that are
    one episode with it, the oldest keeping the rest. Incidents of another status are left as
    they are: someone changed that, and it is theirs to say. Returns how many were merged away."""
    merged = 0
    for incident in sorted(touched.values(), key=lambda item: (item.first_seen_at, item.id)):
        current = incident
        while current.id in touched and current.block is not None:
            others = db.scalars(
                select(Incident).where(
                    Incident.block == current.block,
                    Incident.id != current.id,
                    Incident.status == current.status,
                )
            ).all()
            other = next((item for item in others if _fits(current, item)), None)
            if other is None:
                break
            keep, drop = sorted((current, other), key=lambda item: (item.first_seen_at, item.id))
            _merge(db, keep, drop, verdict_rules)
            touched.pop(drop.id, None)
            touched[keep.id] = keep
            current = keep
            merged += 1
    return merged


def correlate(db: Session, now: datetime) -> Result:
    """One run: reads the signals stored since the last, and files them. The caller commits, so
    that the incidents and the place the run got to are saved together or not at all."""
    if not db.scalar(select(func.pg_try_advisory_xact_lock(LOCK))):
        return Result(skipped=True)
    verdict_rules = verdicts.load(db)
    old = _backfill(db)
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
    if not events and not old:
        return Result()
    touched: dict[int, Incident] = {}
    created = 0
    # In the order they happened, so a signal that was stored late still lands in place.
    for event in sorted(events, key=lambda item: (item.occurred_at, item.id)):
        subject = subject_of(event)
        incident = _current(
            db,
            subject,
            episode.block_of_subject(subject),
            episode.activity_of(event),
            event.occurred_at,
        )
        if incident is None:
            incident = _start(db, event, subject)
            created += 1
        _join(db, incident, event, verdict_rules)
        touched[incident.id] = incident
    filed = len(touched)
    for incident in touched.values():
        _score(incident)
    merged = _consolidate(db, {**{item.id: item for item in old}, **touched}, verdict_rules)
    if events:
        _move_cursor(db, events[-1].id)
    return Result(
        events=len(events),
        created=created,
        updated=filed - created,
        merged=merged,
        behind=len(events) == BATCH,
    )


def _rebuild(db: Session, incident: Incident, verdict_rules: Sequence[VerdictRule]) -> None:
    """Works an incident's summary out again from its signals, judged by the rules as they are."""
    signals = db.scalars(
        select(IncidentSignal)
        .where(IncidentSignal.incident_id == incident.id)
        .order_by(IncidentSignal.occurred_at, IncidentSignal.id)
    ).all()
    first, last = incident.first_seen_at, incident.last_seen_at
    _describe(incident, signals[0])
    incident.signal_count = 0
    incident.verdict_counts = {}
    for signal in signals:
        rule = verdicts.judge(signal, verdict_rules)
        signal.verdict = rule.verdict if rule else None
        signal.verdict_rule_id = rule.id if rule else None
        _absorb(incident, signal, signal.verdict)
    # What an incident that outgrew its timeline saw after it is not there to be read again, but
    # it was seen, and the incident still ends when it did.
    incident.first_seen_at = min(first, incident.first_seen_at)
    incident.last_seen_at = max(last, incident.last_seen_at)
    incident.waves = episode.waves_of([signal.occurred_at for signal in signals])
    _score(incident)


def hold(db: Session) -> None:
    """Waits for a run that is under way, and keeps the next from starting, until the caller
    commits. What a verdict is, and what the incidents say because of it, then change together."""
    db.execute(select(func.pg_advisory_xact_lock(LOCK)))


def reapply(db: Session) -> None:
    """Judges the signals of the incidents that are not over again, after the owner gave, changed
    or took back a verdict. One that is over is history and keeps what was said at the time. The
    caller commits, with the verdict.

    An incident with more signals than it lists (``MAX_SIGNALS``) is judged by the ones it lists,
    and counts those."""
    hold(db)
    verdict_rules = verdicts.load(db)
    for incident in db.scalars(select(Incident).where(Incident.status != "resolved")).all():
        _rebuild(db, incident, verdict_rules)
