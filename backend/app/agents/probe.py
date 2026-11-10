"""Testing the devices on the home network for services that should not be open.

This is the one thing an agent does that reaches out: it opens a connection to a short list of
risky ports on the devices AresGate has seen lately, and notes which answer. That is all it does.
It sends nothing down the connection, reads nothing from it and closes it at once, so it is the
same as asking whether a door is locked, not trying to open it.

It is kept to the owner's own network by the same rule as every integration: only the private
address ranges are reachable (``netguard.HOME_NETWORK``), never the internet, never a cloud
metadata address. It only ever tests devices AresGate already knows, so it can't be pointed at an
address by whoever can write to an agent. And it only runs for an agent the owner has allowed to,
for a run the owner started.
"""

import socket
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from ipaddress import IPv4Address
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import netguard
from app.integrations.netguard import AddressPolicy
from app.models import Device, DeviceAddress

# How long ago a device may have been last seen to be tested, how many are tested in one run, how
# long a connection is waited for, and how many are tried at once.
SEEN_WITHIN: Final = timedelta(days=7)
MAX_HOSTS: Final = 32
TIMEOUT: Final = 0.8
WORKERS: Final = 16

# How serious a service that answers is, most serious first.
SEVERITIES: Final = ("critical", "high", "medium", "low", "info")


@dataclass(frozen=True)
class Service:
    """What listens on a port, how much it matters that it is open to the home network, and why."""

    name: str
    severity: str
    why: str


PORTS: Final[Mapping[int, Service]] = {
    21: Service("FTP", "high", "It sends passwords and files without encryption."),
    22: Service("SSH", "info", "Remote login. Fine if you use it; keep it to keys, not passwords."),
    23: Service(
        "Telnet",
        "critical",
        "A remote login that sends everything, passwords included, in the clear.",
    ),
    80: Service("HTTP", "info", "A web page without encryption. Normal for a router or printer."),
    139: Service(
        "NetBIOS", "medium", "Windows file sharing. Old, and rarely needed on a home network."
    ),
    445: Service("SMB", "medium", "Windows file sharing. Keep it to the machines that need it."),
    554: Service("RTSP", "medium", "A camera's video stream, often with a weak or default login."),
    1883: Service("MQTT", "medium", "Smart home messages, usually with no login."),
    3306: Service(
        "MySQL", "high", "A database that should be reached by one application, not the network."
    ),
    3389: Service(
        "Remote Desktop", "high", "A whole desktop to log in to, a favourite of attackers."
    ),
    5432: Service("PostgreSQL", "high", "A database that should be reached by one application."),
    5900: Service("VNC", "high", "A remote screen that is often weakly protected."),
    6379: Service("Redis", "critical", "A database with no login unless one was set up."),
    9200: Service(
        "Elasticsearch", "high", "A search database with no login unless one was set up."
    ),
    27017: Service("MongoDB", "critical", "A database with no login unless one was set up."),
}


@dataclass(frozen=True)
class Target:
    """A device to test, at the address it was last seen at."""

    device_id: int
    name: str | None
    address: str

    @property
    def label(self) -> str:
        return f"{self.name} ({self.address})" if self.name else self.address


@dataclass(frozen=True)
class Hit:
    """A port that answered."""

    target: Target
    port: int
    service: Service


@dataclass(frozen=True)
class Scan:
    """What a test found: how many devices were tested, how many more there were than the limit,
    and the ports that answered, the most serious first."""

    tested: int
    left_out: int
    hits: list[Hit]


def targets(db: Session, now: datetime, policy: AddressPolicy) -> tuple[list[Target], int]:
    """The devices to test: the ones seen lately, the most recently seen first, each at its latest
    address that the policy reaches. Gives back how many there were past the limit."""
    rows = db.execute(
        select(Device.id, Device.hostname, DeviceAddress.address)
        .join(DeviceAddress, DeviceAddress.device_id == Device.id)
        .where(Device.last_seen_at >= now - SEEN_WITHIN)
        .order_by(Device.last_seen_at.desc(), Device.id, DeviceAddress.last_seen_at.desc())
    ).all()
    found: dict[int, Target] = {}
    taken: set[str] = set()
    for device_id, name, address in rows:
        if device_id in found or not isinstance(address, IPv4Address) or not policy.allows(address):
            continue
        # An address that passed from one device to another is tested once.
        if str(address) in taken:
            continue
        taken.add(str(address))
        found[device_id] = Target(device_id, name, str(address))
    chosen = list(found.values())
    return chosen[:MAX_HOSTS], max(0, len(chosen) - MAX_HOSTS)


def connects(address: str, port: int, timeout: float) -> bool:
    """Whether something accepts a connection there. The connection is closed at once."""
    try:
        with socket.create_connection((address, port), timeout=timeout):
            return True
    except OSError:
        return False


def scan(
    db: Session,
    now: datetime,
    *,
    policy: AddressPolicy = netguard.HOME_NETWORK,
    ports: Mapping[int, Service] = PORTS,
    connect: Callable[[str, int, float], bool] = connects,
) -> Scan:
    """Tests each device on each port, a few at a time, and gives back what answered."""
    chosen, left_out = targets(db, now, policy)
    pairs = [(target, port) for target in chosen for port in ports]

    def try_one(pair: tuple[Target, int]) -> bool:
        return connect(pair[0].address, pair[1], TIMEOUT)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        answers = list(pool.map(try_one, pairs))
    hits = [
        Hit(target, port, ports[port])
        for (target, port), answered in zip(pairs, answers, strict=True)
        if answered
    ]
    hits.sort(
        key=lambda hit: (SEVERITIES.index(hit.service.severity), hit.target.address, hit.port)
    )
    return Scan(len(chosen), left_out, hits)


def line(hit: Hit) -> str:
    return f"{hit.target.label}: port {hit.port} ({hit.service.name}) is open. {hit.service.why}"


def summary(found: Scan) -> str:
    """What a test found, in a few words with no name or address in them."""
    devices = f"{found.tested} device{'' if found.tested == 1 else 's'}"
    if not found.hits:
        return f"tested {devices}, nothing risky answered"
    return f"tested {devices}, {len(found.hits)} open port{'' if len(found.hits) == 1 else 's'}"
