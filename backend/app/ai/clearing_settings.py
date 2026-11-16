"""What the owner lets the AI clear as a false positive, and what that comes to.

Three modes: ``off`` (it clears nothing and lists nothing), ``suggest`` (it marks what looks like a
false positive and waits for the owner's tap: the review queue) and ``automatic`` (it gives the
verdict itself, which the owner can take back: ``app/ai/clearing.py``). Whichever the mode, the
same rules say what the AI may clear, so that what it suggests is what it would have done:

- the reading says it is nothing (``not_suspicious`` or ``low_priority``);
- of a kind the owner allows (noise, probe, unclear: never an attack or a compromise);
- at least as sure as the owner asks, which is what *careful*, *balanced* and *thorough* stand for,
  or a number of their own between 50 and 99;
- of an incident that involves only programs the owner allows (any, until they name some);
- no more serious than the ceiling (critical is never cleared).

An automatic clear also stops, and says so, when the cap for the last 24 hours is reached or the AI
spending limit is used up. Nothing is stored until the owner first saves."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import limits
from app.audit import Action
from app.events.event import Severity
from app.incidents import attention
from app.incidents.verdicts import MUTING
from app.models import AiClearingSettings, AiTriage, AuditEvent, Incident
from app.threats.settings import Tuning

MODES: Final = ("off", "suggest", "automatic")
KINDS: Final = ("noise", "probe", "unclear")
# The most serious an incident can be and still be cleared. Critical never is.
CEILINGS: Final = {"low": Severity.LOW, "medium": Severity.MEDIUM, "high": Severity.HIGH}
# How sure the AI has to be for each way of asking it to be careful.
PRESETS: Final = {"careful": 90, "balanced": 80, "thorough": 65}
MIN_MINIMUM: Final = 50
MAX_MINIMUM: Final = 99
MAX_CAP: Final = 500
DEFAULT_MINIMUM: Final = PRESETS["balanced"]
DEFAULT_CAP: Final = 25
# What the cap counts over.
CAP_PERIOD: Final = timedelta(hours=24)


@dataclass(frozen=True)
class Policy:
    """The owner's settings for the AI clearing incidents."""

    mode: str = "suggest"
    minimum: int = DEFAULT_MINIMUM
    kinds: tuple[str, ...] = KINDS
    # The programs whose incidents it may clear; none named is any.
    sources: tuple[str, ...] = field(default_factory=tuple[str, ...])
    ceiling: str = "medium"
    daily_cap: int = DEFAULT_CAP

    @property
    def aggressiveness(self) -> str:
        """The preset that asks as much confidence as ``minimum``, or ``custom``."""
        return next((name for name, value in PRESETS.items() if value == self.minimum), "custom")


def load(db: Session) -> Policy:
    """The settings as they are saved, or the defaults where nothing has been."""
    row = db.get(AiClearingSettings, 1)
    if row is None:
        return Policy()
    return Policy(
        row.mode, row.minimum, tuple(row.classes), tuple(row.sources), row.ceiling, row.daily_cap
    )


def save(db: Session, policy: Policy, now: datetime) -> bool:
    """Keeps the settings as given and says whether that changed them. The caller commits."""
    if policy == load(db):
        return False
    row = db.get(AiClearingSettings, 1)
    if row is None:
        row = AiClearingSettings(id=1)
        db.add(row)
    row.mode = policy.mode
    row.minimum = policy.minimum
    row.classes = list(policy.kinds)
    row.sources = list(policy.sources)
    row.ceiling = policy.ceiling
    row.daily_cap = policy.daily_cap
    row.updated_at = now
    db.flush()
    return True


def blocked(incident: Incident, reading: AiTriage, policy: Policy, tuning: Tuning) -> str | None:
    """Why the AI may not clear the incident on this reading, in a few words, or None where it
    may. Nothing here is about the mode, the cap or the incident's standing: see
    ``clearing.clears`` for those."""
    if reading.verdict not in MUTING:
        return "The AI did not say it was nothing."
    if reading.classification not in policy.kinds:
        return f"The AI called it {reading.classification}, which it may not clear."
    if reading.confidence < policy.minimum:
        return f"The AI was only {reading.confidence}% sure, and {policy.minimum}% is asked."
    outside = sorted(set(incident.sources) - set(policy.sources)) if policy.sources else []
    if outside:
        return f"It involves {', '.join(outside)}, which the AI may not clear."
    if (
        incident.severity > CEILINGS[policy.ceiling]
        or incident.severity >= attention.CLEARABLE_BELOW
    ):
        return f"It is more serious than {policy.ceiling}, the most the AI may clear."
    if attention.escalated(incident, tuning):
        return "It is more than scanning: a chain of stages or devices, or an attack."
    return None


def cleared_lately(db: Session, now: datetime) -> int:
    """How many verdicts the AI has given in the last 24 hours."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action == Action.VERDICT_GIVEN_BY_AI.value,
                AuditEvent.occurred_at >= now - CAP_PERIOD,
            )
        )
        or 0
    )


def held(db: Session, policy: Policy, now: datetime) -> str | None:
    """Why the AI is not clearing by itself right now, in words: the cap for the day is reached or
    the spending limit is used up. None where nothing is in the way."""
    if policy.mode != "automatic":
        return None
    if cleared_lately(db, now) >= policy.daily_cap:
        return (
            f"The AI has cleared {policy.daily_cap} incidents in the last 24 hours, the most it "
            f"is allowed. What it finds after that waits for you."
        )
    spending = limits.reached(db, now)
    if spending is not None:
        return f"The AI has stopped clearing. {spending}"
    return None
