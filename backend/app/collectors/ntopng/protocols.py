"""What ntopng's hosts and interfaces talk, as metrics: the bytes of each application protocol
(L7, as nDPI names it: DNS, TLS, YouTube), so that the baselines can learn what each device
normally uses and notice a protocol that is new to it.

``GET /lua/rest/v2/get/interface/l7/stats.lua`` takes the interface (``ifid``) and
``ndpistats_mode=sinceStartup``, and answers with an array in ``rsp`` with an object for each
protocol the interface has seen: its ``label`` (``TLS``) and its ``value``, the bytes. ``GET
/lua/rest/v2/get/host/l7/stats.lua`` takes the interface and the address (``host``) and answers
with the same shape for one host, with also the ``duration`` of the protocol. Both collapse the
small protocols into one ``Other`` unless they are asked not to (``collapse_stats=false``), which
would hide exactly the protocol a device starts to use. A host ntopng has forgotten is refused.

The counters are kept as they are, rising: a chart takes the difference between two readings, and
a protocol that was never seen has no reading. They are kept for the hosts that have moved the
most, since each host is a request of its own: a home network has a few dozen.

Read from ntopng's source (``scripts/lua/rest/v2/get/interface/l7/stats.lua`` and
``host/l7/stats.lua``), which has no documentation of the parameters or the answer. The unit of
``value`` is bytes in ntopng's own pages, which these read through the same function; that is
inferred. Not tried against a live ntopng."""

from collections.abc import Mapping, Sequence
from datetime import timedelta

from app.collectors import traffic
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.ntopng.api import PRODUCT, interfaces, names, read
from app.collectors.ntopng.hosts import on_interface
from app.collectors.readings import Readings, number
from app.integrations import probes

INTERFACE = "/lua/rest/v2/get/interface/l7/stats.lua"
HOST = "/lua/rest/v2/get/host/l7/stats.lua"
# How many hosts each run reads the protocols of, the ones with the most bytes.
HOSTS = 40
# How many protocols of one host or interface are kept, the largest first.
PROTOCOLS = 60


class Protocols(Collector):
    key = "ntopng-protocols"
    title = "Application protocols"
    summary = (
        "Reads the application protocols (DNS, TLS, streaming) each busy host and each interface "
        "uses every five minutes, as metrics, so what a device normally talks is known."
    )
    interval = timedelta(minutes=5)
    timeout = timedelta(minutes=2)
    integration = "ntopng"
    connection = "api"

    async def collect(self, context: Context) -> Outcome:
        ports = await names(context)
        readings = Readings(context)
        refused: list[CollectorFailed] = []
        asked = 0
        for ifid in await interfaces(context):
            port = ports.get(ifid, str(ifid))
            for protocol, volume in await _protocols(
                context, INTERFACE, {"ifid": str(ifid), "ndpistats_mode": "sinceStartup"}
            ):
                readings.add("interface.l7_bytes", volume, interface=port, protocol=protocol)
            for address in busiest(await on_interface(context, ifid)):
                asked += 1
                try:
                    found = await _protocols(context, HOST, {"ifid": str(ifid), "host": address})
                except CollectorFailed as failure:
                    # A host can go between the list and the question. It is skipped, unless
                    # none can be read, which is not a host that went.
                    refused.append(failure)
                    continue
                for protocol, volume in found:
                    readings.add("host.l7_bytes", volume, host=address, protocol=protocol)
        if asked and len(refused) == asked:
            raise refused[0]
        return Outcome(items=await readings.save())


def busiest(hosts: Sequence[Mapping[str, object]]) -> list[str]:
    """The addresses of the hosts that have moved the most bytes, the most first."""
    sized = [
        (number(_bytes(host).get("total")) or 0.0, address)
        for host in hosts
        if (address := traffic.text(host, "ip"))
    ]
    return [address for _, address in sorted(sized, reverse=True)[:HOSTS]]


def _bytes(host: Mapping[str, object]) -> Mapping[str, object]:
    return probes.as_object(host.get("bytes")) or {}


async def _protocols(
    context: Context, path: str, query: Mapping[str, str]
) -> list[tuple[str, float]]:
    """The protocols one answer lists with their bytes, the largest first. An answer that isn't
    a list of them is a failure; an entry that has no name or no bytes is left out."""
    rows = probes.as_array(await read(context, path, {**query, "collapse_stats": "false"}))
    if rows is None:
        raise CollectorFailed(probes.unexpected(PRODUCT).message)
    found = [
        (label, volume)
        for row in rows
        if (entry := probes.as_object(row)) is not None
        and (label := traffic.text(entry, "label"))
        and (volume := number(entry.get("value"))) is not None
    ]
    return sorted(found, key=lambda item: item[1], reverse=True)[:PROTOCOLS]
