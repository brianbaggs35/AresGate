"""Incidents: the alerts, bans and other signals from every integration that belong together,
how serious they are, how sure AresGate is and why. For someone signed in."""

from typing import Annotated, Literal, Self, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    IPvAnyAddress,
    model_validator,
)
from sqlalchemy import func, select

from app.api import asking
from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.api.verdicts import Note
from app.audit import Action, Outcome
from app.events.event import Severity
from app.incidents import bulk, engine, episode, queries, rules, search
from app.incidents.queries import Order
from app.models import Incident, IncidentSignal, utcnow

router = APIRouter(prefix="/incidents", tags=["incidents"], dependencies=[Depends(signed_in)])

Status = Literal["open", "investigating", "resolved", "dismissed"]
Verdict = Literal["not_suspicious", "low_priority", "threat"]
Activity = Literal["scan", "brute_force"]
# What to ask for to get the incidents nobody has given a verdict to.
VerdictFilter = Literal["none", "not_suspicious", "low_priority", "threat"]
MAX_PAGE = 200
IncidentId = Annotated[int, Path(ge=1, le=2**63 - 1)]


class ProgramOut(BaseModel):
    """An integration that reported part of an incident."""

    key: str
    name: str


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
    status_changed_at: AwareDatetime | None
    # What the owner's verdicts say of it as a whole: a real threat, not suspicious or low
    # priority, or nothing. The signals they gave a verdict to are listed and counted in
    # ``signal_count``, but everything else here is about the ones they didn't, and an incident of
    # signals they all called not suspicious or low priority is as sure as 0.
    verdict: Verdict | None
    verdict_counts: dict[Verdict, int]
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


class DeviceOut(BaseModel):
    """A device on the network that one of the incident's addresses belongs to."""

    id: int
    address: str
    mac: str
    hostname: str | None
    vendor: str | None


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
    # How many times the firewall turned the subject away around then, or None for an incident
    # about a rule.
    blocked: int | None


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


def _incident(incident: Incident) -> IncidentOut:
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
        status_changed_at=incident.status_changed_at,
        verdict=cast(Verdict | None, incident.verdict),
        verdict_counts=cast(dict[Verdict, int], incident.verdict_counts),
        activities=cast(list[Activity], incident.activities),
        waves=max(incident.waves, 1),
        port_count=len(incident.ports),
        ports_capped=len(incident.ports) >= episode.MAX_PORTS,
        neighbours=episode.neighbours_of(incident.subject, incident.block, incident.addresses),
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
    )


def _detail(db: Db, incident: Incident) -> IncidentDetail:
    return IncidentDetail(
        **_incident(incident).model_dump(),
        reasons=[ReasonOut.model_validate(reason) for reason in incident.reasons],
        grouping=episode.explain(
            subject=incident.subject,
            block=incident.block,
            neighbours=episode.neighbours_of(incident.subject, incident.block, incident.addresses),
            activities=incident.activities,
            waves=max(incident.waves, 1),
            signals=incident.signal_count,
            port_count=len(incident.ports),
        ),
        ports=incident.ports,
        signals=[_signal(signal) for signal in queries.signals(db, incident)],
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
        blocked=queries.blocks(db, incident),
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


@router.get("")
def list_incidents(
    db: Db,
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
                extra=asked.conditions(),
            ),
            limit=limit,
            offset=offset,
            order=order,
        )
        counts = queries.counts(db, list(verdict or []))
    return IncidentPage(
        total=page.total,
        items=[_incident(incident) for incident in page.incidents],
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
                extra=asked.conditions(),
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
