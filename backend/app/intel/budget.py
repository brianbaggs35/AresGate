"""How often, and how many, lookups an access level allows, and whether one may go now.

The free public API allows 4 lookups a minute and 500 a day, so lookups are at least 15 seconds
apart and counted over the last day. VirusTotal's pages give no monthly figure, so the count over
any 30 days stops at 15,000, as a margin. A premium key's limits depend on its plan, so only a
second is kept between its lookups.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import IntelLookup


@dataclass(frozen=True)
class Level:
    """The limits of one access level. ``None`` is no limit of that kind."""

    spacing: timedelta
    per_day: int | None
    per_month: int | None


FREE = Level(spacing=timedelta(seconds=15), per_day=500, per_month=15_000)
PREMIUM = Level(spacing=timedelta(seconds=1), per_day=None, per_month=None)
DAY = timedelta(days=1)
MONTH = timedelta(days=30)


def level_of(options: Mapping[str, str | int]) -> Level:
    """The limits of the access level chosen. Anything but premium is kept to the free limits."""
    return PREMIUM if options.get("tier") == "premium" else FREE


def _requested_since(db: Session, provider: str, since: datetime) -> int:
    count = db.scalar(
        select(func.count(IntelLookup.id)).where(
            IntelLookup.provider == provider, IntelLookup.requested_at >= since
        )
    )
    return count or 0


def may_look_up(db: Session, provider: str, level: Level, now: datetime) -> bool:
    """Whether a lookup may go now: the spacing since the last one has passed, and neither the
    day's nor the month's allowance is used up."""
    last = db.scalar(
        select(func.max(IntelLookup.requested_at)).where(IntelLookup.provider == provider)
    )
    if last is not None and now - last < level.spacing:
        return False
    if level.per_day is not None and _requested_since(db, provider, now - DAY) >= level.per_day:
        return False
    return level.per_month is None or _requested_since(db, provider, now - MONTH) < level.per_month
