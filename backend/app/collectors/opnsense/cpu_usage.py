"""How busy the firewall's processors are, kept as a metric.

OPNsense shows it on the dashboard as a stream that never ends, which a collector can't read.
Its system activity page asks ``top`` once, and answers with ``top``'s header lines, one of which
says where the time went: ``CPU:  1.2% user,  0.0% nice,  0.8% system,  0.1% interrupt, 97.9%
idle``. It takes the firewall a couple of seconds, and the privilege to ask is not the
dashboard's."""

import re
from datetime import timedelta

from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.opnsense.api import PRODUCT, read
from app.collectors.opnsense.readings import Readings, number
from app.integrations import probes

ACTIVITY_PATH = "/api/diagnostics/activity/get_activity"
# One of the shares in the line, split at the commas: "96.0% idle".
_IDLE = re.compile(r"^(\d+(?:\.\d+)?)% idle$")


class CpuUsage(Collector):
    key = "opnsense-cpu-usage"
    title = "Processor use"
    summary = "Reads how busy the firewall's processors are every minute and keeps it as a metric."
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = "opnsense"
    connection = "api"
    module = "firewall"

    async def collect(self, context: Context) -> Outcome:
        busy = busy_percent(await read(context, ACTIVITY_PATH))
        if busy is None:
            raise CollectorFailed(probes.unexpected(PRODUCT).message)
        readings = Readings(context)
        readings.add("cpu.usage_percent", busy)
        return Outcome(items=await readings.save())


def busy_percent(answer: object) -> float | None:
    """The share of the time the processors were not idle, from the header lines of ``top``."""
    lines = probes.as_array((probes.as_object(answer) or {}).get("headers")) or []
    for line in lines:
        if not isinstance(line, str) or not line.startswith("CPU:"):
            continue
        for share in line.removeprefix("CPU:").split(","):
            found = _IDLE.match(share.strip())
            if found and (idle := number(found[1])) is not None and idle <= 100:
                return round(100 - idle, 2)
    return None
