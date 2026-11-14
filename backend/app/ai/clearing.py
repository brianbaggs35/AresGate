"""The AI clears a false positive: it gives a verdict, and the record says the AI did.

An AI that reads an incident may say it is nothing (``not_suspicious``, or ``low_priority``) and why
(``AiTriage.verdict`` and ``verdict_reason``). Until now that was a suggestion for the owner to
accept. With the owner's switch on (Settings > Threat detection, off until they turn it on), a
suggestion the AI is sure of is given as a verdict rule of its own, so that everything that already
respects verdicts respects it: the incident is muted in the timeline, out of the counts of what
needs the owner, and the same match never raises an alarm again.

It is the owner's to take back, and it is never the owner's word:

- a rule says who gave it (``VerdictRule.given_by``) and, for the AI, how sure it was, why, which
  provider and model, and which incident it read;
- taking one back (``app/api/verdicts.py``) also vetoes the match (``AiClearVeto``), so the AI does
  not clear it again; the owner giving the verdict themselves replaces the AI's and makes it theirs;
- the AI never clears what the owner has a verdict on, a critical incident or anything that is more
  than scanning (a chain of stages or of devices, or an AI that is sure it is an attack), and only
  matches by what the incident is about narrowly: its address with the program and the
  signature of its strongest alert, or the program and signature where it names no address.

Each clear is in the audit log.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from ipaddress import ip_address
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.audit import Action, Outcome
from app.incidents import attention, engine
from app.incidents.verdicts import MUTING
from app.models import AiClearVeto, AiTriage, Incident, IncidentSignal, VerdictRule
from app.threats.settings import Tuning

GIVER_AI: Final = "ai"
GIVER_OWNER: Final = "owner"
MAX_NOTE: Final = 500


@dataclass(frozen=True)
class Match:
    """What a verdict is about: the columns a rule matches by."""

    address: str | None
    source: str | None
    signature: str | None


def _match(db: Session, incident: Incident) -> Match | None:
    """What clearing the incident would be about: its address (where it has one) with the program
    and signature of its strongest alert. None where no signal has a signature, since a rule that
    names only an address would clear everything about it."""
    strongest = db.execute(
        select(IncidentSignal.source, IncidentSignal.signature)
        .where(IncidentSignal.incident_id == incident.id, IncidentSignal.signature.is_not(None))
        .order_by(IncidentSignal.severity.desc(), IncidentSignal.occurred_at, IncidentSignal.id)
        .limit(1)
    ).first()
    if strongest is None:
        return None
    try:
        address = str(ip_address(incident.subject))
    except ValueError:
        address = None
    return Match(address, strongest.source, strongest.signature)


def _taken(db: Session, match: Match) -> bool:
    """Whether the owner has taken this match back from the AI, or has a verdict of their own that
    says something of it (the same match, or the program and signature with any address)."""
    vetoed = db.scalars(
        select(AiClearVeto.id).where(
            AiClearVeto.address.is_not_distinct_from(match.address),
            AiClearVeto.source.is_not_distinct_from(match.source),
            AiClearVeto.signature.is_not_distinct_from(match.signature),
        )
    ).first()
    said = db.scalars(
        select(VerdictRule.id).where(
            VerdictRule.destination.is_(None),
            VerdictRule.address.is_not_distinct_from(match.address),
            VerdictRule.source.is_not_distinct_from(match.source),
            VerdictRule.signature.is_not_distinct_from(match.signature),
        )
    ).first()
    return vetoed is not None or said is not None


def clears(incident: Incident, reading: AiTriage, tuning: Tuning) -> bool:
    """Whether the reading is a verdict the AI may give on the incident: the owner's switch is on,
    it says the incident is nothing and is sure enough (as sure as the owner asks of the AI before
    it sets something aside), the incident is going on, is not critical or more than scanning, and
    the owner has said nothing of it."""
    return (
        tuning.ai_gives_verdicts
        and reading.verdict in MUTING
        and reading.confidence >= tuning.clear_from
        and incident.status in attention.ACTIVE
        and incident.verdict is None
        and incident.severity < attention.CLEARABLE_BELOW
        and not attention.escalated(incident, tuning)
    )


def clear(
    db: Session, incident: Incident, reading: AiTriage, tuning: Tuning, now: datetime
) -> VerdictRule | None:
    """Gives the verdict the AI read of the incident, if it may, and returns the rule, or None
    where it may not. The caller commits, with the reading."""
    if not clears(incident, reading, tuning):
        return None
    match = _match(db, incident)
    if match is None or _taken(db, match):
        return None
    engine.hold(db)
    reason = (reading.verdict_reason or reading.headline).strip()
    rule = VerdictRule(
        verdict=str(reading.verdict),
        address=match.address,
        source=match.source,
        signature=match.signature,
        note=reason[:MAX_NOTE],
        given_by=GIVER_AI,
        ai_confidence=reading.confidence,
        ai_provider=reading.provider,
        ai_model=reading.model,
        ai_incident_id=incident.id,
        created_at=now,
        updated_at=now,
    )
    db.add(rule)
    db.flush()
    audit.record(
        db,
        Action.VERDICT_GIVEN_BY_AI,
        Outcome.SUCCESS,
        detail=facts(rule),
        now=now,
    )
    engine.reapply(db, engine.reach(db, rule))
    return rule


def facts(rule: VerdictRule) -> dict[str, str | int | bool]:
    """What the audit log says of a verdict the AI gave or had taken back."""
    said: dict[str, str | int | bool | None] = {
        "verdict_id": rule.id,
        "verdict": rule.verdict,
        "address": str(rule.address) if rule.address is not None else None,
        "source": rule.source,
        "signature": rule.signature,
        "confidence": rule.ai_confidence,
        "provider": rule.ai_provider,
        "model": rule.ai_model,
        "incident_id": rule.ai_incident_id,
    }
    return {name: value for name, value in said.items() if value is not None}


def of(db: Session, incidents: Sequence[Incident]) -> dict[int, VerdictRule]:
    """For each incident the AI cleared, the verdict it gave. An incident is the AI's to have
    cleared only while the owner's muting verdict is not on any of its signals: where they said
    something too, it is theirs."""
    ids = [incident.id for incident in incidents if incident.verdict in MUTING]
    if not ids:
        return {}
    rows = db.execute(
        select(IncidentSignal.incident_id, VerdictRule)
        .join(VerdictRule, VerdictRule.id == IncidentSignal.verdict_rule_id)
        .where(IncidentSignal.incident_id.in_(ids), VerdictRule.verdict.in_(MUTING))
        .distinct()
        .order_by(VerdictRule.id)
    ).all()
    given: dict[int, VerdictRule] = {}
    owned: set[int] = set()
    for incident_id, rule in rows:
        if rule.given_by == GIVER_AI:
            given[incident_id] = rule
        else:
            owned.add(incident_id)
    return {incident_id: rule for incident_id, rule in given.items() if incident_id not in owned}


def claim(rule: VerdictRule) -> bool:
    """Makes a verdict the AI gave the owner's, because they said it themselves or changed it: it
    is theirs to keep, and no longer says how sure the AI was. Whether it was the AI's."""
    if rule.given_by != GIVER_AI:
        return False
    rule.given_by = GIVER_OWNER
    rule.ai_confidence = None
    rule.ai_provider = None
    rule.ai_model = None
    rule.ai_incident_id = None
    return True


def take_back(db: Session, rule: VerdictRule) -> None:
    """Records that the owner took a verdict back from the AI: the AI does not give it again. The
    caller removes the rule and commits."""
    exists = db.scalars(
        select(AiClearVeto.id).where(
            AiClearVeto.address.is_not_distinct_from(rule.address),
            AiClearVeto.source.is_not_distinct_from(rule.source),
            AiClearVeto.signature.is_not_distinct_from(rule.signature),
        )
    ).first()
    if exists is None:
        db.add(AiClearVeto(address=rule.address, source=rule.source, signature=rule.signature))
