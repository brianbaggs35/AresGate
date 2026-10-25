"""What the DHCP servers on OPNsense have in common when they list their leases: the search that
answers with them, and the devices the leases are of.

``POST`` or ``GET`` of a lease search answers with an object whose ``rows`` are the leases:
``address``, ``hwaddr`` (empty for an IPv6 client that gave no hardware address), ``hostname``
(``*`` where the client gave none) and ``mac_info`` (who made its network card, or empty)."""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

from app.collectors.base import CollectorFailed, Context, Outcome
from app.collectors.opnsense import traffic
from app.collectors.opnsense.api import PRODUCT, read
from app.devices.sighting import NewSighting
from app.integrations import probes


async def collect(
    context: Context, path: str, current: Callable[[Mapping[str, object]], bool] = lambda _: True
) -> Outcome:
    """Lists the leases at ``path`` and keeps the devices they are of. ``current`` says which of
    the leases still hold."""
    answer = probes.as_object(await read(context, path))
    rows = probes.as_array(answer.get("rows")) if answer else None
    if rows is None:
        raise CollectorFailed(probes.unexpected(PRODUCT).message)
    leases = [lease for row in rows if (lease := probes.as_object(row)) is not None]
    if rows and not any("hwaddr" in lease for lease in leases):
        raise CollectorFailed("It answered, but the leases aren't in a form AresGate reads.")
    found = sightings([lease for lease in leases if current(lease)], context.now)
    return Outcome(items=await context.record_devices(found))


def sightings(leases: Sequence[Mapping[str, object]], seen_at: datetime) -> list[NewSighting]:
    """The devices the leases are of. A lease of a client that gave no hardware address has no
    device to tell it by."""
    found = (
        NewSighting.of(
            traffic.text(lease, "hwaddr"),
            seen_at,
            address=traffic.text(lease, "address"),
            hostname=traffic.text(lease, "hostname"),
            vendor=traffic.text(lease, "mac_info"),
        )
        for lease in leases
    )
    return [sighting for sighting in found if sighting is not None]
