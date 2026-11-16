"""Trends: how something has been going, in the hours or days behind it, for the pages that are
otherwise lists of the present. Each is one query that counts what is already stored, into buckets
that start on the hour or the day (UTC) and run up to the one that is under way, so a quiet
stretch is a zero and never a gap."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Mapped, Session
from sqlalchemy.sql.elements import ColumnElement

from app.models import AlertDelivery, ApiCall, Event, Incident

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
Step = Literal["hour", "day"]
STEPS: dict[Step, timedelta] = {"hour": HOUR, "day": DAY}
# How an hour of an integration's calls went: none were made, all worked, or one failed.
HourState = Literal["none", "ok", "problem"]
# The most buckets a trend has: a week of hours, which is also more than the days asked for.
MOST_BUCKETS = 24 * 7


def starts(now: datetime, step: Step, count: int) -> list[datetime]:
    """The start of each of the last ``count`` buckets, the oldest first. The last is the one that
    ``now`` is in. A trend has at least two and at most a week of hours."""
    if not 2 <= count <= MOST_BUCKETS:
        raise ValueError(f"A trend has from 2 to {MOST_BUCKETS} buckets, not {count}.")
    length = STEPS[step]
    last = now.replace(minute=0, second=0, microsecond=0)
    if step == "day":
        last = last.replace(hour=0)
    return [last - length * (count - 1 - number) for number in range(count)]


def _bucket(column: Mapped[datetime], step: Step) -> ColumnElement[datetime]:
    return func.date_trunc(step, column, "UTC")


def _places(starting: Sequence[datetime]) -> dict[datetime, int]:
    return {moment: number for number, moment in enumerate(starting)}


def deliveries(
    db: Session,
    starting: Sequence[datetime],
    step: Step,
    destination_id: int | None,
    state: str | None,
) -> dict[int, list[int]]:
    """How many messages the notifier made in each bucket, by the severity of what they were
    about (0 to 4), for the destination and the state the page is looking at."""
    bucket = _bucket(AlertDelivery.created_at, step)
    query = (
        select(bucket, AlertDelivery.severity, func.count())
        .where(AlertDelivery.created_at >= starting[0])
        .group_by(bucket, AlertDelivery.severity)
    )
    if destination_id is not None:
        query = query.where(AlertDelivery.destination_id == destination_id)
    if state is not None:
        query = query.where(AlertDelivery.state == state)
    found: dict[int, list[int]] = {}
    where = _places(starting)
    for moment, severity, count in db.execute(query):
        found.setdefault(severity, [0] * len(starting))[where[moment]] = count
    return found


def traffic(
    db: Session, starting: Sequence[datetime], step: Step, addresses: Sequence[str]
) -> dict[str, tuple[list[int], list[int]]]:
    """For each address, how many events it was the destination of (``incoming``, connections to
    it) and the source of (``outgoing``, the ones it made) in each bucket."""
    found = {address: ([0] * len(starting), [0] * len(starting)) for address in addresses}
    where = _places(starting)
    for side, column in enumerate((Event.dst_address, Event.src_address)):
        bucket = _bucket(Event.occurred_at, step)
        address = func.host(column)
        query = (
            select(address, bucket, func.count())
            .where(Event.occurred_at >= starting[0], address.in_(addresses))
            .group_by(address, bucket)
        )
        for name, moment, count in db.execute(query):
            found[name][side][where[moment]] = count
    return found


def kinds(
    db: Session, starting: Sequence[datetime], step: Step, family_ids: Sequence[int]
) -> dict[int, list[int]]:
    """How many incidents of each kind began in each bucket."""
    bucket = _bucket(Incident.first_seen_at, step)
    query = (
        select(Incident.family_id, bucket, func.count())
        .where(Incident.first_seen_at >= starting[0], Incident.family_id.in_(family_ids))
        .group_by(Incident.family_id, bucket)
    )
    found: dict[int, list[int]] = {family: [0] * len(starting) for family in family_ids}
    where = _places(starting)
    for family, moment, count in db.execute(query):
        # The ones asked for, so the kind is never None.
        found[cast("int", family)][where[moment]] = count
    return found


def integrations(
    db: Session, starting: Sequence[datetime], step: Step
) -> dict[str, list[HourState]]:
    """How each integration's calls went in each bucket: ``problem`` when any failed, ``ok`` when
    all worked and ``none`` when none were made. An integration never called is left out."""
    bucket = _bucket(ApiCall.occurred_at, step)
    failed = func.count().filter(ApiCall.error.is_not(None))
    query = (
        select(ApiCall.integration, bucket, failed)
        .where(ApiCall.occurred_at >= starting[0])
        .group_by(ApiCall.integration, bucket)
    )
    found: dict[str, list[HourState]] = {}
    where = _places(starting)
    for name, moment, failures in db.execute(query):
        found.setdefault(name, ["none"] * len(starting))[where[moment]] = (
            "problem" if failures else "ok"
        )
    return found
