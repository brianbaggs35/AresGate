"""The devices on the firewall's networks, from its ARP table, kept as devices.

``GET /api/diagnostics/interface/get_arp`` answers with an array, an object for each entry of the
table: the ``mac`` and ``ip`` address, the ``intf`` it was learned on, ``manufacturer`` (who made
the network card, or empty), ``hostname`` (``?`` unless the firewall knows one) and ``expired``
for an entry that has gone stale. The firewall's own addresses are in it too, as ``permanent``
entries. An address that did not answer is left out by OPNsense."""

from collections.abc import Sequence
from datetime import datetime, timedelta

from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.opnsense import traffic
from app.collectors.opnsense.api import PRODUCT, read
from app.devices.sighting import NewSighting
from app.integrations import probes

ARP_PATH = "/api/diagnostics/interface/get_arp"


class ArpTable(Collector):
    key = "opnsense-arp-table"
    title = "Devices (ARP table)"
    summary = (
        "Reads the firewall's ARP table every minute and keeps each device in it: its MAC and IP "
        "address and who made its network card."
    )
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = "opnsense"
    connection = "api"
    module = "firewall"

    async def collect(self, context: Context) -> Outcome:
        entries = probes.as_array(await read(context, ARP_PATH))
        if entries is None:
            raise CollectorFailed(probes.unexpected(PRODUCT).message)
        if entries and not any("mac" in (probes.as_object(entry) or {}) for entry in entries):
            raise CollectorFailed("It answered, but the ARP table isn't in a form AresGate reads.")
        return Outcome(items=await context.record_devices(sightings(entries, context.now)))


def sightings(entries: Sequence[object], seen_at: datetime) -> list[NewSighting]:
    """The devices the entries are of. A stale entry is one that didn't answer, so it isn't a
    sighting."""
    objects = (probes.as_object(entry) for entry in entries)
    found = (
        NewSighting.of(
            traffic.text(entry, "mac"),
            seen_at,
            address=traffic.text(entry, "ip"),
            hostname=traffic.text(entry, "hostname"),
            vendor=traffic.text(entry, "manufacturer"),
        )
        for entry in objects
        if entry is not None and entry.get("expired") is not True
    )
    return [sighting for sighting in found if sighting is not None]
