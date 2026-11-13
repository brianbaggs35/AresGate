"""AI judgement of families: one answer for every incident that says the same thing.

A home network sees hundreds of scanners a day, each one an incident of its own, and every one of
them says the same words. Asking an AI about each would cost hundreds of requests to learn one
thing, and would still bury the person who has to read the answers. So the AI is asked about the
*kind* (``app/threats/families.py``): a few lines about each family, many families to a request,
and one answer for all of its incidents (``noise``, ``probe``, ``attack``, ``compromise`` or
``unclear``, with how sure it is and why). That answer is what lets a scan be set aside as
background without anyone reading it, and what keeps an attack from being set aside with it:
``app/incidents/attention.py`` never clears an incident that is a chain of stages, and the AI's
reading of one incident outranks its family (``app/threats/calls.py``).

Everything goes through the gateway (app/ai/gateway.py), so the provider sees only what the
redaction level allows, every request is recorded, and the start of the prompt (the playbook and
the owner's setup, ``brief.py``) is the same every time and is cached.
"""

import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Final, cast

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app import audit
from app.ai import brief, gateway, service
from app.ai.gateway import Answer, Context, Question, Unavailable
from app.ai.redaction import Redactor
from app.ai.triage import LESSON_HEADING, POLICIES, Policy, signal_line
from app.events.event import Severity
from app.incidents import occurrences, queries
from app.incidents.attention import ACTIVE
from app.models import CLASSES, AiCall, Incident, IncidentFamily
from app.models.base import utcnow
from app.review import service as review
from app.review import settings as review_settings
from app.threats import calls, drift, families, learning, settings

PURPOSE: Final = "families"
# How many families one request is about: more would make the answer cut short and the request
# slow, and the families after the first few cost the same to read as to ask about again.
MAX_FAMILIES: Final = 12
MAX_REASON: Final = 160
EXAMPLES: Final = 2
TOP_PORTS: Final = 5
# A request that failed isn't repeated for this long.
PAUSE: Final = timedelta(minutes=15)
# How many incidents' arrays are read to say what a family's incidents have in common.
SAMPLE: Final = 5000

SYSTEM: Final = """\
You will be given a numbered list of FAMILIES. A family is a kind of incident: AresGate's rules \
grouped alerts into incidents, and every incident in a family was reported by the same program \
in the same words and comes from the same sort of place. Many incidents in a family are many \
different addresses doing the same thing, not many different events. For each family, decide \
what kind of thing it is, as an expert would explain it to the owner.

Choose one classification for each:
- compromise: the family is evidence that something on the home network is infected or taken \
over.
- attack: a targeted or active attack that deserves attention.
- probe: scanning, probing or guessing with no sign that it worked: routine background.
- noise: harmless: a misconfiguration, a rule that fires on normal traffic, a known service.
- unclear: too little to tell. Use it freely; it is better than a wrong answer.

"confidence" is how sure you are of the classification for the family as a whole, from 0 to 100. \
A family whose incidents differ a lot (some with exploit words, some with none) is not sure \
background. "reason" is one plain sentence, under 120 characters, that says why.

Answer only with the JSON you are asked for: one entry for each family, with the id you were \
given.\
"""

SCHEMA: Final[Mapping[str, object]] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "families": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "classification": {"type": "string", "enum": list(CLASSES)},
                    "confidence": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "classification", "confidence", "reason"],
            },
        }
    },
    "required": ["families"],
}


@dataclass(frozen=True)
class Judgement:
    classification: str
    confidence: int
    reason: str


@dataclass(frozen=True)
class Judged:
    """Families were judged: how many, and how many incidents that is an answer for."""

    families: int
    incidents: int


@dataclass(frozen=True)
class NotJudged:
    """Nothing was kept, and why, in words for whoever asked."""

    reason: str


Outcome = Judged | NotJudged


def about(count: int) -> str:
    """How the record of requests names a request about families."""
    return f"{count} families" if count != 1 else "1 family"


# -- which families are judged without being asked


def plan(db: Session, now: datetime, policy: Policy | None = None) -> list[int]:
    """The families to judge now, the biggest first: none if AI is off or not set up, or the usage
    level judges none by itself, or the level's hour is used. A family the owner has called is
    never judged, and one is judged again only when it has grown."""
    chosen = service.usage(db, now)
    policy = policy or POLICIES[chosen.usage_level]
    if not chosen.enabled or chosen.provider is None or policy.family_batches <= 0:
        return []
    used = (
        db.scalar(
            select(func.count())
            .select_from(AiCall)
            .where(AiCall.purpose == PURPOSE, AiCall.occurred_at >= now - timedelta(hours=1))
        )
        or 0
    )
    if used >= policy.family_batches:
        return []
    size = (
        select(Incident.family_id.label("id"), func.count().label("size"))
        .where(Incident.status.in_(ACTIVE), Incident.family_id.is_not(None))
        .group_by(Incident.family_id)
        .subquery()
    )
    wanted = IncidentFamily.judged_at.is_(None)
    # A kind that has changed since it was judged (app/threats/drift.py) is judged again whatever
    # its growth, at any level that judges kinds, though never sooner than ``PAUSE``.
    again = (IncidentFamily.judged_at < now - PAUSE) & IncidentFamily.changed_at.is_not(None)
    if policy.family_growth is not None:
        again = or_(
            again,
            (IncidentFamily.judged_at < now - PAUSE)
            & (IncidentFamily.judged_incidents * policy.family_growth <= size.c.size),
        )
    wanted = or_(wanted, again)
    return list(
        db.scalars(
            select(IncidentFamily.id)
            .join(size, size.c.id == IncidentFamily.id)
            .where(size.c.size >= policy.family_min, IncidentFamily.owner_call.is_(None), wanted)
            .order_by(
                IncidentFamily.changed_at.is_not(None).desc(), size.c.size.desc(), IncidentFamily.id
            )
            .limit(MAX_FAMILIES)
        )
    )


# -- what the AI is asked


@dataclass(frozen=True)
class Facts:
    """What a family's incidents come to."""

    family: IncidentFamily
    incidents: int
    alerts: int
    actors: int
    worst: Severity
    banned: int
    first_at: datetime
    last_at: datetime
    sources: list[str]
    stages: list[str]
    ports: list[tuple[int, int]]
    examples: list[occurrences.Occurrence]
    # What the owner has decided of its incidents so far.
    pattern: learning.Pattern = field(default_factory=learning.Pattern)


def _span(first: datetime, last: datetime) -> str:
    hours = (last - first).total_seconds() / 3600
    return f"{hours:.0f} hours" if hours >= 1 else "under an hour"


def facts_of(db: Session, ids: list[int]) -> list[Facts]:
    """What each of the families is, as its active incidents show it."""
    found: list[Facts] = []
    stats = {
        row[0]: row[1:]
        for row in db.execute(
            select(
                Incident.family_id,
                func.count(),
                func.coalesce(func.sum(Incident.signal_count), 0),
                func.count(Incident.subject.distinct()),
                func.max(Incident.severity),
                func.count().filter(Incident.banned),
                func.min(Incident.first_seen_at),
                func.max(Incident.last_seen_at),
            )
            .where(Incident.family_id.in_(ids), Incident.status.in_(ACTIVE))
            .group_by(Incident.family_id)
        )
    }
    sources: dict[int, set[str]] = defaultdict(set)
    stages: dict[int, set[str]] = defaultdict(set)
    ports: dict[int, Counter[int]] = defaultdict(Counter)
    for member, programs, stage_list, port_list in db.execute(
        select(Incident.family_id, Incident.sources, Incident.stages, Incident.ports)
        .where(Incident.family_id.in_(ids), Incident.status.in_(ACTIVE))
        .limit(SAMPLE)
    ):
        family_id = cast("int", member)
        sources[family_id].update(programs)
        stages[family_id].update(stage_list)
        ports[family_id].update(port_list)
    best = {
        cast("int", incident.family_id): incident
        for incident in db.scalars(
            select(Incident)
            .where(Incident.family_id.in_(ids), Incident.status.in_(ACTIVE))
            .ext(distinct_on(Incident.family_id))
            .order_by(Incident.family_id, Incident.confidence.desc(), Incident.id.desc())
        )
    }
    for family in db.scalars(select(IncidentFamily).where(IncidentFamily.id.in_(ids))):
        if family.id not in stats:
            continue
        count, alerts, actors, worst, banned, first, last = stats[family.id]
        found.append(
            Facts(
                family,
                count,
                alerts,
                actors,
                Severity(worst),
                banned,
                first,
                last,
                sorted(sources[family.id]),
                [stage for stage in ("recon", "access", "foothold") if stage in stages[family.id]],
                ports[family.id].most_common(TOP_PORTS),
                occurrences.group(queries.signals(db, best[family.id]))[:EXAMPLES],
            )
        )
    decided = learning.patterns(db, ids)
    found = [
        replace(item, pattern=decided.get(item.family.id, learning.Pattern())) for item in found
    ]
    order = {family_id: place for place, family_id in enumerate(ids)}
    return sorted(found, key=lambda item: order[item.family.id])


_WHERE = {
    families.INTERNET: "the internet",
    families.NETWORK: "the owner's own network",
    families.RULE: "a rule that names no address",
}


def _decided(pattern: learning.Pattern) -> list[str]:
    """What the owner has decided of the incidents of a kind, which is what they think of it."""
    if not pattern.decided:
        return []
    return [
        f"  the owner has decided {pattern.decided} of its incidents: {pattern.benign} closed as "
        f"not suspicious, low priority or dismissed, {pattern.loud} called threats, taken up or "
        "disagreed with"
    ]


def _changed(family: IncidentFamily, redactor: Redactor) -> list[str]:
    """What has changed about a kind since it was last judged, which is why it is asked about
    again, and what it was judged then."""
    lines = drift.lines_of(family, redactor.address)
    if not lines:
        return []
    before = (
        f"you judged it {family.ai_class} ({family.ai_confidence}% sure)"
        if family.ai_class
        else "it was judged before"
    )
    return [f"  CHANGED since {before}:", *(f"    - {line}" for line in lines)]


def prompt_for(facts: list[Facts], redactor: Redactor, taught: Sequence[str] = ()) -> str:
    """Everything the AI is told about the families, every address and name through the
    redactor. The ids are only for this request. ``taught`` is what the owner has disagreed with
    before, if they let it learn from that."""
    lines: list[str] = []
    if taught:
        lines += [LESSON_HEADING, *taught, ""]
    lines.append("Families to judge:")
    for number, item in enumerate(facts, start=1):
        family = item.family
        port_text = ", ".join(f"{port} ({count})" for port, count in item.ports) or "none"
        lines += [
            "",
            f"F{number}: {redactor.text(family.label, 200)}",
            f"  program that reported it most seriously: {family.source}; from: "
            f"{_WHERE[family.reach]}",
            f"  {item.incidents} incidents with {item.alerts} alerts from {item.actors} different "
            f"{'addresses' if family.reach != families.RULE else 'rules'}, over "
            f"{_span(item.first_at, item.last_at)}",
            f"  reported by: {', '.join(item.sources) or 'nobody'}; worst severity: "
            f"{item.worst.name.lower()}; banned: {item.banned} of {item.incidents}",
            f"  stages of an attack seen: {', '.join(item.stages) or 'none'}",
            f"  destination ports touched (incidents): {port_text}",
            *_decided(item.pattern),
            *_changed(family, redactor),
            redactor.evidence(
                f"example from F{number}", [signal_line(example) for example in item.examples]
            ),
        ]
    return "\n".join(lines)


def question_for(db: Session, ids: list[int]) -> tuple[Question, list[Facts]]:
    """The question to ask about families, and the families it is about (those of the ids that
    still have incidents going on), in the order the ids in the prompt are given."""
    found = facts_of(db, ids)
    tuning = settings.load(db)
    return (
        Question(
            purpose=PURPOSE,
            system=SYSTEM,
            build=lambda redactor: prompt_for(
                found, redactor, review.lessons(db, redactor, review_settings.load(db))
            ),
            about=about(len(found)),
            schema=SCHEMA,
            max_tokens=120 * len(found) + 200,
            start=lambda redactor: brief.start(redactor, tuning),
        ),
        found,
    )


# -- what the AI answered


def _json(text: str) -> object:
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except ValueError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        return json.loads(match.group(0)) if match else None


def parse(text: str, count: int) -> dict[int, Judgement] | None:
    """The judgements in an answer, by the number of the family in the prompt (1 to ``count``), or
    None if it isn't an answer. A family it got wrong is left out, not the whole answer."""
    try:
        loaded = _json(text)
    except ValueError:
        return None
    if not isinstance(loaded, dict):
        return None
    entries = cast("dict[str, object]", loaded).get("families")
    if not isinstance(entries, list):
        return None
    found: dict[int, Judgement] = {}
    for entry in cast("list[object]", entries):
        if not isinstance(entry, dict):
            continue
        fields = cast("dict[str, object]", entry)
        given, kind, sure = fields.get("id"), fields.get("classification"), fields.get("confidence")
        said = fields.get("reason")
        reason = audit.clean(said, MAX_REASON) if isinstance(said, str) else None
        match = re.fullmatch(r"F(\d+)", given) if isinstance(given, str) else None
        if (
            match is None
            or not isinstance(kind, str)
            or kind not in CLASSES
            or not isinstance(sure, int | float)
            or isinstance(sure, bool)
            or not 1 <= int(match.group(1)) <= count
        ):
            continue
        found[int(match.group(1))] = Judgement(kind, max(0, min(100, round(sure))), reason or "")
    return found


def keep(db: Session, found: list[Facts], answered: Answer | Unavailable, now: datetime) -> Outcome:
    """Keeps what an answer says of the families, or says why it can't. Each family it judged is
    told to its incidents. The caller commits."""
    if isinstance(answered, Unavailable):
        return NotJudged(answered.reason)
    if not answered.ok:
        return NotJudged(f"The AI provider didn't answer. {answered.reason}")
    judged = parse(answered.text, len(found))
    if not judged:
        cut = (
            " The answer was cut short; a model that thinks a lot may need a larger limit."
            if answered.truncated
            else ""
        )
        return NotJudged(f"The AI answered, but not in a form AresGate could read.{cut} Try again.")
    incidents = 0
    policy = review_settings.load(db)
    like = drift.profiles(db, [item.family.id for item in found])
    for number, judgement in judged.items():
        item = found[number - 1]
        family = item.family
        starts = review.starts(policy, judgement.classification, judgement.confidence)
        family.review = review.carried(
            family.review, family.ai_class, judgement.classification, starts
        )
        if family.review not in review.ANSWERED:
            family.reviewed_at = None
        family.ai_class = judgement.classification
        family.ai_confidence = judgement.confidence
        family.ai_reason = judgement.reason or None
        family.judged_at = now
        family.judged_incidents = item.incidents
        family.call_id = answered.call_id
        family.provider = answered.provider
        family.model = answered.model
        drift.keep(family, like.get(family.id, drift.Profile()), now)
        db.flush()
        calls.sync(db, family_id=family.id)
        incidents += item.incidents
    return Judged(len(judged), incidents)


def ask_now(db: Session, context: Context, ids: list[int], now: datetime | None = None) -> Outcome:
    """Judges families now, for one of the API's own threads. The caller commits."""
    now = now or utcnow()
    question, found = question_for(db, ids)
    if not found:
        return NotJudged("None of those has an incident going on.")
    return keep(db, found, gateway.ask(db, context, question, now), now)
