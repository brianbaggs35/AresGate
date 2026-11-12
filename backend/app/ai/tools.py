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

from sqlalchemy import ColumnElement, and_, false, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.ai import triage
from app.ai.redaction import Redactor, read_address, read_mac
from app.assets import profile
from app.dashboard import IS_BLOCK, Window, noisy_signatures, recent_alerts, top_blocked_sources
from app.events.event import Severity
from app.incidents import cleanup, queries, verdicts
from app.incidents import names as dns_names
from app.incidents import trust as trust_words
from app.incidents.verdicts import MUTING
from app.integrations.registry import INTEGRATIONS
from app.intel import otx, overrides, virustotal
from app.intel import store as intel_store
from app.models import (
    Agent,
    AgentRun,
    AiTriage,
    CollectorHealth,
    Device,
    DeviceAddress,
    Event,
    Incident,
    IncidentChain,
    IntegrationConnection,
    IntelSubject,
    VerdictRule,
)

MAX_ITEMS: Final = 10
MAX_ALERTS: Final = 20
MAX_HOURS: Final = 168
DEFAULT_HOURS: Final = 24
MAX_DEVICES: Final = 5
WHEN: Final = "%Y-%m-%d %H:%M"
# The incidents that still need someone: not settled, and not quieted by the owner's verdicts.
ACTIVE: Final = ("open", "investigating")
# How many days before a window say what is usual, how many ports are looked at for a change, how
# many connections it takes to be a change, and how many times the usual counts as a jump.
BASELINE_DAYS: Final = 7
CHANGE_CANDIDATES: Final = 50
MIN_CHANGE: Final = 10
JUMP: Final = 3


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
    said = profile.for_devices(db, (found.id for found in devices))
    for found in devices:
        addresses = db.scalars(
            select(DeviceAddress.address)
            .where(DeviceAddress.device_id == found.id)
            .order_by(DeviceAddress.last_seen_at.desc())
            .limit(5)
        ).all()
        name = redactor.name(found.hostname) if found.hostname else "unnamed"
        maker = f", made by {redactor.text(found.vendor, 60)}" if found.vendor else ""
        what = profile.describe(said.get(found.id), redactor.text)
        where = ", ".join(redactor.address(str(address)) for address in addresses) or "none known"
        lines.append(
            f"{name} ({redactor.mac(str(found.mac))}){maker}{what}; addresses: {where}; first seen "
            f"{_when(found.first_seen_at)}, last seen {_when(found.last_seen_at)}"
        )
    return Found(lines, [], _plural(len(devices), "device"))


# -- the internet addresses


def _pulse_line(report: IntelSubject, shown: str) -> str:
    """What AlienVault OTX's pulses say of one address, in a line."""
    count = report.malicious + report.suspicious
    return (
        f"AlienVault OTX: {shown} is named by {count} pulses, {report.malicious} of them naming "
        f"malware, an adversary or an attack technique; OTX makes it {report.judgement}."
        if count
        else f"AlienVault OTX: no pulse names {shown}, which says little about it."
    )


def reputation(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """What VirusTotal has said of one address on the internet, if it has been asked about it, and
    what the owner has ruled of it, which stands over the report."""
    address = read_address(args.name or "")
    if address is None:
        return Found(["Give the address to look up, such as 203.0.113.7."], [], "no address given")
    shown = redactor.address(str(address))
    if not address.is_global:
        return Found(
            [f"{shown} isn't on the internet, so VirusTotal isn't asked about it."],
            [],
            f"{shown} isn't on the internet",
        )
    ruling = overrides.for_addresses(db, [address]).get(str(address))
    said: list[str] = []
    if ruling is not None:
        why = f": {redactor.text(ruling.note, 200)}" if ruling.note else "."
        said.append(
            f"The owner of the network has ruled {shown} {ruling.verdict}{why}"
            " That stands over what VirusTotal says."
        )
    pulses = intel_store.report_for(db, otx.PROVIDER, address)
    if pulses is not None:
        said.append(_pulse_line(pulses, shown))
    report = intel_store.report_for(db, virustotal.PROVIDER, address)
    if report is None:
        silent = (
            f"VirusTotal hasn't reported on {shown}: it hasn't been asked, or it has no report."
        )
        what = f"AlienVault OTX's report on {shown}, none from VirusTotal" if pulses else None
        return Found([*said, silent], [], what or f"no VirusTotal report on {shown}")
    total = report.malicious + report.suspicious + report.harmless + report.undetected
    owner = redactor.text(report.owner, 60) if report.owner else "unknown owner"
    lines = [
        *said,
        f"{shown}: {report.malicious} of {total} engines flag it as malicious, "
        f"{report.suspicious} as suspicious, {report.harmless} as harmless and "
        f"{report.undetected} found nothing.",
        f"Owner {owner}, country {report.country or 'unknown'}, community score "
        f"{report.reputation}, analysed {_when(report.analysed_at)}.",
    ]
    return Found(lines, [], f"VirusTotal's report on {shown}")


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


# -- what is new, noisy or repeated


def new_devices(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """The devices seen on the home network for the first time within some hours."""
    hours = _between(args.hours, DEFAULT_HOURS, 1, MAX_HOURS)
    limit = _between(args.limit, 5, 1, MAX_ITEMS)
    found = db.scalars(
        select(Device)
        .where(Device.first_seen_at >= now - timedelta(hours=hours))
        .order_by(Device.first_seen_at.desc(), Device.id)
        .limit(limit)
    ).all()
    if not found:
        return Found(
            [f"No new device appeared in the last {_plural(hours, 'hour')}."],
            [],
            f"no new devices in {_plural(hours, 'hour')}",
        )
    lines: list[str] = []
    for item in found:
        name = redactor.name(item.hostname) if item.hostname else "unnamed"
        maker = f", made by {redactor.text(item.vendor, 60)}" if item.vendor else ""
        addresses = db.scalars(
            select(DeviceAddress.address)
            .where(DeviceAddress.device_id == item.id)
            .order_by(DeviceAddress.last_seen_at.desc())
            .limit(3)
        ).all()
        where = ", ".join(redactor.address(str(address)) for address in addresses) or "none known"
        lines.append(
            f"{name} ({redactor.mac(str(item.mac))}){maker}; addresses: {where}; first seen "
            f"{_when(item.first_seen_at)}"
        )
    return Found(lines, [], _plural(len(found), "new device"))


def noisy_alerts(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """The alerts that were reported most, with how many different addresses sent and received
    them: what is only noise, and what is a campaign."""
    window, hours = _window(now, args.hours)
    limit = _between(args.limit, 5, 1, MAX_ITEMS)
    rows = noisy_signatures(db, window, limit)
    if not rows:
        return Found(
            [f"There were no alerts in the last {_plural(hours, 'hour')}."],
            [],
            f"no alerts in {_plural(hours, 'hour')}",
        )
    lines = [
        f"{row.source} {_severity(row.severity.value)}: "
        f"{redactor.text(row.signature or 'an alert with no name', 200)}, "
        f"{_plural(row.count, 'time')} from "
        f"{_plural(row.from_addresses, 'address', 'addresses')} to "
        f"{_plural(row.to_addresses, 'address', 'addresses')}"
        for row in rows
    ]
    return Found(lines, [], _plural(len(rows), "repeated alert"))


def targeted_ports(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """The ports on the home network that the firewall refused connections to most, and from how
    many addresses."""
    window, hours = _window(now, args.hours)
    limit = _between(args.limit, 5, 1, MAX_ITEMS)
    count = func.count().label("count")
    rows = db.execute(
        select(Event.dst_port, Event.protocol, count, func.count(Event.src_address.distinct()))
        .where(
            IS_BLOCK,
            Event.dst_port.is_not(None),
            Event.occurred_at >= window.start,
            Event.occurred_at < window.end,
        )
        .group_by(Event.dst_port, Event.protocol)
        .order_by(count.desc(), Event.dst_port)
        .limit(limit)
    ).all()
    if not rows:
        return Found(
            [f"The firewall refused nothing aimed at a port in the last {_plural(hours, 'hour')}."],
            [],
            f"no ports targeted in {_plural(hours, 'hour')}",
        )
    lines = [
        f"port {port}/{protocol or 'any'}: {_plural(total, 'connection')} refused from "
        f"{_plural(sources, 'address', 'addresses')}"
        for port, protocol, total, sources in rows
    ]
    return Found(lines, [], _plural(len(rows), "targeted port"))


def what_changed(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """What the firewall turned away that is not usual: the window asked for, compared with what
    the days before it were like. Says how much more, or less, was refused, which ports were
    aimed at much more than usual or never before, and how many addresses are new."""
    window, hours = _window(now, args.hours)
    limit = _between(args.limit, 5, 1, MAX_ITEMS)
    before = window.start - timedelta(days=BASELINE_DAYS)
    # How many windows of this length the days before it hold, to turn their count into a usual.
    windows = BASELINE_DAYS * 24 / hours

    def refused(start: datetime, end: datetime) -> ColumnElement[bool]:
        return and_(IS_BLOCK, Event.occurred_at >= start, Event.occurred_at < end)

    now_total = db.scalar(select(func.count()).where(refused(window.start, window.end))) or 0
    usual_total = (db.scalar(select(func.count()).where(refused(before, window.start))) or 0) / (
        windows
    )
    if now_total == 0 and usual_total == 0:
        return Found(
            [f"The firewall refused nothing in the last {_plural(hours, 'hour')}, or before."],
            [],
            "nothing refused, nothing usual",
        )
    lines = [
        f"In the last {_plural(hours, 'hour')} the firewall refused {now_total} connections; "
        f"in a window this long it usually refuses {_usual(usual_total)}."
    ]
    lines += _changed_ports(db, window, before, windows, limit)
    new_sources = db.scalar(
        select(func.count(Event.src_address.distinct())).where(
            refused(window.start, window.end),
            Event.src_address.is_not(None),
            Event.src_address.not_in(
                select(Event.src_address).where(
                    refused(before, window.start), Event.src_address.is_not(None)
                )
            ),
        )
    )
    lines.append(
        f"{_plural(new_sources or 0, 'address', 'addresses')} refused in this window had never "
        f"been refused in the {_plural(BASELINE_DAYS, 'day')} before."
    )
    return Found(lines, [], f"how the last {_plural(hours, 'hour')} compare with usual")


def _usual(count: float) -> str:
    return "fewer than 1" if count < 1 else f"{count:.0f}"


def _changed_ports(
    db: Session,
    window: Window,
    before: datetime,
    windows: float,
    limit: int,
) -> list[str]:
    """The ports aimed at much more than usual, or for the first time, the biggest jumps first."""
    count = func.count().label("count")
    now_rows = db.execute(
        select(Event.dst_port, Event.protocol, count)
        .where(
            IS_BLOCK,
            Event.dst_port.is_not(None),
            Event.occurred_at >= window.start,
            Event.occurred_at < window.end,
        )
        .group_by(Event.dst_port, Event.protocol)
        .order_by(count.desc())
        .limit(CHANGE_CANDIDATES)
    ).all()
    usual = {
        (port, protocol): total / windows
        for port, protocol, total in db.execute(
            select(Event.dst_port, Event.protocol, count)
            .where(
                IS_BLOCK,
                Event.dst_port.in_([row[0] for row in now_rows]),
                Event.occurred_at >= before,
                Event.occurred_at < window.start,
            )
            .group_by(Event.dst_port, Event.protocol)
        )
    }
    jumps: list[tuple[float, str]] = []
    for port, protocol, total in now_rows:
        typical = usual.get((port, protocol), 0.0)
        name = f"port {port}/{protocol or 'any'}"
        if typical == 0 and total >= MIN_CHANGE:
            jumps.append(
                (float(total), f"{name}: {_plural(total, 'connection')}, never refused before")
            )
        elif typical and total >= MIN_CHANGE and total / typical >= JUMP:
            jumps.append(
                (
                    total / typical,
                    f"{name}: {_plural(total, 'connection')}, {total / typical:.0f} times what "
                    f"is usual ({_usual(typical)})",
                )
            )
    jumps.sort(key=lambda item: -item[0])
    return [line for _, line in jumps[:limit]] or ["No port was aimed at much more than usual."]


def repeated_incidents(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """The open incidents that say the same thing about different subjects, which are probably one
    campaign or one noisy rule, and so are better dealt with together."""
    limit = _between(args.limit, 5, 1, MAX_ITEMS)
    count = func.count().label("count")
    groups = db.execute(
        select(Incident.title, count, func.min(Incident.severity), func.max(Incident.severity))
        .where(
            Incident.status.in_(ACTIVE),
            or_(Incident.verdict.is_(None), Incident.verdict.not_in(MUTING)),
        )
        .group_by(Incident.title)
        .having(count > 1)
        .order_by(count.desc(), Incident.title)
        .limit(limit)
    ).all()
    if not groups:
        return Found(["No open incidents repeat each other."], [], "no repeated incidents")
    lines: list[str] = []
    refs: list[Ref] = []
    for title, total, _low, high in groups:
        ids = db.scalars(
            select(Incident.id)
            .where(Incident.title == title, Incident.status.in_(ACTIVE))
            .order_by(Incident.id)
            .limit(MAX_ITEMS)
        ).all()
        refs += [Ref("incident", str(item), f"Incident {item}") for item in ids]
        lines.append(
            f'{_plural(total, "open incident")} say "{redactor.text(title, 160)}" (up to '
            f"{_severity(high)}): " + ", ".join(f"[incident {item}]" for item in ids)
        )
    return Found(lines, refs, _plural(len(groups), "repeated incident"))


def agent_findings(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """What each agent reported the last time it finished a run, so that one agent can build on
    the work of another. The words were written by a model, so they are redacted as any others."""
    limit = _between(args.limit, 5, 1, MAX_ITEMS)
    latest = (
        select(AgentRun)
        .ext(distinct_on(AgentRun.agent_id))
        .where(AgentRun.status == "succeeded")
        .order_by(AgentRun.agent_id, AgentRun.finished_at.desc())
        .subquery()
    )
    rows = db.execute(
        select(Agent.name, latest.c.finished_at, latest.c.summary, latest.c.findings)
        .join(latest, latest.c.agent_id == Agent.id)
        .order_by(latest.c.finished_at.desc())
        .limit(limit)
    ).all()
    if not rows:
        return Found(["No agent has finished a run yet."], [], "no agent findings")
    lines: list[str] = []
    for name, finished, summary, findings in rows:
        said = redactor.text(summary, 300) or "nothing"
        lines.append(f"{redactor.text(name, 80)}, {_when(finished)}: {said}")
        lines += [
            f"- {item.get('severity', 'info')}: {redactor.text(str(item.get('title', '')), 160)}"
            for item in findings[:MAX_ITEMS]
        ]
    return Found(lines, [], _plural(len(rows), "agent report"))


def cleanup_candidates(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """What could be tidied among the incidents: open ones that say the same thing, old quiet ones
    and ones the AI is sure are noise. Each has a key to name it by."""
    limit = _between(args.limit, 10, 1, MAX_ITEMS)
    found = cleanup.find(db, now)[:limit]
    if not found:
        return Found(["There is nothing to tidy."], [], "nothing to tidy")
    lines: list[str] = []
    refs: dict[int, Ref] = {}
    for item in found:
        ids = ", ".join(f"[incident {number}]" for number in item.incidents[:MAX_ITEMS])
        kept = f"; [incident {item.keep}] stays open" if item.keep is not None else ""
        lines.append(
            f"[candidate {item.key}] {item.kind}, {item.confidence} of 100 sure: "
            f"{redactor.text(item.title, 160)} would {item.action} {ids}{kept}"
        )
        for number in (*item.incidents[:MAX_ITEMS], *([item.keep] if item.keep else [])):
            refs.setdefault(number, Ref("incident", str(number), f"Incident {number}"))
    return Found(lines, list(refs.values()), _plural(len(found), "thing to tidy", "things to tidy"))


def who_is(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """What one address on the internet is called, by its reverse lookup (the name its owner gave
    it), and what kind of server that makes it. The name is public, so it is not redacted; the
    address is shown as the redactor shows it."""
    address = read_address(args.name or "")
    if address is None:
        return Found(["Give the address to look up, such as 203.0.113.7."], [], "no address given")
    shown = redactor.address(str(address))
    if not address.is_global:
        return Found(
            [f"{shown} isn't on the internet, so it has no name to look up."],
            [],
            f"{shown} isn't on the internet",
        )
    name = dns_names.lookup(db, [str(address)], now).get(str(address))
    if name is None:
        return Found(
            [f"{shown} has no name: its owner gave it no reverse record, or none could be asked."],
            [],
            f"no name for {shown}",
        )
    return Found(
        [f"{shown} is called {redactor.text(name, 253)} by its reverse DNS record."],
        [],
        f"the name of {shown}",
    )


# -- the attacks across two devices


def attack_chains(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """The attacks that crossed two devices: an exploit aimed at a device on the network, and the
    device calling out soon after. Each says which link is confirmed and which is a guess."""
    limit = _between(args.limit, 5, 1, MAX_ITEMS)
    found = list(
        db.scalars(
            select(IncidentChain)
            .where(IncidentChain.last_seen_at >= now - timedelta(days=7))
            .order_by(IncidentChain.last_seen_at.desc())
            .limit(limit)
        )
    )
    if not found:
        return Found(["No attack has been seen crossing two devices lately."], [], "no chains")
    lines: list[str] = []
    refs: list[Ref] = []
    for chain in found:
        steps = db.scalars(
            select(Incident).where(Incident.chain_id == chain.id).order_by(Incident.first_seen_at)
        )
        device = redactor.address(chain.device)
        sure = "confirmed" if chain.confirmed else "inferred, which is a guess"
        lines.append(f"[chain {chain.id}] an attack on {device}, {sure}, {chain.steps} steps:")
        for step in steps:
            why = redactor.text(step.chain_reason or "", 200)
            lines.append(
                f"- [incident {step.id}] {step.chain_role} ({step.chain_link}): "
                f"{redactor.text(step.title, 160)}. {why}"
            )
            refs.append(Ref("incident", str(step.id), f"Incident {step.id}"))
    return Found(lines, refs, _plural(len(found), "attack across two devices"))


# -- what the owner trusts


def trusted(db: Session, redactor: Redactor, args: Args, now: datetime) -> Found:
    """What the owner has said is safe, which stands over what any program says of it: each
    decision with how much it is trusted, why and how many signals it has kept from raising an
    alarm. Nothing is trusted unless the owner said so, so an agent can only point at it."""
    limit = _between(args.limit, 10, 1, MAX_ITEMS)
    found = list(
        db.scalars(
            select(VerdictRule)
            .where(VerdictRule.verdict.in_(MUTING))
            .order_by(VerdictRule.updated_at.desc(), VerdictRule.id.desc())
            .limit(limit)
        )
    )
    if not found:
        return Found(["The owner has not said that anything is safe."], [], "nothing is trusted")
    kept = verdicts.hits(db, [rule.id for rule in found])
    lines: list[str] = []
    for rule in found:
        applied = kept.get(rule.id, (0, None))[0]
        level = "safe" if rule.verdict == "not_suspicious" else "low priority"
        about = redactor.text(trust_words.about(rule), 200)
        why = f": {redactor.text(rule.note, 200)}" if rule.note else ""
        lines.append(
            f"[trust {rule.id}] {about} is trusted as {level}, applied to {applied} signals{why}"
        )
    return Found(lines, [], _plural(len(found), "trust decision"))


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
    Tool(
        "reputation",
        "What VirusTotal says of one address on the internet: how many security engines flag "
        "it, and who owns it. Uses: name, for the address.",
        reputation,
    ),
    Tool(
        "who_is",
        "What one address on the internet is called, by its reverse lookup, which shows what "
        "kind of server it is. Uses: name, for the address.",
        who_is,
    ),
    Tool(
        "trusted",
        "What the owner has said is safe, each with how much it is trusted, why and how many "
        "signals it has kept from raising an alarm. Uses: limit (1-10, default 10).",
        trusted,
    ),
    Tool(
        "attack_chains",
        "The attacks that crossed two devices: an exploit aimed at a device on the network and "
        "the device calling out soon after, with which links are confirmed and which are "
        "guesses. Uses: limit (1-10, default 5).",
        attack_chains,
    ),
    Tool(
        "new_devices",
        "Devices that appeared on the home network for the first time recently. Uses: hours "
        "(1-168, default 24), limit (1-10, default 5).",
        new_devices,
    ),
    Tool(
        "noisy_alerts",
        "The alerts reported most, with how many addresses sent and received them. Uses: hours "
        "(1-168, default 24), limit (1-10, default 5).",
        noisy_alerts,
    ),
    Tool(
        "targeted_ports",
        "The ports on the home network that the firewall refused most connections to, and from "
        "how many addresses. Uses: hours (1-168, default 24), limit (1-10, default 5).",
        targeted_ports,
    ),
    Tool(
        "what_changed",
        "What the firewall turned away that is not usual: how much more or less than the days "
        "before, which ports were aimed at much more than usual or for the first time, and how "
        "many addresses are new. Uses: hours (1-168, default 24), limit (1-10, default 5).",
        what_changed,
    ),
    Tool(
        "repeated_incidents",
        "Open incidents that say the same thing about different subjects, so are one campaign or "
        "one noisy rule. Uses: limit (1-10, default 5).",
        repeated_incidents,
    ),
    Tool(
        "agent_findings",
        "What the other agents reported the last time each one finished a run, with how serious "
        "each finding was. Uses: limit (1-10, default 5).",
        agent_findings,
    ),
    Tool(
        "cleanup_candidates",
        "What could be tidied among the incidents: open ones that say the same thing, old quiet "
        "ones, and ones the AI is sure are noise, each with a key. Uses: limit (1-10, default 10).",
        cleanup_candidates,
    ),
)


def names() -> tuple[str, ...]:
    """What each of the lookups is called, in the order they are listed."""
    return tuple(tool.name for tool in TOOLS)


def by_name(name: str) -> Tool | None:
    return next((tool for tool in TOOLS if tool.name == name), None)
