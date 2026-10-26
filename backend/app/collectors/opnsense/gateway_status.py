"""Whether each of the firewall's gateways is up, and how its link is doing, kept as metrics.

``GET /api/routes/gateway/status`` answers with ``items``, one object for each gateway: its
``name`` and ``status`` (``none`` when nothing is wrong, ``delay``, ``loss`` or ``delay+loss``
when the link is poor, ``down`` and ``force_down`` when it is not usable) and, for a gateway whose
monitoring has measured it, its ``delay`` (``1.2 ms``), ``stddev`` (``0.3 ms``) and ``loss``
(``0.0 %``). What it has no reading of is ``~``."""

from datetime import timedelta

from app.collectors import traffic
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.opnsense.api import PRODUCT, read
from app.collectors.opnsense.readings import Readings, leading_number
from app.integrations import probes

STATUS_PATH = "/api/routes/gateway/status"
_DOWN = frozenset({"down", "force_down"})


class GatewayStatus(Collector):
    key = "opnsense-gateway-status"
    title = "Gateways"
    summary = (
        "Reads whether each gateway is up, and its delay, jitter and packet loss, every minute "
        "and keeps each as a metric."
    )
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = "opnsense"
    connection = "api"
    module = "firewall"

    async def collect(self, context: Context) -> Outcome:
        answer = probes.as_object(await read(context, STATUS_PATH))
        gateways = probes.as_array(answer.get("items")) if answer else None
        if gateways is None:
            raise CollectorFailed(probes.unexpected(PRODUCT).message)
        readings = Readings(context)
        for item in gateways:
            gateway = probes.as_object(item)
            name = traffic.text(gateway, "name") if gateway else ""
            if gateway is None or not name:
                continue
            down = traffic.text(gateway, "status").lower() in _DOWN
            readings.add("gateway.up", 0.0 if down else 1.0, gateway=name)
            readings.add("gateway.latency_ms", leading_number(gateway.get("delay")), gateway=name)
            readings.add("gateway.jitter_ms", leading_number(gateway.get("stddev")), gateway=name)
            readings.add("gateway.loss_percent", leading_number(gateway.get("loss")), gateway=name)
        return Outcome(items=await readings.save())
