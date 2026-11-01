"""What the assistant may look at when it answers a question (app/ai/chat.py).

A model that answers questions about a network has to be told what the network is doing, and it
can't be told everything. So it asks for what it needs, from this short list, and is given that:
open incidents, one incident, recent alerts, who the firewall blocked most, a device, and how the
integrations are doing. Every one of them only reads. There is no tool that changes anything, and
no way to ask for a table or a query, so the model can't reach what this list doesn't offer.

A tool writes the lines it finds through the redactor it is given (app/ai/redaction.py), so a
provider that must not see an address sees a stand-in for it, and gives back references to what
the lines are about, which the answer may cite and the chat page turns into links. What a lookup
found is summed up in a few words with no name or address in them, to tell the owner what the
answer was based on.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import ColumnElement, false, or_, select
from sqlalchemy.orm import Session

from app.ai import triage
from app.ai.redaction import Redactor, read_address, read_mac
from app.dashboard import Window, recent_alerts, top_blocked_sources
from app.events.event import Severity
from app.incidents import queries
from app.incidents.verdicts import MUTING
from app.integrations.registry import INTEGRATIONS
from app.models import (
    AiTriage,
    CollectorHealth,
    Device,
    DeviceAddress,
    Incident,
    IntegrationConnection,
)

MAX_ITEMS: Final = 10
MAX_ALERTS: Final = 20
MAX_HOURS: Final = 168
DEFAULT_HOURS: Final = 24
MAX_DEVICES: Final = 5
WHEN: Final = "%Y-%m-%d %H:%M"
# The incidents that still need someone: not settled, and not quieted by the owner's verdicts.
ACTIVE: Final = ("open", "investigating")


@dataclass(frozen=True)
class Args:
    """What a lookup is asked for. A model fills what its tool uses and leaves the rest empty."""

    id: int | None = None
    name: str | None = None
    hours: int | None = None
    limit: int | None = None


@dataclass(frozen=True)
class Ref:
    """Something a lookup found that an answer may cite: ``kind`` is ``incident`` or
    ``integration``, ``key`` is its id, and ``label`` is what the page calls it."""

    kind: str
    key: str
    label: str


@dataclass(frozen=True)
class Found:
    """What a lookup found: the lines, already through the redactor, what they are about, and a
    few words for the owner saying what was found."""

    lines: list[str]
    refs: list[Ref]
    summary: str


Run = Callable[[Session, Redactor, Args, datetime], Found]


@dataclass(frozen=True)
class Tool:
    name: str
    # What it gives, and which of the arguments it uses, for the model to read.
    description: str
    run: Run


def _between(value: int | None, default: int, low: int, high: int) -> int:
    return default if value is None else max(low, min(high, value))


def _plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else many or one + 's'}"


def _when(moment: datetime | None) -> str:
    return f"{moment:{WHEN}} UTC" if moment else "never"


def _severity(value: int) -> str:
    return Severity(value).name.lower()


# -- incidents


def _incident_line(incident: Incident, reading: AiTriage | None, redactor: Redactor) -> str:
    sources = ", ".join(incident.sources) or "nobody"
    line = (
        f"[incident {incident.id}] {_severity(incident.severity)}, AresGate's confidence "
        f"{incident.confidence} of 100, {incident.status}: {redactor.text(incident.title, 160)} "
        f"(about {redactor.text(incident.subject, 120)}); last seen {_when(incident.last_seen_at)}"
        f", {_plural(incident.signal_count, 'signal')} from {sources}"
    )
    if reading is not None:
        line += (
            f"; the AI's reading: {reading.classification}, {redactor.text(reading.headline, 160)}"
        )
    return line


def open_incidents(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """The incidents that need someone, the most serious and surest first."""
    limit = _between(args.limit, 5, 1, MAX_ITEMS)
    rows = db.execute(
        select(Incident, AiTriage)
        .outerjoin(AiTriage, AiTriage.incident_id == Incident.id)
        .where(
            Incident.status.in_(ACTIVE),
            or_(Incident.verdict.is_(None), Incident.verdict.not_in(MUTING)),
        )
        .order_by(
            Incident.severity.desc(), Incident.confidence.desc(), Incident.last_seen_at.desc()
        )
        .limit(limit)
    ).all()
    if not rows:
        return Found(["There are no open incidents."], [], "no open incidents")
    return Found(
        [_incident_line(incident, reading, redactor) for incident, reading in rows],
        [Ref("incident", str(incident.id), f"Incident {incident.id}") for incident, _ in rows],
        _plural(len(rows), "open incident"),
    )


def incident(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """Everything known about one incident: why it is as serious as it is, who it involves and
    its signals."""
    found = queries.get(db, args.id) if args.id is not None else None
    if found is None:
        return Found([f"There is no incident {args.id}."], [], "no such incident")
    lines = [f"[incident {found.id}]", *triage.prompt_for(db, found, redactor).splitlines()]
    return Found(
        lines, [Ref("incident", str(found.id), f"Incident {found.id}")], f"incident {found.id}"
    )


# -- events


def _end(redactor: Redactor, address: object, port: int | None) -> str:
    if address is None:
        return "?"
    shown = redactor.address(str(address))
    return f"{shown}:{port}" if port else shown


def _window(now: datetime, hours: int | None) -> tuple[Window, int]:
    length = _between(hours, DEFAULT_HOURS, 1, MAX_HOURS)
    # The buckets are not used by the lookups: they only need a window to read.
    window = Window(
        "asked", now - timedelta(hours=length), now, timedelta(hours=1), timedelta(hours=1)
    )
    return window, length


def alerts(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """The latest alerts from the firewall, the intrusion detection systems and the agents."""
    window, hours = _window(now, args.hours)
    limit = _between(args.limit, 10, 1, MAX_ALERTS)
    events = recent_alerts(db, window, limit)
    if not events:
        return Found(
            [f"There were no alerts in the last {_plural(hours, 'hour')}."],
            [],
            f"no alerts in {_plural(hours, 'hour')}",
        )
    lines = [
        f"{event.occurred_at:{WHEN}} {event.source} {_severity(event.severity)}: "
        f"{redactor.text(event.signature or event.summary, 200)} "
        f"{_end(redactor, event.src_address, event.src_port)} -> "
        f"{_end(redactor, event.dst_address, event.dst_port)}"
        for event in events
    ]
    return Found(lines, [], f"{_plural(len(events), 'alert')} in {_plural(hours, 'hour')}")


def blocked_sources(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """The addresses the firewall turned away most, and how many connections of each."""
    window, hours = _window(now, args.hours)
    limit = _between(args.limit, 5, 1, MAX_ITEMS)
    sources = top_blocked_sources(db, window, limit)
    if not sources:
        return Found(
            [f"The firewall blocked nothing in the last {_plural(hours, 'hour')}."],
            [],
            f"nothing blocked in {_plural(hours, 'hour')}",
        )
    lines = [
        f"{redactor.address(str(item.address))}: {_plural(item.count, 'connection')} blocked"
        for item in sources
    ]
    return Found(lines, [], f"{_plural(len(sources), 'blocked address', 'blocked addresses')}")


# -- devices


def _device_filter(redactor: Redactor, name: str) -> ColumnElement[bool]:
    """Which devices a name means: an address or a hardware address, or part of a name or a
    maker's name. The model only ever saw stand-ins, so they are turned back first."""
    wanted = redactor.reveal(name).strip()
    address = read_address(wanted)
    if address is not None:
        return Device.id.in_(
            select(DeviceAddress.device_id).where(DeviceAddress.address == address)
        )
    mac = read_mac(wanted)
    if mac is not None:
        return Device.mac == mac
    # A % or a _ is part of a name, not a wildcard, so neither is searched for.
    plain = wanted.replace("%", "").replace("_", "")
    if not plain:
        return false()
    like = f"%{plain}%"
    return or_(Device.hostname.ilike(like), Device.vendor.ilike(like))


def device(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """The devices on the home network that a name, an address or a maker matches."""
    if not args.name or not args.name.strip():
        return Found(["Name the device, or give its address."], [], "no device named")
    devices = db.scalars(
        select(Device)
        .where(_device_filter(redactor, args.name))
        .order_by(Device.last_seen_at.desc(), Device.id)
        .limit(MAX_DEVICES)
    ).all()
    if not devices:
        return Found(["No device on the home network matches that."], [], "no such device")
    lines: list[str] = []
    for found in devices:
        addresses = db.scalars(
            select(DeviceAddress.address)
            .where(DeviceAddress.device_id == found.id)
            .order_by(DeviceAddress.last_seen_at.desc())
            .limit(5)
        ).all()
        name = redactor.name(found.hostname) if found.hostname else "unnamed"
        maker = f", made by {redactor.text(found.vendor, 60)}" if found.vendor else ""
        where = ", ".join(redactor.address(str(address)) for address in addresses) or "none known"
        lines.append(
            f"{name} ({redactor.mac(str(found.mac))}){maker}; addresses: {where}; first seen "
            f"{_when(found.first_seen_at)}, last seen {_when(found.last_seen_at)}"
        )
    return Found(lines, [], _plural(len(devices), "device"))


# -- the integrations


def integrations(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """Whether each connected integration and its collectors are working, and what went wrong."""
    connections = db.scalars(
        select(IntegrationConnection).order_by(
            IntegrationConnection.integration, IntegrationConnection.connection
        )
    ).all()
    if not connections:
        return Found(["No integration is connected yet."], [], "no integrations")
    lines: list[str] = []
    refs: dict[str, Ref] = {}
    for connection in connections:
        known = INTEGRATIONS.get(connection.integration)
        name = known.name if known else connection.integration
        refs[connection.integration] = Ref("integration", connection.integration, name)
        state = f"last worked {_when(connection.last_success_at)}"
        if connection.last_error:
            state += f"; failing: {redactor.text(connection.last_error, 200)}"
        lines.append(
            f"[integration {connection.integration}] {name} ({connection.connection}): {state}"
        )
    failing = db.scalars(
        select(CollectorHealth)
        .where(CollectorHealth.consecutive_failures > 0)
        .order_by(CollectorHealth.integration, CollectorHealth.collector)
    ).all()
    lines += [
        f"collector {item.collector} of {item.integration}: failed {item.consecutive_failures} "
        f"times in a row: {redactor.text(item.last_error or 'no reason given', 200)}"
        for item in failing
    ]
    return Found(
        lines,
        list(refs.values()),
        f"{_plural(len(connections), 'integration')}, {len(failing)} collectors failing",
    )


TOOLS: Final[Sequence[Tool]] = (
    Tool(
        "open_incidents",
        "The incidents that still need someone, the most serious first. Uses: limit (1-10, "
        "default 5).",
        open_incidents,
    ),
    Tool(
        "incident",
        "Everything known about one incident: why AresGate is as sure as it is, the devices "
        "involved and its signals. Uses: id (the number in [incident N]).",
        incident,
    ),
    Tool(
        "alerts",
        "The latest alerts from the firewall, the intrusion detection systems and the agents. "
        "Uses: hours (1-168, default 24), limit (1-20, default 10).",
        alerts,
    ),
    Tool(
        "blocked_sources",
        "The addresses the firewall turned away most. Uses: hours (1-168, default 24), limit "
        "(1-10, default 5).",
        blocked_sources,
    ),
    Tool(
        "device",
        "Devices on the home network that a name, an address, a hardware address or a maker "
        "matches. Uses: name.",
        device,
    ),
    Tool(
        "integrations",
        "Whether each integration and its collectors are working, and what went wrong. Uses "
        "nothing.",
        integrations,
    ),
)
NAMES: Final = tuple(tool.name for tool in TOOLS)


def by_name(name: str) -> Tool | None:
    return next((tool for tool in TOOLS if tool.name == name), None)
