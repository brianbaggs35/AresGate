"""Which collectors there are. Adding one means writing it and listing it here."""

from collections.abc import Iterable, Sequence

from app.collectors.base import Collector
from app.collectors.connection_check import ConnectionCheck
from app.collectors.crowdsec.decisions import Decisions
from app.collectors.ntopng.alerts import Alerts as NtopngAlerts
from app.collectors.ntopng.hosts import Hosts
from app.collectors.ntopng.interface import InterfaceTraffic as NtopngInterfaceTraffic
from app.collectors.opnsense.arp_table import ArpTable
from app.collectors.opnsense.cpu_usage import CpuUsage
from app.collectors.opnsense.crowdsec import PluginAlerts, PluginDecisions
from app.collectors.opnsense.dnsmasq_leases import DnsmasqLeases
from app.collectors.opnsense.firewall_log import FirewallLog
from app.collectors.opnsense.gateway_status import GatewayStatus
from app.collectors.opnsense.interface_traffic import InterfaceTraffic
from app.collectors.opnsense.kea_leases import KeaLeases
from app.collectors.opnsense.suricata_alerts import SuricataAlerts
from app.collectors.opnsense.system_health import SystemHealth
from app.collectors.wazuh.agents import Agents
from app.collectors.wazuh.alerts import Alerts

COLLECTORS: Sequence[Collector] = (
    ConnectionCheck(),
    FirewallLog(),
    SuricataAlerts(),
    PluginDecisions(),
    PluginAlerts(),
    SystemHealth(),
    CpuUsage(),
    InterfaceTraffic(),
    GatewayStatus(),
    ArpTable(),
    DnsmasqLeases(),
    KeaLeases(),
    Decisions(),
    Hosts(),
    NtopngInterfaceTraffic(),
    NtopngAlerts(),
    Alerts(),
    Agents(),
)


def find(key: str, collectors: Iterable[Collector] = COLLECTORS) -> Collector | None:
    return next((item for item in collectors if item.key == key), None)
