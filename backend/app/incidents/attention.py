"""Whether an incident needs the owner, said in one place.

The dashboard's sentence, its Needs you lane, the Incidents page's links, the Threats page and
(later) a notifier that decides what is worth a message all ask the same question: of an incident
that is going on, is it something the owner should be asked about, and if not, why not? Asking it
of one function keeps them from drifting apart, which is how a banner came to say "3,642 serious
alerts" while nothing needed anyone.

An incident has exactly one *standing*, the first of these that is true:

- ``HANDLED``: it is resolved or dismissed already.
- ``MUTED``: the owner's own verdict calls it not suspicious or low priority.
- ``UNSURE``: AresGate's confidence in it is below the floor, which is lower for an incident that
  touched an important device and higher for one that touched only guest or IoT devices (the
  owner's settings say by how much; see ``app/threats/importance.py``).
- ``AI_CLEARED``: it would need the owner, but an AI judged it background (noise or a probe) and
  was sure enough (the owner's settings say how sure), and nothing in it says otherwise.
- ``NEEDS_YOU``: everything else.

What needs the owner is then told in two: a **threat** (high confidence that it is real) and a
**suspect** (worth a look, not yet sure). A chain, which is more than scanning (an exploit after a
scan, a sign that it worked: ``app/threats/stages.py``) or an attack across two devices (an exploit
at one, then that device calling out: ``app/threats/chains.py``), is never unsure and never set
aside, and an AI that is sure it is an attack or a compromise makes it a threat whatever the rules
think.
While the AI is watching, rules alone do not make a threat: it has to agree, except for the most
serious, which cannot wait for it. So the standing of a scan is a thing the AI decides, and the
standing of an attack is not left to it alone.

``standing`` answers it for one incident row, and ``clauses`` is the same rule as SQL, for
counting and listing many. A test holds the two to agreeing, so change them together.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from sqlalchemy import ColumnElement, and_, case, false, func, or_, select
from sqlalchemy.orm import Session

from app.events.event import Severity
from app.incidents import rules
from app.incidents.verdicts import MUTING
from app.models import Incident
from app.threats import calls, stages
from app.threats.settings import Tuning

# The statuses of an incident that someone still has to look at.
ACTIVE: Final = ("open", "investigating")
# How sure AresGate has to be of an incident for it to be asked about: medium confidence, unless
# the owner's settings say more.
NEEDS_YOU_FROM: Final = rules.MEDIUM_FROM
# How sure it has to be of one for it to be called urgent, which is what raises the alarm.
URGENT_FROM: Final = rules.HIGH_FROM


class Standing(StrEnum):
    HANDLED = "handled"
    MUTED = "muted"
    UNSURE = "unsure"
    AI_CLEARED = "ai_cleared"
    NEEDS_YOU = "needs_you"


class Lane(StrEnum):
    """Where an incident goes on the Threats page. Handled and muted ones are in none."""

    THREAT = "threat"
    SUSPECT = "suspect"
    BACKGROUND = "background"


# The most serious an incident can be and still be set aside: a critical one is never background.
CLEARABLE_BELOW: Final = Severity.CRITICAL


def escalated(incident: Incident, tuning: Tuning) -> bool:
    """Whether the incident is more than the rules alone say: a chain of stages, a step of a chain
    across two devices (``app/threats/chains.py``), or an AI that is sure it is an attack or a
    compromise. Such an incident is never unsure and never set aside."""
    return (
        stages.is_chain(incident.stages or [])
        or incident.chain_id is not None
        or (
            incident.ai_class in calls.LOUD
            and incident.ai_confidence is not None
            and incident.ai_confidence >= tuning.threat_from
        )
    )


def _cleared(incident: Incident, tuning: Tuning) -> bool:
    return (
        tuning.ai_may_clear
        and incident.verdict is None
        and incident.ai_class in calls.QUIET
        and incident.ai_confidence is not None
        and incident.ai_confidence >= tuning.clear_from
        and incident.severity < CLEARABLE_BELOW
    )


def standing(
    incident: Incident, floor: int = NEEDS_YOU_FROM, tuning: Tuning | None = None
) -> Standing:
    """Why an incident is or isn't asked about: the first reason that applies to it."""
    tuning = tuning or Tuning()
    if incident.status not in ACTIVE:
        return Standing.HANDLED
    if incident.verdict in MUTING:
        return Standing.MUTED
    sure = escalated(incident, tuning)
    if incident.confidence < floor + tuning.shift(incident.importance) and not sure:
        return Standing.UNSURE
    if not sure and _cleared(incident, tuning):
        return Standing.AI_CLEARED
    return Standing.NEEDS_YOU


def needs_you(
    incident: Incident, floor: int = NEEDS_YOU_FROM, tuning: Tuning | None = None
) -> bool:
    """Whether the owner should be asked about the incident."""
    return standing(incident, floor, tuning) is Standing.NEEDS_YOU


def is_threat(
    incident: Incident, floor: int = NEEDS_YOU_FROM, tuning: Tuning | None = None
) -> bool:
    """Whether it needs the owner and is highly likely to be real: the owner said so, it is more
    than the rules alone say (a chain, or an AI that is sure), or the rules are sure enough and,
    while an AI is watching, it can't wait for it to agree."""
    tuning = tuning or Tuning()
    if not needs_you(incident, floor, tuning):
        return False
    rules_sure = incident.confidence >= tuning.threat_from and (
        not tuning.confirming or incident.severity >= CLEARABLE_BELOW
    )
    return incident.verdict == "threat" or escalated(incident, tuning) or rules_sure


def urgent(incident: Incident, floor: int = NEEDS_YOU_FROM, tuning: Tuning | None = None) -> bool:
    """Whether it needs the owner and AresGate is highly confident that it is real, which is what
    raises the alarm."""
    return is_threat(incident, floor, tuning)


def lane_of(
    incident: Incident, floor: int = NEEDS_YOU_FROM, tuning: Tuning | None = None
) -> Lane | None:
    """The lane an incident is in, or None for one that is handled or muted."""
    found = standing(incident, floor, tuning)
    if found in (Standing.HANDLED, Standing.MUTED):
        return None
    if found is Standing.NEEDS_YOU:
        return Lane.THREAT if is_threat(incident, floor, tuning) else Lane.SUSPECT
    return Lane.BACKGROUND


# The AI's call with a null as something that matches nothing, so that a negation of a condition
# on it is true for an incident nobody has judged and not unknown.
_KIND = func.coalesce(Incident.ai_class, "")
_SURE = func.coalesce(Incident.ai_confidence, 0)
_VERDICT = func.coalesce(Incident.verdict, "")


def _escalated_clause(tuning: Tuning) -> ColumnElement[bool]:
    return or_(
        Incident.stages.contains([stages.FOOTHOLD]),
        func.cardinality(Incident.stages) > 1,
        Incident.chain_id.is_not(None),
        and_(_KIND.in_(calls.LOUD), tuning.threat_from <= _SURE),
    )


def clauses(
    floor: int = NEEDS_YOU_FROM, tuning: Tuning | None = None
) -> dict[Standing, ColumnElement[bool]]:
    """``standing`` as SQL: for each standing, the condition on an incident row that gives it.
    They don't overlap, and between them they cover every incident."""
    tuning = tuning or Tuning()
    active = Incident.status.in_(ACTIVE)
    loud = or_(Incident.verdict.is_(None), Incident.verdict.not_in(MUTING))
    escalated = _escalated_clause(tuning)
    # An incident that touched an important device is asked about at a lower floor, and one that
    # touched only guest and IoT devices at a higher one (``Tuning.shift``).
    moved = case(
        (Incident.importance > 0, floor - tuning.important_drop),
        (Incident.importance < 0, floor + tuning.low_raise),
        else_=floor,
    )
    sure = or_(Incident.confidence >= moved, escalated)
    cleared = (
        and_(
            Incident.verdict.is_(None),
            _KIND.in_(calls.QUIET),
            tuning.clear_from <= _SURE,
            Incident.severity < CLEARABLE_BELOW,
            ~escalated,
        )
        if tuning.ai_may_clear
        else false()
    )
    return {
        Standing.HANDLED: ~active,
        Standing.MUTED: and_(active, ~loud),
        Standing.UNSURE: and_(active, loud, ~sure),
        Standing.AI_CLEARED: and_(active, loud, sure, cleared),
        Standing.NEEDS_YOU: and_(active, loud, sure, ~cleared),
    }


def threat_clause(floor: int = NEEDS_YOU_FROM, tuning: Tuning | None = None) -> ColumnElement[bool]:
    """``is_threat`` as SQL."""
    tuning = tuning or Tuning()
    rules_sure = Incident.confidence >= tuning.threat_from
    if tuning.confirming:
        rules_sure = and_(rules_sure, Incident.severity >= CLEARABLE_BELOW)
    return and_(
        clauses(floor, tuning)[Standing.NEEDS_YOU],
        or_(_VERDICT == "threat", _escalated_clause(tuning), rules_sure),
    )


def urgent_clause(floor: int = NEEDS_YOU_FROM, tuning: Tuning | None = None) -> ColumnElement[bool]:
    """``urgent`` as SQL."""
    return threat_clause(floor, tuning)


def lane_clauses(
    floor: int = NEEDS_YOU_FROM, tuning: Tuning | None = None
) -> dict[Lane, ColumnElement[bool]]:
    """``lane_of`` as SQL."""
    by = clauses(floor, tuning)
    threat = threat_clause(floor, tuning)
    return {
        Lane.THREAT: threat,
        Lane.SUSPECT: and_(by[Standing.NEEDS_YOU], ~threat),
        Lane.BACKGROUND: or_(by[Standing.UNSURE], by[Standing.AI_CLEARED]),
    }


@dataclass(frozen=True)
class Tally:
    """How many of the incidents that are going on stand each way."""

    muted: int
    unsure: int
    cleared: int
    needs_you: int
    urgent: int

    @property
    def active(self) -> int:
        return self.muted + self.unsure + self.cleared + self.needs_you

    @property
    def suspects(self) -> int:
        return self.needs_you - self.urgent


def tally(db: Session, floor: int = NEEDS_YOU_FROM, tuning: Tuning | None = None) -> Tally:
    """Counts the incidents that are going on by their standing, at that floor."""
    by = clauses(floor, tuning)
    row = db.execute(
        select(
            func.count().filter(by[Standing.MUTED]),
            func.count().filter(by[Standing.UNSURE]),
            func.count().filter(by[Standing.AI_CLEARED]),
            func.count().filter(by[Standing.NEEDS_YOU]),
            func.count().filter(urgent_clause(floor, tuning)),
        )
    ).one()
    return Tally(*row)
