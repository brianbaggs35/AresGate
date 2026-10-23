"""Which collectors there are. Adding one means writing it and listing it here."""

from collections.abc import Iterable, Sequence

from app.collectors.base import Collector
from app.collectors.connection_check import ConnectionCheck
from app.collectors.opnsense.firewall_log import FirewallLog

COLLECTORS: Sequence[Collector] = (ConnectionCheck(), FirewallLog())


def find(key: str, collectors: Iterable[Collector] = COLLECTORS) -> Collector | None:
    return next((item for item in collectors if item.key == key), None)
