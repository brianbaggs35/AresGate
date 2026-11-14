"""The watchdog: tells the destinations when a collector goes quiet, since a monitor that has
stopped looking is the worst failure there is, and says so again when it is back.

A collector has gone quiet when it hasn't had a run that worked for three times how often it is
meant to run, and at least a quarter of an hour. That covers a program that is down, a key that
was changed, a firewall that was moved, and a worker that is stuck. It does not cover one that has
never worked, which is a set-up still going on and is shown on the status page and the
integration's page, nor a worker that has stopped altogether: the worker is also what sends, so
there is nobody left to say so. The status page says that one.

A message is one row in the notifier's outbox (``AlertDelivery`` of kind ``watchdog``). It is told
once for each stretch of silence: the key holds when the collector last worked, and that does not
change while it is quiet, so a retry, a restart or a second pass never says it twice. When the
collector works again, a destination that was told of the silence is told that it is back; one that
was only waiting to be told (held for quiet hours) is not told of either. A silent monitor is
treated as critical: it is sent through quiet hours where the destination lets critical incidents
through, and held for them otherwise. It is not counted in the messages an hour a destination
allows, since it is about AresGate itself and not what is going on in the network.
"""

from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import discord
from app.alerts import rules as alert_rules
from app.collectors.registry import find
from app.incidents import rules as incident_rules
from app.models import AlertDelivery, AlertDestination, CollectorHealth

# The least time without a run that worked before a collector counts as quiet, and how many of its
# own intervals.
QUIET_AFTER: Final = timedelta(minutes=15)
INTERVALS: Final = 3
# How far back the messages told of silences are looked at for one that has ended.
LOOKBACK: Final = timedelta(days=30)
# What a collector that has never worked is taken to have last done, which is never asked about.
EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
# Where the status page, which lists every collector, is in AresGate.
PAGE: Final = "/status"

SILENT: Final = "silent"
BACK: Final = "back"
# Not yet sent, whether waiting for quiet hours, for its turn or to be tried again.
UNSENT: Final = ("queued", "held", "retrying", "limited")


def quiet_for(row: CollectorHealth) -> timedelta:
    """How long a collector may go without a run that worked."""
    return max(QUIET_AFTER, timedelta(seconds=row.interval_seconds) * INTERVALS)


def is_silent(row: CollectorHealth, now: datetime) -> bool:
    """Whether the collector has stopped working: it did, and has not for a good while. One that
    never did is a set-up that isn't finished, not a monitor that went quiet."""
    return row.last_success_at is not None and now - row.last_success_at > quiet_for(row)


def _short(identity: UUID) -> str:
    """The start of a collector's id, which is as much as fits in a key and is enough to find it."""
    return identity.hex[:16]


def silence_key(row: CollectorHealth) -> str:
    """The key of the message about a stretch of silence: when the collector last worked, which
    stays the same until it works again, and which collector it is."""
    last = row.last_success_at or EPOCH
    return f"s{int(last.timestamp())}:{_short(row.id)}"


def _back_key(silence: str) -> str:
    return f"b{silence[1:]}"


def _collector_of(key: str, health: list[CollectorHealth]) -> CollectorHealth | None:
    short = key.rsplit(":", 1)[-1]
    return next((row for row in health if _short(row.id) == short), None)


def name_of(row: CollectorHealth) -> str:
    """What to call the collector in words: the program, and what it reads."""
    collector = find(row.collector)
    what = collector.title if collector else row.collector
    return f"{incident_rules.name_of(row.integration)} · {what}"


def _held(rules: alert_rules.Rules, now: datetime) -> bool:
    quiet = rules.quiet
    return quiet is not None and not quiet.critical_passes and alert_rules.in_quiet(quiet, now)


def _wait_until(rules: alert_rules.Rules, held: bool, now: datetime) -> datetime:
    return alert_rules.quiet_ends(rules.quiet, now) if held and rules.quiet else now


def decide(
    db: Session, destination: AlertDestination, rules: alert_rules.Rules, now: datetime
) -> None:
    """Writes to the outbox what a destination is to be told of the collectors, and takes back
    what is out of date. The caller commits."""
    health = list(db.scalars(select(CollectorHealth)))
    rows = list(
        db.scalars(
            select(AlertDelivery).where(
                AlertDelivery.destination_id == destination.id,
                AlertDelivery.kind == "watchdog",
                AlertDelivery.created_at >= now - LOOKBACK,
            )
        )
    )
    keys = {row.key for row in rows}
    held = _held(rules, now)
    for collector in health:
        if is_silent(collector, now) and silence_key(collector) not in keys:
            db.add(
                _made(
                    destination,
                    SILENT,
                    silence_key(collector),
                    name_of(collector),
                    held,
                    rules,
                    now,
                )
            )
    for row in rows:
        _follow_up(db, destination, rules, row, health, keys, held, now)


def _made(
    destination: AlertDestination,
    reason: str,
    key: str,
    title: str,
    held: bool,
    rules: alert_rules.Rules,
    now: datetime,
) -> AlertDelivery:
    return AlertDelivery(
        destination_id=destination.id,
        kind="watchdog",
        reason=reason,
        key=key,
        state="held" if held else "queued",
        title=title,
        created_at=now,
        due_at=_wait_until(rules, held, now),
        was_held=held,
    )


def _follow_up(
    db: Session,
    destination: AlertDestination,
    rules: alert_rules.Rules,
    row: AlertDelivery,
    health: list[CollectorHealth],
    keys: set[str],
    held: bool,
    now: datetime,
) -> None:
    """What to do about a message already made: let it go when quiet hours end, take it back when
    the collector is working again before it was sent, or tell that it is back after it was."""
    if row.state == "held" and not held:
        row.state = "queued"
        row.due_at = now
    if row.reason != SILENT:
        return
    collector = _collector_of(row.key, health)
    if collector is None or is_silent(collector, now) or silence_key(collector) == row.key:
        # It has gone, or it has not worked again since: nothing has changed.
        return
    if row.state in UNSENT:
        row.state = "dropped"
        row.note = "Not sent. It reported again before this was sent."
    elif row.state == "sent" and _back_key(row.key) not in keys:
        keys.add(_back_key(row.key))
        db.add(_made(destination, BACK, _back_key(row.key), name_of(collector), held, rules, now))


def message_for(
    row: AlertDelivery, health: list[CollectorHealth], origin: str, at: datetime
) -> dict[str, object] | None:
    """What a message says, or none when the collector it is about has gone (its connection was
    removed)."""
    collector = _collector_of(row.key, health)
    if collector is None or collector.last_success_at is None:
        return None
    name = name_of(collector)
    link = f"{origin}{PAGE}"
    worked = f"{collector.last_success_at:%Y-%m-%d %H:%M} UTC"
    if row.reason == BACK:
        return discord.message(
            title=f"{name} is reporting again",
            description=f"It worked again at {worked}.",
            color=discord.GREEN,
            footer="AresGate · watchdog",
            link=link,
            at=at,
        )
    lines = [
        f"{name} hasn't worked since {worked}, so AresGate may be missing what it would have seen.",
    ]
    if collector.last_error:
        lines.append(f"The last attempt said: {collector.last_error}")
    lines.append(f"[Open the status page]({link}) to see how it is doing.")
    return discord.message(
        title=f"{name} has gone quiet",
        description="\n".join(lines),
        color=discord.RED,
        footer="AresGate · watchdog",
        link=link,
        at=at,
    )
