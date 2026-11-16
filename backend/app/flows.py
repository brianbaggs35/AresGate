"""Where the traffic on the network goes, as the firewall's log tells it: who connected, to which
service and to where, and how much of it was refused.

The connections are the firewall events that name both ends (a pass, which the firewall logs when
it is told to, and a block). They are counted, not measured: an event is one connection the
firewall wrote down, not a number of bytes. Each is read as a path through three columns, the
address that connected, the service it asked for (protocol and port) and the address it reached,
and the paths are added up so that the busiest are drawn and the rest are folded into one
"others" in each column.
"""

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address
from typing import Final, Literal

from sqlalchemy import Interval, case, func, literal, literal_column, select
from sqlalchemy.orm import Session

from app.events.event import Severity
from app.models import AddressName, Event

Address = IPv4Address | IPv6Address
Direction = Literal["all", "outgoing", "incoming", "inside"]
Column = Literal["source", "service", "destination"]
Scope = Literal["local", "outside"]
COLUMNS: Final[tuple[Column, ...]] = ("source", "service", "destination")

# The windows that can be asked for, in hours, and how wide each bar of the timeline is for them.
HOURS: Final = (1, 6, 24, 168)
STRIDE: Final = {
    1: timedelta(minutes=5),
    6: timedelta(minutes=15),
    24: timedelta(hours=1),
    168: timedelta(hours=6),
}
# How many different paths are read: the busiest, so a network that is scanned all week has more
# than anyone could draw, and the picture says it was cut.
MAX_PATHS: Final = 5000
# How many nodes each column draws before the rest are folded into one.
SHOWN: Final[dict[Column, int]] = {"source": 8, "service": 6, "destination": 8}
OTHERS: Final = "others"


@dataclass(frozen=True)
class Node:
    """One block in a column: an address or a service, and the connections through it."""

    id: str
    column: Column
    label: str
    # For an address, what its reverse lookup said if one is kept, and which side of the firewall
    # it is on; for a service, its protocol and port (0 where it has none).
    name: str | None
    scope: Scope | None
    protocol: str | None
    port: int | None
    events: int
    blocked: int
    # How many nodes are folded into this one, for "others".
    folded: int


@dataclass(frozen=True)
class Link:
    """The connections that went from one node to the next, and how many were refused."""

    source: str
    target: str
    events: int
    blocked: int


@dataclass(frozen=True)
class Bar:
    """The connections in one stretch of the window."""

    at: datetime
    allowed: int
    blocked: int


@dataclass(frozen=True)
class Flow:
    hours: int
    direction: Direction
    since: datetime
    until: datetime
    stride_seconds: int
    events: int
    blocked: int
    nodes: tuple[Node, ...]
    links: tuple[Link, ...]
    timeline: tuple[Bar, ...]
    # Whether more paths were seen than are read, so the picture is of the busiest.
    capped: bool


@dataclass(frozen=True)
class _Path:
    source: Address
    destination: Address
    protocol: str | None
    port: int | None
    events: int
    blocked: int


def scope_of(address: Address) -> Scope:
    return "outside" if address.is_global else "local"


def _direction(path: _Path) -> Direction:
    inside = not path.source.is_global
    reached_inside = not path.destination.is_global
    if inside and reached_inside:
        return "inside"
    return "outgoing" if inside else "incoming"


def service_id(protocol: str | None, port: int | None) -> str:
    """The service as one word: ``tcp/443``, or ``icmp`` where there is no port."""
    name = protocol or "ip"
    return f"{name}/{port}" if port else name


_BLOCKED = case((Event.severity >= int(Severity.LOW), 1), else_=0)
_WHERE = (
    Event.kind == literal_column("'firewall'"),
    Event.src_address.is_not(None),
    Event.dst_address.is_not(None),
)


def _paths(db: Session, since: datetime, until: datetime) -> tuple[list[_Path], bool]:
    count = func.count()
    rows = db.execute(
        select(
            Event.src_address,
            Event.dst_address,
            Event.protocol,
            Event.dst_port,
            count.label("events"),
            func.sum(_BLOCKED).label("blocked"),
        )
        .where(*_WHERE, Event.occurred_at >= since, Event.occurred_at < until)
        .group_by(Event.src_address, Event.dst_address, Event.protocol, Event.dst_port)
        .order_by(count.desc())
        .limit(MAX_PATHS)
    ).all()
    paths = [
        _Path(source, destination, protocol, port, events, int(blocked or 0))
        for source, destination, protocol, port, events, blocked in rows
        if source is not None and destination is not None
    ]
    return paths, len(rows) == MAX_PATHS


def _timeline(db: Session, since: datetime, until: datetime, stride: timedelta) -> tuple[Bar, ...]:
    bucket = func.date_bin(literal(stride, Interval()), Event.occurred_at, since).label("bucket")
    rows = db.execute(
        select(bucket, func.count(), func.sum(_BLOCKED))
        .where(*_WHERE, Event.occurred_at >= since, Event.occurred_at < until)
        .group_by(bucket)
        .order_by(bucket)
    ).all()
    found = {at: (events, int(blocked or 0)) for at, events, blocked in rows}
    bars: list[Bar] = []
    at = since
    while at < until:
        events, blocked = found.get(at, (0, 0))
        bars.append(Bar(at=at, allowed=events - blocked, blocked=blocked))
        at += stride
    return tuple(bars)


def _names(db: Session, addresses: list[str]) -> dict[str, str]:
    if not addresses:
        return {}
    found = db.execute(
        select(AddressName.address, AddressName.name).where(AddressName.address.in_(addresses))
    ).all()
    return {address: name for address, name in found if name}


def _address_node(column: Column, address: Address, events: int, blocked: int) -> Node:
    text = str(address)
    return Node(
        id=f"{column}:{text}",
        column=column,
        label=text,
        name=None,
        scope=scope_of(address),
        protocol=None,
        port=None,
        events=events,
        blocked=blocked,
        folded=0,
    )


def _service_node(protocol: str | None, port: int | None, events: int, blocked: int) -> Node:
    return Node(
        id=f"service:{service_id(protocol, port)}",
        column="service",
        label=service_id(protocol, port),
        name=None,
        scope=None,
        protocol=protocol,
        port=port or 0,
        events=events,
        blocked=blocked,
        folded=0,
    )


def _ends(path: _Path) -> tuple[tuple[Column, str, Node], ...]:
    """The three nodes a path goes through, with no connections counted in them yet."""
    service = service_id(path.protocol, path.port)
    return (
        ("source", str(path.source), _address_node("source", path.source, 0, 0)),
        ("service", service, _service_node(path.protocol, path.port, 0, 0)),
        (
            "destination",
            str(path.destination),
            _address_node("destination", path.destination, 0, 0),
        ),
    )


def build(db: Session, now: datetime, hours: int = 24, direction: Direction = "all") -> Flow:
    """The connections of the last ``hours`` hours, of one direction or of all."""
    since = now - timedelta(hours=hours)
    stride = STRIDE[hours]
    read, capped = _paths(db, since, now)
    paths = [path for path in read if direction == "all" or _direction(path) == direction]

    # What each node of each column carried (connections, and of them refused), to find the
    # busiest of each.
    carried: dict[Column, dict[str, list[int]]] = {
        column: defaultdict(lambda: [0, 0]) for column in COLUMNS
    }
    made: dict[Column, dict[str, Node]] = {column: {} for column in COLUMNS}
    for path in paths:
        for column, key, node in _ends(path):
            made[column].setdefault(key, node)
            carried[column][key][0] += path.events
            carried[column][key][1] += path.blocked

    shown: dict[Column, list[str]] = {}
    for column in COLUMNS:
        tally = carried[column]
        ranked = sorted(tally, key=lambda key: (-tally[key][0], key))
        shown[column] = ranked[: SHOWN[column]]

    def place(column: Column, key: str) -> str:
        return f"{column}:{key}" if key in shown[column] else f"{column}:{OTHERS}"

    # Links are the paths added up between each pair of neighbouring columns, with the nodes that
    # were not shown folded into one.
    reach: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for path in paths:
        (_, source, _), (_, service, _), (_, destination, _) = _ends(path)
        ids = (
            place("source", source),
            place("service", service),
            place("destination", destination),
        )
        for pair in ((ids[0], ids[1]), (ids[1], ids[2])):
            reach[pair][0] += path.events
            reach[pair][1] += path.blocked

    nodes: list[Node] = []
    for column in COLUMNS:
        for key in shown[column]:
            events, blocked = carried[column][key]
            nodes.append(replace(made[column][key], events=events, blocked=blocked))
        folded = [key for key in carried[column] if key not in shown[column]]
        if folded:
            nodes.append(
                Node(
                    id=f"{column}:{OTHERS}",
                    column=column,
                    label="Others",
                    name=None,
                    scope=None,
                    protocol=None,
                    port=None,
                    events=sum(carried[column][key][0] for key in folded),
                    blocked=sum(carried[column][key][1] for key in folded),
                    folded=len(folded),
                )
            )

    names = _names(db, [node.label for node in nodes if node.scope == "outside"])
    nodes = [
        replace(node, name=names.get(node.label)) if node.label in names else node for node in nodes
    ]
    links = tuple(
        Link(source=source, target=target, events=events, blocked=blocked)
        for (source, target), (events, blocked) in sorted(
            reach.items(), key=lambda item: (-item[1][0], item[0])
        )
    )
    return Flow(
        hours=hours,
        direction=direction,
        since=since,
        until=now,
        stride_seconds=int(stride.total_seconds()),
        events=sum(path.events for path in paths),
        blocked=sum(path.blocked for path in paths),
        nodes=tuple(nodes),
        links=links,
        timeline=_timeline(db, since, now, stride),
        capped=capped,
    )
