"""Changing many incidents at once: the status of each, or a verdict on what each is about.

Every change is worked out the same way whether it is made or only asked about, so that what a
person is told before a large change is what it then does. It says how much it touches, how much
of that it changes, and how to take it back.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Final, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.models import Incident, IncidentSignal, VerdictRule

# The most incidents a change is made to at once. A home network has far fewer than this, so it
# is the limit of what a person can look over before saying yes, not of what the database can do.
MAX_INCIDENTS: Final = 1000

Address = IPv4Address | IPv6Address


@dataclass(frozen=True)
class Scope:
    """What a verdict on an incident is about: all that is set, and no more, has to match."""

    address: Address | None = None
    source: str | None = None
    signature: str | None = None


@dataclass(frozen=True)
class Done:
    """What a change did, or would do."""

    # How many incidents it was asked about, how many signals are in them, and in how many of
    # them it changes anything.
    incidents: int
    signals: int
    changed: int
    # The incidents a verdict could not be given on, as they name no address and no alert, and
    # how many verdicts it makes or changes.
    skipped: int = 0
    verdicts: int = 0
    # How to take it back: the incidents it changed, by the status they had, and the verdicts it
    # made (with what they said before, if they existed).
    statuses: dict[str, list[int]] = field(default_factory=dict[str, list[int]])
    rules: list[tuple[int, str | None]] = field(default_factory=list[tuple[int, str | None]])
    # The incidents it changed, for the record.
    ids: list[int] = field(default_factory=list[int])


def set_status(incidents: Sequence[Incident], status: str, *, now: datetime, apply: bool) -> Done:
    """Says that this is what is being done about them all. Those that are already so are left
    alone."""
    previous: dict[str, list[int]] = defaultdict(list)
    for incident in incidents:
        if incident.status == status:
            continue
        previous[incident.status].append(incident.id)
        if apply:
            incident.status = status
            incident.status_changed_at = now
    ids = sorted(id_ for found in previous.values() for id_ in found)
    return Done(
        incidents=len(incidents),
        signals=sum(incident.signal_count for incident in incidents),
        changed=len(ids),
        statuses=dict(previous),
        ids=ids,
    )


def scope_of(subject: str, alert: tuple[str, str] | None) -> Scope | None:
    """What a verdict on an incident is about: the address it is about, or where it is about a
    rule that names none, the first alert in it. Nothing if there is neither."""
    if not subject.startswith("rule:"):
        try:
            return Scope(address=ip_address(subject))
        except ValueError:
            return None
    return Scope(source=alert[0], signature=alert[1]) if alert else None


def _first_alerts(db: Session, incident_ids: list[int]) -> dict[int, tuple[str, str]]:
    """For each incident, the alert that came first: the one with a signature, and its source."""
    rows = db.execute(
        select(IncidentSignal.incident_id, IncidentSignal.source, IncidentSignal.signature)
        .where(IncidentSignal.incident_id.in_(incident_ids), IncidentSignal.signature.is_not(None))
        .ext(distinct_on(IncidentSignal.incident_id))
        .order_by(IncidentSignal.incident_id, IncidentSignal.occurred_at, IncidentSignal.id)
    )
    return {incident_id: (source, cast(str, signature)) for incident_id, source, signature in rows}


def _by_scope(
    db: Session, incidents: Sequence[Incident]
) -> tuple[dict[Scope, list[Incident]], int]:
    """The incidents about each address or alert, and how many name neither."""
    alerts = _first_alerts(db, [i.id for i in incidents if i.subject.startswith("rule:")])
    about: dict[Scope, list[Incident]] = {}
    skipped = 0
    for incident in incidents:
        scope = scope_of(incident.subject, alerts.get(incident.id))
        if scope is None:
            skipped += 1
        else:
            about.setdefault(scope, []).append(incident)
    return about, skipped


def _is_said(rule: VerdictRule, verdict: str, note: str | None) -> bool:
    """Whether a rule already says this, so that there is nothing to change."""
    return rule.verdict == verdict and not (note and note != rule.note)


def _add_rule(db: Session, scope: Scope, verdict: str, note: str | None) -> VerdictRule:
    rule = VerdictRule(
        verdict=verdict,
        address=scope.address,
        source=scope.source,
        signature=scope.signature,
        note=note or None,
    )
    db.add(rule)
    db.flush()
    return rule


def _amend(rule: VerdictRule, verdict: str, note: str | None) -> tuple[int, str] | None:
    """Gives a rule the verdict and the note. What to put back if the verdict changed."""
    said = rule.verdict
    rule.verdict = verdict
    if note:
        rule.note = note
    return (rule.id, said) if said != verdict else None


def give_verdict(
    db: Session,
    incidents: Sequence[Incident],
    verdict: str,
    note: str | None,
    *,
    apply: bool,
) -> Done:
    """Says what is thought of what each incident is about, as a verdict like any other: one for
    each address or alert, whatever the number of incidents about it, and one that says so
    already is left alone. The caller then judges the signals again, and commits."""
    about, skipped = _by_scope(db, incidents)
    known = {
        (rule.address, rule.source, rule.signature): rule
        for rule in db.scalars(select(VerdictRule))
    }

    rules: list[tuple[int, str | None]] = []
    verdicts = 0
    ids: list[int] = []
    for scope, found in about.items():
        rule = known.get((scope.address, scope.source, scope.signature))
        if rule is not None and _is_said(rule, verdict, note):
            continue
        verdicts += 1
        ids.extend(incident.id for incident in found)
        if not apply:
            continue
        if rule is None:
            rules.append((_add_rule(db, scope, verdict, note).id, None))
        elif undo := _amend(rule, verdict, note):
            rules.append(undo)
    return Done(
        incidents=len(incidents),
        signals=sum(incident.signal_count for incident in incidents),
        changed=len(ids),
        skipped=skipped,
        verdicts=verdicts,
        rules=rules,
        ids=sorted(ids),
    )


def take_back(
    db: Session,
    statuses: dict[str, list[int]],
    rules: Sequence[tuple[int, str | None]],
    *,
    now: datetime,
) -> tuple[int, int]:
    """Undoes what a change did: puts the statuses back, and each verdict it made goes, or says
    what it said before. Returns how many incidents and how many verdicts that touched."""
    restored = 0
    for status, ids in statuses.items():
        for incident in db.scalars(select(Incident).where(Incident.id.in_(ids))):
            if incident.status != status:
                incident.status = status
                incident.status_changed_at = now
                restored += 1
    found = {
        rule.id: rule
        for rule in db.scalars(
            select(VerdictRule).where(VerdictRule.id.in_([rule_id for rule_id, _ in rules]))
        )
    }
    changed = 0
    for rule_id, replaced in rules:
        rule = found.get(rule_id)
        if rule is None:
            continue
        changed += 1
        if replaced is None:
            db.delete(rule)
        else:
            rule.verdict = replaced
    return restored, changed
