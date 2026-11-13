"""Devices: every address that took part in a connection the integrations reported, the home's own
and the ones on the Internet side, and what each did. Read-only, for someone signed in."""

from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import AwareDatetime, BaseModel

from app.api.assets import (
    EventOut,
    IdentityOut,
    PortOut,
    ProfileOut,
    StandingOut,
    StatusName,
    event_out,
    identity_out,
    profile_out,
    standing_out,
)
from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.api.deps import Db, signed_in
from app.assets import profile as profiles
from app.assets.inventory import Asset
from app.devices import seen
from app.devices.seen import Direction, Scope, Sort
from app.events.event import Severity
from app.models import utcnow

router = APIRouter(prefix="/devices", tags=["devices"], dependencies=[Depends(signed_in)])

MAX_PAGE = 100
MAX_SEARCH = 200


class OwnedOut(BaseModel):
    """The asset an address is, when the Assets list holds it."""

    key: str
    name: str
    vendor: str | None
    mac: str | None
    status: StatusName
    # One of the firewall's own addresses, which all the traffic to and from the Internet crosses.
    own: bool
    profile: ProfileOut | None
    suggested_label: str | None
    # What the fingerprinting service says it is, once it has been asked.
    identity: IdentityOut | None


class FlaggedOut(BaseModel):
    """The incidents of the week the address is in, and how serious the worst is."""

    count: int
    worst: SeverityName


class DeviceOut(BaseModel):
    """An address and what it did over the last week. ``incoming`` is the events that name it as the
    destination, the connections made to it, and ``outgoing`` those it made."""

    address: str
    scope: Scope
    # What its reverse lookup called it, when one is kept.
    name: str | None
    asset: OwnedOut | None
    incoming: int
    outgoing: int
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime
    # The ports its connections used, the most often first, and the protocols.
    ports: list[PortOut]
    protocols: list[str]
    incidents: FlaggedOut | None
    # What threat intelligence kept of it, for one on the Internet side; nothing is asked for it.
    standing: StandingOut | None


class ScopeCounts(BaseModel):
    """How many devices there are of each scope, among those the search finds."""

    all: int
    yours: int
    local: int
    outside: int


class DevicesOut(BaseModel):
    items: list[DeviceOut]
    total: int
    counts: ScopeCounts
    # How many days the connections are read over.
    days: int
    # More addresses were seen than are read: the list is the ones seen most recently.
    capped: bool


class ConnectionOut(BaseModel):
    """What the device did with one peer over one port. ``outgoing`` is the device connecting to the
    peer, and the port is the one at the far end of the connection, the service that was reached."""

    direction: Direction
    # None when the event did not say where the other end was.
    peer: str | None
    port: int | None
    protocol: str | None
    events: int
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime


class InvolvedOut(BaseModel):
    """An incident the address is in, and the kind of threat and the chain it belongs to."""

    id: int
    title: str
    severity: SeverityName
    confidence: int
    status: str
    verdict: str | None
    last_seen_at: AwareDatetime
    signal_count: int
    sources: list[str]
    family_id: int | None
    family_label: str | None
    chain_id: int | None


class DeviceDetailOut(BaseModel):
    device: DeviceOut
    events_day: int
    events_week: int
    connections: list[ConnectionOut]
    events: list[EventOut]
    incidents: list[InvolvedOut]


def _owned(asset: Asset | None) -> OwnedOut | None:
    if asset is None:
        return None
    return OwnedOut(
        key=asset.key,
        name=asset.name,
        vendor=asset.vendor,
        mac=asset.mac,
        status=asset.status,
        own=asset.own,
        profile=profile_out(asset.profile),
        suggested_label=profiles.BY_KEY[asset.suggested].label if asset.suggested else None,
        identity=identity_out(asset.identity),
    )


def _device(item: seen.Device) -> DeviceOut:
    flagged = item.incidents
    return DeviceOut(
        address=str(item.address),
        scope=item.scope,
        name=item.name,
        asset=_owned(item.asset),
        incoming=item.tally.incoming,
        outgoing=item.tally.outgoing,
        first_seen_at=item.tally.first_seen_at,
        last_seen_at=item.tally.last_seen_at,
        ports=[
            PortOut(port=port.port, protocol=port.protocol, events=port.events)
            for port in item.ports
        ],
        protocols=list(item.protocols),
        incidents=None
        if flagged is None
        else FlaggedOut(count=flagged.count, worst=SEVERITY_NAMES[Severity(flagged.worst)]),
        standing=standing_out(item.standing),
    )


@router.get("")
def list_devices(
    db: Db,
    q: Annotated[
        str,
        Query(
            max_length=MAX_SEARCH,
            description="Words that each have to be in its address, its name, or the name, maker "
            "or hardware address of the asset it is.",
        ),
    ] = "",
    scope: Annotated[
        Scope | None,
        Query(description="Only the home's own devices, other private addresses, or the Internet."),
    ] = None,
    direction: Annotated[
        Direction | None,
        Query(description="Only those that were connected to, or that made a connection."),
    ] = None,
    flagged: Annotated[bool, Query(description="Only those in an incident this week.")] = False,
    sort: Annotated[Sort, Query()] = "recent",
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DevicesOut:
    """The devices that match, the ones seen most recently first unless asked for another order."""
    found = seen.search(
        db,
        utcnow(),
        text=q,
        scope=scope,
        direction=direction,
        flagged_only=flagged,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return DevicesOut(
        items=[_device(item) for item in found.items],
        total=found.total,
        counts=ScopeCounts(
            all=found.counts.everything,
            yours=found.counts.yours,
            local=found.counts.local,
            outside=found.counts.outside,
        ),
        days=seen.WEEK.days,
        capped=found.capped,
    )


def _connection(item: seen.Connection) -> ConnectionOut:
    return ConnectionOut(
        direction=item.direction,
        peer=None if item.peer is None else str(item.peer),
        port=item.port,
        protocol=item.protocol,
        events=item.events,
        first_seen_at=item.first_seen_at,
        last_seen_at=item.last_seen_at,
    )


def _involved(item: seen.Involved) -> InvolvedOut:
    return InvolvedOut(
        id=item.id,
        title=item.title,
        severity=SEVERITY_NAMES[Severity(item.severity)],
        confidence=item.confidence,
        status=item.status,
        verdict=item.verdict,
        last_seen_at=item.last_seen_at,
        signal_count=item.signal_count,
        sources=list(item.sources),
        family_id=item.family_id,
        family_label=item.family_label,
        chain_id=item.chain_id,
    )


def _address(text: str) -> IPv4Address | IPv6Address:
    try:
        return ip_address(text)
    except ValueError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "There is no device with that address."
        ) from None


@router.get("/{address}", responses={404: {"description": "Nothing is known of that address."}})
def get_device(
    address: Annotated[
        str, Path(max_length=45, description="An IPv4 or IPv6 address, such as 192.168.1.20.")
    ],
    db: Db,
) -> DeviceDetailOut:
    """What one address did over the last week."""
    found = seen.load(db, _address(address), utcnow())
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no device with that address.")
    mine = {str(found.device.address)}
    return DeviceDetailOut(
        device=_device(found.device),
        events_day=found.events_day,
        events_week=found.events_week,
        connections=[_connection(item) for item in found.connections],
        events=[event_out(item, mine) for item in found.events],
        incidents=[_involved(item) for item in found.incidents],
    )
