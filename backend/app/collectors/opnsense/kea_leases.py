"""The devices that hold a lease from the firewall's Kea DHCP server, kept as devices.

``GET /api/kea/leases4/search`` lists the IPv4 leases Kea has given out (see ``leases``), each
with a ``state``: 0 for one that holds, and another number for one that was declined or has run
out and is waiting to be cleared away. IPv6 leases are a privilege of their own, and are not
read."""

from collections.abc import Mapping
from datetime import timedelta

from app.collectors.base import Collector, Context, Outcome
from app.collectors.opnsense import leases, traffic

LEASES_PATH = "/api/kea/leases4/search"


def holds(lease: Mapping[str, object]) -> bool:
    """Whether Kea says the lease is in force. A lease that doesn't say is taken to be."""
    return traffic.text(lease, "state") in ("", "0")


class KeaLeases(Collector):
    key = "opnsense-kea-leases"
    title = "Devices (Kea leases)"
    summary = (
        "Reads the IPv4 DHCP leases of the firewall's Kea every five minutes and keeps the device "
        "of each: its MAC and IP address, its host name and who made its network card."
    )
    interval = timedelta(minutes=5)
    timeout = timedelta(minutes=1)
    integration = "opnsense"
    connection = "api"
    module = "kea"

    async def collect(self, context: Context) -> Outcome:
        return await leases.collect(context, LEASES_PATH, holds)
