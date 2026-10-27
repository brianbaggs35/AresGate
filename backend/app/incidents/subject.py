"""What a signal is about, which is what decides which incident it joins."""

from ipaddress import IPv4Address, IPv6Address

from app.models import Event, IncidentSignal

Address = IPv4Address | IPv6Address

BROADCAST = IPv4Address("255.255.255.255")
MAX_SUBJECT = 300
# What an event and a signal in an incident's timeline are, which have in common all that deciding
# what it is about, and what the owner has said of it, needs.
Signal = Event | IncidentSignal


def usable(address: Address) -> bool:
    """Whether an address says anything about who is involved: not the unspecified address,
    loopback, multicast or link-local ones, nor the broadcast address, which every device on a
    network has traffic with."""
    return not (
        address.is_unspecified
        or address.is_loopback
        or address.is_multicast
        or address.is_link_local
        or address == BROADCAST
    )


def addresses_of(event: Signal) -> list[Address]:
    """The addresses a signal names that say anything, the source before the destination."""
    named = (event.src_address, event.dst_address)
    return [address for address in named if address is not None and usable(address)]


def subject_of(event: Signal) -> str:
    """The address a signal is about. Where one end is outside the network and the other isn't,
    the outside one: it is the one that links what the firewall, the intrusion detection and the
    host logs each saw of the same thing, whichever way the traffic went. Otherwise the
    source, or the destination if that is all there is. A signal that names no address is about
    the rule that raised it."""
    addresses = addresses_of(event)
    if not addresses:
        return f"rule:{event.source}:{event.signature or event.kind}"[:MAX_SUBJECT]
    outside = [address for address in addresses if address.is_global]
    return str((outside or addresses)[0])
