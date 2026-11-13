"""The owner's verdicts: which of the rules they made a signal matches, and what that says of an
incident made of such signals.

A signal that is not suspicious or low priority is muted: it stays in the timeline and is counted
in the incident, but it adds nothing to how serious or how sure the incident is, so an incident
made only of such signals is sure of nothing and raises no alarm. A signal that is a real threat
makes the incident certain, whatever else it holds.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network
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


def matches(rule: VerdictRule, signal: Signal, about: set[str] | None = None) -> bool:
    """Whether a signal is what a rule is about: all that it names, and no more is asked. The
    addresses it is about (see ``_about``) can be given when they are known, as they are the same
    for every rule."""
    if rule.source is not None and rule.source != signal.source:
        return False
    if rule.signature is not None and rule.signature != signal.signature:
        return False
    if rule.destination is not None:
        return _sent_to(rule.address, rule.destination, signal)
    return rule.address is None or str(rule.address) in (_about(signal) if about is None else about)


def _sent_to(
    device: IPv4Address | IPv6Address | None, network: IPv4Network | IPv6Network, signal: Signal
) -> bool:
    """Whether a signal is the device sending to the network a rule names. Only what the device
    sends is about it: what comes back to it, or is sent to it by something else, is not, so an
    attack on the device still counts."""
    return (
        device is not None
        and signal.src_address == device
        and signal.dst_address is not None
        and signal.dst_address in network
    )


def _about(signal: Signal) -> set[str]:
    """The addresses a verdict on an address applies to a signal by: the one it is about and the
    one it came from, and not the one it was going to. A device that an attack is aimed at is
    not excused the attack by being called fine."""
    named = {str(signal.src_address)} if signal.src_address is not None else set[str]()
    subject = subject_of(signal)
    return named if subject.startswith("rule:") else {*named, subject}


def _weight(rule: VerdictRule) -> tuple[int, int]:
    """The rule that names more is the more specific, and wins; then the stronger verdict."""
    named = (rule.address, rule.source, rule.signature, rule.destination)
    return sum(item is not None for item in named), STRENGTH[rule.verdict]


def standing(
    rules: Sequence[VerdictRule], source: str, signature: str | None
) -> VerdictRule | None:
    """The rule that says what the owner thinks of an alert that a program gave this signature,
    whichever address it comes from. A rule that names an address says it of the alerts about that
    address only, so it is not one of them."""
    return max(
        (
            rule
            for rule in rules
            if rule.address is None
            and rule.source in (None, source)
            and rule.signature in (None, signature)
        ),
        key=_weight,
        default=None,
    )


def judge(signal: Signal, rules: Sequence[VerdictRule]) -> VerdictRule | None:
    """The rule that decides what is said of a signal, or none if the owner has said nothing."""
    # What a signal is about is worked out once, however many rules there are to ask.
    about = _about(signal) if any(rule.address is not None for rule in rules) else None
    return max((rule for rule in rules if matches(rule, signal, about)), key=_weight, default=None)


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
