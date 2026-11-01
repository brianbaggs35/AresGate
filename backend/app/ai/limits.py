"""What may be spent on AI. The owner can set a limit for the last 24 hours and one for the
calendar month (UTC, which is how providers bill it). Reaching one stops the requests to a
provider that charges by the token until spending falls below it, so a worker that runs by itself
can't spend more than was agreed. A provider on the owner's own computer costs nothing and is
never stopped.

Only calls with a known price count: a model the catalog has no price for is counted as calls and
tokens on the usage page, but its cost is not known, so it can't be held to a limit."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import service
from app.models import AiCall

MICROS = Decimal(1_000_000)
# How much of a limit is spent when the page starts to warn.
WARN_AT = Decimal("0.8")
# The most a limit can be: a typing mistake, not a plan, above this.
MAX_DOLLARS = Decimal(1_000_000)

State = Literal["none", "ok", "warning", "reached"]


@dataclass(frozen=True)
class Limit:
    """One limit and how much of it is gone."""

    # What it is for, in the owner's words: ``day`` or ``month``.
    period: Literal["day", "month"]
    limit_micros: int | None
    spent_micros: int

    @property
    def state(self) -> State:
        if self.limit_micros is None:
            return "none"
        if self.spent_micros >= self.limit_micros:
            return "reached"
        if self.spent_micros >= self.limit_micros * WARN_AT:
            return "warning"
        return "ok"


def month_start(now: datetime) -> datetime:
    """The first moment of the calendar month (UTC) that ``now`` is in."""
    now = now.astimezone(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC)


def next_month(now: datetime) -> datetime:
    """The first moment of the calendar month after the one ``now`` is in."""
    start = month_start(now)
    return (start + timedelta(days=32)).replace(day=1)


def spent(db: Session, since: datetime) -> int:
    """What the calls since ``since`` cost, in millionths of a dollar, counting those whose price
    is known."""
    total = db.scalar(
        select(func.coalesce(func.sum(AiCall.cost_micros), 0)).where(AiCall.occurred_at >= since)
    )
    return int(total or 0)


def dollars(micros: int) -> str:
    """An amount of money as it is written: ``$1.25``, or more places for a very small one."""
    amount = Decimal(micros) / MICROS
    places = 2 if amount == 0 or amount >= Decimal("0.01") else 4
    return f"${amount.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP):,}"


def status(db: Session, now: datetime) -> tuple[Limit, Limit]:
    """The day's limit and the month's, with what has been spent against each."""
    chosen = service.usage(db, now)
    return (
        Limit("day", chosen.daily_limit_micros, spent(db, now - timedelta(hours=24))),
        Limit("month", chosen.monthly_limit_micros, spent(db, month_start(now))),
    )


def reached(db: Session, now: datetime) -> str | None:
    """Why a request to a provider that charges can't be made, if a limit is used up."""
    for limit in status(db, now):
        if limit.state != "reached" or limit.limit_micros is None:
            continue
        if limit.period == "day":
            return (
                f"The daily AI spending limit ({dollars(limit.limit_micros)}) is used up. "
                "Requests start again when spending in the last 24 hours falls below it. "
                "Raise it under Settings > AI usage."
            )
        return (
            f"The monthly AI spending limit ({dollars(limit.limit_micros)}) is used up. "
            "Requests start again next month. Raise it under Settings > AI usage."
        )
    return None


def to_micros(amount: Decimal | None) -> int | None:
    """A limit in dollars as the database keeps it, or None for no limit."""
    if amount is None:
        return None
    return int((amount * MICROS).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def set_limits(
    db: Session, daily: Decimal | None, monthly: Decimal | None, now: datetime
) -> tuple[Limit, Limit]:
    """Keeps the limits, in dollars (None for no limit). The caller commits."""
    chosen = service.usage(db, now)
    chosen.daily_limit_micros = to_micros(daily)
    chosen.monthly_limit_micros = to_micros(monthly)
    chosen.updated_at = now
    db.flush()
    return status(db, now)
