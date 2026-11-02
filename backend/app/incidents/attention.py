"""Whether an incident needs the owner, said in one place.

The dashboard's sentence, its Needs you lane, the Incidents page's links and (later) a notifier
that decides what is worth a message all ask the same question: of an incident that is going on,
is it something the owner should be asked about, and if not, why not? Asking it of one function
keeps them from drifting apart, which is how a banner came to say "3,642 serious alerts" while
nothing needed anyone.

An incident has exactly one *standing*, the first of these that is true:

- ``HANDLED``: it is resolved or dismissed already.
- ``AI_CLEARED``: the AI called it a false positive and the owner has not overruled it (ticket
  163; nothing is cleared this way until that lands, but the name is here so that callers can
  branch on it now).
- ``MUTED``: the owner's own verdict calls it not suspicious or low priority.
- ``UNSURE``: AresGate's confidence in it is below the floor.
- ``NEEDS_YOU``: everything else.

``standing`` answers it for one incident row, and ``clauses`` is the same rule as SQL, for
counting and listing many. A test holds the two to agreeing, so change them together.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from sqlalchemy import ColumnElement, and_, false, func, or_, select
from sqlalchemy.orm import Session

from app.incidents import rules
from app.incidents.verdicts import MUTING
from app.models import Incident

# The statuses of an incident that someone still has to look at.
ACTIVE: Final = ("open", "investigating")
# How sure AresGate has to be of an incident for it to be asked about: medium confidence, unless
# the owner's settings say more.
NEEDS_YOU_FROM: Final = rules.MEDIUM_FROM
# How sure it has to be of one for it to be called urgent, which is what raises the alarm.
URGENT_FROM: Final = rules.HIGH_FROM


class Standing(StrEnum):
    HANDLED = "handled"
    AI_CLEARED = "ai_cleared"
    MUTED = "muted"
    UNSURE = "unsure"
    NEEDS_YOU = "needs_you"


def standing(incident: Incident, floor: int = NEEDS_YOU_FROM) -> Standing:
    """Why an incident is or isn't asked about: the first reason that applies to it."""
    if incident.status not in ACTIVE:
        return Standing.HANDLED
    if incident.verdict in MUTING:
        return Standing.MUTED
    if incident.confidence < floor:
        return Standing.UNSURE
    return Standing.NEEDS_YOU


def needs_you(incident: Incident, floor: int = NEEDS_YOU_FROM) -> bool:
    """Whether the owner should be asked about the incident."""
    return standing(incident, floor) is Standing.NEEDS_YOU


def urgent(incident: Incident, floor: int = NEEDS_YOU_FROM) -> bool:
    """Whether it needs the owner and AresGate is highly confident that it is real."""
    return needs_you(incident, floor) and incident.confidence >= URGENT_FROM


def clauses(floor: int = NEEDS_YOU_FROM) -> dict[Standing, ColumnElement[bool]]:
    """``standing`` as SQL: for each standing, the condition on an incident row that gives it.
    They don't overlap, and between them they cover every incident."""
    active = Incident.status.in_(ACTIVE)
    loud = or_(Incident.verdict.is_(None), Incident.verdict.not_in(MUTING))
    sure = Incident.confidence >= floor
    return {
        Standing.HANDLED: ~active,
        # Nothing is cleared by the AI until ticket 163, so no incident has this standing yet.
        Standing.AI_CLEARED: false(),
        Standing.MUTED: and_(active, ~loud),
        Standing.UNSURE: and_(active, loud, ~sure),
        Standing.NEEDS_YOU: and_(active, loud, sure),
    }


def urgent_clause(floor: int = NEEDS_YOU_FROM) -> ColumnElement[bool]:
    """``urgent`` as SQL."""
    return and_(clauses(floor)[Standing.NEEDS_YOU], Incident.confidence >= URGENT_FROM)


@dataclass(frozen=True)
class Tally:
    """How many of the incidents that are going on stand each way."""

    muted: int
    unsure: int
    needs_you: int
    urgent: int

    @property
    def active(self) -> int:
        return self.muted + self.unsure + self.needs_you


def tally(db: Session, floor: int = NEEDS_YOU_FROM) -> Tally:
    """Counts the incidents that are going on by their standing, at that floor."""
    by = clauses(floor)
    row = db.execute(
        select(
            func.count().filter(by[Standing.MUTED]),
            func.count().filter(by[Standing.UNSURE]),
            func.count().filter(by[Standing.NEEDS_YOU]),
            func.count().filter(urgent_clause(floor)),
        )
    ).one()
    return Tally(*row)
