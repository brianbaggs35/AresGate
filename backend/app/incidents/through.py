"""What it travelled through: the devices on the owner's network that an incident touched, as
the Assets page lists them.

``hops.py`` draws the programs that saw an incident. This names the *devices*: the firewall or
router that all traffic to and from the Internet crosses, the device the traffic was for (or came
from), and the other devices that turned up in it. Like the path, it is only what was read: a
device is here because an address of the incident is one of its addresses, never because it might
be on the way. An address that no asset has is listed as an address, so that nothing the incident
names is left out, and the page can say it is not on the list.

The owner's classification (see ``assets/profile.py``) comes with each asset, so that "the
router" and "Dad's work laptop" are what the page says and not a hardware address.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Final, Literal

from app.assets.inventory import Asset
from app.models import Incident, IncidentSignal

Role = Literal["gateway", "target", "also"]
Address = IPv4Address | IPv6Address
# How many devices the section lists: an incident that swept a whole network names far more.
MAX_STOPS: Final = 12


@dataclass(frozen=True)
class Stop:
    """One place on the way: a device (or an address with no device) and why it is here."""

    role: Role
    address: str
    asset: Asset | None
    # How many of the incident's signals name this address.
    signals: int


def _inside(address: Address) -> bool:
    return not address.is_global


def _owners(assets: Iterable[Asset]) -> dict[Address, Asset]:
    """Which asset has each address: the one that has it now, and failing that one that had it."""
    now: dict[Address, Asset] = {}
    had: dict[Address, Asset] = {}
    for asset in assets:
        for number, address in enumerate(asset.addresses):
            (now if number < asset.current else had).setdefault(address, asset)
    return {**had, **now}


def _addresses(incident: Incident, signals: Sequence[IncidentSignal]) -> dict[Address, int]:
    """The addresses of the owner's network that the incident names, with how many signals name
    each, the most first."""
    counts: dict[Address, int] = {}
    for signal in signals:
        for address in (signal.src_address, signal.dst_address):
            if address is not None and _inside(address):
                counts[address] = counts.get(address, 0) + 1
    for address in incident.addresses:
        if _inside(address):
            counts.setdefault(address, 0)
    try:
        subject = ip_address(incident.subject)
    except ValueError:
        subject = None
    if subject is not None and _inside(subject):
        counts.setdefault(subject, 0)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0].version, int(item[0]))))


def _public(address: Address | None) -> bool:
    return address is not None and address.is_global


def _reaches_internet(incident: Incident, signals: Sequence[IncidentSignal]) -> bool:
    """Whether any end of the incident is on the Internet, which is what makes the firewall part
    of the way."""
    named = [*incident.addresses, *(a for s in signals for a in (s.src_address, s.dst_address))]
    return any(_public(address) for address in named) or _public(_subject(incident))


def _subject(incident: Incident) -> Address | None:
    """The incident's address, or None for one that is about a rule."""
    try:
        return ip_address(incident.subject)
    except ValueError:
        return None


def build(
    incident: Incident,
    signals: Sequence[IncidentSignal],
    assets: Sequence[Asset],
    *,
    outbound: bool,
) -> list[Stop]:
    """The devices an incident touched, in the order the traffic met them: the firewall first for
    traffic coming in and last for traffic going out. Nothing for an incident that names no
    address of the network and does not cross the firewall."""
    owners = _owners(assets)
    gateways = (
        [asset for asset in assets if asset.own] if _reaches_internet(incident, signals) else []
    )
    seen = {asset.key for asset in gateways}
    named = _addresses(incident, signals)
    subject = _subject(incident)
    target = subject if subject in named else next(iter(named), None)
    inner: list[Stop] = []
    for address, count in named.items():
        owner = owners.get(address)
        if owner is not None and owner.key in seen:
            continue
        if owner is not None:
            seen.add(owner.key)
        role: Role = "target" if address == target else "also"
        inner.append(Stop(role, str(address), owner, count))
    inner.sort(key=lambda stop: stop.role != "target")
    gateway = [Stop("gateway", _where(asset), asset, 0) for asset in gateways]
    return [*inner[:MAX_STOPS], *gateway] if outbound else [*gateway, *inner[:MAX_STOPS]]


def _where(asset: Asset) -> str:
    """The address a device is listed at, or its name where it has none."""
    return str(asset.addresses[0]) if asset.addresses else asset.name
