"""The owner's noise filters: how sure AresGate has to be of an incident before it asks about it,
and which signals are set aside without anyone having to say so, one verdict at a time.

A filtered signal is kept. It is listed in the incident's timeline, counted, and explained
("set aside because it was between two addresses on your network"), and it leaves what the
incident says of itself (its severity, its programs, its confidence) to the signals that are not
set aside, the way a signal the owner called low priority does. Nothing is deleted, and changing
a filter judges the incidents that are not over again (see ``engine.reapply``).

An incident too thin to ask about (see ``too_thin``) has its signals set aside the same way, and
a repeating scan or brute force is grouped with the gap the owner chose (see ``episode.Gaps``).

The owner's verdicts come first: a signal that a verdict is about is judged by it, even a real
threat, and is never also filtered. A ban is a program's decision that something was an attack,
so it is never filtered either.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_network
from typing import Final

from sqlalchemy import ColumnElement, cast, or_
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.events.event import Severity
from app.incidents import episode, rules
from app.incidents.subject import Signal
from app.models import IncidentSignal, NoiseSettings

# Why a signal was set aside.
INSIDE: Final = "inside"
SEVERITY: Final = "severity"
THIN: Final = "thin"
REASONS: Final = (INSIDE, SEVERITY, THIN)

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
# How long a scan or a brute force may go quiet before its next signal is a new incident, in
# hours, until the owner says otherwise (the engine's own: see ``episode.GAPS``).
DEFAULT_SCAN_GAP_HOURS: Final = 4
DEFAULT_BRUTE_FORCE_GAP_HOURS: Final = 6
MAX_GAP_HOURS: Final = 24
# The fewest signals an incident of one program's low-severity signals needs before it is asked
# about. One is no minimum at all, so every incident is asked about, as before this setting.
DEFAULT_THIN_LOW_SIGNALS: Final = 1
MAX_THIN_LOW_SIGNALS: Final = 10


@dataclass(frozen=True)
class Filters:
    """What the owner has set: the confidence floor, whether signals inside the network are set
    aside, the lowest severity that counts for the programs that have one, how long a scan or a
    brute force may go quiet, and the fewest signals an incident of low ones needs."""

    confidence_floor: int = DEFAULT_FLOOR
    quiet_inside: bool = False
    source_floors: Mapping[str, int] = field(default_factory=dict[str, int])
    scan_gap_hours: int = DEFAULT_SCAN_GAP_HOURS
    brute_force_gap_hours: int = DEFAULT_BRUTE_FORCE_GAP_HOURS
    thin_low_signals: int = DEFAULT_THIN_LOW_SIGNALS

    def gaps(self) -> episode.Gaps:
        """How long a scan or a brute force may go quiet, as the owner set it."""
        return episode.Gaps(
            scan=timedelta(hours=self.scan_gap_hours),
            brute_force=timedelta(hours=self.brute_force_gap_hours),
        )


def load(db: Session) -> Filters:
    """The filters as they are saved, or the defaults where nothing has been."""
    row = db.get(NoiseSettings, 1)
    if row is None:
        return Filters()
    return Filters(
        confidence_floor=row.confidence_floor,
        quiet_inside=row.quiet_inside,
        source_floors=dict(row.source_floors),
        scan_gap_hours=row.scan_gap_hours,
        brute_force_gap_hours=row.brute_force_gap_hours,
        thin_low_signals=row.thin_low_signals,
    )


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
    row.scan_gap_hours = noise.scan_gap_hours
    row.brute_force_gap_hours = noise.brute_force_gap_hours
    row.thin_low_signals = noise.thin_low_signals
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


def too_thin(signals: Sequence[IncidentSignal], minimum: int) -> bool:
    """Whether an incident is too thin to ask about: what its verdicts and the other filters leave
    of it is one program's low-severity signals, and fewer than ``minimum`` of them are not
    duplicates. An incident with a verdict on any of its signals is never thin: the owner has
    looked at it, and a verdict outranks a filter."""
    if minimum <= 1 or any(signal.verdict is not None for signal in signals):
        return False
    left = [signal for signal in signals if signal.filtered_by is None]
    return (
        len({signal.source for signal in left}) == 1
        and all(signal.severity == Severity.LOW for signal in left)
        and sum(not signal.duplicate for signal in left) < minimum
    )
