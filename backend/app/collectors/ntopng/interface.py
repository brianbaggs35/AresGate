"""The interface ntopng watches, as metrics: how much has passed through it, and how many hosts,
devices and flows it holds.

``GET /lua/rest/v2/get/interface/data.lua`` takes the interface (``ifid``) and answers with an
object in ``rsp``: its name (``ifname``), the bytes and packets that came in (``bytes_download``,
``packets_download``) and went out (``bytes_upload``, ``packets_upload``) since ntopng started,
``drops``, the bytes from local hosts to remote ones and back (``local2remote``,
``remote2local``), and how many hosts (``num_hosts``, ``num_local_hosts``), devices
(``num_devices``) and flows (``num_flows``) it holds and how many alerts are engaged now
(``engaged_alerts``). The counters are kept as they are, rising; a chart takes the difference
between two readings.

The unit of the answer's ``throughput_bps`` isn't given in ntopng's documentation, so it isn't
read: the speed is the difference between counters. Read from ntopng's source (``scripts/lua/rest/
v2/get/interface/data.lua``) and from the REST API v2 examples (section 2.1.1). Not tried against a
live ntopng."""

from datetime import timedelta

from app.collectors import traffic
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.ntopng.api import PRODUCT, interface, read
from app.collectors.readings import Readings, number
from app.integrations import probes

PATH = "/lua/rest/v2/get/interface/data.lua"
# What ntopng calls each counter, and what it is kept as. The names are the ones the OPNsense
# collectors give the same things, so a chart can use either.
_READINGS = (
    ("bytes_download", "interface.bytes_in"),
    ("bytes_upload", "interface.bytes_out"),
    ("packets_download", "interface.packets_in"),
    ("packets_upload", "interface.packets_out"),
    ("drops", "interface.drops"),
    ("local2remote", "interface.bytes_local_to_remote"),
    ("remote2local", "interface.bytes_remote_to_local"),
    ("num_hosts", "interface.hosts"),
    ("num_local_hosts", "interface.local_hosts"),
    ("num_devices", "interface.devices"),
    ("num_flows", "interface.flows"),
    ("engaged_alerts", "interface.alerts_engaged"),
)


class InterfaceTraffic(Collector):
    key = "ntopng-interface"
    title = "Interface traffic"
    summary = (
        "Reads how much has passed through the interface ntopng watches every minute, and how "
        "many hosts, devices and flows it holds, and keeps them as metrics."
    )
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = "ntopng"
    connection = "api"

    async def collect(self, context: Context) -> Outcome:
        data = probes.as_object(await read(context, PATH, {"ifid": interface(context)}))
        if data is None:
            raise CollectorFailed(probes.unexpected(PRODUCT).message)
        name = traffic.text(data, "ifname") or interface(context)
        readings = Readings(context)
        for member, metric in _READINGS:
            readings.add(metric, number(data.get(member)), interface=name)
        if not readings.samples:
            raise CollectorFailed("It answered, but the interface isn't in a form AresGate reads.")
        return Outcome(items=await readings.save())
