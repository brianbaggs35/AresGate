"""How often, and how many, lookups an access level allows, and whether one may go now.

The free public API allows 4 lookups a minute and 500 a day, so lookups are at least 15 seconds
apart and counted over the last day. VirusTotal's pages give no monthly figure, so the count over
any 30 days stops at 15,000, as a margin. A premium key's limits depend on its plan, so only a
second is kept between its lookups.

The background loop keeps its own lookups further apart: on the free key, four minutes, so that
its 360 a day are spread over the whole day and the other 140 of the 500 stay for searches by hand.
A search is not held back by that spacing, only by the spacing above and the day's and month's
allowances.

Every lookup, whether the background loop makes it or a person searches, is kept through
``reserve``. It takes a lock first, so two lookups that are asked for at the same time can't both
see room for one more.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.intel import store
from app.models import IntelLookup

# The lock every lookup takes while it checks the limits and keeps its place: a number that stands
# for the letters ARIT, so that it is recognisable in the database.
_LOCK = 0x41524954
NONE = timedelta(0)


@dataclass(frozen=True)
class Level:
    """The limits of one access level. ``None`` is no limit of that kind. ``background_spacing`` is
    the least time the background loop leaves between its lookups, and since it is measured from
    the last lookup of any kind, a search holds the loop back too."""

    spacing: timedelta
    per_day: int | None
    per_month: int | None
    background_spacing: timedelta = NONE


class Wait(Exception):
    """A lookup may not go yet. ``wait`` is how long until one may."""

    def __init__(self, wait: timedelta) -> None:
        super().__init__(f"A lookup may go in {wait}.")
        self.wait = wait


FREE = Level(
    spacing=timedelta(seconds=15),
    per_day=500,
    per_month=15_000,
    background_spacing=timedelta(minutes=4),
)
PREMIUM = Level(spacing=timedelta(seconds=1), per_day=None, per_month=None)
DAY = timedelta(days=1)
MONTH = timedelta(days=30)


def level_of(options: Mapping[str, str | int]) -> Level:
    """The limits of the access level chosen. Anything but premium is kept to the free limits."""
    return PREMIUM if options.get("tier") == "premium" else FREE


def _requested_since(db: Session, provider: str, since: datetime) -> int:
    """How many lookups were requested after ``since``."""
    count = db.scalar(
        select(func.count(IntelLookup.id)).where(
            IntelLookup.provider == provider, IntelLookup.requested_at > since
        )
    )
    return count or 0


def _until_room(
    db: Session, provider: str, now: datetime, window: timedelta, limit: int
) -> timedelta:
    """How long until fewer than ``limit`` lookups fall within the last ``window``. The lookup that
    has to leave the window first is the one at position count - limit, oldest first."""
    since = now - window
    count = _requested_since(db, provider, since)
    if count < limit:
        return NONE
    # There is one, since the count is at least the limit, so ``one`` finds it.
    leaving = db.scalars(
        select(IntelLookup.requested_at)
        .where(IntelLookup.provider == provider, IntelLookup.requested_at > since)
        .order_by(IntelLookup.requested_at)
        .offset(count - limit)
        .limit(1)
    ).one()
    return leaving + window - now


def wait_for(
    db: Session, provider: str, level: Level, now: datetime, *, background: bool = False
) -> timedelta:
    """How long until a lookup may go: none if one may go now. Each limit is looked at on its own,
    and the longest wait is the one given. The background loop's lookups keep the longer spacing."""
    waits = [NONE]
    last = db.scalar(
        select(func.max(IntelLookup.requested_at)).where(IntelLookup.provider == provider)
    )
    gap = max(level.spacing, level.background_spacing) if background else level.spacing
    if last is not None and now - last < gap:
        waits.append(last + gap - now)
    if level.per_day is not None:
        waits.append(_until_room(db, provider, now, DAY, level.per_day))
    if level.per_month is not None:
        waits.append(_until_room(db, provider, now, MONTH, level.per_month))
    return max(waits)


def may_look_up(db: Session, provider: str, level: Level, now: datetime) -> bool:
    """Whether a lookup may go now: the spacing since the last one has passed, and neither the
    day's nor the month's allowance is used up."""
    return wait_for(db, provider, level, now) == NONE


def reserve(
    db: Session,
    provider: str,
    level: Level,
    now: datetime,
    *,
    background: bool = False,
    kind: str = "ip",
    address: IPv4Address | IPv6Address | None = None,
    subject: str | None = None,
) -> int:
    """Keeps that a lookup is about to be made, if the limits allow one now, and returns its id.
    Raises ``Wait`` if they don't. The caller commits, which also lets go of the lock."""
    db.execute(select(func.pg_advisory_xact_lock(_LOCK)))
    wait = wait_for(db, provider, level, now, background=background)
    if wait > NONE:
        raise Wait(wait)
    return store.record(db, provider, address, now, kind=kind, subject=subject)
