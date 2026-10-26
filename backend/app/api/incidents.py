"""Incidents: the alerts, bans and other signals from every integration that belong together,
how serious they are, how sure AresGate is and why. For someone signed in."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, IPvAnyAddress

from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.events.event import Severity
from app.incidents import queries, rules
from app.models import Incident, IncidentSignal, utcnow

router = APIRouter(prefix="/incidents", tags=["incidents"], dependencies=[Depends(signed_in)])

Status = Literal["open", "investigating", "resolved", "dismissed"]
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
    # Oldest first. Only the first so many are kept; ``signal_count`` has them all.
    signals: list[SignalOut]
    devices: list[DeviceOut]
    # How many times the firewall turned the subject away around then, or None for an incident
    # about a rule.
    blocked: int | None


class IncidentPage(BaseModel):
    total: int
    items: list[IncidentOut]
    # How many incidents there are in each status, whatever the search was for.
    counts: dict[Status, int]


class StatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Status


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
    )


def _detail(db: Db, incident: Incident) -> IncidentDetail:
    return IncidentDetail(
        **_incident(incident).model_dump(),
        reasons=[ReasonOut.model_validate(reason) for reason in incident.reasons],
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


@router.get("")
def list_incidents(
    db: Db,
    state: Annotated[
        list[Status] | None,
        Query(alias="status", description="Only these, e.g. open. Repeat it for several."),
    ] = None,
    min_severity: Annotated[SeverityName | None, Query()] = None,
    min_confidence: Annotated[int, Query(ge=0, le=rules.MAX_CONFIDENCE)] = 0,
    address: Annotated[IPvAnyAddress | None, Query(description="Ones that name this.")] = None,
    since: Annotated[AwareDatetime | None, Query(description="Going on from this time.")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IncidentPage:
    """Incidents, the ones that were going most recently first."""
    minimum = None
    if min_severity is not None:
        minimum = next(level for level, name in SEVERITY_NAMES.items() if name == min_severity)
    page = queries.search(
        db,
        statuses=list(state or []),
        min_severity=minimum,
        min_confidence=min_confidence,
        address=address,
        since=since,
        limit=limit,
        offset=offset,
    )
    return IncidentPage(
        total=page.total,
        items=[_incident(incident) for incident in page.incidents],
        counts=cast(dict[Status, int], queries.counts(db)),
    )


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
