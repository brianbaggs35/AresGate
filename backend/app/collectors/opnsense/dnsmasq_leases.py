"""The devices that hold a lease from the firewall's Dnsmasq DHCP server, kept as devices.

``GET /api/dnsmasq/leases/search`` lists the leases dnsmasq has given out, IPv4 and IPv6 (see
``leases``). Dnsmasq writes only the leases that haven't run out."""

from datetime import timedelta

from app.collectors.base import Collector, Context, Outcome
from app.collectors.opnsense import leases

LEASES_PATH = "/api/dnsmasq/leases/search"


class DnsmasqLeases(Collector):
    key = "opnsense-dnsmasq-leases"
    title = "Devices (Dnsmasq leases)"
    summary = (
        "Reads the DHCP leases of the firewall's Dnsmasq every five minutes and keeps the device "
        "of each: its MAC and IP address, its host name and who made its network card."
    )
    interval = timedelta(minutes=5)
    timeout = timedelta(minutes=1)
    integration = "opnsense"
    connection = "api"
    module = "dnsmasq"

    async def collect(self, context: Context) -> Outcome:
        return await leases.collect(context, LEASES_PATH)
