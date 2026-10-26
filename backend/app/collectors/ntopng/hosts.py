"""The hosts on the local network, as ntopng sees them: how much each has sent and received as
metrics, and the devices among them.

``GET /lua/rest/v2/get/host/active.lua`` takes the interface (``ifid``), ``mode=local`` for the
hosts of the local networks and ``all`` for every one in a single answer, not a page. The answer
is an object whose ``data`` is an array with an object for each host: its ``ip``, ``name``, and
``mac`` (as ntopng knows it), ``bytes`` (``sent``, ``recvd`` and ``total`` since ntopng first
saw it), ``thpt`` (``bps`` and ``pps`` now), ``num_flows`` (the flows it is in now), ``score``
(how suspicious ntopng finds its behaviour so far), ``is_broadcast_domain`` and when it was
``first_seen`` and ``last_seen``.

The byte counters are kept as they are, rising; a chart takes the difference between two
readings. ntopng starts a host's counters again when it has forgotten the host, which a chart sees
as a drop. A host is a device only if it is in ntopng's own broadcast domain, where the MAC address
ntopng has for it is its own; for a host behind a router it is the router's.

Read from ntopng's source, since its documentation has the endpoint and an example of the answer
but not its parameters (``scripts/lua/rest/v2/get/host/active.lua``), and from the REST API v2
examples (section 2.2.1) for the answer. Not tried against a live ntopng."""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from app.collectors import traffic
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.ntopng.api import PRODUCT, interface, read
from app.collectors.readings import Readings, number
from app.devices.sighting import NewSighting
from app.integrations import probes

PATH = "/lua/rest/v2/get/host/active.lua"
# The most hosts one run keeps. A home network has dozens.
LIMIT = 1000


class Hosts(Collector):
    key = "ntopng-hosts"
    title = "Hosts"
    summary = (
        "Reads the hosts on the local network every minute: how much each has sent and received "
        "and its flows, as metrics, and each device among them."
    )
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = "ntopng"
    connection = "api"

    async def collect(self, context: Context) -> Outcome:
        answer = probes.as_object(
            await read(context, PATH, {"ifid": interface(context), "mode": "local", "all": "true"})
        )
        rows = probes.as_array(answer.get("data")) if answer else None
        if rows is None:
            raise CollectorFailed(probes.unexpected(PRODUCT).message)
        found = [host for row in rows[:LIMIT] if (host := probes.as_object(row)) is not None]
        if rows and not found:
            raise CollectorFailed("It answered, but the hosts aren't in a form AresGate reads.")
        readings = Readings(context)
        for host in found:
            if address := traffic.text(host, "ip"):
                for metric, value in measure(host).items():
                    readings.add(metric, value, host=address)
        await readings.save()
        await context.record_devices(sightings(found, context.now))
        return Outcome(items=len(found))


def _member(host: Mapping[str, object], key: str) -> Mapping[str, object]:
    return probes.as_object(host.get(key)) or {}


def measure(host: Mapping[str, object]) -> dict[str, float | None]:
    """What there is to read of one host, by the name it is kept under: none where ntopng left
    it out."""
    sent = _member(host, "bytes")
    return {
        "host.bytes_sent": number(sent.get("sent")),
        "host.bytes_received": number(sent.get("recvd")),
        "host.throughput_bps": number(_member(host, "thpt").get("bps")),
        "host.flows": number(_member(host, "num_flows").get("total")),
        "host.score": number(_member(host, "score").get("total")),
    }


def sightings(hosts: Sequence[Mapping[str, object]], seen_at: datetime) -> list[NewSighting]:
    """The devices among the hosts: those in ntopng's broadcast domain that it has a MAC address
    for."""
    found = (
        NewSighting.of(
            traffic.text(host, "mac"),
            seen_at,
            address=traffic.text(host, "ip"),
            hostname=_name(host),
        )
        for host in hosts
        if host.get("is_broadcast_domain") is True
    )
    return [sighting for sighting in found if sighting is not None]


def _name(host: Mapping[str, object]) -> str | None:
    """The name ntopng has for a host. It adds the label it would show for the address in
    brackets when that differs from the name, and uses the address when it has no name."""
    address = traffic.text(host, "ip")
    name = traffic.text(host, "name").partition(" [")[0].strip()
    return None if not name or name == address or name.startswith(f"{address}@") else name
