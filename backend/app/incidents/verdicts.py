"""The owner's verdicts: which of the rules they made a signal matches, and what that says of an
incident made of such signals.

A signal that is not suspicious or low priority is muted: it stays in the timeline and is counted
in the incident, but it adds nothing to how serious or how sure the incident is, so an incident
made only of such signals is sure of nothing and raises no alarm. A signal that is a real threat
makes the incident certain, whatever else it holds.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.incidents.subject import Signal, subject_of
from app.models import IncidentSignal, VerdictRule

NOT_SUSPICIOUS: Final = "not_suspicious"
LOW_PRIORITY: Final = "low_priority"
THREAT: Final = "threat"
# The verdicts that keep a signal from counting.
MUTING: Final = (NOT_SUSPICIOUS, LOW_PRIORITY)
# When two rules of the same weight disagree, the one that would raise an alarm wins: the owner
# said so about at least that much.
STRENGTH: Final = {NOT_SUSPICIOUS: 0, LOW_PRIORITY: 1, THREAT: 2}


def load(db: Session) -> list[VerdictRule]:
    """Every rule, oldest first, so that the same signals are always judged the same way."""
    return list(db.scalars(select(VerdictRule).order_by(VerdictRule.id)))


def hits(db: Session, rule_ids: Sequence[int]) -> dict[int, tuple[int, datetime]]:
    """For each rule that has been applied to a signal in an incident's timeline, how many and
    when the latest happened."""
    rows = db.execute(
        select(
            IncidentSignal.verdict_rule_id,
            func.count(),
            func.max(IncidentSignal.occurred_at),
        )
        .where(IncidentSignal.verdict_rule_id.in_(rule_ids))
        .group_by(IncidentSignal.verdict_rule_id)
    ).all()
    return {rule_id: (count, last) for rule_id, count, last in rows if rule_id is not None}


def matches(rule: VerdictRule, signal: Signal) -> bool:
    """Whether a signal is what a rule is about: all that it names, and no more is asked."""
    if rule.source is not None and rule.source != signal.source:
        return False
    if rule.signature is not None and rule.signature != signal.signature:
        return False
    return rule.address is None or str(rule.address) in _about(signal)


def _about(signal: Signal) -> set[str]:
    """The addresses a verdict on an address applies to a signal by: the one it is about and the
    one it came from, and not the one it was going to. A device that an attack is aimed at is
    not excused the attack by being called fine."""
    named = {str(signal.src_address)} if signal.src_address is not None else set[str]()
    subject = subject_of(signal)
    return named if subject.startswith("rule:") else {*named, subject}


def _weight(rule: VerdictRule) -> tuple[int, int]:
    """The rule that names more is the more specific, and wins; then the stronger verdict."""
    named = (rule.address, rule.source, rule.signature)
    return sum(item is not None for item in named), STRENGTH[rule.verdict]


def judge(signal: Signal, rules: Sequence[VerdictRule]) -> VerdictRule | None:
    """The rule that decides what is said of a signal, or none if the owner has said nothing."""
    return max((rule for rule in rules if matches(rule, signal)), key=_weight, default=None)


def muted(counts: Mapping[str, int]) -> int:
    """How many of an incident's signals are not suspicious or low priority."""
    return sum(counts.get(verdict, 0) for verdict in MUTING)


def rollup(counts: Mapping[str, int], signals: int) -> str | None:
    """What the verdicts say of the incident as a whole."""
    if counts.get(THREAT, 0):
        return THREAT
    if signals and muted(counts) == signals:
        return LOW_PRIORITY if counts.get(LOW_PRIORITY, 0) else NOT_SUSPICIOUS
    return None
