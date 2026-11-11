"""Chains: an attack that crossed from the internet into a device and then out again.

An incident is about one address, so an attack that got in through a flaw and then made a device
call out is two of them: the one about the outside address that attacked, and the one about the
outside address the device then called (a beacon, a command server, a new connection it had no
business making). Seen apart, the second looks like a device talking to the internet and the first
like an attempt. Seen together they are what Microsoft Sentinel's Fusion looks for: an inside
device that was attacked by an exploit and shortly afterwards calls out.

They are linked by the device and the time, and by nothing else:

- the attacker is an incident with a signal that is a flaw being tried (``access``), or already a
  sign it worked (``foothold``), aimed at the device;
- the callout is an incident with a signal the device itself sent to an address on the internet, at
  least medium serious, within ``WINDOW`` after that.

The link is **confirmed** when what the device sent is itself a sign that an attack worked (a
beacon, malware, a command server). It is **inferred** when the device only called out: the
timing and the device agree, and nothing else does, so it is said to be a guess and never more.
Without an exploit aimed at the device there is no link at all: scanning is what the internet does
to every address, and a device calling out is what devices do, so neither makes a chain alone.

A chain is a threat: its steps are never unsure and never set aside (``attention.py``).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.events.event import Severity
from app.incidents.subject import Address
from app.incidents.verdicts import MUTING
from app.models import Incident, IncidentChain, IncidentSignal
from app.threats import stages

ATTACKER: Final = "attacker"
CALLOUT: Final = "callout"
CONFIRMED: Final = "confirmed"
INFERRED: Final = "inferred"
# How soon after an exploit was aimed at a device a call out from it counts as what followed.
WINDOW: Final = timedelta(hours=6)
# How far back an incident may have last been going on and still be looked at again.
LOOKBACK: Final = timedelta(hours=24)
# The signals read in a pass, and how many a pass links.
BATCH: Final = 2000
MIN_SEVERITY: Final = Severity.MEDIUM
MAX_REASON: Final = 300
STEPS: Final = (ATTACKER, CALLOUT)


@dataclass
class _Calls:
    """What a device sent out in one incident: when each time, and which of them were a sign that
    an attack worked."""

    incident: Incident
    device: Address
    # The first of them.
    first: IncidentSignal
    times: list[datetime] = field(default_factory=list[datetime])
    footholds: list[tuple[datetime, str]] = field(default_factory=list[tuple[datetime, str]])


def _inside(address: Address) -> bool:
    return address.is_private and not address.is_loopback and not address.is_link_local


def _quiet(signal: IncidentSignal) -> bool:
    return signal.verdict in MUTING or signal.filtered_by is not None


def how_long(delta: timedelta) -> str:
    minutes = max(int(delta.total_seconds() // 60), 0)
    if minutes < 1:
        return "moments"
    if minutes < 90:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    return f"{round(minutes / 60)} hours"


def _what(signal: IncidentSignal) -> str:
    return (signal.signature or signal.summary).strip()


def _outgoing(db: Session, now: datetime) -> list[_Calls]:
    """The incidents with signals a device on the network sent to the internet, which are not yet
    in a chain (or are, on an inferred link that a stronger sign may confirm)."""
    rows = db.execute(
        select(IncidentSignal, Incident)
        .join(Incident, Incident.id == IncidentSignal.incident_id)
        .where(
            Incident.last_seen_at >= now - LOOKBACK,
            or_(
                Incident.chain_id.is_(None),
                and_(Incident.chain_role == CALLOUT, Incident.chain_link == INFERRED),
            ),
            IncidentSignal.src_address.is_not(None),
            IncidentSignal.dst_address.is_not(None),
            IncidentSignal.duplicate.is_(False),
            IncidentSignal.severity >= MIN_SEVERITY,
        )
        .order_by(IncidentSignal.occurred_at)
        .limit(BATCH)
    ).all()
    found: dict[tuple[int, Address], _Calls] = {}
    for signal, incident in rows:
        sender, target = signal.src_address, signal.dst_address
        if sender is None or target is None or _quiet(signal):
            continue
        if not (_inside(sender) and target.is_global):
            continue
        calls = found.setdefault((incident.id, sender), _Calls(incident, sender, signal))
        calls.times.append(signal.occurred_at)
        if stages.stage_of(signal) == stages.FOOTHOLD:
            calls.footholds.append((signal.occurred_at, _what(signal)))
    return list(found.values())


def _attacks(db: Session, calls: _Calls) -> dict[int, tuple[Incident, IncidentSignal]]:
    """For each incident that aimed an exploit at the device just before it called out, the first
    signal that did."""
    rows = db.execute(
        select(IncidentSignal, Incident)
        .join(Incident, Incident.id == IncidentSignal.incident_id)
        .where(
            IncidentSignal.dst_address == calls.device,
            IncidentSignal.occurred_at >= calls.times[0] - WINDOW,
            IncidentSignal.occurred_at <= calls.times[-1],
            IncidentSignal.duplicate.is_(False),
            Incident.id != calls.incident.id,
        )
        .order_by(IncidentSignal.occurred_at)
    ).all()
    found: dict[int, tuple[Incident, IncidentSignal]] = {}
    for signal, incident in rows:
        outside = signal.src_address is not None and signal.src_address.is_global
        tried = stages.stage_of(signal) in (stages.ACCESS, stages.FOOTHOLD)
        if outside and tried and not _quiet(signal):
            found.setdefault(incident.id, (incident, signal))
    return found


def _after(calls: _Calls, attack: IncidentSignal) -> list[datetime]:
    """When the device called out within the window after an exploit was aimed at it."""
    started = attack.occurred_at
    return [at for at in calls.times if started <= at <= started + WINDOW]


def _free(db: Session, incident: Incident, device: Address) -> bool:
    """Whether an incident may be a step of a chain of this device: it is in none yet, or in this
    device's. An attacker already in the chain of another device is left there."""
    if incident.chain_id is None:
        return True
    return db.scalar(
        select(IncidentChain.device).where(IncidentChain.id == incident.chain_id)
    ) == str(device)


def _chain_for(
    db: Session, calls: _Calls, attacks: dict[int, tuple[Incident, IncidentSignal]]
) -> IncidentChain:
    """The chain these steps are already part of, or a new one."""
    for incident in (calls.incident, *(incident for incident, _ in attacks.values())):
        if incident.chain_id is not None:
            return db.get_one(IncidentChain, incident.chain_id)
    chain = IncidentChain(
        device=str(calls.device),
        first_seen_at=min(signal.occurred_at for _, signal in attacks.values()),
        last_seen_at=calls.times[-1],
        confirmed=False,
        steps=0,
    )
    db.add(chain)
    db.flush()
    return chain


def _set(incident: Incident, chain: IncidentChain, role: str, link: str, reason: str) -> bool:
    """Makes an incident a step of the chain, and says whether that changed anything."""
    wanted = (chain.id, role, link, reason[:MAX_REASON])
    have = (incident.chain_id, incident.chain_role, incident.chain_link, incident.chain_reason)
    if have == wanted:
        return False
    incident.chain_id, incident.chain_role, incident.chain_link, incident.chain_reason = wanted
    return True


def _how(calls: _Calls, attacks: list[IncidentSignal]) -> tuple[str, str]:
    """How the device's calls out are tied to the exploits before them: the link, and why."""
    for at, what in calls.footholds:
        before = [attack.occurred_at for attack in attacks if attack.occurred_at <= at]
        if before:
            return CONFIRMED, (
                f"{calls.device} did what a device that was taken over does ({what}), "
                f"{how_long(at - max(before))} after the attack."
            )
    called = _what(calls.first)
    began = min(at for at in calls.times if at >= min(a.occurred_at for a in attacks))
    after = max(a.occurred_at for a in attacks if a.occurred_at <= began)
    return INFERRED, (
        f"{calls.device} called out ({called}), {how_long(began - after)} after the attack. The "
        "device and the timing agree and nothing else does, so this link is inferred."
    )


def _link_one(db: Session, calls: _Calls) -> int:
    """Links one incident's calls out to the exploits that came before them, if any. Returns how
    many incidents were linked or changed."""
    attacks = {
        key: (incident, signal)
        for key, (incident, signal) in _attacks(db, calls).items()
        if _after(calls, signal) and _free(db, incident, calls.device)
    }
    if not attacks or not _free(db, calls.incident, calls.device):
        return 0
    chain = _chain_for(db, calls, attacks)
    changed = 0
    for incident, signal in attacks.values():
        reason = f"{_what(signal)}, aimed at {calls.device}."
        changed += _set(incident, chain, ATTACKER, CONFIRMED, reason)
    link, reason = _how(calls, [signal for _, signal in attacks.values()])
    changed += _set(calls.incident, chain, CALLOUT, link, reason)
    return changed


def _refresh(db: Session) -> None:
    """Works out each chain from its steps again, and drops one that is not both an attacker and
    a callout any more: its steps (an incident that was merged into another, say) are what made
    it a chain."""
    for chain in db.scalars(select(IncidentChain)):
        members = list(db.scalars(select(Incident).where(Incident.chain_id == chain.id)))
        if {member.chain_role for member in members} != set(STEPS):
            for member in members:
                member.chain_id = member.chain_role = member.chain_link = None
                member.chain_reason = None
            db.delete(chain)
            continue
        chain.steps = len(members)
        chain.first_seen_at = min(member.first_seen_at for member in members)
        chain.last_seen_at = max(member.last_seen_at for member in members)
        chain.confirmed = any(
            member.chain_role == CALLOUT and member.chain_link == CONFIRMED for member in members
        )


def link(db: Session, now: datetime) -> int:
    """Links the incidents that are one attack across two devices into chains, and returns how
    many incidents it linked or changed."""
    changed = sum(_link_one(db, calls) for calls in _outgoing(db, now))
    db.flush()
    _refresh(db)
    db.flush()
    return changed
