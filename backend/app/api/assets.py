"""Assets: the devices on the network, as every integration that can list them tells it, merged
into one list. Read-only, for someone signed in."""

from collections.abc import Sequence
from ipaddress import IPv4Address, IPv6Address
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import AwareDatetime, BaseModel

from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.api.deps import Db, signed_in
from app.assets import detail, inventory, search
from app.assets.detail import Reading
from app.assets.inventory import Asset, Inventory, Listing
from app.assets.search import Sort
from app.devices import ways
from app.events.event import Severity
from app.models import utcnow

router = APIRouter(prefix="/assets", tags=["assets"], dependencies=[Depends(signed_in)])

MAX_PAGE = 100
StatusName = Literal["online", "recent", "away"]
# The longest words a search takes in: more than any address or name.
MAX_SEARCH = 200
MAX_SOURCES = 8


class ListingOut(BaseModel):
    """One integration listing an asset, and how."""

    source: str
    source_name: str
    via: str
    via_label: str
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime
    # Whether being listed this way says it is on the network now.
    presence: bool
    # For a machine with no hardware address that was merged into a device: by what.
    matched_by: Literal["address", "hostname"] | None
    # For a machine, the integration's word for how it is doing, such as active.
    state: str | None


class AssetOut(BaseModel):
    # What a page links to: device-12 or host-3.
    key: str
    kind: Literal["device", "host"]
    name: str
    hostname: str | None
    vendor: str | None
    mac: str | None
    # The hardware address was made up by the device (as a phone does on Wi-Fi), not the maker's.
    private_mac: bool
    # The addresses it has now, then the ones it had.
    addresses: list[str]
    current_addresses: int
    status: StatusName
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime
    is_new: bool
    # Something says what it is: a name or a maker.
    identified: bool
    listings: list[ListingOut]
    # The ids of the interfaces whose networks hold one of its current addresses.
    interfaces: list[int]


class SupplierOut(BaseModel):
    """An integration that can list devices."""

    key: str
    name: str
    # Every connection it needs is set up.
    connected: bool
    # What it lists, such as the ARP table.
    ways: list[str]
    # How many assets it lists, in the whole inventory.
    assets: int


class InterfaceChoice(BaseModel):
    id: int
    name: str
    assets: int


class CountsOut(BaseModel):
    """How many are in each state, with every choice made but the state."""

    all: int
    online: int
    recent: int
    away: int


class AssetsOut(BaseModel):
    total: int
    items: list[AssetOut]
    counts: CountsOut
    suppliers: list[SupplierOut]
    # The interfaces that have networks to tell which assets are on them.
    interfaces: list[InterfaceChoice]
    # How many of the whole inventory each filter would find.
    new: int
    unidentified: int
    # When the first asset was first listed; null while there is none.
    watching_since: AwareDatetime | None
    # How many are on the Internet side (the provider's equipment, say) and so not in the list.
    outside: int


def _listing(item: Listing) -> ListingOut:
    way = ways.WAYS.get(item.via)
    return ListingOut(
        source=item.source,
        source_name=inventory.name_of(item.source),
        via=item.via,
        via_label=way.label if way else item.via,
        first_seen_at=item.first_seen_at,
        last_seen_at=item.last_seen_at,
        presence=item.presence,
        matched_by=item.matched_by,
        state=item.state,
    )


def asset_out(asset: Asset) -> AssetOut:
    return AssetOut(
        key=asset.key,
        kind=asset.kind,
        name=asset.name,
        hostname=asset.hostname,
        vendor=asset.vendor,
        mac=asset.mac,
        private_mac=asset.private_mac,
        addresses=[str(address) for address in asset.addresses],
        current_addresses=asset.current,
        status=asset.status,
        first_seen_at=asset.first_seen_at,
        last_seen_at=asset.last_seen_at,
        is_new=asset.is_new,
        identified=asset.identified,
        listings=[_listing(item) for item in asset.listings],
        interfaces=list(asset.interfaces),
    )


def _out(found: inventory.Inventory, page: search.Page) -> AssetsOut:
    return AssetsOut(
        total=page.total,
        items=[asset_out(asset) for asset in page.assets],
        counts=CountsOut(
            all=page.counts.all,
            online=page.counts.online,
            recent=page.counts.recent,
            away=page.counts.away,
        ),
        suppliers=[
            SupplierOut(
                key=item.key,
                name=item.name,
                connected=item.connected,
                ways=list(item.ways),
                assets=page.facets.sources.get(item.key, 0),
            )
            for item in found.suppliers
        ],
        interfaces=[
            InterfaceChoice(
                id=item.id, name=item.name, assets=page.facets.interfaces.get(item.id, 0)
            )
            for item in found.networks
        ],
        new=page.facets.new,
        unidentified=page.facets.unidentified,
        watching_since=found.watching_since,
        outside=found.outside,
    )


@router.get("")
def list_assets(
    db: Db,
    q: Annotated[
        str,
        Query(
            max_length=MAX_SEARCH,
            description="Words that each have to be in its name, maker, hardware address, "
            "an address or the name of an integration that lists it.",
        ),
    ] = "",
    state: Annotated[
        StatusName | None,
        Query(alias="status", description="Only those that are online, recent or away."),
    ] = None,
    source: Annotated[
        list[str] | None,
        Query(max_length=MAX_SOURCES, description="Listed by this integration. Repeat it."),
    ] = None,
    interface: Annotated[
        int | None, Query(ge=1, le=2**63 - 1, description="On this interface's networks.")
    ] = None,
    new: Annotated[bool, Query(description="Only those first listed in the last week.")] = False,
    unidentified: Annotated[bool, Query(description="Only those with no name or maker.")] = False,
    sort: Annotated[Sort, Query()] = "recent",
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AssetsOut:
    """The assets that match, the ones listed most recently first unless asked for another
    order."""
    found: Inventory = inventory.load(db, utcnow())
    query = search.Query(
        text=q,
        status=state,
        sources=tuple(dict.fromkeys(source or [])),
        interface=interface,
        new=new,
        unidentified=unidentified,
        sort=sort,
    )
    return _out(found, search.search(found, query, limit=limit, offset=offset))


AssetKey = Annotated[
    str,
    Path(
        pattern=r"^(device|host)-[1-9][0-9]{0,18}$",
        description="An asset's key, such as device-12 or host-3.",
    ),
]


class AddressOut(BaseModel):
    """An address the asset has had, and whether it has it now."""

    address: str
    current: bool
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime


class NetworkOut(BaseModel):
    """An interface whose networks hold one of the asset's addresses."""

    id: int
    name: str


class EventOut(BaseModel):
    """An event one of the asset's addresses was in, as the program that reported it saw it."""

    id: int
    occurred_at: AwareDatetime
    source: str
    source_name: str
    kind: str
    severity: SeverityName
    summary: str
    signature: str | None
    src_address: str | None
    src_port: int | None
    dst_address: str | None
    dst_port: int | None
    protocol: str | None
    # Whether the asset sent it, rather than the one it was sent to.
    outbound: bool


class PeerOut(BaseModel):
    """Another address the asset's traffic went to, or came from."""

    address: str
    events: int
    last_seen_at: AwareDatetime


class ReadingOut(BaseModel):
    """What was sent and received in a stretch of time, in bytes, or null if it was not measured."""

    at: AwareDatetime
    sent: float | None
    received: float | None


class TrafficOut(BaseModel):
    """The asset's traffic as ntopng measured it: the last day by the hour, the last week by the
    day, and the totals of each."""

    measured: bool
    hours: list[ReadingOut]
    days: list[ReadingOut]
    sent_day: float
    received_day: float
    sent_week: float
    received_week: float


class IncidentOut(BaseModel):
    """An incident one of the asset's addresses is in."""

    id: int
    title: str
    severity: SeverityName
    confidence: int
    status: str
    verdict: str | None
    last_seen_at: AwareDatetime
    signal_count: int
    sources: list[str]


class VerdictOut(BaseModel):
    """A verdict the owner gave about one of the asset's addresses."""

    id: int
    verdict: str
    address: str | None
    destination: str | None
    source: str | None
    signature: str | None
    note: str | None
    created_at: AwareDatetime


class AssetDetailOut(BaseModel):
    """One asset's page: everything AresGate knows of it."""

    asset: AssetOut
    networks: list[NetworkOut]
    addresses: list[AddressOut]
    events: list[EventOut]
    # How many events its addresses were in, in the last day and in the last week.
    events_day: int
    events_week: int
    talks_to: list[PeerOut]
    contacted_by: list[PeerOut]
    traffic: TrafficOut
    incidents: list[IncidentOut]
    verdicts: list[VerdictOut]


def _text(address: IPv4Address | IPv6Address | None) -> str | None:
    return None if address is None else str(address)


def _reading(item: Reading) -> ReadingOut:
    return ReadingOut(at=item.at, sent=item.sent, received=item.received)


def _total(readings: Sequence[Reading]) -> tuple[float, float]:
    """What was sent and received over some hours, counting nothing where it was not measured."""
    return (
        sum(item.sent or 0.0 for item in readings),
        sum(item.received or 0.0 for item in readings),
    )


def _event(item: detail.EventSeen, mine: set[str]) -> EventOut:
    source = _text(item.src_address)
    return EventOut(
        id=item.id,
        occurred_at=item.occurred_at,
        source=item.source,
        source_name=inventory.name_of(item.source),
        kind=item.kind,
        severity=SEVERITY_NAMES[Severity(item.severity)],
        summary=item.summary,
        signature=item.signature,
        src_address=source,
        src_port=item.src_port,
        dst_address=_text(item.dst_address),
        dst_port=item.dst_port,
        protocol=item.protocol,
        outbound=source is not None and source in mine,
    )


def _peer(item: detail.Peer) -> PeerOut:
    return PeerOut(address=str(item.address), events=item.events, last_seen_at=item.last_seen_at)


def _detail_out(found: detail.Detail) -> AssetDetailOut:
    mine = {str(address) for address in found.asset.addresses}
    sent_day, received_day = _total(found.traffic.hours[-detail.HOURS_PER_DAY :])
    sent_week, received_week = _total(found.traffic.hours)
    return AssetDetailOut(
        asset=asset_out(found.asset),
        networks=[NetworkOut(id=item.id, name=item.name) for item in found.networks],
        addresses=[
            AddressOut(
                address=str(item.address),
                current=item.current,
                first_seen_at=item.first_seen_at,
                last_seen_at=item.last_seen_at,
            )
            for item in found.addresses
        ],
        events=[_event(item, mine) for item in found.events],
        events_day=found.events_day,
        events_week=found.events_week,
        talks_to=[_peer(item) for item in found.talks_to],
        contacted_by=[_peer(item) for item in found.contacted_by],
        traffic=TrafficOut(
            measured=found.traffic.measured,
            hours=[_reading(item) for item in found.traffic.hours[-detail.HOURS_PER_DAY :]],
            days=[_reading(item) for item in found.traffic.days],
            sent_day=sent_day,
            received_day=received_day,
            sent_week=sent_week,
            received_week=received_week,
        ),
        incidents=[
            IncidentOut(
                id=item.id,
                title=item.title,
                severity=SEVERITY_NAMES[Severity(item.severity)],
                confidence=item.confidence,
                status=item.status,
                verdict=item.verdict,
                last_seen_at=item.last_seen_at,
                signal_count=item.signal_count,
                sources=list(item.sources),
            )
            for item in found.incidents
        ],
        verdicts=[
            VerdictOut(
                id=item.id,
                verdict=item.verdict,
                address=_text(item.address),
                destination=item.destination,
                source=item.source,
                signature=item.signature,
                note=item.note,
                created_at=item.created_at,
            )
            for item in found.verdicts
        ],
    )


@router.get("/{key}", responses={404: {"description": "There is no asset with that key."}})
def get_asset(key: AssetKey, db: Db) -> AssetDetailOut:
    """One asset's page: what the connected programs and AresGate's own records say of it. An
    asset on the Internet side has no page, as it is not on the list."""
    found = detail.load(db, key, utcnow())
    if found is None:
        raise HTTPException(status_code=404, detail="There is no asset with that key.")
    return _detail_out(found)
