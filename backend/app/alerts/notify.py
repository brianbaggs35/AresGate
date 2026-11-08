"""The notifier: tells each destination of the incidents its rules choose, once, and keeps a log.

``rules.decide`` says whether an incident is worth a message to a destination. This is what acts
on it, on a schedule, in the worker. For each destination that is turned on and has an address it
does, in this order:

1. **Decides what is new.** Looks at the incidents seen lately (and any it still has to send
   about), and for each that the rules choose, writes one row to the outbox
   (``AlertDelivery``) unless it has already been told. An incident is told once (``new``), and
   again only when it gets worse (its severity or its confidence band, see ``rank_of``, is higher
   than anything already told) or is reopened after the owner dealt with it. The outbox's unique
   key is what makes that true across retries and restarts. One the owner has since dealt with,
   or called not suspicious, is dropped from the outbox before it is sent.
2. **Holds, limits and summarises.** A message that comes in during quiet hours waits for them to
   end, and two or more that waited are said in one summary. A destination hears of at most so
   many incidents an hour; the ones over that are said in one summary an hour, so a scan from a
   thousand addresses is a message and not a flood.
3. **Sends.** One message at a time, a moment apart, with Discord's own limits respected: a 429
   waits as long as Discord says, and a spent allowance in the headers waits too. A failure that
   could pass is tried again after a longer wait each time, up to ``MAX_ATTEMPTS``, and then given
   up on and said so in the log. A webhook Discord refuses (deleted, or a wrong token) is never
   tried again, since repeated refusals count against the address, until it is replaced.

The sender sends a message at least once: if the worker stops between Discord taking a message
and the row being saved, the message is sent again when it starts. The log (``AlertDelivery``)
keeps what became of every message and why, and the Alerts page shows it.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.alerts import destinations, discord, message
from app.alerts import rules as alert_rules
from app.alerts.destinations import Unusable
from app.alerts.discord import Sent, Webhook
from app.config import Settings
from app.incidents import queries
from app.incidents import rules as incident_rules
from app.integrations.client import Recorder
from app.integrations.netguard import AddressPolicy
from app.models import AlertDelivery, AlertDestination, Incident, utcnow

logger = logging.getLogger(__name__)

# Often enough that a threat is in a channel within a minute of being found.
INTERVAL: Final = timedelta(seconds=30)
# How far back an incident is looked at when it has not been told of: what was seen in the last
# couple of hours is news, and what is older is not.
LOOKBACK: Final = timedelta(hours=2)
# How long after a message was due it is still worth sending.
STALE: Final = timedelta(hours=2)
MAX_ATTEMPTS: Final = 6
FIRST_RETRY: Final = timedelta(seconds=30)
LONGEST_RETRY: Final = timedelta(minutes=15)
HOUR: Final = timedelta(hours=1)
# The most incidents looked at for a destination in one pass, newest first.
CANDIDATES: Final = 500
# Seconds between one message and the next to the same channel, so as not to hit Discord's limit.
PACE: Final = 1.0
# The longest a pass waits for Discord to say it may go on; for longer the rest wait for the next.
MAX_PAUSE: Final = 10.0

# Waiting to be sent, and those and the ones a summary will tell of.
PENDING: Final = ("queued", "held", "retrying")
WAITING: Final = (*PENDING, "limited")
# What no longer changes.
SETTLED_STATES: Final = ("summarized", "sent", "failed", "dropped")


def band_of(confidence: int) -> int:
    """How sure AresGate is, in the three bands the Incidents page uses: 2 is high (65 or more),
    1 medium (35 or more), 0 low."""
    if confidence >= incident_rules.HIGH_FROM:
        return 2
    if confidence >= incident_rules.MEDIUM_FROM:
        return 1
    return 0


def rank_of(incident: Incident) -> int:
    """How bad an incident is as one number that only goes up when it gets worse: its severity
    first and its confidence band after."""
    return incident.severity * 10 + band_of(incident.confidence)


def _next_message(
    rules: alert_rules.Rules, incident: Incident, rows: list[AlertDelivery]
) -> tuple[str, str] | None:
    """Whether the incident is to be told of again, as the reason and the unique key of the
    message, or none if there is nothing new. ``rows`` are the messages already made about it
    for this destination."""
    told = [row for row in rows if row.state not in ("failed", "dropped")]
    if not told:
        return "new", "new"
    closed = max((row.closed_at for row in rows if row.closed_at is not None), default=None)
    if closed is not None and max(row.created_at for row in rows) <= closed:
        return "reopened", f"reopened:{int(closed.timestamp())}"
    rank = rank_of(incident)
    if rules.again_when_worse and rank > max(row.rank for row in told):
        return "worse", f"worse:{rank}"
    return None


def _wait_until(rules: alert_rules.Rules, held: bool, now: datetime) -> datetime:
    """When a message may go: now, or when quiet hours end if it is held for them."""
    return alert_rules.quiet_ends(rules.quiet, now) if held and rules.quiet else now


def _set_aside(
    rows: list[AlertDelivery], reason: alert_rules.Reason, text: str, now: datetime
) -> None:
    """The owner's rules, or what the owner did, no longer let the incident through: what was
    waiting is not sent, and a settled incident is marked so that a reopening is seen."""
    for row in rows:
        if row.state in WAITING:
            row.state = "dropped"
            row.note = f"Not sent. {text}."
        if reason == "settled" and row.closed_at is None:
            row.closed_at = now


def _tell(
    db: Session,
    destination: AlertDestination,
    rules: alert_rules.Rules,
    incident: Incident,
    rows: list[AlertDelivery],
    decision: alert_rules.Decision,
    now: datetime,
) -> None:
    """Makes the message the rules call for, if there is one, and moves what waits in or out of
    quiet hours."""
    for row in rows:
        if row.state == "held" and not decision.held:
            row.state = "queued"
            row.due_at = now
        elif row.state == "queued" and decision.held and row.attempts == 0:
            row.state = "held"
            row.was_held = True
            row.due_at = _wait_until(rules, True, now)
    found = _next_message(rules, incident, rows)
    if found is None:
        return
    reason, key = found
    state = "held" if decision.held else "queued"
    existing = next((row for row in rows if row.key == key), None)
    if existing is None:
        db.add(
            AlertDelivery(
                destination_id=destination.id,
                incident_id=incident.id,
                kind="incident",
                reason=reason,
                key=key,
                state=state,
                rank=rank_of(incident),
                title=incident.title,
                severity=incident.severity,
                confidence=incident.confidence,
                created_at=now,
                due_at=_wait_until(rules, decision.held, now),
                was_held=decision.held,
            )
        )
    elif existing.state == "dropped":
        # It was left out and the rules choose it again, such as when a verdict is taken back.
        existing.state = state
        existing.note = None
        existing.due_at = _wait_until(rules, decision.held, now)
        existing.was_held = decision.held


def _incidents(db: Session, destination: AlertDestination, now: datetime) -> list[Incident]:
    """The incidents worth a look for a destination: those seen lately since it began listening,
    and any it still has a message waiting about."""
    since = max(now - LOOKBACK, destination.listening_since)
    recent = list(
        db.scalars(
            select(Incident)
            .where(Incident.last_seen_at >= since)
            .order_by(Incident.last_seen_at.desc(), Incident.id.desc())
            .limit(CANDIDATES)
        )
    )
    waiting = select(AlertDelivery.incident_id).where(
        AlertDelivery.destination_id == destination.id,
        AlertDelivery.state.in_(WAITING),
        AlertDelivery.incident_id.is_not(None),
    )
    others = db.scalars(
        select(Incident).where(
            Incident.id.in_(waiting), Incident.id.not_in([incident.id for incident in recent])
        )
    )
    return [*recent, *others]


def decide_new(
    db: Session, destination: AlertDestination, rules: alert_rules.Rules, now: datetime
) -> None:
    """Writes to the outbox what the rules say a destination is to be told, and drops what they no
    longer say."""
    incidents = _incidents(db, destination, now)
    if not incidents:
        return
    by_incident: dict[int, list[AlertDelivery]] = defaultdict(list)
    for row in db.scalars(
        select(AlertDelivery).where(
            AlertDelivery.destination_id == destination.id,
            AlertDelivery.kind == "incident",
            AlertDelivery.incident_id.in_([incident.id for incident in incidents]),
        )
    ):
        by_incident[row.incident_id or 0].append(row)
    for incident in incidents:
        rows = by_incident[incident.id]
        decision = alert_rules.decide(rules, incident, now)
        if decision.reason is None:
            _tell(db, destination, rules, incident, rows, decision, now)
        else:
            _set_aside(rows, decision.reason, alert_rules.explain(decision.reason, rules), now)


@dataclass(frozen=True)
class Job:
    """A message ready to go: what to send, and where."""

    delivery_id: int
    destination_id: int
    webhook: Webhook
    payload: dict[str, object]


def _summary(
    db: Session,
    destination: AlertDestination,
    reason: str,
    rows: list[AlertDelivery],
    now: datetime,
) -> AlertDelivery:
    """A message that tells of several incidents at once, which they point to."""
    summary = AlertDelivery(
        destination_id=destination.id,
        kind="summary",
        reason=reason,
        key=f"{reason}:{int(now.timestamp())}",
        state="queued",
        title=f"{len(rows)} incidents",
        covers=len(rows),
        created_at=now,
        due_at=now,
    )
    db.add(summary)
    db.flush()
    for row in rows:
        row.state = "summarized"
        row.summary_id = summary.id
        row.note = "Told in a summary."
    return summary


def _expire(db: Session, destination: AlertDestination, now: datetime) -> None:
    """Gives up on what was due long ago: a message that late is not news."""
    db.execute(
        update(AlertDelivery)
        .where(
            AlertDelivery.destination_id == destination.id,
            AlertDelivery.state.in_(WAITING),
            AlertDelivery.due_at < now - STALE,
        )
        .values(state="failed", note="Not sent in time: by then it was no longer news.")
    )
    db.flush()


def _sent_lately(db: Session, destination: AlertDestination, now: datetime) -> int:
    return (
        db.scalar(
            select(func.count()).where(
                AlertDelivery.destination_id == destination.id,
                AlertDelivery.kind == "incident",
                AlertDelivery.state == "sent",
                AlertDelivery.sent_at > now - HOUR,
            )
        )
        or 0
    )


def _summarised_lately(db: Session, destination: AlertDestination, now: datetime) -> bool:
    return (
        db.scalar(
            select(func.count()).where(
                AlertDelivery.destination_id == destination.id,
                AlertDelivery.kind == "summary",
                AlertDelivery.reason == "limit",
                AlertDelivery.created_at > now - HOUR,
            )
        )
        or 0
    ) > 0


def due_now(
    db: Session, destination: AlertDestination, rules: alert_rules.Rules, now: datetime
) -> list[AlertDelivery]:
    """The messages to send to a destination now: those that are due, as many as it allows an hour
    and then a summary of the rest."""
    _expire(db, destination, now)
    due = list(
        db.scalars(
            select(AlertDelivery)
            .where(
                AlertDelivery.destination_id == destination.id,
                AlertDelivery.state.in_(("queued", "retrying")),
                AlertDelivery.due_at <= now,
            )
            .order_by(AlertDelivery.rank.desc(), AlertDelivery.created_at, AlertDelivery.id)
        )
    )
    summaries = [row for row in due if row.kind == "summary"]
    held = [row for row in due if row.kind == "incident" and row.was_held and row.attempts == 0]
    if len(held) >= 2:
        # They waited for quiet hours to end, and they are told as one.
        summaries.append(_summary(db, destination, "quiet", held, now))
    else:
        held = []
    ready: list[AlertDelivery] = []
    allowed = rules.max_per_hour - _sent_lately(db, destination, now)
    for row in due:
        if row.kind == "summary" or row in held:
            continue
        if allowed > 0:
            ready.append(row)
            allowed -= 1
        else:
            row.state = "limited"
            row.note = f"Held back: {rules.max_per_hour} messages an hour were already sent."
    limited = list(
        db.scalars(
            select(AlertDelivery).where(
                AlertDelivery.destination_id == destination.id,
                AlertDelivery.state == "limited",
                AlertDelivery.summary_id.is_(None),
            )
        )
    )
    if limited and not _summarised_lately(db, destination, now):
        summaries.append(_summary(db, destination, "limit", limited, now))
    return [*ready, *summaries]


def _devices(db: Session, incident: Incident) -> list[message.Device]:
    return [
        (str(address), device.hostname or device.vendor or device.mac)
        for address, device in queries.devices(db, incident)
    ]


def build(
    db: Session, destination: AlertDestination, row: AlertDelivery, origin: str, now: datetime
) -> dict[str, object] | None:
    """What a row says, or none when there is nothing left to say (the incident is gone)."""
    if row.kind == "summary":
        named = list(
            db.scalars(
                select(Incident)
                .join(AlertDelivery, AlertDelivery.incident_id == Incident.id)
                .where(AlertDelivery.summary_id == row.id)
                .order_by(AlertDelivery.rank.desc(), AlertDelivery.id)
                .limit(message.SUMMARY_NAMES)
            )
        )
        return message.summary_message(
            reason=row.reason,
            covers=row.covers,
            named=named,
            detail=destination.detail,
            origin=origin,
            max_per_hour=destination.max_per_hour,
            at=now,
        )
    incident = db.get(Incident, row.incident_id) if row.incident_id else None
    if incident is None:
        return None
    return message.incident_message(
        incident,
        reason=row.reason,
        detail=destination.detail,
        origin=origin,
        devices=_devices(db, incident) if destination.detail == "full" else (),
        at=now,
    )


def plan(db: Session, settings: Settings, now: datetime) -> list[Job]:
    """One pass of deciding: what is to be sent now, to whom. Saves nothing but the outbox; the
    caller commits."""
    addressed = destinations.with_address(db)
    jobs: list[Job] = []
    for destination in destinations.listing(db):
        if not destination.enabled or destination.refused or destination.id not in addressed:
            continue
        try:
            webhook = destinations.open_webhook(db, settings, destination)
        except Unusable as problem:
            destinations.record_attempt(destination, str(problem), now)
            continue
        rules = alert_rules.of(destination)
        decide_new(db, destination, rules, now)
        for row in due_now(db, destination, rules, now):
            payload = build(db, destination, row, settings.public_origin, now)
            if payload is None:
                row.state = "dropped"
                row.note = "Not sent. The incident is gone."
                continue
            jobs.append(Job(row.id, destination.id, webhook, payload))
    return jobs


def retry_in(attempts: int) -> timedelta:
    """How long to wait after the ``attempts``-th failed try: 30 seconds, then twice as long each
    time, up to a quarter of an hour."""
    return min(FIRST_RETRY * 2 ** max(0, attempts - 1), LONGEST_RETRY)


def keep(db: Session, delivery_id: int, sent: Sent, now: datetime) -> str:
    """Keeps how sending a message went, and says what became of it."""
    row = db.get(AlertDelivery, delivery_id)
    destination = db.get(AlertDestination, row.destination_id) if row else None
    if row is None or destination is None:
        # The destination was removed while the message was on its way.
        return "gone"
    destinations.record_attempt(destination, sent, now)
    row.attempts += 1
    if sent.ok:
        row.state = "sent"
        row.sent_at = now
        row.note = None
    elif sent.gone:
        row.state = "failed"
        row.note = sent.problem
        destination.refused = True
        db.execute(
            update(AlertDelivery)
            .where(
                AlertDelivery.destination_id == destination.id,
                AlertDelivery.state.in_(WAITING),
            )
            .values(
                state="failed",
                note="Not sent. Discord doesn't accept the webhook; replace its address.",
            )
        )
    elif sent.retry and row.attempts < MAX_ATTEMPTS:
        row.state = "retrying"
        row.note = sent.problem
        row.due_at = now + max(retry_in(row.attempts), timedelta(seconds=sent.retry_after or 0))
    else:
        row.state = "failed"
        row.note = sent.problem
    outcome = row.state
    db.commit()
    return outcome


def settle(new_session: Callable[[], Session], delivery_id: int, sent: Sent, now: datetime) -> str:
    """``keep``, in a session of its own."""
    with new_session() as db:
        return keep(db, delivery_id, sent, now)


@dataclass(frozen=True)
class Report:
    """How a pass went."""

    sent: int = 0
    retrying: int = 0
    failed: int = 0


async def notify_once(
    settings: Settings,
    new_session: Callable[[], Session],
    recorder: Recorder,
    policy: AddressPolicy,
    origin: str | None = None,
    *,
    pace: float = PACE,
) -> Report:
    """One pass: decides what to send, sends it and keeps how it went."""

    def prepare() -> list[Job]:
        with new_session() as db:
            jobs = plan(db, settings, utcnow())
            db.commit()
            return jobs

    jobs = await asyncio.to_thread(prepare)
    resting: set[int] = set()
    counts = {"sent": 0, "retrying": 0, "failed": 0}
    for job in jobs:
        if job.destination_id in resting:
            continue
        sent = await discord.send(
            job.webhook,
            job.payload,
            connection=f"destination-{job.destination_id}",
            recorder=recorder,
            policy=policy,
            origin=origin,
        )
        outcome = await asyncio.to_thread(settle, new_session, job.delivery_id, sent, utcnow())
        counts[outcome] = counts.get(outcome, 0) + 1
        if not sent.ok or (sent.pause or 0) > MAX_PAUSE:
            # Discord is not taking messages from this webhook now: the rest wait for the next pass.
            resting.add(job.destination_id)
        else:
            await asyncio.sleep(max(pace, sent.pause or 0))
    return Report(counts["sent"], counts["retrying"], counts["failed"])


async def run(
    settings: Settings,
    new_session: Callable[[], Session],
    recorder: Recorder,
    policy: AddressPolicy,
    *,
    enabled: bool = True,
    interval: timedelta = INTERVAL,
) -> None:
    """Tells destinations, waits, and tells them again until cancelled. A failure (the database
    isn't up yet, or was restarted) is logged and tried again next time, because it must never
    stop the worker. When collecting is off there is nothing new to tell of."""
    while True:
        if enabled:
            try:
                report = await notify_once(settings, new_session, recorder, policy)
                if report.sent or report.retrying or report.failed:
                    logger.info(
                        "Alerts: %d sent, %d to try again, %d given up on",
                        report.sent,
                        report.retrying,
                        report.failed,
                    )
            except Exception:
                logger.exception("Couldn't send the latest alerts")
        await asyncio.sleep(interval.total_seconds())
