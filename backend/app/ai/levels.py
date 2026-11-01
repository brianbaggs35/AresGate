"""How much AI is used without being asked. The owner chooses one of five levels on the usage page,
and the worker that reads incidents by itself follows it (app/ai/triage.py: ``POLICIES``). The
words that describe each level are made from those policies here, so what the page promises is what
the worker does.

A level never limits what the owner asks for: Start investigating on an incident and a question in
the Assistant are answered at every level. Spending limits (app/ai/limits.py) hold at every level
too."""

from dataclasses import dataclass
from typing import Final, Literal

from sqlalchemy.orm import Session

from app.ai import service
from app.ai.triage import PAUSE, POLICIES, Policy
from app.events.event import Severity
from app.models.base import utcnow

LevelKey = Literal["very_low", "low", "medium", "high", "maximum"]

LABELS: Final[dict[str, str]] = {
    "very_low": "Very low",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "maximum": "Maximum",
}


@dataclass(frozen=True)
class Level:
    key: str
    label: str
    # What the worker reads by itself, in a sentence or two.
    summary: str
    # The most it reads in an hour; 0 reads nothing by itself.
    per_hour: int


def _describe(policy: Policy) -> str:
    if policy.minimum is None:
        return (
            "Reads nothing by itself. AI answers only when you ask, with Start investigating on "
            "an incident or a question in the Assistant."
        )
    which = (
        "every incident, even the least serious"
        if policy.minimum is Severity.INFO
        else f"incidents rated {policy.minimum.name.lower()} or higher"
    )
    again = (
        "Reads each one once."
        if policy.growth is None
        else (
            f"Reads one again when it has {policy.growth:g} times the signals it had, but not "
            f"within {int(PAUSE.total_seconds() // 60)} minutes."
        )
    )
    return f"Reads {which}, up to {policy.per_hour} an hour. {again}"


def _build() -> tuple[Level, ...]:
    return tuple(
        Level(key, LABELS[key], _describe(policy), policy.per_hour)
        for key, policy in POLICIES.items()
    )


LEVELS: Final = _build()


def current(db: Session) -> str:
    """The level the owner chose, ``medium`` until they say otherwise."""
    return service.usage(db, utcnow()).usage_level


def choose(db: Session, key: LevelKey) -> tuple[str, str]:
    """Keeps the level, and says what it was and what it is now. The caller commits."""
    now = utcnow()
    chosen = service.usage(db, now)
    before = chosen.usage_level
    chosen.usage_level = key
    chosen.updated_at = now
    db.flush()
    return before, key
