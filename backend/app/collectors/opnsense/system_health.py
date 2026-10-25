"""The firewall's health: its load, how long it has been up, its memory and its disks, kept as
metrics.

Three requests, all of the dashboard's: ``system_time`` (the load averages, as the text
``0.31, 0.30, 0.27``, and the uptime, as ``1 day, 02:03:04`` in the firewall's language),
``system_resources`` (the memory, in bytes) and ``system_disk`` (a ``devices`` list with each
file system's size, use and mount point; newer versions also give bytes)."""

import re
from datetime import timedelta

from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.opnsense import traffic
from app.collectors.opnsense.api import PRODUCT, read
from app.collectors.opnsense.readings import Readings, number
from app.integrations import probes

TIME_PATH = "/api/diagnostics/system/system_time"
RESOURCES_PATH = "/api/diagnostics/system/system_resources"
DISK_PATH = "/api/diagnostics/system/system_disk"
# The days are a number and a word in the firewall's language, which can be any: "1 day, ".
_UPTIME = re.compile(r"^(?:(\d+)\D+)?(\d{1,2}):(\d{2}):(\d{2})$")
_LOADS = ("system.load_1m", "system.load_5m", "system.load_15m")
# The file systems on a disk, not the ones OPNsense makes in memory or the install media.
_DISKS = frozenset({"ufs", "zfs"})


class SystemHealth(Collector):
    key = "opnsense-system-health"
    title = "System health"
    summary = (
        "Reads the firewall's load, uptime, memory and disk space every minute and keeps each "
        "as a metric."
    )
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = "opnsense"
    connection = "api"
    module = "firewall"

    async def collect(self, context: Context) -> Outcome:
        readings = Readings(context)
        _times(readings, await read(context, TIME_PATH))
        _memory(readings, await read(context, RESOURCES_PATH))
        _disks(readings, await read(context, DISK_PATH))
        if not readings.samples:
            raise CollectorFailed(probes.unexpected(PRODUCT).message)
        return Outcome(items=await readings.save())


def uptime_seconds(shown: object) -> float | None:
    """How long the firewall has been up, from the text it shows it as, such as ``1 day,
    02:03:04`` or ``00:42:10``."""
    found = _UPTIME.match(shown.strip()) if isinstance(shown, str) else None
    if found is None:
        return None
    days, hours, minutes, seconds = (int(part or 0) for part in found.groups())
    return float(days * 86400 + hours * 3600 + minutes * 60 + seconds)


def _times(readings: Readings, answer: object) -> None:
    data = probes.as_object(answer) or {}
    readings.add("system.uptime_seconds", uptime_seconds(data.get("uptime")))
    loads = data.get("loadavg")
    # "N/A", when the firewall can't tell, has no commas.
    parts = loads.split(",") if isinstance(loads, str) else []
    if len(parts) == len(_LOADS):
        for name, part in zip(_LOADS, parts, strict=True):
            readings.add(name, number(part))


def _memory(readings: Readings, answer: object) -> None:
    memory = probes.as_object((probes.as_object(answer) or {}).get("memory")) or {}
    readings.add("system.memory_total_bytes", number(memory.get("total")))
    readings.add("system.memory_used_bytes", number(memory.get("used")))


def _disks(readings: Readings, answer: object) -> None:
    devices = probes.as_array((probes.as_object(answer) or {}).get("devices")) or []
    for device in devices:
        disk = probes.as_object(device)
        mount = traffic.text(disk, "mountpoint") if disk else ""
        if disk is None or not mount or traffic.text(disk, "type") not in _DISKS:
            continue
        readings.add("disk.used_percent", number(disk.get("used_pct")), mount=mount)
        readings.add("disk.used_bytes", number(disk.get("used_bytes")), mount=mount)
        readings.add("disk.total_bytes", number(disk.get("total_bytes")), mount=mount)
