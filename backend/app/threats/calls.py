"""What is thought of an incident beyond the rules, and whose opinion that is.

Three voices can say what kind of thing an incident is, and the owner's comes first:

1. The owner's word on its family: ``background`` (it is noise, whatever the AI says) or
   ``watch`` (never set it aside).
2. The AI's reading of this one incident (app/ai/triage.py).
3. The AI's judgement of its family (app/ai/families.py), which is one answer for all of it.

An AI's opinion counts only while it is in effect (``counts``): one that the owner disagreed with
never does, and one that is waiting for their review counts only if it raises the alarm, because
the AI may sound an alarm on its own but sets something aside only with the owner's agreement, or
as they allowed (``app/review``).

The result is kept on the incident (``ai_class``, ``ai_confidence``, ``ai_basis``) so that
counting and listing need only its columns. ``resolve`` is the whole rule; ``sync`` applies it.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AiTriage, Incident, IncidentFamily

NOISE: Final = "noise"
QUIET: Final = ("noise", "probe")
LOUD: Final = ("compromise", "attack")
OWNER: Final = "owner"
READING: Final = "reading"
FAMILY: Final = "family"
CHUNK: Final = 5000


@dataclass(frozen=True)
class Call:
    """What is thought of an incident: its kind, how sure, and by whom."""

    kind: str | None
    confidence: int | None
    basis: str | None


NONE: Final = Call(None, None, None)


def counts(review: str | None, kind: str | None) -> bool:
    """Whether an AI's opinion of ``kind`` is in effect given where its review stands: it counts
    when the owner agreed or it counted at once, and a waiting one counts only if it is loud."""
    if review == "disagreed":
        return False
    return review != "pending" or kind in LOUD


def resolve(
    owner: str | None,
    reading: tuple[str, int] | None,
    family: tuple[str | None, int | None],
) -> Call:
    """The call for an incident from the owner's word on its family, the AI's reading of it and
    the AI's judgement of the family."""
    if owner == "background":
        return Call(NOISE, 100, OWNER)
    if reading is not None:
        chosen = Call(reading[0], reading[1], READING)
    elif family[0] is not None and family[1] is not None:
        chosen = Call(family[0], family[1], FAMILY)
    else:
        chosen = NONE
    if owner == "watch" and chosen.kind in QUIET:
        # Never set aside: the owner's word stands, and nothing says what it is.
        return Call(None, None, OWNER)
    return chosen


def sync(
    db: Session, incident_ids: Sequence[int] | None = None, family_id: int | None = None
) -> int:
    """Works out the call for incidents (the given ones, or a family's, or all) and keeps it where
    it has changed. Returns how many changed. The caller commits."""
    query = (
        select(
            Incident.id,
            Incident.ai_class,
            Incident.ai_confidence,
            Incident.ai_basis,
            IncidentFamily.owner_call,
            IncidentFamily.ai_class,
            IncidentFamily.ai_confidence,
            AiTriage.classification,
            AiTriage.confidence,
            IncidentFamily.review,
            AiTriage.review,
        )
        .outerjoin(IncidentFamily, IncidentFamily.id == Incident.family_id)
        .outerjoin(AiTriage, AiTriage.incident_id == Incident.id)
    )
    if incident_ids is not None:
        query = query.where(Incident.id.in_(incident_ids))
    if family_id is not None:
        query = query.where(Incident.family_id == family_id)
    changes: dict[Call, list[int]] = defaultdict(list)
    for row in db.execute(query):
        (
            incident_id,
            kind,
            sure,
            basis,
            owner,
            family_kind,
            family_sure,
            read_kind,
            read_sure,
            family_review,
            read_review,
        ) = row
        reading = (read_kind, read_sure) if read_kind and counts(read_review, read_kind) else None
        family = (family_kind, family_sure) if counts(family_review, family_kind) else (None, None)
        call = resolve(owner, reading, family)
        if call != Call(kind, sure, basis):
            changes[call].append(incident_id)
    for call, ids in changes.items():
        for start in range(0, len(ids), CHUNK):
            db.execute(
                update(Incident)
                .where(Incident.id.in_(ids[start : start + CHUNK]))
                .values(ai_class=call.kind, ai_confidence=call.confidence, ai_basis=call.basis)
            )
    return sum(len(ids) for ids in changes.values())
