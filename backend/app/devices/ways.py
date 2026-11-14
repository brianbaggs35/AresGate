"""The ways an integration lists devices, and what each can say about one.

A DHCP lease is a promise of an address that outlasts the device, so a device that is only on a
lease is "seen" but not "there". The ARP table, ntopng's active hosts and a Wazuh agent that is
in touch can only list what is on the network now, so they are what makes a device online."""

from typing import Final, NamedTuple


class Way(NamedTuple):
    """One way of listing devices."""

    # What a page calls it.
    label: str
    # Whether being listed this way means the device is on the network now.
    presence: bool


ARP: Final = "arp"
DHCP: Final = "dhcp"
HOSTS: Final = "hosts"
AGENT: Final = "agent"
INVENTORY: Final = "inventory"

WAYS: Final[dict[str, Way]] = {
    ARP: Way("ARP table", True),
    DHCP: Way("DHCP leases", False),
    HOSTS: Way("Active hosts", True),
    AGENT: Way("Agent", True),
    # What an agent's inventory says is on the machine says nothing of whether it is on now.
    INVENTORY: Way("Agent inventory", False),
}


def check(via: str) -> str:
    """``via`` itself, or an error for a way this version doesn't know: a collector chose it, so
    a wrong one is a mistake in the collector."""
    if via not in WAYS:
        raise ValueError(f"No device is listed {via!r}; the ways are {', '.join(WAYS)}.")
    return via
