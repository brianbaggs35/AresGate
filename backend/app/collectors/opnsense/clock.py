"""The time on the firewall.

OPNsense's log says when each line was written in the firewall's own time zone, with no zone
and, in the older log format, no year. What AresGate needs to turn that into a moment is how far
the firewall's time is from UTC, and the firewall's clock says so: it answers with the time as it
shows it. The difference from AresGate's own clock, to the nearest quarter of an hour (time
zones come in those steps), is the time zone; what is left over is the two clocks disagreeing.
"""

from datetime import datetime, timedelta

from app.collectors.base import CollectorFailed, Context
from app.collectors.opnsense.api import read
from app.integrations import probes
from app.models import utcnow

TIME_PATH = "/api/diagnostics/system/system_time"
STEP = timedelta(minutes=15)
# Two clocks further apart than this can't both be right, and the times in the log would be
# wrong by as much, so the collector says so instead of storing them.
MAX_SKEW = timedelta(minutes=5)


async def utc_offset(context: Context) -> timedelta:
    """How far ahead of UTC the firewall's time is."""
    data = probes.as_object(await read(context, TIME_PATH))
    shown = data.get("datetime") if data else None
    local = parse_system_time(shown) if isinstance(shown, str) else None
    if local is None:
        raise CollectorFailed(
            "OPNsense answered with a time in a form AresGate doesn't read, so the times in its "
            "log can't be worked out."
        )
    return offset_from(local, utcnow())


def parse_system_time(shown: str) -> datetime | None:
    """OPNsense's time, such as ``Fri Oct 23 15:01:02 ADT 2026``, without the zone's name."""
    words = shown.split()
    if len(words) != 6:
        return None
    try:
        return datetime.strptime(" ".join([*words[1:4], words[5]]), "%b %d %H:%M:%S %Y")
    except ValueError:
        return None


def offset_from(local: datetime, now: datetime) -> timedelta:
    """The time zone that makes the firewall's local time agree with ``now``. Raises
    ``CollectorFailed`` if the two clocks disagree by more than the zone can explain."""
    difference = local - now.replace(tzinfo=None)
    offset = round(difference / STEP) * STEP
    skew = difference - offset
    if abs(skew) > MAX_SKEW:
        minutes = round(abs(skew).total_seconds() / 60)
        direction = "ahead of" if skew > timedelta(0) else "behind"
        raise CollectorFailed(
            f"OPNsense's clock is {minutes} minutes {direction} AresGate's, so the times in its "
            "log can't be trusted. Set the right time on either one."
        )
    return offset
