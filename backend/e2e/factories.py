"""Makes extra records on demand, for a test that needs more than the baseline holds.

Each factory fills in whatever it isn't given, so a test only names what it cares about. They
work on any session, so the backend's own tests can use them too.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from ipaddress import ip_address
from typing import Any, Literal, NamedTuple
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors import registry
from app.collectors.base import Collector
from app.config import Settings
from app.devices.sighting import NewSighting
from app.devices.store import record as record_devices
from app.events.event import NewEvent, Severity
from app.events.store import record as record_events
from app.incidents import engine as incident_engine
from app.metrics.sample import NewSample
from app.metrics.store import record as record_samples
from app.models import CollectorHealth, Incident, SystemInfo, User, VerdictRule
from app.security import passwords
from app.security.accounts import normalize_username

DEFAULT_VALUE = "an e2e value"
DEFAULT_PASSWORD = "an e2e password for testing"  # nosec B105: made up, for test accounts


def system_info(
    session: Session, *, key: str | None = None, value: str = DEFAULT_VALUE
) -> SystemInfo:
    row = SystemInfo(key=key or f"factory-{uuid4().hex[:8]}", value=value)
    session.add(row)
    session.flush()
    return row


def account(
    session: Session, *, username: str | None = None, password: str = DEFAULT_PASSWORD
) -> User:
    user = User(
        username=normalize_username(username or f"factory-{uuid4().hex[:8]}"),
        password_hash=passwords.hash_password(password),
    )
    session.add(user)
    session.flush()
    return user


# Where the alerts of `activity` say they came from, one after the other.
_ALERT_SOURCES = ("wazuh", "opnsense", "ntopng")
# How often the interfaces' counters are read, and how far back.
_READ_EVERY = timedelta(minutes=5)
_READINGS = 37


class Recorded(NamedTuple):
    """How much `activity` stored."""

    alerts: int
    blocked: int
    samples: int
    devices: int
    collectors: int


CollectorState = Literal["waiting", "ok", "problem", "late"]


def activity(
    session: Session,
    settings: Settings,
    now: datetime,
    *,
    alerts: Mapping[Severity, int],
    blocked: Mapping[str, int],
    traffic: Mapping[str, float],
    devices: int,
    collectors: Sequence[CollectorState],
) -> Recorded:
    """Stores what the dashboard shows, as of ``now`` and the hours before it: that many alerts
    of each severity (from Wazuh, OPNsense and ntopng in turn, a few minutes apart, the most
    serious first), that many connections the firewall refused from each address, a steady
    speed in megabits a second for each interface of the firewall over the last three hours,
    that many devices seen for the first time half an hour ago, and a collector of the firewall
    in each of the states given."""
    events = [
        _alert(severity, number, now)
        for number, severity in enumerate(
            (level for level, count in sorted(alerts.items(), reverse=True) for _ in range(count)),
            start=1,
        )
    ]
    refused = [
        _refusal(address, number, now)
        for address, count in blocked.items()
        for number in range(count)
    ]
    samples = [
        sample
        for interface, megabits in traffic.items()
        for sample in _readings(interface, megabits, now)
    ]
    sightings = [_sighting(number, now) for number in range(devices)]
    record_events(session, settings, [*events, *refused], now)
    record_samples(session, settings, samples, now)
    record_devices(session, sightings, now)
    jobs = _FIREWALL_JOBS[: len(collectors)]
    rows = [_collector(job, state, now) for job, state in zip(jobs, collectors, strict=True)]
    session.add_all(rows)
    return Recorded(len(events), len(refused), len(samples), len(sightings), len(rows))


# The jobs that read from a firewall, which `activity` gives a record of how each is doing.
_FIREWALL_JOBS = [item for item in registry.COLLECTORS if item.reads("opnsense", "api")]


def _collector(job: Collector, state: CollectorState, now: datetime) -> CollectorHealth:
    """A collector's record as it is in that state: not run yet, working, failed on its last
    run, or not run for much longer than it should."""
    row = CollectorHealth(
        collector=job.key,
        integration="opnsense",
        connection="api",
        interval_seconds=int(job.interval.total_seconds()),
    )
    if state == "waiting":
        return row
    ran = now - (timedelta(hours=1) if state == "late" else timedelta(minutes=1))
    row.last_started_at = row.last_finished_at = row.last_success_at = ran
    row.last_duration_ms = 120
    row.next_run_at = ran + job.interval
    if state == "problem":
        row.consecutive_failures = 1
        row.last_error = "The firewall didn't answer."
    return row


def _alert(severity: Severity, number: int, now: datetime) -> NewEvent:
    return NewEvent(
        source=_ALERT_SOURCES[number % len(_ALERT_SOURCES)],
        connection="e2e",
        kind="alert",
        severity=severity,
        occurred_at=now - timedelta(minutes=4 * number),
        identity=(f"e2e-alert-{number}",),
        summary=f"{severity.name.capitalize()} alert {number}",
        signature=f"e2e.{severity.name.lower()}",
        src_address="198.51.100.20",
        dst_address="192.168.1.20",
    )


def _refusal(address: str, number: int, now: datetime) -> NewEvent:
    return NewEvent(
        source="opnsense",
        connection="api",
        kind="firewall",
        severity=Severity.LOW,
        occurred_at=now - timedelta(minutes=3 * (number + 1)),
        identity=(f"e2e-refused-{address}-{number}",),
        summary=f"Blocked from {address}",
        src_address=address,
    )


def _readings(interface: str, megabits: float, now: datetime) -> list[NewSample]:
    """The counters of an interface, read every five minutes, rising so that it received
    ``megabits`` a second and sent a quarter of that."""
    received_per_second = megabits * 1_000_000 / 8
    readings: list[NewSample] = []
    for number in range(_READINGS):
        at = now - _READ_EVERY * (_READINGS - 1 - number)
        elapsed = (_READ_EVERY * number).total_seconds()
        for name, rate in (
            ("interface.bytes_in", received_per_second),
            ("interface.bytes_out", received_per_second / 4),
        ):
            readings.append(
                NewSample(
                    source="opnsense",
                    connection="api",
                    name=name,
                    value=1_000_000_000 + rate * elapsed,
                    sampled_at=at,
                    labels={"interface": interface},
                )
            )
    return readings


def _sighting(number: int, now: datetime) -> NewSighting:
    return NewSighting(
        mac=f"02:00:00:00:00:{number + 1:02x}",
        seen_at=now - timedelta(minutes=30),
        address=ip_address(f"192.168.1.{number + 10}"),
        hostname=f"e2e-device-{number + 1}",
    )


# Public addresses for attackers, in turn: the documentation ranges are not outside the network
# as far as the engine is concerned.
_ATTACKERS = ("93.184.216.34", "8.8.8.8", "1.1.1.1", "9.9.9.9", "208.67.222.222")
# What the programs that saw an attack call themselves, and how each reports a signal.
_CONNECTIONS = {"wazuh": "indexer", "opnsense": "api", "crowdsec": "lapi", "ntopng": "api"}
IncidentStatusName = Literal["open", "investigating", "resolved", "dismissed"]


class IncidentSpec(NamedTuple):
    """An attack for `incidents` to store: what the programs saw of it, and when."""

    # Where it came from; the next of a few public addresses when None.
    address: str | None = None
    severity: Severity = Severity.HIGH
    # Who saw it, in turn: the signals are shared between them.
    programs: Sequence[str] = ("wazuh",)
    signals: int = 1
    # Whether CrowdSec banned the address afterwards, and the time it said was left of the ban
    # when it was first read (a Go duration; none given when empty).
    ban: bool = False
    ban_left: str = "3h59m12s"
    # How many times the firewall turned the address away before the ban and after it, and how
    # many alerts Suricata stopped.
    blocks: int = 0
    blocks_after_ban: int = 0
    dropped: int = 0
    # How long ago the last signal was.
    minutes_ago: int = 10
    # The device on the network that was attacked, and what it is called when it is known.
    device: str = "192.168.1.20"
    device_name: str | None = None
    status: IncidentStatusName = "open"
    # A bot sweeping the network: every signal is a port scan, from the address and this many of
    # its neighbours in turn (they must stay in the address's /24), over as many bursts.
    neighbours: int = 0
    waves: int = 1
    # The ports the signals touch, in turn; only the ssh port when empty.
    ports: Sequence[int] = ()
    scan: bool = False


class IncidentsRecorded(NamedTuple):
    """How much `incidents` stored."""

    signals: int
    incidents: int


def incidents(
    session: Session, settings: Settings, now: datetime, specs: Sequence[IncidentSpec]
) -> IncidentsRecorded:
    """Stores the alerts of each attack the way the programs would have, a few minutes apart
    and ending ``minutes_ago`` before ``now``, a device for each that has a name, and runs the
    engine that files them into incidents, as the worker does every half minute."""
    events: list[NewEvent] = []
    sightings: list[NewSighting] = []
    addresses = [
        spec.address or _ATTACKERS[number % len(_ATTACKERS)] for number, spec in enumerate(specs)
    ]
    for number, (spec, address) in enumerate(zip(specs, addresses, strict=True)):
        events.extend(_attack(number, address, spec, now))
        if spec.device_name:
            sightings.append(
                NewSighting(
                    mac=f"02:00:00:00:10:{number + 1:02x}",
                    seen_at=now - timedelta(hours=1),
                    address=ip_address(spec.device),
                    hostname=spec.device_name,
                    vendor="E2E Devices",
                )
            )
    # Stored a minute ago, so that the engine reads them as settled.
    record_events(session, settings, events, now - timedelta(minutes=1))
    record_devices(session, sightings, now)
    session.flush()
    incident_engine.correlate(session, now)
    session.flush()
    for spec, address in zip(specs, addresses, strict=True):
        if spec.status != "open":
            row = session.scalars(select(Incident).where(Incident.subject == address)).one()
            row.status = spec.status
            row.status_changed_at = now
    return IncidentsRecorded(len(events), len(specs))


# How far apart the signals of a burst are, and how much quiet there is between two bursts: more
# than the engine's quarter of an hour, and less than any gap that would start another incident.
_STEP = timedelta(minutes=4)
_QUIET = timedelta(minutes=40)


def _attack(number: int, address: str, spec: IncidentSpec, now: datetime) -> list[NewEvent]:
    """The signals of one attack: the first and worst as serious as asked, the rest a level or
    two below, then the ban. A scan is all one kind of signal, spread as asked."""
    last = now - timedelta(minutes=spec.minutes_ago)
    # The signals are shared between the bursts, the last of which ends at ``last``.
    per_wave = -(-spec.signals // spec.waves)
    gap = _STEP * (per_wave - 1) + _QUIET
    events: list[NewEvent] = []
    for signal in range(spec.signals):
        program = spec.programs[signal % len(spec.programs)]
        wave, place = divmod(signal, per_wave)
        later_waves = (spec.signals - 1) // per_wave - wave
        later_in_wave = min(per_wave, spec.signals - wave * per_wave) - 1 - place
        source = str(ip_address(address) + signal % (spec.neighbours + 1))
        port = spec.ports[signal % len(spec.ports)] if spec.ports else 22
        # The first is the strongest; the others are medium, or low once that is the strongest.
        severity = spec.severity if signal == 0 else min(spec.severity, Severity.MEDIUM)
        events.append(
            NewEvent(
                source=program,
                connection=_CONNECTIONS.get(program, "e2e"),
                kind="alert",
                severity=severity,
                occurred_at=last - gap * later_waves - _STEP * later_in_wave,
                identity=(f"e2e-incident-{number}-{signal}",),
                summary=f"{program.capitalize()} saw {source} try ssh",
                signature="ET SCAN Potential SSH Scan"
                if spec.scan or signal > 0
                else "Brute force on ssh",
                src_address=source,
                src_port=40_000 + signal,
                dst_address=spec.device,
                dst_port=port,
                protocol="tcp",
            )
        )
    banned_at = last + timedelta(seconds=30)
    if spec.ban:
        events.append(_ban(number, address, spec.ban_left, banned_at))
    events.extend(
        _turned_away(number, address, "before", last - timedelta(seconds=10 * (place + 1)), place)
        for place in range(spec.blocks)
    )
    events.extend(
        _turned_away(
            number, address, "after", banned_at + timedelta(seconds=15 * (place + 1)), place
        )
        for place in range(spec.blocks_after_ban)
    )
    events.extend(
        _stopped(number, address, spec.device, last - timedelta(seconds=5 * (place + 1)), place)
        for place in range(spec.dropped)
    )
    return events


def _ban(number: int, address: str, left: str, at: datetime) -> NewEvent:
    """CrowdSec's ban of an address, as its collector keeps it: dated by the minute it was read."""
    return NewEvent(
        source="crowdsec",
        connection="lapi",
        kind="decision",
        severity=Severity.LOW,
        occurred_at=at,
        identity=(f"e2e-incident-{number}-ban",),
        summary=f"Ban {address} for {left}: crowdsecurity/ssh-bf" if left else f"Ban {address}",
        signature="crowdsecurity/ssh-bf",
        src_address=address,
        raw={
            "id": number + 1,
            "origin": "crowdsec",
            "type": "ban",
            "scope": "Ip",
            "value": address,
            "scenario": "crowdsecurity/ssh-bf",
            **({"duration": left} if left else {}),
        },
    )


def _turned_away(number: int, address: str, when: str, at: datetime, place: int) -> NewEvent:
    return NewEvent(
        source="opnsense",
        connection="api",
        kind="firewall",
        severity=Severity.LOW,
        occurred_at=at,
        identity=(f"e2e-incident-{number}-block-{when}-{place}",),
        summary=f"Blocked tcp {address}",
        src_address=address,
        protocol="tcp",
    )


def _stopped(number: int, address: str, device: str, at: datetime, place: int) -> NewEvent:
    """An alert that Suricata stopped, as the firewall's collector keeps it."""
    return NewEvent(
        source="opnsense",
        connection="api",
        kind="alert",
        severity=Severity.LOW,
        occurred_at=at,
        identity=(f"e2e-incident-{number}-dropped-{place}",),
        summary=f"ET SCAN Potential SSH Scan (blocked): tcp {address} to {device}:22",
        signature="ET SCAN Potential SSH Scan",
        src_address=address,
        dst_address=device,
        dst_port=22,
        protocol="tcp",
        raw={"alert_action": "blocked"},
    )


class EventSpec(NamedTuple):
    """An event for `events` to store, as a program would have reported it."""

    source: str = "opnsense"
    connection: str | None = None
    kind: str = "firewall"
    severity: Severity = Severity.INFO
    summary: str = "Blocked tcp"
    signature: str | None = None
    src_address: str | None = None
    src_port: int | None = None
    dst_address: str | None = None
    dst_port: int | None = None
    protocol: str | None = None
    # How long ago the last of them happened.
    seconds_ago: int = 60
    # The program's own record of it, when it has one.
    raw: Mapping[str, Any] | None = None
    # How many to make, that far apart (the first of them the oldest).
    repeat: int = 1
    every_seconds: int = 30


def events(session: Session, settings: Settings, now: datetime, specs: Sequence[EventSpec]) -> int:
    """Stores events as of now, for the Logs page to show, and returns how many. They are not
    filed into incidents."""
    stored: list[NewEvent] = []
    for number, spec in enumerate(specs):
        for place in range(spec.repeat):
            behind = spec.every_seconds * (spec.repeat - 1 - place)
            stored.append(
                NewEvent(
                    source=spec.source,
                    connection=spec.connection or _CONNECTIONS.get(spec.source, "e2e"),
                    kind=spec.kind,
                    severity=spec.severity,
                    occurred_at=now - timedelta(seconds=spec.seconds_ago + behind),
                    identity=(f"e2e-event-{number}-{place}",),
                    summary=spec.summary,
                    signature=spec.signature,
                    src_address=spec.src_address,
                    src_port=spec.src_port,
                    dst_address=spec.dst_address,
                    dst_port=spec.dst_port,
                    protocol=spec.protocol,
                    raw=spec.raw,
                )
            )
    record_events(session, settings, stored, now)
    return len(stored)


class VerdictSpec(NamedTuple):
    """A verdict for `verdicts` to give: what it says and what it is about."""

    verdict: Literal["not_suspicious", "low_priority", "threat"]
    address: str | None = None
    source: str | None = None
    signature: str | None = None
    note: str | None = None


def verdicts(session: Session, specs: Sequence[VerdictSpec]) -> int:
    """Gives the verdicts the way the Settings page does, and judges the incidents that are
    there by them, so that the order a test makes incidents and verdicts in doesn't matter."""
    for spec in specs:
        session.add(
            VerdictRule(
                verdict=spec.verdict,
                address=ip_address(spec.address) if spec.address else None,
                source=spec.source,
                signature=spec.signature,
                note=spec.note,
            )
        )
    session.flush()
    incident_engine.reapply(session)
    return len(specs)
