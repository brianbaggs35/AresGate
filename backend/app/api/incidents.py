"""Incidents: the alerts, bans and other signals from every integration that belong together,
how serious they are, how sure AresGate is and why. For someone signed in."""

from dataclasses import dataclass
from typing import Annotated, Literal, NamedTuple, Self, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    IPvAnyAddress,
    model_validator,
)
from sqlalchemy import ColumnElement, func, or_, select

from app.ai import catalog, triage
from app.api import asking
from app.api.ai import AiContext
from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.api.verdicts import Note
from app.audit import Action, Outcome
from app.events.event import Severity
from app.incidents import (
    attention,
    bulk,
    engine,
    episode,
    evidence,
    filters,
    insights,
    occurrences,
    queries,
    response,
    rules,
    search,
)
from app.incidents.attention import Lane
from app.incidents.queries import Order
from app.models import AiTriage, Incident, IncidentFamily, IncidentSignal, utcnow
from app.threats import explain
from app.threats import settings as threat_settings
from app.threats.settings import Tuning

router = APIRouter(prefix="/incidents", tags=["incidents"], dependencies=[Depends(signed_in)])

Status = Literal["open", "investigating", "resolved", "dismissed"]
Verdict = Literal["not_suspicious", "low_priority", "threat"]
Activity = Literal["scan", "brute_force"]
Classification = Literal["compromise", "attack", "probe", "noise", "unclear"]
# Where an incident goes on the Threats page (app/incidents/attention.py).
LaneName = Literal["threat", "suspect", "background"]
Stage = Literal["recon", "access", "foothold"]
# Whose word the call on an incident is: the owner's, the AI's reading of it or of its family.
Basis = Literal["owner", "reading", "family"]
# What to ask for to get the incidents nobody has given a verdict to.
VerdictFilter = Literal["none", "not_suspicious", "low_priority", "threat"]
MAX_PAGE = 200
IncidentId = Annotated[int, Path(ge=1, le=2**63 - 1)]


class ProgramOut(BaseModel):
    """An integration that reported part of an incident."""

    key: str
    name: str


class BanOut(BaseModel):
    """A decision CrowdSec made about one of the incident's addresses."""

    address: str
    # What kind of remedy it was: a ban, nearly always.
    kind: str
    # What made it, and where it came from, in words.
    scenario: str | None
    origin: str | None
    # When AresGate first read it, which is when it knows of it, and when it runs out, where the
    # time CrowdSec said was left is understood.
    seen_at: AwareDatetime
    ends_at: AwareDatetime | None
    simulated: bool
    # Whether it still holds, as far as is known: only a ban that was meant counts.
    in_force: bool


class ResponseOut(BaseModel):
    """What was done about an incident, from what AresGate has read of the programs that act: the
    bans CrowdSec made, how often the firewall turned the address away and how many alerts
    Suricata stopped."""

    state: response.State
    # The state in words, for a chip.
    label: str
    bans: list[BanOut]
    # How often the firewall turned the subject away around the time of the incident, and from the
    # time of the first ban to the end of it, and when it last did.
    blocked: int
    blocked_since_ban: int | None
    last_blocked_at: AwareDatetime | None
    # How many alerts Suricata stopped, in the same time.
    dropped: int
    # What can't be told, and why, in words.
    unknown: list[str]


class GlanceOut(BaseModel):
    """What the AI made of an incident, in a word and how sure it was, for a list."""

    classification: Classification
    confidence: int


class CallOut(BaseModel):
    """What is made of an incident beyond the rules, and whose word it is."""

    classification: Classification
    confidence: int
    basis: Basis


class IncidentOut(BaseModel):
    id: int
    title: str
    # The address the signals are about, or rule:<integration>:<rule> where they name none.
    subject: str
    severity: SeverityName
    # How sure AresGate is that it is a real attack, 0 to 100, and in a word.
    confidence: int
    confidence_level: rules.Level
    status: Status
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime
    # How many signals it has, which can be more than the timeline lists.
    signal_count: int
    sources: list[ProgramOut]
    addresses: list[str]
    # Whether an integration banned the address.
    banned: bool
    # What was done about it: banned, blocked, or nothing yet.
    response: ResponseOut
    status_changed_at: AwareDatetime | None
    # What the owner's verdicts say of it as a whole: a real threat, not suspicious or low
    # priority, or nothing. The signals they gave a verdict to are listed and counted in
    # ``signal_count``, but everything else here is about the ones they didn't, and an incident of
    # signals they all called not suspicious or low priority is as sure as 0.
    verdict: Verdict | None
    verdict_counts: dict[Verdict, int]
    # How many of its signals the owner's noise filters set aside, which are listed and counted
    # like the ones a verdict leaves out.
    filtered_count: int
    # What kind of activity it was, where its signals say: scanning, brute force.
    activities: list[Activity]
    # How many bursts its signals came in, with at least a quarter of an hour of quiet between them.
    waves: int
    # How many different destination ports they touched (as far as are kept: ``ports_capped``
    # says there were at least that many).
    port_count: int
    ports_capped: bool
    # How many other addresses of the subject's block are in it: a bot spread over a block is one
    # incident (see app/incidents/episode.py).
    neighbours: int
    # What the AI made of it, if it has read it (``IncidentDetail.reading`` has the rest).
    ai: GlanceOut | None
    # Where it goes: a threat (highly likely to be real), a suspect (worth a look) or background
    # (AresGate isn't sure, or an AI judged it noise or a probe). None for one that is dismissed,
    # resolved or called not suspicious or low priority by the owner.
    lane: LaneName | None
    # How many of its signals another program had already reported (so they count once).
    duplicates: int
    # How far it got along the path of an attack: scanning, trying a flaw, a sign it worked.
    stages: list[Stage]
    # The kind of incident it is (see ``FamilyBrief``) and what is thought of it, by the owner or
    # an AI: the word of the owner on the family, then the AI's reading of it, then its family's.
    family_id: int | None
    call: CallOut | None


class ReasonOut(BaseModel):
    """One thing that makes AresGate as sure as it is."""

    rule: str
    points: int
    text: str


class SignalOut(BaseModel):
    occurred_at: AwareDatetime
    source: str
    source_name: str
    kind: str
    severity: SeverityName
    summary: str
    signature: str | None
    src_address: str | None
    src_port: int | None
    dst_address: str | None
    dst_port: int | None
    protocol: str | None
    # What the owner's verdicts said of it, and the rule they said it by while that exists.
    verdict: Verdict | None
    verdict_rule_id: int | None
    # Which noise filter set it aside, if one did and no verdict was about it.
    filtered_by: Literal["inside", "severity", "thin"] | None
    # Whether another program had already reported the same thing a moment before (it counts once).
    duplicate: bool


class DeviceOut(BaseModel):
    """A device on the network that one of the incident's addresses belongs to."""

    id: int
    address: str
    mac: str
    hostname: str | None
    vendor: str | None


class ReadingOut(BaseModel):
    """What an AI provider made of an incident: its opinion, kept as it was given. It never
    changes the incident, and the verdict it suggests is only given if the owner gives it."""

    classification: Classification
    confidence: int
    headline: str
    story: str
    # Things the owner can check for themselves, most useful first.
    checks: list[str]
    verdict: Verdict | None
    verdict_reason: str | None
    read_at: AwareDatetime
    # Who read it: the provider's name and the model.
    provider: str
    model: str
    # How many signals the incident had when it was read, so a page can say that more came since.
    signals_read: int


class FactOut(BaseModel):
    label: str
    value: str


class TechniqueOut(BaseModel):
    """A technique of the MITRE ATT&CK framework."""

    id: str
    tactic: str
    technique: str


class NamedOut(BaseModel):
    """Something an alert names: a host name, a URL, a user. ``kind`` is what sort of thing."""

    kind: str
    value: str


class TrafficOut(BaseModel):
    """How much the flow an alert is about carried, as its program counted it."""

    packets_out: int | None
    packets_in: int | None
    bytes_out: int | None
    bytes_in: int | None


class EvidenceOut(BaseModel):
    """What one program said of an alert besides who, where and when (app/incidents/evidence.py).
    A member is empty where the program said nothing for it."""

    facts: list[FactOut]
    tags: list[str]
    mitre: list[TechniqueOut]
    named: list[NamedOut]
    traffic: TrafficOut | None
    # The machine it is about, the application it was and the log line it came from.
    host: str | None
    app: str | None
    excerpt: str | None


class ConfirmationOut(BaseModel):
    """A program that reported the same alert as the first, and what it said of it."""

    source: str
    source_name: str
    signature: str | None
    severity: SeverityName
    count: int
    first_at: AwareDatetime
    last_at: AwareDatetime
    evidence: EvidenceOut | None


class OccurrenceOut(BaseModel):
    """Signals that say the same thing the same way, as one that happened ``count`` times."""

    signal: SignalOut
    count: int
    last_at: AwareDatetime
    duplicates: int
    # What the program that reported it said besides the basics, where it said any (and, for the
    # busiest of an incident with a great many, only for those), and the programs that agreed.
    evidence: EvidenceOut | None
    confirmations: list[ConfirmationOut]


class CountedOut(BaseModel):
    value: str
    count: int


class CountedTechniqueOut(TechniqueOut):
    count: int


class CountedNamedOut(NamedOut):
    count: int


class ContributionOut(BaseModel):
    """What one program told of an incident: how many of its alerts it reported, and what kinds of
    detail it gave besides the basics."""

    source: str
    source_name: str
    reports: int
    adds: list[str]


class InsightsOut(BaseModel):
    """What the programs between them knew of the incident, added up alert by alert."""

    techniques: list[CountedTechniqueOut]
    tags: list[CountedOut]
    hosts: list[CountedOut]
    apps: list[CountedOut]
    named: list[CountedNamedOut]
    programs: list[ContributionOut]


class FamilyBrief(BaseModel):
    """A kind of incident: the ones that a program reported in the same words about the same sort of
    place (see app/threats/families.py), and what is thought of all of them."""

    id: int
    label: str
    source: str
    source_name: str
    reach: Literal["internet", "network", "rule"]
    # The owner's word: ``background`` sets the kind aside, ``watch`` never does.
    owner_call: Literal["background", "watch"] | None
    # What an AI made of the family as a whole, how sure it was and why.
    classification: Classification | None
    confidence: int | None
    reason: str | None
    judged_at: AwareDatetime | None
    # How many incidents of the family are going on.
    incidents: int


class IncidentDetail(IncidentOut):
    # Why AresGate is as sure as it is: the reasons and their points add up to the confidence.
    reasons: list[ReasonOut]
    # Why these signals are one incident, in plain words, a fact to a line.
    grouping: list[str]
    # The destination ports they touched, sorted.
    ports: list[int]
    # Oldest first. Only the first so many are kept; ``signal_count`` has them all.
    signals: list[SignalOut]
    devices: list[DeviceOut]
    # How many times the firewall turned the subject away around then (``response`` says more), or
    # None for an incident about a rule.
    blocked: int | None
    reading: ReadingOut | None
    # Why it is in the lane it is in, a fact to a line.
    why: list[str]
    # The signals grouped by what they say, in the order each first happened.
    occurrences: list[OccurrenceOut]
    family: FamilyBrief | None
    # What the programs said besides the basics, added up. None when none said anything.
    insights: InsightsOut | None


class TermOut(BaseModel):
    """One term of the search, as it was understood."""

    # The field it is about (``source``, ``severity``), or none for plain text.
    field: str | None
    # What it was understood as, to show: ``Source: Wazuh``, ``Not address: 10.0.0.0/8``.
    label: str
    negated: bool
    # Where it was in the search, as the characters from ``start`` up to ``end``.
    start: int
    end: int


class SourceCount(BaseModel):
    key: str
    name: str
    count: int


class FacetsOut(BaseModel):
    """How the incidents found are spread, whatever page of them it is."""

    severity: dict[SeverityName, int]
    # The integrations that reported part of any of them, the most first.
    sources: list[SourceCount]


class IncidentPage(BaseModel):
    total: int
    items: list[IncidentOut]
    terms: list[TermOut]
    facets: FacetsOut
    # How many incidents there are in each status, whatever the search was for except which
    # verdicts it asked about.
    counts: dict[Status, int]
    # How many more it would have found if it hadn't left out the ones the owner called not
    # suspicious or low priority, which asking for anything else does.
    quieted: int


class StatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Status


IncidentNumber = Annotated[int, Field(ge=1, le=2**63 - 1)]
SomeIncidents = Annotated[list[IncidentNumber], Field(min_length=1, max_length=bulk.MAX_INCIDENTS)]


class Matching(BaseModel):
    """The incidents a list of them is of: what it was asked, said the way the list is asked."""

    model_config = ConfigDict(extra="forbid")

    status: list[Status] = []
    verdict: list[VerdictFilter] = []
    min_severity: SeverityName | None = None
    min_confidence: int = Field(default=0, ge=0, le=rules.MAX_CONFIDENCE)
    address: IPvAnyAddress | None = None
    since: AwareDatetime | None = None
    q: str = ""
    tz: str | None = None
    # Only those in these lanes, and of this kind (see ``list_incidents``).
    lane: list[LaneName] = []
    family: int | None = Field(default=None, ge=1, le=2**63 - 1)


class BulkIn(BaseModel):
    """A change to many incidents, which is made all together or not at all."""

    model_config = ConfigDict(extra="forbid")

    # Which: the ones that were picked, or all that a list of incidents would show.
    ids: SomeIncidents | None = None
    matching: Matching | None = None
    # What to change: what is being done about them, or what is thought of what they are about.
    status: Status | None = None
    verdict: Verdict | None = None
    note: Note | None = None
    # Only say what it would do, and change nothing.
    preview: bool = False

    @model_validator(mode="after")
    def _one_of_each(self) -> Self:
        if (self.ids is None) == (self.matching is None):
            raise ValueError("Say which incidents, by their ids or by what matches.")
        if (self.status is None) == (self.verdict is None):
            raise ValueError("Say what to change: a status, or a verdict.")
        if self.note is not None and self.verdict is None:
            raise ValueError("A note goes with a verdict.")
        if self.ids is not None:
            self.ids = list(dict.fromkeys(self.ids))
        return self


class RuleBack(BaseModel):
    """A verdict a change made: it goes, or says again what it said before."""

    model_config = ConfigDict(extra="forbid")

    id: IncidentNumber
    replaced: Verdict | None = None


class Undo(BaseModel):
    """What it takes to take a change back, as the change said it."""

    model_config = ConfigDict(extra="forbid")

    # The incidents that were changed, by the status they had.
    statuses: dict[Status, SomeIncidents] = {}
    rules: Annotated[list[RuleBack], Field(max_length=bulk.MAX_INCIDENTS)] = []


class BulkOut(BaseModel):
    preview: bool
    # How many incidents it is about, and how many signals are in them.
    incidents: int
    signals: int
    # In how many of them it changes anything (the others already are so).
    changed: int
    # For a verdict: how many incidents it could not be given on, as they name no address and
    # no alert, and how many verdicts it makes or changes, since one covers every incident about
    # the same address or alert.
    skipped: int
    verdicts: int
    # How to take it back, if it changed anything and was not only asked about.
    undo: Undo | None


class UndoOut(BaseModel):
    incidents: int
    verdicts: int


def _program(key: str) -> ProgramOut:
    return ProgramOut(key=key, name=rules.name_of(key))


def _response(done: response.Response) -> ResponseOut:
    now = utcnow()
    return ResponseOut(
        state=done.state,
        label=done.label,
        bans=[
            BanOut(
                address=ban.address,
                kind=ban.kind,
                scenario=ban.scenario,
                origin=ban.origin,
                seen_at=ban.seen_at,
                ends_at=ban.ends_at,
                simulated=ban.simulated,
                in_force=ban.in_force(now),
            )
            for ban in done.bans
        ],
        blocked=done.tally.blocked,
        blocked_since_ban=done.tally.after_ban if any(ban.real for ban in done.bans) else None,
        last_blocked_at=done.tally.last_blocked_at,
        dropped=done.tally.dropped,
        unknown=list(done.unknown),
    )


def _glance(read: AiTriage | None) -> GlanceOut | None:
    if read is None:
        return None
    return GlanceOut(
        classification=cast(Classification, read.classification), confidence=read.confidence
    )


def _reading(read: AiTriage | None) -> ReadingOut | None:
    if read is None:
        return None
    known = catalog.provider(read.provider)
    return ReadingOut(
        classification=cast(Classification, read.classification),
        confidence=read.confidence,
        headline=read.headline,
        story=read.story,
        checks=read.checks,
        verdict=cast(Verdict | None, read.verdict),
        verdict_reason=read.verdict_reason,
        read_at=read.read_at,
        provider=known.label if known else read.provider,
        model=read.model,
        signals_read=read.signals_read,
    )


@dataclass(frozen=True)
class Judging:
    """What decides the lane an incident is in: how sure it takes for an incident to be asked
    about, and the owner's threat detection settings."""

    floor: int
    tuning: Tuning


def _judging(db: Db) -> Judging:
    return Judging(filters.load(db).confidence_floor, threat_settings.load(db))


def _call(incident: Incident) -> CallOut | None:
    if incident.ai_class is None or incident.ai_confidence is None or incident.ai_basis is None:
        return None
    return CallOut(
        classification=cast(Classification, incident.ai_class),
        confidence=incident.ai_confidence,
        basis=cast(Basis, incident.ai_basis),
    )


def _incident(
    incident: Incident, done: response.Response, judging: Judging, read: AiTriage | None = None
) -> IncidentOut:
    lane = attention.lane_of(incident, judging.floor, judging.tuning)
    return IncidentOut(
        id=incident.id,
        title=incident.title,
        subject=incident.subject,
        severity=SEVERITY_NAMES[Severity(incident.severity)],
        confidence=incident.confidence,
        confidence_level=rules.level_of(incident.confidence),
        status=cast(Status, incident.status),
        first_seen_at=incident.first_seen_at,
        last_seen_at=incident.last_seen_at,
        signal_count=incident.signal_count,
        sources=[_program(key) for key in incident.sources],
        addresses=[str(address) for address in incident.addresses],
        banned=incident.banned,
        response=_response(done),
        status_changed_at=incident.status_changed_at,
        verdict=cast(Verdict | None, incident.verdict),
        verdict_counts=cast(dict[Verdict, int], incident.verdict_counts),
        filtered_count=incident.filtered_count,
        activities=cast(list[Activity], incident.activities),
        waves=max(incident.waves, 1),
        port_count=len(incident.ports),
        ports_capped=len(incident.ports) >= episode.MAX_PORTS,
        neighbours=episode.neighbours_of(incident.subject, incident.block, incident.addresses),
        ai=_glance(read),
        lane=lane.value if lane else None,
        duplicates=incident.duplicate_count,
        stages=cast(list[Stage], incident.stages),
        family_id=incident.family_id,
        call=_call(incident),
    )


def _signal(signal: IncidentSignal) -> SignalOut:
    return SignalOut(
        occurred_at=signal.occurred_at,
        source=signal.source,
        source_name=rules.name_of(signal.source),
        kind=signal.kind,
        severity=SEVERITY_NAMES[Severity(signal.severity)],
        summary=signal.summary,
        signature=signal.signature,
        src_address=str(signal.src_address) if signal.src_address else None,
        src_port=signal.src_port,
        dst_address=str(signal.dst_address) if signal.dst_address else None,
        dst_port=signal.dst_port,
        protocol=signal.protocol,
        verdict=cast(Verdict | None, signal.verdict),
        verdict_rule_id=signal.verdict_rule_id,
        filtered_by=cast(Literal["inside", "severity", "thin"] | None, signal.filtered_by),
        duplicate=signal.duplicate,
    )


# How many of an incident's occurrences are sent with what their programs said of them: the most
# serious and the most often repeated, since an incident can have a thousand.
EVIDENCE_LIMIT = 30


def _evidence(said: evidence.Evidence | None) -> EvidenceOut | None:
    if said is None:
        return None
    seen = said.get("traffic")
    return EvidenceOut(
        facts=[FactOut(label=label, value=value) for label, value in said["facts"]],
        tags=said["tags"],
        mitre=[TechniqueOut(**each) for each in said["mitre"]],
        named=[NamedOut(**each) for each in said["indicators"]],
        traffic=TrafficOut(
            packets_out=seen.get("packets_out"),
            packets_in=seen.get("packets_in"),
            bytes_out=seen.get("bytes_out"),
            bytes_in=seen.get("bytes_in"),
        )
        if seen
        else None,
        host=said.get("host"),
        app=said.get("app"),
        excerpt=said.get("excerpt"),
    )


def _insights(found: insights.Insights) -> InsightsOut | None:
    if found.empty:
        return None
    return InsightsOut(
        techniques=[
            CountedTechniqueOut(
                id=each.id, tactic=each.tactic, technique=each.technique, count=each.count
            )
            for each in found.techniques
        ],
        tags=[CountedOut(value=each.value, count=each.count) for each in found.tags],
        hosts=[CountedOut(value=each.value, count=each.count) for each in found.hosts],
        apps=[CountedOut(value=each.value, count=each.count) for each in found.apps],
        named=[
            CountedNamedOut(kind=each.kind, value=each.value, count=each.count)
            for each in found.named
        ],
        programs=[
            ContributionOut(
                source=each.source,
                source_name=rules.name_of(each.source),
                reports=each.reports,
                adds=each.adds,
            )
            for each in found.programs
        ],
    )


def _occurrences(found: list[occurrences.Occurrence]) -> list[OccurrenceOut]:
    """The occurrences as they are told, the first of them in the order they happened. Only the
    busiest say what their programs said."""
    ranked = sorted(
        range(len(found)),
        key=lambda index: (-found[index].first.severity, -found[index].count, index),
    )
    detailed = set(ranked[:EVIDENCE_LIMIT])
    return [
        OccurrenceOut(
            signal=_signal(each.first),
            count=each.count,
            last_at=each.last_at,
            duplicates=each.duplicates,
            evidence=_evidence(evidence.load(each.first)) if index in detailed else None,
            confirmations=[
                ConfirmationOut(
                    source=one.source,
                    source_name=rules.name_of(one.source),
                    signature=one.signature,
                    severity=SEVERITY_NAMES[Severity(one.severity)],
                    count=one.count,
                    first_at=one.first_at,
                    last_at=one.last_at,
                    evidence=_evidence(one.evidence) if index in detailed else None,
                )
                for one in each.confirmations
            ],
        )
        for index, each in enumerate(found)
    ]


def _family(db: Db, incident: Incident) -> FamilyBrief | None:
    if incident.family_id is None:
        return None
    family = db.get(IncidentFamily, incident.family_id)
    if family is None:  # pragma: no cover - a family is only deleted with its incidents
        return None
    return brief_of(family, size(db, family.id))


def size(db: Db, family_id: int) -> int:
    """How many incidents of a family are going on."""
    return (
        db.scalar(
            select(func.count()).where(
                Incident.family_id == family_id, Incident.status.in_(attention.ACTIVE)
            )
        )
        or 0
    )


def brief_of(family: IncidentFamily, incidents: int) -> FamilyBrief:
    return FamilyBrief(
        id=family.id,
        label=family.label,
        source=family.source,
        source_name=rules.name_of(family.source),
        reach=cast(Literal["internet", "network", "rule"], family.reach),
        owner_call=cast(Literal["background", "watch"] | None, family.owner_call),
        classification=cast(Classification | None, family.ai_class),
        confidence=family.ai_confidence,
        reason=family.ai_reason,
        judged_at=family.judged_at,
        incidents=incidents,
    )


def _detail(db: Db, incident: Incident) -> IncidentDetail:
    done = response.of(db, [incident])[incident.id]
    read = db.get(AiTriage, incident.id)
    judging = _judging(db)
    seen = queries.signals(db, incident)
    grouped = occurrences.group(seen)
    return IncidentDetail(
        **_incident(incident, done, judging, read).model_dump(),
        reasons=[ReasonOut.model_validate(reason) for reason in incident.reasons],
        grouping=episode.explain(
            subject=incident.subject,
            block=incident.block,
            neighbours=episode.neighbours_of(incident.subject, incident.block, incident.addresses),
            activities=incident.activities,
            waves=max(incident.waves, 1),
            signals=incident.signal_count,
            port_count=len(incident.ports),
            gaps=filters.load(db).gaps(),
        ),
        ports=incident.ports,
        signals=[_signal(signal) for signal in seen],
        devices=[
            DeviceOut(
                id=device.id,
                address=str(address),
                mac=device.mac,
                hostname=device.hostname,
                vendor=device.vendor,
            )
            for address, device in queries.devices(db, incident)
        ],
        blocked=None if done.state == "no_address" else done.tally.blocked,
        reading=_reading(read),
        why=explain.why(incident, judging.floor, judging.tuning),
        occurrences=_occurrences(grouped),
        family=_family(db, incident),
        insights=_insights(insights.of(grouped)),
    )


def _found(db: Db, incident_id: int) -> Incident:
    incident = queries.get(db, incident_id)
    if incident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no such incident.")
    return incident


def _facets(found: queries.Facets) -> FacetsOut:
    return FacetsOut(
        severity={name: found.severity.get(level, 0) for level, name in SEVERITY_NAMES.items()},
        sources=[
            SourceCount(key=key, name=rules.name_of(key), count=count)
            for key, count in sorted(found.source.items(), key=lambda item: (-item[1], item[0]))
        ],
    )


def _ask(db: Db, text: str, zone: str | None) -> search.Search:
    return asking.ask(db, text, zone, search.parse)


def _minimum(name: SeverityName | None) -> Severity | None:
    if name is None:
        return None
    return next(level for level, known in SEVERITY_NAMES.items() if known == name)


def _in_lanes(
    judging: Judging, lanes: list[LaneName] | None, family: int | None
) -> list[ColumnElement[bool]]:
    """What an incident has to be to be in the lanes asked for, and the family, if one was."""
    found: list[ColumnElement[bool]] = []
    if lanes:
        by = attention.lane_clauses(judging.floor, judging.tuning)
        found.append(or_(*(by[Lane(name)] for name in set(lanes))))
    if family is not None:
        found.append(Incident.family_id == family)
    return found


class _Scope(NamedTuple):
    """Which lanes and which kind of incident a list was asked to be narrowed to."""

    lanes: list[LaneName] | None
    family: int | None


def _scope(
    lane: Annotated[
        list[LaneName] | None,
        Query(
            description="Only those in this lane (threat, suspect or background), which are "
            "incidents that are going on. Repeat it for several."
        ),
    ] = None,
    family: Annotated[int | None, Query(ge=1, le=2**63 - 1, description="Only this kind.")] = None,
) -> _Scope:
    return _Scope(lane, family)


@router.get("")
def list_incidents(
    db: Db,
    scope: Annotated[_Scope, Depends(_scope)],
    state: Annotated[
        list[Status] | None,
        Query(alias="status", description="Only these, e.g. open. Repeat it for several."),
    ] = None,
    verdict: Annotated[
        list[VerdictFilter] | None,
        Query(description="Only these, e.g. threat, or none for those without. Repeat it."),
    ] = None,
    min_severity: Annotated[SeverityName | None, Query()] = None,
    min_confidence: Annotated[int, Query(ge=0, le=rules.MAX_CONFIDENCE)] = 0,
    address: Annotated[IPvAnyAddress | None, Query(description="Ones that name this.")] = None,
    since: Annotated[AwareDatetime | None, Query(description="Going on from this time.")] = None,
    q: Annotated[
        str,
        Query(
            description="A search in words, such as: severity>=high source:wazuh -port:22 ssh. "
            "Everything it says has to be true, as well as the rest."
        ),
    ] = "",
    tz: Annotated[
        str | None,
        Query(description="The time zone the person is in, such as America/Halifax."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: Annotated[
        Order,
        Query(description="recent: going most recently first. priority: most serious first."),
    ] = "recent",
) -> IncidentPage:
    """Incidents, the ones that were going most recently first unless asked for the most
    serious and surest first."""
    asked = _ask(db, q, tz)
    judging = _judging(db)
    with asking.in_time(db):
        page = queries.search(
            db,
            verdicts=list(verdict or []),
            where=queries.conditions(
                statuses=list(state or []),
                min_severity=_minimum(min_severity),
                min_confidence=min_confidence,
                address=address,
                since=since,
                extra=[*asked.conditions(), *_in_lanes(judging, scope.lanes, scope.family)],
            ),
            limit=limit,
            offset=offset,
            order=order,
        )
        counts = queries.counts(db, list(verdict or []))
    done = response.of(db, page.incidents)
    read = {
        found.incident_id: found
        for found in db.scalars(
            select(AiTriage).where(AiTriage.incident_id.in_([i.id for i in page.incidents]))
        )
    }
    return IncidentPage(
        total=page.total,
        items=[
            _incident(incident, done[incident.id], judging, read.get(incident.id))
            for incident in page.incidents
        ],
        terms=[
            TermOut(
                field=term.field,
                label=term.label,
                negated=term.negated,
                start=term.start,
                end=term.end,
            )
            for term in asked.terms
        ],
        facets=_facets(page.facets),
        counts=cast(dict[Status, int], counts),
        quieted=page.quieted,
    )


def _picked(db: Db, body: BulkIn) -> list[Incident]:
    """The incidents a change is for: those that were picked and still exist, or all that match
    what a list was asked, unless that is more than can be looked over."""
    if body.ids is not None:
        return list(
            db.scalars(select(Incident).where(Incident.id.in_(body.ids)).order_by(Incident.id))
        )
    matching = cast(Matching, body.matching)
    asked = _ask(db, matching.q, matching.tz)
    with asking.in_time(db):
        total, found = queries.selected(
            db,
            verdicts=list(matching.verdict),
            where=queries.conditions(
                statuses=list(matching.status),
                min_severity=_minimum(matching.min_severity),
                min_confidence=matching.min_confidence,
                address=matching.address,
                since=matching.since,
                extra=[
                    *asked.conditions(),
                    *_in_lanes(_judging(db), list(matching.lane), matching.family),
                ],
            ),
            limit=bulk.MAX_INCIDENTS,
        )
    if total > bulk.MAX_INCIDENTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"That is {total:,} incidents, and {bulk.MAX_INCIDENTS:,} is the most that can be "
            "changed at once. Narrow it down first.",
        )
    # Only finding them was to be quick; what is done to them is not held to the same limit.
    db.execute(select(func.set_config("statement_timeout", "0", True)))
    return found


@router.post("/bulk")
def change_incidents(
    body: BulkIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> BulkOut:
    """Says what is being done about many incidents, or what is thought of what they are about,
    in one go: all of them or none. A verdict is one for each address (or alert, where an
    incident names no address), not for each incident, and it is judged again at once, as any
    verdict is. With ``preview`` nothing is changed and the answer says what would be. Otherwise it
    says how to take the change back, and the activity log has one entry for it, with the ids."""
    apply = not body.preview
    incidents = _picked(db, body)
    if body.status is not None:
        done = bulk.set_status(incidents, body.status, now=utcnow(), apply=apply)
        facts: dict[str, str | int | bool] = {"change": "status", "to": body.status}
    else:
        verdict = cast(Verdict, body.verdict)
        if apply:
            engine.hold(db)
        done = bulk.give_verdict(db, incidents, verdict, body.note, apply=apply)
        facts = {"change": "verdict", "verdict": verdict, "verdicts": done.verdicts}
    undo = None
    if apply and done.ids:
        record_audit(
            db,
            request,
            Action.INCIDENTS_CHANGED,
            Outcome.SUCCESS,
            user=auth.user,
            detail={
                **facts,
                "incidents": done.changed,
                "ids": ",".join(str(incident_id) for incident_id in done.ids),
            },
        )
        if body.verdict is not None:
            engine.reapply(db)
        db.commit()
        if done.statuses or done.rules:
            undo = Undo(
                statuses=cast(dict[Status, SomeIncidents], done.statuses),
                rules=[
                    RuleBack(id=rule_id, replaced=cast(Verdict | None, replaced))
                    for rule_id, replaced in done.rules
                ],
            )
    return BulkOut(
        preview=body.preview,
        incidents=done.incidents,
        signals=done.signals,
        changed=done.changed,
        skipped=done.skipped,
        verdicts=done.verdicts,
        undo=undo,
    )


@router.post("/bulk/undo")
def take_back_change(
    body: Undo,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> UndoOut:
    """Takes back a change made to many incidents in one go, as it said how to: the statuses go
    back to what they were, and each verdict it made goes or says again what it said. One entry
    in the activity log says so."""
    if body.rules:
        engine.hold(db)
    restored, changed = bulk.take_back(
        db,
        {status: list(ids) for status, ids in body.statuses.items()},
        [(rule.id, rule.replaced) for rule in body.rules],
        now=utcnow(),
    )
    if restored or changed:
        record_audit(
            db,
            request,
            Action.INCIDENTS_CHANGE_UNDONE,
            Outcome.SUCCESS,
            user=auth.user,
            detail={"incidents": restored, "verdicts": changed},
        )
        if changed:
            engine.reapply(db)
        db.commit()
    return UndoOut(incidents=restored, verdicts=changed)


@router.get("/{incident_id}")
def get_incident(incident_id: IncidentId, db: Db) -> IncidentDetail:
    """One incident with the reasons for its confidence, its timeline and the devices in it."""
    return _detail(db, _found(db, incident_id))


@router.patch("/{incident_id}")
def set_status(
    incident_id: IncidentId,
    body: StatusIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> IncidentDetail:
    """Says what is being done about an incident. A resolved incident is over: a signal that
    comes later starts another. One that is dismissed keeps taking signals, quietly."""
    incident = _found(db, incident_id)
    if incident.status != body.status:
        record_audit(
            db,
            request,
            Action.INCIDENT_STATUS_CHANGED,
            Outcome.SUCCESS,
            user=auth.user,
            detail={"incident": incident.id, "from": incident.status, "to": body.status},
        )
        incident.status = body.status
        incident.status_changed_at = utcnow()
        db.commit()
    return _detail(db, incident)


class TriageOut(BaseModel):
    """What came of asking the AI about an incident. When it could not be asked (AI is off, no
    provider is chosen, the provider failed) ``ok`` is false and ``reason`` says why in words for
    whoever asked, and the incident is as it was."""

    ok: bool
    reason: str | None
    incident: IncidentDetail


@router.post("/{incident_id}/triage")
def read_incident(
    incident_id: IncidentId,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    context: AiContext,
) -> TriageOut:
    """Has the AI read the incident now, and keeps what it made of it (one reading for each
    incident, the latest). Asks the chosen provider, which sees what Settings > AI allows, and
    changes nothing else about the incident. It can take a minute."""
    incident = _found(db, incident_id)
    outcome = triage.ask_now(db, context, incident)
    read = outcome.triage if isinstance(outcome, triage.Read) else None
    record_audit(
        db,
        request,
        Action.INCIDENT_TRIAGED,
        Outcome.SUCCESS if read else Outcome.FAILURE,
        user=auth.user,
        detail={"incident": incident.id}
        | ({"classification": read.classification, "model": read.model} if read else {}),
    )
    db.commit()
    return TriageOut(
        ok=read is not None,
        reason=None if read else cast(triage.NotRead, outcome).reason,
        incident=_detail(db, incident),
    )
