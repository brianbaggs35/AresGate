"""The review queue: what the AI cleared, and what it suggests clearing, for the owner to confirm or
take back.

- *Cleared* is a verdict the AI gave itself (``VerdictRule.given_by = "ai"``, see
  ``app/ai/clearing.py``). **Confirm** makes it the owner's, so it is firm and no longer says it was
  the AI's. **Take back** removes it, judges the incident again and tells the AI not to clear that
  match again.
- *Waiting* is an incident the AI read as nothing and may clear under the owner's settings
  (``app/ai/clearing_settings.py``), that nobody has a verdict on: what the AI suggests when it is
  to ask first, and what it would have cleared where it is stopped (by its cap for the day or the
  AI spending limit). **Confirm** gives the verdict as the owner's. **Take back** turns the
  suggestion down and tells the AI not to suggest that match again.

Every step is in the audit log with the incident it was about, so the incident can say what
happened to it and who did it."""

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import clearing, clearing_settings
from app.ai.clearing import GIVER_AI, GIVER_OWNER
from app.audit import Action
from app.incidents import attention, engine
from app.incidents.verdicts import MUTING
from app.models import AiTriage, AuditEvent, Incident, VerdictRule
from app.threats import settings as threat_settings
from app.threats.settings import Tuning

# How many readings are weighed for what waits. The newest are weighed first.
CANDIDATES: Final = 500
# What a verdict the AI gave can be changed to, and what a suggestion can be confirmed as.
VERDICTS: Final = ("not_suspicious", "low_priority")
# What the trail on an incident is made of.
TRAIL: Final = (
    Action.VERDICT_GIVEN_BY_AI.value,
    Action.AI_CLEAR_CONFIRMED.value,
    Action.VERDICT_TAKEN_BACK_FROM_AI.value,
    Action.AI_SUGGESTION_CONFIRMED.value,
    Action.AI_SUGGESTION_DISMISSED.value,
)


@dataclass(frozen=True)
class Waiting:
    """An incident the AI suggests clearing."""

    incident: Incident
    reading: AiTriage


@dataclass(frozen=True)
class Cleared:
    """A verdict the AI gave, with the incident it was about and what it read, either of which may
    be gone."""

    rule: VerdictRule
    incident: Incident | None
    reading: AiTriage | None


def waiting(db: Session, policy: clearing_settings.Policy, tuning: Tuning) -> list[Waiting]:
    """What the AI suggests clearing, newest reading first. Nothing where it is off."""
    if policy.mode == "off":
        return []
    rows = db.execute(
        select(Incident, AiTriage)
        .join(AiTriage, AiTriage.incident_id == Incident.id)
        .where(
            Incident.status.in_(attention.ACTIVE),
            Incident.verdict.is_(None),
            AiTriage.verdict.in_(MUTING),
        )
        .order_by(AiTriage.read_at.desc(), Incident.id.desc())
        .limit(CANDIDATES)
    ).all()
    found: list[Waiting] = []
    for incident, reading in rows:
        if clearing_settings.blocked(incident, reading, policy, tuning) is not None:
            continue
        match = clearing.match_of(db, incident)
        if match is not None and not clearing.taken(db, match):
            found.append(Waiting(incident, reading))
    return found


def cleared(db: Session) -> list[Cleared]:
    """The verdicts the AI gave that the owner has not made theirs, newest first."""
    rules = db.scalars(
        select(VerdictRule)
        .where(VerdictRule.given_by == GIVER_AI)
        .order_by(VerdictRule.created_at.desc(), VerdictRule.id.desc())
    ).all()
    ids = [rule.ai_incident_id for rule in rules if rule.ai_incident_id is not None]
    incidents = {item.id: item for item in db.scalars(select(Incident).where(Incident.id.in_(ids)))}
    readings = {
        item.incident_id: item
        for item in db.scalars(select(AiTriage).where(AiTriage.incident_id.in_(ids)))
    }
    return [
        Cleared(
            rule, incidents.get(rule.ai_incident_id or 0), readings.get(rule.ai_incident_id or 0)
        )
        for rule in rules
    ]


Facts = dict[str, str | int | bool]


def counts(db: Session) -> tuple[int, int]:
    """How many suggestions wait, and how many verdicts of the AI's the owner has not confirmed."""
    found = waiting(db, clearing_settings.load(db), threat_settings.load(db))
    unconfirmed = db.scalar(
        select(func.count()).select_from(VerdictRule).where(VerdictRule.given_by == GIVER_AI)
    )
    return len(found), int(unconfirmed or 0)


def confirm_cleared(rule: VerdictRule, now: datetime) -> Facts | None:
    """Makes a verdict the AI gave the owner's, and says what the audit log says of it, or None
    where it was not the AI's. The caller commits."""
    facts = clearing.facts(rule)
    if not clearing.claim(rule):
        return None
    rule.updated_at = now
    return facts


def confirm_suggestion(
    db: Session, incident: Incident, reading: AiTriage, verdict: str | None, now: datetime
) -> tuple[VerdictRule, Facts] | None:
    """Gives the verdict the AI suggested (or ``verdict``, if the owner says another) as the
    owner's own, and returns it with what the audit log says of it, or None where there is no
    longer anything to give it on. The caller commits."""
    match = clearing.match_of(db, incident)
    if match is None or clearing.said(db, match):
        return None
    engine.hold(db)
    rule = VerdictRule(
        verdict=verdict or str(reading.verdict),
        address=match.address,
        source=match.source,
        signature=match.signature,
        note=(reading.verdict_reason or reading.headline).strip()[: clearing.MAX_NOTE],
        given_by=GIVER_OWNER,
        created_at=now,
        updated_at=now,
    )
    db.add(rule)
    db.flush()
    facts = {**clearing.facts(rule), "incident_id": incident.id, "confidence": reading.confidence}
    engine.reapply(db, engine.reach(db, rule))
    return rule, facts


def dismiss_suggestion(db: Session, incident: Incident) -> Facts | None:
    """Turns a suggestion down, so the AI does not suggest that match again, and says what the
    audit log says of it, or None where it has no match to say so about. The caller commits."""
    match = clearing.match_of(db, incident)
    if match is None:
        return None
    clearing.veto(db, match)
    said: dict[str, str | int | None] = {
        "incident_id": incident.id,
        "address": match.address,
        "source": match.source,
        "signature": match.signature,
    }
    return {name: value for name, value in said.items() if value is not None}


@dataclass(frozen=True)
class Step:
    """One thing that happened to an incident's clearing: what, when, and who did it."""

    action: str
    at: datetime
    by: str
    verdict: str | None
    confidence: int | None


def trail(db: Session, incident_id: int) -> list[Step]:
    """What happened to the AI clearing an incident, oldest first: the AI clearing it or
    suggesting it, and the owner confirming, taking back or turning down."""
    rows = db.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.action.in_(TRAIL),
            AuditEvent.detail["incident_id"].as_integer() == incident_id,
        )
        .order_by(AuditEvent.occurred_at, AuditEvent.id)
    ).all()
    return [
        Step(
            row.action,
            row.occurred_at,
            "the AI" if row.action == Action.VERDICT_GIVEN_BY_AI.value else row.username or "you",
            str(row.detail["verdict"]) if row.detail and "verdict" in row.detail else None,
            int(row.detail["confidence"]) if row.detail and "confidence" in row.detail else None,
        )
        for row in rows
    ]
