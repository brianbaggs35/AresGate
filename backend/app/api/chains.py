"""Chains: attacks that went from the internet into a device and out again, linked across the two
incidents that saw each half (see app/threats/chains.py). For someone signed in."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import incidents as incident_api
from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.api.deps import Db, signed_in
from app.events.event import Severity
from app.incidents import attention, filters, occurrences, queries, rules
from app.models import Device, DeviceAddress, Incident, IncidentChain, IncidentSignal
from app.threats import chains
from app.threats import settings as threat_settings

router = APIRouter(prefix="/threats/chains", tags=["threats"], dependencies=[Depends(signed_in)])

ChainId = Annotated[int, Path(ge=1, le=2**63 - 1)]
Link = Literal["confirmed", "inferred"]
Role = Literal["attacker", "callout"]
MAX_PAGE = 100
# How many occurrences a step shows as its evidence: the ones that name the device.
EVIDENCE = 12
NO_SUCH_CHAIN = "There's no such chain."


class StepOut(BaseModel):
    """One incident of a chain: what it did, how it is tied to the chain and the evidence."""

    role: Role
    # Whether the tie was seen (confirmed) or only guessed from the device and the timing.
    link: Link
    # Why it is a step, in words.
    reason: str
    incident_id: int
    title: str
    subject: str
    severity: SeverityName
    status: incident_api.Status
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime
    signal_count: int
    # How many of its alerts another program also reported, which count once.
    duplicates: int
    # Every program that reported part of it.
    sources: list[incident_api.ProgramOut]
    stages: list[incident_api.Stage]
    # What the programs said of the signals that name the device, the same alert from several
    # programs counted once and listing each of them.
    evidence: list[incident_api.OccurrenceOut]


class ChainOut(BaseModel):
    id: int
    # The inside address of the device the attack went through, and what it is called if known.
    device: str
    device_name: str | None
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime
    # Whether the device was seen doing what a taken-over device does, and not only calling out.
    confirmed: bool
    steps: int
    severity: SeverityName
    # A threat while any step is one that needs attention; None once all are handled or muted.
    lane: incident_api.LaneName | None
    # In one line: who got in, and where the device then called.
    summary: str


class ChainPage(BaseModel):
    total: int
    items: list[ChainOut]


class ChainDetail(ChainOut):
    # In the order they happened.
    path: list[StepOut]
    # Why it is a threat, a fact to a line.
    why: list[str]


def _name_of(db: Session, device: str) -> str | None:
    return db.scalar(
        select(Device.hostname)
        .join(DeviceAddress, DeviceAddress.device_id == Device.id)
        .where(func.host(DeviceAddress.address) == device)
        .order_by(DeviceAddress.last_seen_at.desc())
        .limit(1)
    )


def _members(db: Session, chain: IncidentChain) -> list[Incident]:
    return list(
        db.scalars(
            select(Incident)
            .where(Incident.chain_id == chain.id)
            .order_by(Incident.first_seen_at, Incident.id)
        )
    )


def _lane(db: Session, members: list[Incident]) -> incident_api.LaneName | None:
    floor = filters.load(db).confidence_floor
    tuning = threat_settings.load(db)
    found = {attention.lane_of(each, floor, tuning) for each in members} - {None}
    if not found:
        return None
    return "threat" if attention.Lane.THREAT in found else "suspect"


def _summary(chain: IncidentChain, members: list[Incident]) -> str:
    attackers = [each.subject for each in members if each.chain_role == chains.ATTACKER]
    callouts = [each.subject for each in members if each.chain_role == chains.CALLOUT]
    got_in = " and ".join(attackers) or "an outside address"
    called = " and ".join(callouts) or "the internet"
    return f"{got_in} attacked {chain.device}, which then called {called}."


def _out(db: Session, chain: IncidentChain, members: list[Incident]) -> ChainOut:
    return ChainOut(
        id=chain.id,
        device=chain.device,
        device_name=_name_of(db, chain.device),
        first_seen_at=chain.first_seen_at,
        last_seen_at=chain.last_seen_at,
        confirmed=chain.confirmed,
        steps=chain.steps,
        severity=SEVERITY_NAMES[Severity(max(each.severity for each in members))],
        lane=_lane(db, members),
        summary=_summary(chain, members),
    )


def _touching(signals: list[IncidentSignal], device: str) -> list[IncidentSignal]:
    """The signals that name the device, which are the part of an incident that is the chain."""
    return [each for each in signals if device in (str(each.src_address), str(each.dst_address))]


def _step(db: Session, chain: IncidentChain, incident: Incident) -> StepOut:
    shown = _touching(queries.signals(db, incident), chain.device)
    grouped = occurrences.group(shown)[:EVIDENCE]
    return StepOut(
        role=cast(Role, incident.chain_role),
        link=cast(Link, incident.chain_link),
        reason=incident.chain_reason or "",
        incident_id=incident.id,
        title=incident.title,
        subject=incident.subject,
        severity=SEVERITY_NAMES[Severity(incident.severity)],
        status=cast(incident_api.Status, incident.status),
        first_seen_at=incident.first_seen_at,
        last_seen_at=incident.last_seen_at,
        signal_count=incident.signal_count,
        duplicates=incident.duplicate_count,
        sources=[
            incident_api.ProgramOut(key=key, name=rules.name_of(key)) for key in incident.sources
        ],
        stages=cast(list[incident_api.Stage], incident.stages),
        evidence=incident_api.occurrences_out(grouped),
    )


def _why(chain: IncidentChain, members: list[Incident]) -> list[str]:
    lines = [
        "A chain is more than scanning: an exploit was aimed at a device on your network, and "
        "that device then called out, so it is a threat whatever else its steps look like.",
    ]
    lines.extend(each.chain_reason for each in members if each.chain_reason)
    if not chain.confirmed:
        lines.append(
            "Nothing seen proves the device was taken over (a beacon, malware, a command server), "
            "so the call out is an inference from the device and the timing, and it is kept "
            "apart from what was seen."
        )
    return lines


def _found(db: Session, chain_id: int) -> IncidentChain:
    chain = db.get(IncidentChain, chain_id)
    if chain is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_SUCH_CHAIN)
    return chain


@router.get("")
def list_chains(
    db: Db,
    confirmed: Annotated[
        bool | None, Query(description="Only the chains that were seen, or only the inferred ones.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChainPage:
    """The chains, the most recent first."""
    wanted = [] if confirmed is None else [IncidentChain.confirmed.is_(confirmed)]
    total = db.scalar(select(func.count()).select_from(IncidentChain).where(*wanted)) or 0
    found = db.scalars(
        select(IncidentChain)
        .where(*wanted)
        .order_by(IncidentChain.last_seen_at.desc(), IncidentChain.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return ChainPage(total=total, items=[_out(db, each, _members(db, each)) for each in found])


@router.get("/{chain_id}")
def get_chain(chain_id: ChainId, db: Db) -> ChainDetail:
    """One chain: its steps in the order they happened and the evidence behind each."""
    chain = _found(db, chain_id)
    members = _members(db, chain)
    return ChainDetail(
        **_out(db, chain, members).model_dump(),
        path=[_step(db, chain, each) for each in members],
        why=_why(chain, members),
    )
