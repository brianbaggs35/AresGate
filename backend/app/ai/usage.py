"""What AI has been used for, worked out from the record of every call (``ai_calls``): how many
calls, how many tokens and what they cost by day, provider, model and use; what used the most; how
this month is going and where it is heading. The usage page and its CSV file read these.

Costs are estimates: each call was priced when it was made from the catalog's price list
(app/ai/catalog.py), which is a snapshot. A call to a model the catalog has no price for is
counted in calls and tokens but has no cost, and is said to have none rather than counted as free.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, Date, desc, func, null, select
from sqlalchemy.orm import InstrumentedAttribute, Session, defer

from app.ai import limits
from app.models import AiCall

# The ranges the page can show, in days.
_RANGES = {"7d": 7, "30d": 30, "90d": 90}
RANGES = tuple(_RANGES)
TOP_CONSUMERS = 8
# The most calls a CSV file holds. Enough for months of use at the highest level.
MAX_EXPORT = 100_000

TOKENS = AiCall.input_tokens + AiCall.output_tokens
PRICED = func.coalesce(func.sum(AiCall.cost_micros), 0)
UNPRICED = func.count().filter(AiCall.cost_micros.is_(None))


@dataclass(frozen=True)
class Span:
    """Whole days, as the person reading the page counts them (in their time zone), ending with
    today. ``days`` has the moment each begins."""

    key: str
    zone: ZoneInfo
    start: datetime
    end: datetime
    days: tuple[datetime, ...]
    dates: tuple[date, ...]

    @property
    def previous_start(self) -> datetime:
        return self.start - (self.end - self.start)


def zone_of(name: str) -> ZoneInfo | None:
    """The time zone of that name, or None where there is no such zone."""
    try:
        return ZoneInfo(name)
    except ValueError, OSError, KeyError:
        return None


def _midnight(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)


def span(key: str, now: datetime, zone: ZoneInfo) -> Span:
    """The last 7, 30 or 90 days, as the zone counts them, ending with the day ``now`` is in."""
    today = now.astimezone(zone).date()
    dates = tuple(today - timedelta(days=back) for back in reversed(range(_RANGES[key])))
    return Span(
        key,
        zone,
        _midnight(dates[0], zone),
        _midnight(today + timedelta(days=1), zone),
        tuple(_midnight(day, zone) for day in dates),
        dates,
    )


@dataclass(frozen=True)
class Totals:
    calls: int
    failed: int
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    # What the calls with a known price cost, and how many have none.
    cost_micros: int
    unpriced: int


def _within(start: datetime, end: datetime) -> ColumnElement[bool]:
    return (AiCall.occurred_at >= start) & (AiCall.occurred_at < end)


def totals(db: Session, start: datetime, end: datetime) -> Totals:
    """Everything between two moments, added up."""
    row = db.execute(
        select(
            func.count(),
            func.count().filter(AiCall.ok.is_(False)),
            func.coalesce(func.sum(AiCall.input_tokens), 0),
            func.coalesce(func.sum(AiCall.cached_tokens), 0),
            func.coalesce(func.sum(AiCall.output_tokens), 0),
            PRICED,
            UNPRICED,
        ).where(_within(start, end))
    ).one()
    return Totals(*(int(value) for value in row))


@dataclass(frozen=True)
class Day:
    """One use's calls, tokens and cost on one day."""

    purpose: str
    calls: int
    tokens: int
    cost_micros: int


def by_day(db: Session, window: Span) -> dict[date, list[Day]]:
    """What each use took on each day of the span, for the days there was any."""
    local = func.date(func.timezone(window.zone.key, AiCall.occurred_at)).cast(Date)
    rows = db.execute(
        select(local, AiCall.purpose, func.count(), func.sum(TOKENS), PRICED)
        .where(_within(window.start, window.end))
        .group_by(local, AiCall.purpose)
        .order_by(local, AiCall.purpose)
    ).all()
    found: dict[date, list[Day]] = {}
    for day, purpose, calls, tokens, cost in rows:
        found.setdefault(day, []).append(Day(purpose, int(calls), int(tokens or 0), int(cost or 0)))
    return found


@dataclass(frozen=True)
class Group:
    """Calls added up by what they have in common, such as the model."""

    key: str
    # The provider, for a group of models.
    provider: str | None
    calls: int
    tokens: int
    cost_micros: int
    unpriced: int


def _grouped(
    db: Session,
    window: Span,
    key: InstrumentedAttribute[str],
    provider: InstrumentedAttribute[str] | None = None,
) -> list[Group]:
    """The calls in the span added up by ``key``, the costliest first."""
    columns = [key] if provider is None else [key, provider]
    rows = db.execute(
        select(
            key,
            null() if provider is None else provider,
            func.count(),
            func.sum(TOKENS),
            PRICED,
            UNPRICED,
        )
        .where(_within(window.start, window.end))
        .group_by(*columns)
        .order_by(desc(PRICED), desc(func.sum(TOKENS)), key)
    ).all()
    return [
        Group(str(name), made_by, int(calls), int(tokens or 0), int(cost or 0), int(unpriced or 0))
        for name, made_by, calls, tokens, cost, unpriced in rows
    ]


def by_provider(db: Session, window: Span) -> list[Group]:
    return _grouped(db, window, AiCall.provider)


def by_model(db: Session, window: Span) -> list[Group]:
    return _grouped(db, window, AiCall.model, AiCall.provider)


def by_purpose(db: Session, window: Span) -> list[Group]:
    return _grouped(db, window, AiCall.purpose)


@dataclass(frozen=True)
class Consumer:
    """One thing the AI was asked about, such as an incident, and what it took."""

    about: str
    purpose: str
    calls: int
    tokens: int
    cost_micros: int


def top_consumers(db: Session, window: Span) -> list[Consumer]:
    """What the AI was asked about that took the most, by cost and then by tokens."""
    rows = db.execute(
        select(AiCall.about, AiCall.purpose, func.count(), func.sum(TOKENS), PRICED)
        .where(_within(window.start, window.end), AiCall.about.is_not(None))
        .group_by(AiCall.about, AiCall.purpose)
        .order_by(desc(PRICED), desc(func.sum(TOKENS)), AiCall.about)
        .limit(TOP_CONSUMERS)
    ).all()
    return [
        Consumer(str(about), purpose, int(calls), int(tokens or 0), int(cost or 0))
        for about, purpose, calls, tokens, cost in rows
    ]


@dataclass(frozen=True)
class Month:
    """The calendar month (UTC, as providers bill it) so far, and where it is heading."""

    start: datetime
    end: datetime
    spent_micros: int
    unpriced: int
    # At this pace, what the month will have cost; None until there is a day to go on, or
    # nothing has been spent.
    projected_micros: int | None


def month(db: Session, now: datetime) -> Month:
    start = limits.month_start(now)
    end = limits.next_month(now)
    so_far = totals(db, start, now + timedelta(microseconds=1))
    elapsed = now - start
    projected = None
    if so_far.cost_micros > 0 and elapsed >= timedelta(days=1):
        projected = round(so_far.cost_micros * ((end - start) / elapsed))
    return Month(start, end, so_far.cost_micros, so_far.unpriced, projected)


def calls(db: Session, window: Span, limit: int, offset: int) -> tuple[list[AiCall], int]:
    """The calls in the span, newest first, without what was asked and answered (which is large),
    and how many there are in all."""
    total = db.scalar(select(func.count()).where(_within(window.start, window.end))) or 0
    rows = db.scalars(
        select(AiCall)
        .options(defer(AiCall.prompt), defer(AiCall.answer))
        .where(_within(window.start, window.end))
        .order_by(desc(AiCall.occurred_at), desc(AiCall.id))
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), int(total)


def export(db: Session, window: Span) -> list[AiCall]:
    """Every call in the span, oldest first, for a file."""
    return list(
        db.scalars(
            select(AiCall)
            .options(defer(AiCall.prompt), defer(AiCall.answer))
            .where(_within(window.start, window.end))
            .order_by(AiCall.occurred_at, AiCall.id)
            .limit(MAX_EXPORT)
        ).all()
    )
