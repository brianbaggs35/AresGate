"""Reading the events back: the newest first a page at a time, the ones that came after what a
page showed, one event whole, and how the ones found are spread. The logs page and the export
read them, and so can the AI analyst.

Events are kept in a table of weeks (``app/partitions.py``) with the time in the key, so a page is
found by the time and the id of the last event of the page before it, not by counting rows:
the thousandth page costs what the first does.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final, NamedTuple

from sqlalchemy import (
    ColumnElement,
    Interval,
    and_,
    desc,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.orm import Session, defer

from app.events.event import Severity
from app.models import Event, IncidentSignal

LEVELS: Final = len(Severity)
EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND: Final = timedelta(microseconds=1)
# What a cursor looks like, which is all the API has to check before reading one.
CURSOR_PATTERN: Final = r"^\d{1,17}\.\d{1,19}$"

# How many events a summary reads: the newest this many that match. A busy firewall can log
# millions in a month; the spread of the latest 50,000 is what a person looks at, and it takes a
# few hundredths of a second whatever else there is.
SUMMARY_WINDOW: Final = 50_000
# The widths of a bar of the volume chart that are tried, the narrowest first, and the most bars.
BUCKET_SECONDS: Final = (60, 300, 900, 1800, 3600, 3 * 3600, 6 * 3600, 12 * 3600, 86400, 7 * 86400)
MAX_BARS: Final = 60
# Monday in the year 2000, so that a bucket of a day or a week begins on one.
_ORIGIN: Final = datetime(2000, 1, 3, tzinfo=UTC)
# How many rows an export reads at a time.
EXPORT_CHUNK: Final = 1000


class Cursor(NamedTuple):
    """Where an event is in the order the logs are read in: when it happened, and its number."""

    at: datetime
    id: int

    def __str__(self) -> str:
        return f"{(self.at - EPOCH) // _MICROSECOND}.{self.id}"

    @classmethod
    def of(cls, event: Event) -> Cursor:
        return cls(event.occurred_at, event.id)

    @classmethod
    def parse(cls, text: str) -> Cursor:
        micros, number = text.split(".")
        return cls(EPOCH + int(micros) * _MICROSECOND, int(number))


@dataclass(frozen=True)
class Row:
    """An event as the list shows it: without the program's own record, which can be large."""

    event: Event
    has_raw: bool


@dataclass(frozen=True)
class Page:
    """Events newest first, and whether there are more of them past the end."""

    rows: list[Row]
    more: bool


# Whether the program's own record was kept. An event stored without one holds the JSON ``null``,
# which the database does not call missing.
_kept = func.coalesce(func.jsonb_typeof(Event.raw), "null") != "null"


def _older_than(cursor: Cursor) -> ColumnElement[bool]:
    return and_(
        # Says which weeks can hold it, which a comparison of the pair does not.
        Event.occurred_at <= cursor.at,
        or_(
            Event.occurred_at < cursor.at,
            and_(Event.occurred_at == cursor.at, Event.id < cursor.id),
        ),
    )


def _newer_than(cursor: Cursor) -> ColumnElement[bool]:
    return and_(
        Event.occurred_at >= cursor.at,
        or_(
            Event.occurred_at > cursor.at,
            and_(Event.occurred_at == cursor.at, Event.id > cursor.id),
        ),
    )


def page(
    db: Session,
    *,
    where: Sequence[ColumnElement[bool]],
    limit: int,
    before: Cursor | None = None,
    after: Cursor | None = None,
) -> Page:
    """The events that match, newest first: from the start, or those older than ``before``. With
    ``after`` they are the ones newer than it, the oldest of them first as far as ``limit`` goes
    (so a page that has been left far behind catches up in order), and ``more`` says whether
    there are others newer still."""
    statement = select(Event, _kept.label("has_raw")).options(defer(Event.raw)).where(*where)
    if after is not None:
        statement = statement.where(_newer_than(after)).order_by(Event.occurred_at, Event.id)
    else:
        if before is not None:
            statement = statement.where(_older_than(before))
        statement = statement.order_by(desc(Event.occurred_at), desc(Event.id))
    found = db.execute(statement.limit(limit + 1)).all()
    rows = [Row(event, has_raw) for event, has_raw in found[:limit]]
    if after is not None:
        rows.reverse()
    return Page(rows=rows, more=len(found) > limit)


def get(db: Session, cursor: Cursor) -> Event | None:
    """One event, with the program's own record."""
    return db.scalars(
        select(Event).where(Event.occurred_at == cursor.at, Event.id == cursor.id)
    ).one_or_none()


def incident_of(db: Session, event: Event) -> int | None:
    """The incident the event was filed into, if it was."""
    return db.scalar(select(IncidentSignal.incident_id).where(IncidentSignal.event_id == event.id))


@dataclass(frozen=True)
class Volume:
    """How many events there were in each stretch of time, by severity: ``counts[bar][level]``."""

    start: datetime
    seconds: int
    counts: list[list[int]]


@dataclass(frozen=True)
class Summary:
    """How the events that match are spread, whichever page of them is on screen. The counts by
    severity, integration and kind are of every event that matches, so that choosing one of them
    narrows the search to exactly the number it showed. The volume over time is of the newest
    ``SUMMARY_WINDOW`` of them, and ``capped`` says there were more than that."""

    matched: int
    # Whether the volume left out the oldest events because there were more than it reads.
    capped: bool
    severity: dict[int, int] = field(default_factory=dict[int, int])
    sources: dict[str, int] = field(default_factory=dict[str, int])
    kinds: dict[str, int] = field(default_factory=dict[str, int])
    volume: Volume | None = None


def bar_width(span: timedelta) -> int:
    """The narrowest bar, in seconds, that draws the time in at most ``MAX_BARS`` of them."""
    for seconds in BUCKET_SECONDS:
        if span.total_seconds() / seconds <= MAX_BARS:
            return seconds
    return BUCKET_SECONDS[-1]


def summary(db: Session, *, where: Sequence[ColumnElement[bool]]) -> Summary:
    """The spread of the events that match: by severity, integration and kind (all of them) and
    over time (the newest ``SUMMARY_WINDOW``)."""
    # One pass over the matching events: the groups are few, so the three counts come from one
    # grouping, and the same event is counted once whichever of them is chosen next.
    spread = db.execute(
        select(Event.severity, Event.source, Event.kind, func.count())
        .where(*where)
        .group_by(Event.severity, Event.source, Event.kind)
    ).all()
    total = sum(count for _, _, _, count in spread)
    if not total:
        return Summary(matched=0, capped=False)
    severity: dict[int, int] = {}
    sources: dict[str, int] = {}
    kinds: dict[str, int] = {}
    for level, source, kind, count in spread:
        severity[level] = severity.get(level, 0) + count
        sources[source] = sources.get(source, 0) + count
        kinds[kind] = kinds.get(kind, 0) + count
    return Summary(
        matched=total,
        capped=total > SUMMARY_WINDOW,
        severity=severity,
        sources=sources,
        kinds=kinds,
        volume=_volume(db, where),
    )


def _volume(db: Session, where: Sequence[ColumnElement[bool]]) -> Volume:
    """How many of the newest ``SUMMARY_WINDOW`` events that match there were in each stretch of
    time, by severity."""
    window = (
        select(Event.occurred_at, Event.severity)
        .where(*where)
        .order_by(desc(Event.occurred_at), desc(Event.id))
        .limit(SUMMARY_WINDOW)
        .cte("window")
    )
    first, last = db.execute(
        select(func.min(window.c.occurred_at), func.max(window.c.occurred_at))
    ).one()
    seconds = bar_width(last - first)
    bar = func.date_bin(
        literal(timedelta(seconds=seconds), Interval), window.c.occurred_at, _ORIGIN
    )
    rows = db.execute(
        select(bar, window.c.severity, func.count()).group_by(bar, window.c.severity)
    ).all()
    bars: dict[datetime, list[int]] = {}
    for when, level, count in rows:
        bars.setdefault(when, [0] * LEVELS)[level] = count
    start = min(bars)
    stretch = int((max(bars) - start).total_seconds() // seconds) + 1
    return Volume(
        start=start,
        seconds=seconds,
        counts=[
            bars.get(start + timedelta(seconds=seconds * index), [0] * LEVELS)
            for index in range(stretch)
        ],
    )


def export(
    db: Session, *, where: Sequence[ColumnElement[bool]], limit: int, raw: bool
) -> Iterator[list[Event]]:
    """The events that match, newest first, in chunks, up to ``limit`` of them."""
    cursor: Cursor | None = None
    left = limit
    while left > 0:
        statement = select(Event).where(*where).order_by(desc(Event.occurred_at), desc(Event.id))
        if not raw:
            statement = statement.options(defer(Event.raw))
        if cursor is not None:
            statement = statement.where(_older_than(cursor))
        chunk = list(db.scalars(statement.limit(min(EXPORT_CHUNK, left))))
        if not chunk:
            return
        yield chunk
        left -= len(chunk)
        cursor = Cursor.of(chunk[-1])
        # The rows are on their way out, so the session does not keep hold of them.
        db.expunge_all()
