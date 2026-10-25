"""What a sighting is when a collector hands it over, before it is stored: a device that was
listed by an integration, such as in a firewall's ARP table or among its DHCP leases, with what
the listing says about it."""

import re
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Self

from app.audit import clean

MAX_HOSTNAME = 253
MAX_VENDOR = 128

# Six bytes of one or two hex digits, joined by colons or by hyphens: FreeBSD writes the bytes
# without their leading zeros ("0:c:29:a:b:c"). Or the twelve digits run together.
_BYTES = re.compile(r"^[0-9a-f]{1,2}([:-])(?:[0-9a-f]{1,2}\1){4}[0-9a-f]{1,2}$")
_RUN = re.compile(r"^[0-9a-f]{12}$")
# What programs put where a device has no name.
_NO_NAME = frozenset({"*", "?", "-"})


def mac_address(value: str) -> str | None:
    """A hardware address in the one form it is kept in, ``aa:bb:cc:00:11:22``, or None for
    text that isn't the address of a device: not six bytes, all zeros, or one with the multicast
    bit set, which the broadcast address has too."""
    text = value.strip().lower()
    if _RUN.match(text):
        parts = [text[at : at + 2] for at in range(0, 12, 2)]
    elif _BYTES.match(text):
        parts = [part.zfill(2) for part in re.split(r"[:-]", text)]
    else:
        return None
    first = int(parts[0], 16)
    if first & 1 or not any(int(part, 16) for part in parts):
        return None
    return ":".join(parts)


@dataclass(frozen=True)
class NewSighting:
    """A device as a collector found it. Make one with ``of``, which cleans up what the other
    system said: it may hold anything."""

    # In the form ``mac_address`` gives.
    mac: str
    # When it was listed.
    seen_at: datetime
    address: IPv4Address | IPv6Address | None = None
    hostname: str | None = None
    vendor: str | None = None

    def __post_init__(self) -> None:
        if mac_address(self.mac) != self.mac:
            raise ValueError(f"A sighting's MAC address is six bytes, not {self.mac!r}.")
        if self.seen_at.tzinfo is None:
            raise ValueError("A sighting's time must have a time zone.")

    @classmethod
    def of(
        cls,
        mac: str,
        seen_at: datetime,
        *,
        address: str | None = None,
        hostname: str | None = None,
        vendor: str | None = None,
    ) -> Self | None:
        """The sighting, or None when ``mac`` isn't a device's address. An address that isn't
        one, a name that isn't a name and a maker that isn't there are left out: they shouldn't
        cost the device."""
        found = mac_address(mac)
        if found is None:
            return None
        return cls(
            found,
            seen_at,
            _address(address),
            _hostname(hostname),
            _text(vendor, MAX_VENDOR),
        )


def _address(value: str | None) -> IPv4Address | IPv6Address | None:
    if value is None:
        return None
    try:
        # A link-local address may say which interface it was on, which the database can't hold.
        return ip_address(value.strip().partition("%")[0])
    except ValueError:
        return None


def _hostname(value: str | None) -> str | None:
    """A name as it is written to a person: without the dot that ends a fully qualified one."""
    return _text(None if value is None else value.strip().removesuffix("."), MAX_HOSTNAME)


def _text(value: str | None, limit: int) -> str | None:
    """Text from a program, made safe to keep: control characters become spaces, anything that
    isn't text is replaced, and it's cut to fit. What stands for no name is no text."""
    cleaned = clean(value, limit)
    if cleaned is None or cleaned in _NO_NAME:
        return None
    return cleaned.encode("utf-8", "replace").decode("utf-8")
