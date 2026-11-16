"""Where each device on the network talks to, and when it talks somewhere it never has.

A destination is the network its address is in (a /24, or a /64 for IPv6) and the port, so that
one site's many addresses, and a content network's, are one place. Every outbound connection a
program saw (the firewall's log, ntopng's flows) teaches what is normal for the device it came
from. A device is only judged once it has been watched for a week and is known to talk to a
fair number of places: until then everything is new to it. What happened before the last hour
only teaches, so that starting this does not raise an alarm for the past. A device that reaches
places it never has is one deviation for the run, with how many, and a great many at once is
worth more than a few (a scan, or a program looking for somewhere to send data)."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    ip_network,
)
from typing import Final

from sqlalchemy import Boolean, delete, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import baselines
from app.events.event import NewEvent, Severity
from app.incidents.engine import SETTLE
from app.incidents.subject import usable
from app.models import Event, KnownDestination, SystemInfo

Address = IPv4Address | IPv6Address
Network = IPv4Network | IPv6Network

# The events that say who talked to whom.
KINDS: Final = ("firewall", "flow")
# How many events one run learns from.
BATCH: Final = 5000
# How many rows one statement writes.
CHUNK: Final = 1000
# A device is judged once it has been learned about for this long and for this many places.
WATCHED_FOR: Final = timedelta(days=7)
MIN_PLACES: Final = 20
# Only what happened this recently can be a deviation. Older only teaches.
RECENT: Final = timedelta(hours=1)
# A device that reaches this many new places at once is worth a higher severity.
MANY: Final = 10
# How many places a sentence lists.
LISTED: Final = 3
# What is no longer kept: places a device has not been to in this long, unless they are expected.
FORGET_AFTER: Final = timedelta(days=90)

CURSOR_KEY: Final = "baselines.destinations_cursor"

Place = tuple[Address, Network, int]


@dataclass(frozen=True)
class Seen:
    """What was learned of one place in a run."""

    first: datetime
    last: datetime
    hits: int


def network_of(address: Address) -> Network:
    """The network a destination is in: its /24, or its /64."""
    return ip_network(f"{address}/{24 if address.version == 4 else 64}", strict=False)


def is_inside(address: Address) -> bool:
    """Whether an address is a device on the network: a private one that says who it is."""
    return address.is_private and usable(address)


def _outbound(events: list[Event]) -> dict[Place, Seen]:
    """The places a device on the network went to that are on the internet, from the events."""
    seen: dict[Place, Seen] = {}
    for event in events:
        client, server = event.src_address, event.dst_address
        if client is None or server is None or not is_inside(client) or not server.is_global:
            continue
        place = (client, network_of(server), event.dst_port or 0)
        before = seen.get(place)
        seen[place] = (
            Seen(event.occurred_at, event.occurred_at, 1)
            if before is None
            else Seen(
                min(before.first, event.occurred_at),
                max(before.last, event.occurred_at),
                before.hits + 1,
            )
        )
    return seen


def _watched(db: Session, clients: set[Address]) -> dict[Address, tuple[datetime, int]]:
    """For each of these devices, when it was first learned about and how many places it is known
    to talk to."""
    rows = db.execute(
        select(
            KnownDestination.client,
            func.min(KnownDestination.first_seen_at),
            func.count(),
        )
        .where(KnownDestination.client.in_(clients))
        .group_by(KnownDestination.client)
    )
    return {client: (began, places) for client, began, places in rows}


def _learn(db: Session, seen: dict[Place, Seen]) -> list[Place]:
    """Keeps what was seen, and returns the places that were not known before."""
    fresh: list[Place] = []
    items = list(seen.items())
    for start in range(0, len(items), CHUNK):
        chunk = items[start : start + CHUNK]
        statement = insert(KnownDestination).values(
            [
                {
                    "client": client,
                    "network": network,
                    "port": port,
                    "first_seen_at": what.first,
                    "last_seen_at": what.last,
                    "hits": what.hits,
                }
                for (client, network, port), what in chunk
            ]
        )
        statement = statement.on_conflict_do_update(
            index_elements=["client", "network", "port"],
            set_={
                "first_seen_at": func.least(
                    KnownDestination.first_seen_at, statement.excluded.first_seen_at
                ),
                "last_seen_at": func.greatest(
                    KnownDestination.last_seen_at, statement.excluded.last_seen_at
                ),
                "hits": KnownDestination.hits + statement.excluded.hits,
            },
        ).returning(
            KnownDestination.client,
            KnownDestination.network,
            KnownDestination.port,
            literal_column("(xmax = 0)", Boolean).label("inserted"),
        )
        fresh.extend(
            (client, network, port)
            for client, network, port, inserted in db.execute(statement)
            if inserted
        )
    return fresh


def _where(network: Network, port: int) -> str:
    return f"{network} port {port}" if port else f"{network}"


def _event(
    client: Address, places: list[tuple[Network, int]], known: int, now: datetime
) -> NewEvent:
    listed = ", ".join(_where(network, port) for network, port in places[:LISTED])
    more = len(places) - LISTED
    many = len(places) >= MANY
    first_network, first_port = places[0]
    return NewEvent(
        source=baselines.SOURCE,
        connection=baselines.CONNECTION,
        kind=baselines.KIND,
        severity=Severity.MEDIUM if many else Severity.LOW,
        occurred_at=now,
        identity=("destination", str(client), str(first_network), first_port),
        summary=(
            f"{client} reached {len(places)} {'place' if len(places) == 1 else 'places'} it "
            f"never has: {listed}{f' and {more} more' if more > 0 else ''}. It is known to talk "
            f"to {known} others."
        ),
        signature="A device reached somewhere new",
        src_address=str(client),
        raw={
            "baseline": "destination",
            "confidence": min(90, 30 + 5 * len(places)),
            "new_places": [
                {"network": str(network), "port": port} for network, port in places[:50]
            ],
            "new_count": len(places),
            "known_places": known,
        },
    )


def run(db: Session, now: datetime) -> list[NewEvent]:
    """Learns from the events stored since the last run, and returns the deviations. Forgets the
    places no device has been to for a long time."""
    cursor = db.get(SystemInfo, CURSOR_KEY)
    after = int(cursor.value) if cursor is not None else 0
    events = list(
        db.scalars(
            select(Event)
            .where(
                Event.id > after,
                Event.kind.in_(KINDS),
                Event.received_at <= now - SETTLE,
                Event.src_address.is_not(None),
                Event.dst_address.is_not(None),
            )
            .order_by(Event.id)
            .limit(BATCH)
        )
    )
    deviations: list[NewEvent] = []
    if events:
        seen = _outbound(events)
        watched = _watched(db, {client for client, _, _ in seen})
        fresh = _learn(db, seen)
        deviations = _deviations(fresh, seen, watched, now)
        if cursor is None:
            db.add(SystemInfo(key=CURSOR_KEY, value=str(events[-1].id)))
        else:
            cursor.value = str(events[-1].id)
    # Places the owner said are expected stay, however long ago a device was last there.
    db.execute(
        delete(KnownDestination).where(
            KnownDestination.last_seen_at < now - FORGET_AFTER,
            KnownDestination.expected.is_(False),
        )
    )
    return deviations


def _deviations(
    fresh: list[Place],
    seen: dict[Place, Seen],
    watched: dict[Address, tuple[datetime, int]],
    now: datetime,
) -> list[NewEvent]:
    new: dict[Address, list[tuple[Network, int]]] = defaultdict(list)
    for client, network, port in fresh:
        began = watched.get(client)
        if (
            began is not None
            and began[0] <= now - WATCHED_FOR
            and began[1] >= MIN_PLACES
            and seen[(client, network, port)].last >= now - RECENT
        ):
            new[client].append((network, port))
    return [
        _event(
            client,
            sorted(places, key=lambda place: (str(place[0]), place[1])),
            watched[client][1],
            now,
        )
        for client, places in new.items()
    ]
