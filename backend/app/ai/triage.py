"""AI triage: an AI provider reads an incident and says what it makes of it.

The incident engine groups signals and says how sure it is from rules anyone can read. Triage
adds a second opinion that can read what rules can't: what kind of thing this is (``compromise``,
``attack``, ``probe``, ``noise`` or ``unclear``), how sure the AI is, the story in plain words,
what to check and what the owner might tell AresGate about it. It is the AI's opinion and is kept
and shown as one: it never changes the incident, never acts on anything and never gives a verdict
by itself. The owner presses a button to accept a suggestion.

An incident is read when the owner asks (the page's button, or *Start investigating*) and, at the
usage level the owner chose, by the worker as new incidents come in. Everything goes through the
gateway (app/ai/gateway.py), so the provider sees only what the redaction level allows and every
request is recorded.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, cast

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import audit
from app.ai import brief, gateway, service
from app.ai.gateway import Answer, Context, Question, Unavailable
from app.ai.redaction import Redactor
from app.assets import profile
from app.events.event import Severity
from app.incidents import attention, conversations, filters, insights, occurrences, queries
from app.incidents.verdicts import MUTING
from app.intel import overrides, virustotal
from app.intel import store as intel_store
from app.models import CLASSES, AiCall, AiTriage, Incident, IntelOverride, IntelSubject
from app.models.base import utcnow
from app.models.verdicts import VERDICTS
from app.threats import calls, settings

PURPOSE: Final = "triage"
MAX_SIGNALS: Final = 30
FIRST_SIGNALS: Final = 10
MAX_CHECKS: Final = 4
MAX_OBSERVATIONS: Final = 5
MAX_OBSERVATION: Final = 240
# How many conversations and techniques are told of what the programs said, and how many lines
# of what they said there is room for.
MAX_TOLD: Final = 6
MAX_HEADLINE: Final = 160
MAX_STORY: Final = 2000
MAX_CHECK: Final = 300
MAX_REASON: Final = 300
# A request that failed, or an answer that couldn't be read, is not asked again for this long, so
# a provider that is down isn't asked every minute about every incident.
PAUSE: Final = timedelta(minutes=15)

SYSTEM: Final = """\
You are the analyst of AresGate, a security monitor for one home network. You are given one \
incident that AresGate's rules put together from the alerts of the firewall, the intrusion \
detection systems and the traffic monitors. Say what you make of it, as an expert explaining to \
the owner, who is technical but busy.

Judge only from the evidence you are given. Do not invent facts, products or addresses: if the \
evidence does not show something, say that it does not.

Choose one classification:
- compromise: evidence that something on the home network is infected, has been taken over or has \
leaked data (a device talking to a known-bad host or command server, a login that worked after \
guessing, malware alerts about a device).
- attack: a targeted or active attack from outside that deserves attention (exploit attempts \
against a service that really is exposed, guessing against a login that is open to the internet).
- probe: scanning, probing or guessing with no sign that it worked: routine background.
- noise: harmless (a misconfiguration, a rule that fires on normal traffic, a known service).
- unclear: the evidence is too thin to tell.

"confidence" is how sure you are of the classification, from 0 to 100. Be honest: a few signals \
are thin evidence.

"verdict" is what you suggest the owner tell AresGate, so that it judges the same kind of signal \
that way from then on: "not_suspicious" for noise, "low_priority" for a probe that is only \
background, "threat" only for a compromise or an attack you are sure of, and "none" if the owner \
should decide. Alarms must stay rare: suggest "threat" only with a confidence of 80 or more. Say \
why in "verdict_reason", in one sentence.

"observations" are one to five short, plain statements of what stands out in what was actually \
sent, taken from "What the programs said of the traffic" and nothing else: who talked to whom and \
over what service, what was asked for, how much moved and for how long, where the other end is and \
whether any program or reputation service flags it, and what the programs that said more add. \
Where the owner has ruled an address safe or suspicious, that is a fact about their network, so it \
stands over what a reputation service said of it. Say what is ordinary as well as what is not, and \
never a guess. If the programs said nothing beyond \
the basics, it may be empty.

"headline" is one plain sentence of under 100 characters that says what happened to what. \
"story" is two to four sentences: what happened in order, what it means for the home, and what \
has already been done about it (a ban or a block, if there was one). "checks" are one to four \
short things the owner can check for themselves, most useful first; for a probe or noise it may \
be empty.

Answer only with the JSON you are asked for.\
"""

SCHEMA: Final[Mapping[str, object]] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "classification": {"type": "string", "enum": list(CLASSES)},
        "confidence": {"type": "integer"},
        "headline": {"type": "string"},
        "story": {"type": "string"},
        "checks": {"type": "array", "items": {"type": "string"}},
        "observations": {"type": "array", "items": {"type": "string"}},
        "verdict": {"type": "string", "enum": ["none", *VERDICTS]},
        "verdict_reason": {"type": "string"},
    },
    "required": [
        "classification",
        "confidence",
        "headline",
        "story",
        "checks",
        "observations",
        "verdict",
        "verdict_reason",
    ],
}


@dataclass(frozen=True)
class Reading:
    """What the AI answered, checked: a field it got wrong makes the whole answer unusable."""

    classification: str
    confidence: int
    headline: str
    story: str
    checks: list[str]
    observations: list[str]
    verdict: str | None
    verdict_reason: str | None


@dataclass(frozen=True)
class Read:
    """An incident was read, and this is what the AI made of it."""

    triage: AiTriage


@dataclass(frozen=True)
class NotRead:
    """It was not read, and why, in words for whoever asked."""

    reason: str


Outcome = Read | NotRead


def about(incident_id: int) -> str:
    """How the record of requests names an incident, which is how it is found there again."""
    return f"incident {incident_id}"


# -- what the AI is asked


def _end(address: object, port: int | None) -> str:
    if address is None:
        return "?"
    return f"{address}:{port}" if port else str(address)


def signal_line(occurrence: occurrences.Occurrence) -> str:
    """One line for a kind of signal: when it happened, or when it began and ended and how many
    times, and what it said."""
    signal = occurrence.first
    where = ""
    if signal.src_address or signal.dst_address:
        where = (
            f" {_end(signal.src_address, signal.src_port)} -> "
            f"{_end(signal.dst_address, signal.dst_port)}"
        )
    protocol = f" {signal.protocol}" if signal.protocol else ""
    what = signal.signature or signal.summary
    severity = Severity(signal.severity).name.lower()
    when = signal.occurred_at.strftime("%Y-%m-%d %H:%M:%S")
    if occurrence.count > 1:
        when = f"{when} to {occurrence.last_at:%Y-%m-%d %H:%M:%S}, {occurrence.count} times,"
    verdict = f" [owner: {signal.verdict}]" if signal.verdict else ""
    return f"{when} {signal.source} {signal.kind} {severity}: {what}{where}{protocol}{verdict}"


def _timeline(found: list[occurrences.Occurrence]) -> list[str]:
    """One line for each kind of signal, which repeats are folded into; of a long incident the
    first and the last, which tell how it began and where it stands."""
    if len(found) <= MAX_SIGNALS:
        return [signal_line(item) for item in found]
    left = len(found) - MAX_SIGNALS
    return [
        *(signal_line(item) for item in found[:FIRST_SIGNALS]),
        f"... {left} more kinds in between ...",
        *(signal_line(item) for item in found[FIRST_SIGNALS - MAX_SIGNALS :]),
    ]


def prompt_for(db: Session, incident: Incident, redactor: Redactor) -> str:
    """Everything the AI is told about one incident, every address and name through the redactor."""
    severity = Severity(incident.severity).name.lower()
    lines = [
        f"Incident: {redactor.text(incident.title, 200)}",
        f"About: {redactor.text(incident.subject, 200)}",
        f"Severity of the worst signal: {severity}",
        f"AresGate's own confidence that it is a real attack: {incident.confidence} of 100",
        f"First seen {incident.first_seen_at:%Y-%m-%d %H:%M} UTC, last seen "
        f"{incident.last_seen_at:%Y-%m-%d %H:%M} UTC (over "
        f"{_span(incident.last_seen_at - incident.first_seen_at)})",
        f"Signals: {incident.signal_count}, reported by {', '.join(incident.sources) or 'nobody'}",
    ]
    if incident.activities:
        lines.append(f"Kinds of activity: {', '.join(incident.activities)}")
    if incident.waves > 1:
        lines.append(f"They came in {incident.waves} separate bursts")
    if incident.ports:
        lines.append(f"Destination ports touched: {', '.join(str(p) for p in incident.ports[:20])}")
    lines.append(f"An integration banned the address: {'yes' if incident.banned else 'no'}")
    if incident.verdict_counts:
        said = ", ".join(f"{count} {name}" for name, count in incident.verdict_counts.items())
        lines.append(f"What the owner already said of some of its signals: {said}")
    if incident.reasons:
        lines.append("Why AresGate's rules are as sure as they are:")
        lines += [
            f"- {redactor.text(str(reason.get('text', '')), 200)}" for reason in incident.reasons
        ]
    lines += _device_lines(db, incident, redactor)
    lines += _reputation_lines(db, incident, redactor)
    found = occurrences.group(queries.signals(db, incident))
    lines.append(redactor.evidence("signals, oldest first", _timeline(found)))
    if told := _told_lines(found):
        lines.append(redactor.evidence("What the programs said of the traffic", told))
    return "\n".join(lines)


def _end_text(end: conversations.End) -> str:
    """One end of a conversation: the address with its name, port and service, and where it is."""
    text = end.address if end.name is None else f"{end.address} ({end.name})"
    if end.port is not None:
        text += f":{end.port}"
        text += f" ({end.service})" if end.service else ""
    where = [word for word in (end.location, end.country) if word]
    if end.blacklisted:
        where.append("on a blacklist")
    return f"{text} [{', '.join(where)}]" if where else text


def size_of(count: int) -> str:
    size = float(count)
    for unit in ("B", "kB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1000
    raise AssertionError("unreachable")  # pragma: no cover


def _conversation_line(each: conversations.Conversation) -> str:
    """One conversation in a line: who to whom, what over, how many alerts and what the programs
    said of the flow."""
    kind = " ".join(word for word in (each.protocol, each.app) if word)
    parts = [
        f"{_end_text(each.client)} -> {_end_text(each.server)}" + (f" {kind}" if kind else ""),
        f"{each.alerts} alerts of {each.kinds} kinds",
    ]
    if each.bytes_out is not None or each.bytes_in is not None:
        sent, got = each.bytes_out or 0, each.bytes_in or 0
        parts.append(f"largest flow sent {size_of(sent)} and got {size_of(got)}")
    if each.duration is not None:
        parts.append(f"lasted {each.duration} s")
    if each.names:
        parts.append("asked for " + ", ".join(name["value"] for name in each.names))
    parts.append("reported by " + ", ".join(each.programs))
    return "; ".join(parts)


def _told_lines(found: list[occurrences.Occurrence]) -> list[str]:
    """What the connected programs said of the incident beyond the basics, a line each: the
    conversations, the techniques they matched it to and the words that sort it. Nothing where
    none of them said anything."""
    said = insights.of(found)
    told = conversations.of(found)
    lines = [f"Conversation: {_conversation_line(each)}" for each in told.items[:MAX_TOLD]]
    if told.total > MAX_TOLD:
        lines.append(f"... {told.total - MAX_TOLD} more conversations ...")
    lines += [
        f"Technique {each.id} {each.name} ({each.tactic or 'tactic not said'}): {each.count} alerts"
        for each in said.techniques[:MAX_TOLD]
    ]
    if said.tags:
        lines.append("Groups and categories: " + ", ".join(each.value for each in said.tags))
    lines += [f"Machine it was about: {each.value}" for each in said.hosts[:MAX_TOLD]]
    lines += [
        f"{each.kind} named: {each.value} ({each.count} alerts)" for each in said.named[:MAX_TOLD]
    ]
    return lines


def _device_lines(db: Session, incident: Incident, redactor: Redactor) -> list[str]:
    """The devices on the home network that the incident involves, by stand-in."""
    devices = queries.devices(db, incident)
    if not devices:
        return []
    lines = ["Devices on the home network involved:"]
    said = profile.for_devices(db, (device.id for _, device in devices))
    for address, device in devices:
        name = redactor.name(device.hostname) if device.hostname else "unnamed"
        vendor = f", made by {redactor.text(device.vendor, 60)}" if device.vendor else ""
        what = profile.describe(said.get(device.id), redactor.text)
        lines.append(f"- {redactor.address(str(address))}: {name}{vendor}{what}")
    return lines


def _reputation_lines(db: Session, incident: Incident, redactor: Redactor) -> list[str]:
    """What VirusTotal has said of the internet addresses an incident involves, if it has said
    anything about any of them, and what the owner has ruled of them, which stands over it. A report
    is only kept for an address that was asked about; a ruling may be of any."""
    reports = intel_store.reports_for(db, virustotal.PROVIDER, incident.addresses)
    rulings = overrides.for_addresses(db, incident.addresses)
    lines: list[str] = []
    if reports:
        lines += ["What VirusTotal says of the internet addresses involved:"] + [
            f"- {_reputation(report, redactor)}" for report in reports
        ]
    if rulings:
        lines += ["What the owner of the network has ruled of the internet addresses involved:"] + [
            f"- {_ruling(ruling, redactor)}" for ruling in rulings.values()
        ]
    return lines


def _ruling(ruling: IntelOverride, redactor: Redactor) -> str:
    """One address's ruling, as the AI reads it: what the owner made of it, and why."""
    why = f": {redactor.text(ruling.note, 200)}" if ruling.note else ""
    return f"{redactor.address(ruling.subject)} is ruled {ruling.verdict} by the owner{why}"


def _reputation(report: IntelSubject, redactor: Redactor) -> str:
    """One address's report, as the AI reads it: what the engines made of it, and who owns it."""
    owner = redactor.text(report.owner, 60) if report.owner else "unknown owner"
    total = report.malicious + report.suspicious + report.harmless + report.undetected
    return (
        f"{redactor.address(report.subject)}: {report.malicious} of {total} engines flag it "
        f"as malicious and {report.suspicious} as suspicious; owner {owner}, "
        f"{report.country or 'unknown country'}; community score {report.reputation}; "
        f"analysed {report.analysed_at:%Y-%m-%d}"
    )


def _span(span: timedelta) -> str:
    minutes = int(span.total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)} minutes"
    hours, rest = divmod(minutes, 60)
    if hours < 48:
        return f"{hours} h {rest} min"
    return f"{hours // 24} days"


def question_for(db: Session, incident: Incident) -> Question:
    """The question to ask about an incident."""
    hostnames = [device.hostname for _, device in queries.devices(db, incident) if device.hostname]
    tuning = settings.load(db)
    return Question(
        purpose=PURPOSE,
        system=SYSTEM,
        build=lambda redactor: prompt_for(db, incident, redactor),
        about=about(incident.id),
        schema=SCHEMA,
        max_tokens=900,
        names=hostnames,
        start=lambda redactor: brief.start(redactor, tuning),
    )


# -- what the AI answered


def _text(value: object, limit: int) -> str | None:
    return audit.clean(value, limit) if isinstance(value, str) else None


def _json(text: str) -> object:
    """The JSON object in an answer, which some models put inside a code fence or a sentence."""
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except ValueError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        return json.loads(match.group(0)) if match else None


def parse(text: str) -> Reading | None:
    """The reading in an answer, or None if it isn't one. Numbers are kept to their range and
    words to their length; a classification it isn't allowed to give makes it unusable, and a
    verdict it isn't allowed to give is left out."""
    try:
        loaded = _json(text)
    except ValueError:
        return None
    if not isinstance(loaded, dict):
        return None
    fields = cast("dict[str, object]", loaded)
    classification = fields.get("classification")
    confidence = fields.get("confidence")
    headline = _text(fields.get("headline"), MAX_HEADLINE)
    story = _text(fields.get("story"), MAX_STORY)
    if (
        not isinstance(classification, str)
        or classification not in CLASSES
        or not isinstance(confidence, int | float)
        or isinstance(confidence, bool)
        or headline is None
        or story is None
    ):
        return None
    given = fields.get("checks")
    items = cast("list[object]", given) if isinstance(given, list) else []
    texts = (_text(item, MAX_CHECK) for item in items)
    seen = fields.get("observations")
    noted = (
        (_text(item, MAX_OBSERVATION) for item in cast("list[object]", seen))
        if isinstance(seen, list)
        else ()
    )
    verdict = fields.get("verdict")
    return Reading(
        classification=classification,
        confidence=max(0, min(100, round(confidence))),
        headline=headline,
        story=story,
        checks=[line for line in texts if line][:MAX_CHECKS],
        observations=[line for line in noted if line][:MAX_OBSERVATIONS],
        verdict=verdict if isinstance(verdict, str) and verdict in VERDICTS else None,
        verdict_reason=_text(fields.get("verdict_reason"), MAX_REASON),
    )


def keep(db: Session, incident: Incident, answered: Answer | Unavailable, now: datetime) -> Outcome:
    """Keeps what an answer says of an incident, or says why it can't. The caller commits."""
    if isinstance(answered, Unavailable):
        return NotRead(answered.reason)
    if not answered.ok:
        return NotRead(f"The AI provider didn't answer. {answered.reason}")
    reading = parse(answered.text)
    if reading is None:
        cut = (
            " The answer was cut short; a model that thinks a lot may need a larger limit."
            if answered.truncated
            else ""
        )
        return NotRead(f"The AI answered, but not in a form AresGate could read.{cut} Try again.")
    values: dict[str, object] = {
        "call_id": answered.call_id,
        "read_at": now,
        "signals_read": incident.signal_count,
        "classification": reading.classification,
        "confidence": reading.confidence,
        "headline": reading.headline,
        "story": reading.story,
        "checks": reading.checks,
        "observations": reading.observations,
        "verdict": reading.verdict,
        "verdict_reason": reading.verdict_reason,
        "provider": answered.provider,
        "model": answered.model,
    }
    # An owner who asks while the worker is reading the same incident must not fail on the other's
    # row: whichever finishes last is the one kept.
    db.execute(
        insert(AiTriage)
        .values(incident_id=incident.id, **values)
        .on_conflict_do_update(index_elements=[AiTriage.incident_id], set_=values)
    )
    kept = db.scalars(
        select(AiTriage)
        .where(AiTriage.incident_id == incident.id)
        .execution_options(populate_existing=True)
    ).one()
    # What it thinks of this incident now outranks what was thought of its family.
    calls.sync(db, [incident.id])
    return Read(kept)


def ask_now(
    db: Session, context: Context, incident: Incident, now: datetime | None = None
) -> Outcome:
    """Reads an incident now, for one of the API's own threads. The caller commits."""
    now = now or utcnow()
    return keep(db, incident, gateway.ask(db, context, question_for(db, incident), now), now)


# -- what is read without being asked


@dataclass(frozen=True)
class Policy:
    """What a usage level lets the worker read by itself."""

    # The least serious incident it reads; None reads none by itself.
    minimum: Severity | None
    per_hour: int
    # An incident it has read is read again when it has this many times the signals it had then
    # (and at least ``PAUSE`` has passed); None never reads one twice.
    growth: float | None
    # Whether it reads incidents that AresGate's rules are unsure of. The quiet ones are judged
    # by their family instead (app/ai/families.py), which costs a tenth as much.
    reads_unsure: bool = False
    # What it does for families: how many batches of them it judges in an hour (none at 0), the
    # fewest incidents a family has to have to be worth judging, and how much a family has to
    # grow before it is judged again (None: never).
    family_batches: int = 0
    family_min: int = 0
    family_growth: float | None = None


POLICIES: Final[dict[str, Policy]] = {
    "very_low": Policy(None, 0, None),
    "low": Policy(Severity.HIGH, 6, None, False, 1, 20, None),
    "medium": Policy(Severity.MEDIUM, 20, 4.0, False, 2, 5, 4.0),
    "high": Policy(Severity.LOW, 60, 2.0, True, 4, 3, 2.0),
    "maximum": Policy(Severity.INFO, 150, 1.5, True, 8, 2, 1.5),
}
# At most this many in one run, so a burst of new incidents is read steadily and not all at once.
PER_RUN: Final = 5


def plan(db: Session, now: datetime) -> list[int]:
    """The incidents to read now, most serious first: none if AI is off or not set up, or the
    usage level reads none by itself, and no more than the level allows in an hour. Those the owner
    called not suspicious or low priority are never read, and neither is one that was asked about
    lately."""
    chosen = service.usage(db, now)
    policy = POLICIES[chosen.usage_level]
    if not chosen.enabled or chosen.provider is None or policy.minimum is None:
        return []
    used = (
        db.scalar(
            select(func.count())
            .select_from(AiCall)
            .where(AiCall.purpose == PURPOSE, AiCall.occurred_at >= now - timedelta(hours=1))
        )
        or 0
    )
    room = min(policy.per_hour - used, PER_RUN)
    if room <= 0:
        return []
    asked_lately = exists().where(
        AiCall.purpose == PURPOSE,
        AiCall.about == func.concat("incident ", Incident.id),
        AiCall.occurred_at >= now - PAUSE,
    )
    tuning = settings.load(db)
    by = attention.clauses(filters.load(db).confidence_floor, tuning)
    # Incidents the rules are unsure of, or that an AI has already set aside as background, are not
    # read one by one: that is what families are for.
    skipped = by[attention.Standing.AI_CLEARED]
    if not policy.reads_unsure:
        skipped = or_(skipped, by[attention.Standing.UNSURE])
    unread = AiTriage.incident_id.is_(None)
    wanted = unread
    if policy.growth is not None:
        grown = and_(
            AiTriage.read_at < now - PAUSE,
            AiTriage.signals_read * policy.growth <= Incident.signal_count,
        )
        wanted = or_(unread, grown)
    candidates = (
        select(Incident.id)
        .outerjoin(AiTriage, AiTriage.incident_id == Incident.id)
        .where(
            Incident.status.in_(("open", "investigating")),
            Incident.severity >= policy.minimum,
            or_(Incident.verdict.is_(None), Incident.verdict.not_in(MUTING)),
            wanted,
            ~asked_lately,
            ~skipped,
        )
        .order_by(
            Incident.severity.desc(), Incident.confidence.desc(), Incident.last_seen_at.desc()
        )
        .limit(room)
    )
    return list(db.scalars(candidates))
