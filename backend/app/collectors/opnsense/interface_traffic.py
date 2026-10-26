"""What has passed through each of the firewall's network interfaces, kept as metrics.

``GET /api/diagnostics/interface/get_interface_statistics`` answers with ``statistics``, an
object with a member for each address of each interface, from ``netstat``: the interface's
``name`` (``igc0``), the ``network`` it is for (``<Link#1>`` for the interface itself, and a
network for each address it has) and the counters since it came up. The counters are kept as
they are, rising; a chart takes the difference between two readings to find the speed."""

import re
from collections.abc import Mapping
from datetime import timedelta

from app.collectors import traffic
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.opnsense.api import PRODUCT, read
from app.collectors.readings import Readings, number
from app.integrations import probes

STATISTICS_PATH = "/api/diagnostics/interface/get_interface_statistics"
# What netstat calls each counter, and what it is kept as.
_COUNTERS = (
    ("received-bytes", "interface.bytes_in"),
    ("sent-bytes", "interface.bytes_out"),
    ("received-packets", "interface.packets_in"),
    ("sent-packets", "interface.packets_out"),
    ("received-errors", "interface.errors_in"),
    ("send-errors", "interface.errors_out"),
    ("dropped-packets", "interface.drops_in"),
)
# Not a network the firewall serves: its own loopback, the logging, state-sync and encapsulation
# pseudo interfaces.
_INTERNAL = re.compile(r"^(?:lo|pflog|pfsync|enc)\d*$")


class InterfaceTraffic(Collector):
    key = "opnsense-interface-traffic"
    title = "Interface traffic"
    summary = (
        "Reads the bytes, packets and errors that have passed through each network interface "
        "every minute and keeps them as metrics."
    )
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = "opnsense"
    connection = "api"
    module = "firewall"

    async def collect(self, context: Context) -> Outcome:
        answer = probes.as_object(await read(context, STATISTICS_PATH))
        statistics = probes.as_object(answer.get("statistics")) if answer else None
        if statistics is None:
            raise CollectorFailed(probes.unexpected(PRODUCT).message)
        readings = Readings(context)
        for name, counters in interfaces(statistics).items():
            for member, metric in _COUNTERS:
                readings.add(metric, number(counters.get(member)), interface=name)
        return Outcome(items=await readings.save())


def interfaces(statistics: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """The counters of each interface that serves a network, by name. An interface is listed once
    for itself and once for each address it has; the counters of the first are the ones that
    count everything, so it is the one taken, or else whichever came first."""
    chosen: dict[str, dict[str, object]] = {}
    own: set[str] = set()
    for member in statistics.values():
        node = probes.as_object(member)
        name = traffic.text(node, "name") if node else ""
        if node is None or not name or _INTERNAL.match(name):
            continue
        is_own = traffic.text(node, "network").startswith("<Link#")
        if name not in chosen or (is_own and name not in own):
            chosen[name] = node
        if is_own:
            own.add(name)
    return chosen
