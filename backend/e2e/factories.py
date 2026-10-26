"""Makes extra records on demand, for a test that needs more than the baseline holds.

Each factory fills in whatever it isn't given, so a test only names what it cares about. They
work on any session, so the backend's own tests can use them too.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from ipaddress import ip_address
from typing import Literal, NamedTuple
from uuid import uuid4

from sqlalchemy.orm import Session

from app.collectors import registry
from app.collectors.base import Collector
from app.config import Settings
from app.devices.sighting import NewSighting
from app.devices.store import record as record_devices
from app.events.event import NewEvent, Severity
from app.events.store import record as record_events
from app.metrics.sample import NewSample
from app.metrics.store import record as record_samples
from app.models import CollectorHealth, SystemInfo, User
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
