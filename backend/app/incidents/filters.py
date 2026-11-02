"""The owner's noise filters: how sure AresGate has to be of an incident before it asks about it,
and which signals are set aside without anyone having to say so, one verdict at a time.

A filtered signal is kept. It is listed in the incident's timeline, counted, and explained
("set aside because it was between two addresses on your network"), and it leaves what the
incident says of itself (its severity, its programs, its confidence) to the signals that are not
set aside, the way a signal the owner called low priority does. Nothing is deleted, and changing
a filter judges the incidents that are not over again (see ``engine.reapply``).

The owner's verdicts come first: a signal that a verdict is about is judged by it, even a real
threat, and is never also filtered. A ban is a program's decision that something was an attack,
so it is never filtered either.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_network
from typing import Final

from sqlalchemy import ColumnElement, cast, or_
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.events.event import Severity
from app.incidents import rules
from app.incidents.subject import Signal
from app.models import NoiseSettings

# Why a signal was set aside.
INSIDE: Final = "inside"
SEVERITY: Final = "severity"
REASONS: Final = (INSIDE, SEVERITY)

# The addresses that are on a network of the owner's, or can't be anywhere else: private, shared
# (carrier-grade NAT), link-local and unique local ones. The dashboard's noise report counts the
# same ones.
NETWORKS: Final = (
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "100.64.0.0/10",
    "169.254.0.0/16",
    "fc00::/7",
    "fe80::/10",
)
_PARSED: Final[tuple[IPv4Network | IPv6Network, ...]] = tuple(ip_network(net) for net in NETWORKS)

# How sure AresGate has to be of an incident for it to be asked about, until the owner says.
DEFAULT_FLOOR: Final = rules.MEDIUM_FROM
# The severities a program's floor can be: the engine reads nothing below low.
FLOOR_SEVERITIES: Final = (Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)


@dataclass(frozen=True)
class Filters:
    """What the owner has set: the confidence floor, whether signals inside the network are set
    aside, and the lowest severity that counts for the programs that have one."""

    confidence_floor: int = DEFAULT_FLOOR
    quiet_inside: bool = False
    source_floors: Mapping[str, int] = field(default_factory=dict[str, int])


def load(db: Session) -> Filters:
    """The filters as they are saved, or the defaults where nothing has been."""
    row = db.get(NoiseSettings, 1)
    if row is None:
        return Filters()
    return Filters(row.confidence_floor, row.quiet_inside, dict(row.source_floors))


def save(db: Session, noise: Filters) -> bool:
    """Keeps the filters as they are given, and says whether that changed them. The caller
    commits, after judging the incidents again (``engine.reapply``)."""
    if noise == load(db):
        return False
    row = db.get(NoiseSettings, 1)
    if row is None:
        row = NoiseSettings(id=1)
        db.add(row)
    row.confidence_floor = noise.confidence_floor
    row.quiet_inside = noise.quiet_inside
    row.source_floors = dict(noise.source_floors)
    db.flush()
    return True


def inside(address: IPv4Address | IPv6Address | None) -> bool:
    """Whether an address is one that can only be on a network of the owner's."""
    return address is not None and any(
        address in net for net in _PARSED if net.version == address.version
    )


def inside_clause(
    column: InstrumentedAttribute[IPv4Address | IPv6Address | None],
) -> ColumnElement[bool]:
    """``inside`` as SQL, for counting what an address column holds that is on the owner's own
    network."""
    return or_(*(column.op("<<=")(cast(net, INET)) for net in NETWORKS))


def judge(signal: Signal, filters: Filters) -> str | None:
    """Why a signal is set aside by the filters, or None if they leave it alone."""
    if signal.kind == "decision":
        return None
    floor = filters.source_floors.get(signal.source)
    if floor is not None and signal.severity < floor:
        return SEVERITY
    if filters.quiet_inside and inside(signal.src_address) and inside(signal.dst_address):
        return INSIDE
    return None
