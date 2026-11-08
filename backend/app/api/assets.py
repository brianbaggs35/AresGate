"""Assets: the devices on the network, as every integration that can list them tells it, merged
into one list. Read-only, for someone signed in."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel

from app.api.deps import Db, signed_in
from app.assets import inventory, search
from app.assets.inventory import Asset, Inventory, Listing
from app.assets.search import Sort
from app.devices import ways
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
