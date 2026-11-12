"""Finding assets: the words typed, the choices made, the order and the page, worked out on an
inventory that is already in memory (see ``inventory.py``)."""

from dataclasses import dataclass
from typing import Final, Literal

from app.assets.inventory import Address, Asset, Inventory, Status, name_of

Sort = Literal["recent", "name", "address", "first"]
STATUSES: Final[tuple[Status, ...]] = ("online", "recent", "away")
UNCLASSIFIED: Final = "unclassified"


@dataclass(frozen=True)
class Query:
    """What an asset has to be to be found. Nothing given matches every asset."""

    text: str = ""
    status: Status | None = None
    # Listed by any of these integrations.
    sources: tuple[str, ...] = ()
    # On this interface, by the networks the owner gave it.
    interface: int | None = None
    new: bool = False
    unidentified: bool = False
    # The kind the owner said it is, or ``UNCLASSIFIED`` for those they have not classified.
    kind: str | None = None
    sort: Sort = "recent"


@dataclass(frozen=True)
class Counts:
    """How many assets are in each state, with every choice made but the state."""

    online: int
    recent: int
    away: int

    @property
    def all(self) -> int:
        return self.online + self.recent + self.away


@dataclass(frozen=True)
class Facets:
    """How the whole inventory is spread, whatever was chosen: what each choice would find."""

    sources: dict[str, int]
    interfaces: dict[int, int]
    new: int
    unidentified: int
    # How many the owner has classified as each kind, and how many they have not classified.
    kinds: dict[str, int]
    unclassified: int


@dataclass(frozen=True)
class Page:
    """One page of a search, and how many assets it found in all."""

    total: int
    assets: list[Asset]
    counts: Counts
    facets: Facets


def _text(asset: Asset) -> str:
    """Everything a word is looked for in, in lowercase: the name, the maker, the addresses (the
    hardware one with and without its colons) and the integrations that list it."""
    parts = [asset.name, asset.hostname or "", asset.vendor or "", *map(str, asset.addresses)]
    if asset.profile is not None:
        parts += [asset.profile.label, asset.profile.purpose or ""]
    if asset.mac:
        parts += [asset.mac, asset.mac.replace(":", "")]
    parts += [name_of(item.source) for item in asset.listings]
    return " ".join(parts).lower()


def _words(text: str) -> list[str]:
    """The words of a search, with a hardware address written with hyphens read as with colons."""
    return [
        word.replace("-", ":") if word.count("-") == 5 else word for word in text.lower().split()
    ]


def _matches(asset: Asset, query: Query, words: list[str]) -> bool:
    """Whether an asset is found by everything in the query but the state."""
    if query.sources and not any(item.source in query.sources for item in asset.listings):
        return False
    if query.interface is not None and query.interface not in asset.interfaces:
        return False
    if query.new and not asset.is_new:
        return False
    if query.unidentified and asset.identified:
        return False
    if query.kind is not None and _kind_of(asset) != query.kind:
        return False
    if words:
        haystack = _text(asset)
        return all(word in haystack for word in words)
    return True


def _kind_of(asset: Asset) -> str:
    """The kind the owner said an asset is, or ``UNCLASSIFIED``."""
    return asset.profile.kind if asset.profile else UNCLASSIFIED


def _order(sort: Sort, asset: Asset) -> tuple[object, ...]:
    """Where an asset goes: ties are broken by name and key, so the order never shuffles."""
    tie = (asset.name.casefold(), asset.key)
    if sort == "name":
        return tie
    if sort == "address":
        # Addresses in order of number, the ones that have none last.
        first: Address | None = asset.addresses[0] if asset.addresses else None
        return (first is None, first.version if first else 0, int(first) if first else 0, *tie)
    moment = asset.first_seen_at if sort == "first" else asset.last_seen_at
    return (-moment.timestamp(), *tie)


def facets(inventory: Inventory) -> Facets:
    """What each choice would find in the inventory as a whole."""
    sources: dict[str, int] = {}
    interfaces: dict[int, int] = {}
    kinds: dict[str, int] = {}
    for asset in inventory.assets:
        kinds[_kind_of(asset)] = kinds.get(_kind_of(asset), 0) + 1
        for source in {item.source for item in asset.listings}:
            sources[source] = sources.get(source, 0) + 1
        for interface in asset.interfaces:
            interfaces[interface] = interfaces.get(interface, 0) + 1
    return Facets(
        sources=sources,
        interfaces=interfaces,
        new=sum(asset.is_new for asset in inventory.assets),
        unidentified=sum(not asset.identified for asset in inventory.assets),
        kinds={kind: count for kind, count in kinds.items() if kind != UNCLASSIFIED},
        unclassified=kinds.get(UNCLASSIFIED, 0),
    )


def search(inventory: Inventory, query: Query, *, limit: int, offset: int = 0) -> Page:
    """The assets that match, in order, one page of them with how many there are in all and in
    each state."""
    words = _words(query.text)
    found = [asset for asset in inventory.assets if _matches(asset, query, words)]
    counts = Counts(*(sum(asset.status == status for asset in found) for status in STATUSES))
    if query.status is not None:
        found = [asset for asset in found if asset.status == query.status]
    found.sort(key=lambda asset: _order(query.sort, asset))
    return Page(len(found), found[offset : offset + limit], counts, facets(inventory))
