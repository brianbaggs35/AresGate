"""The same alert, seen by two programs.

OPNsense's intrusion detection, ntopng and Wazuh can each raise an alert about the very same
traffic, and so can one program on two interfaces. They are different detectors and it matters
that more than one agrees, so both are kept and an incident lists them, but they are *one alert*:
counting them twice is how a home network ends up with twice the alerts it had.

An alert is a twin of an earlier one when a different program reported it within moments, about
the same source and the same destination (or the same port, where the address differs because the
firewall translated it: one end the internet's address and the other the home network's). The
earlier is the original, and the twin points at it (``Event.twin_of``) so that counting an alert
once is a filter. Two collectors that store at the very same moment can each miss the other; the
next pair is caught.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event

# How far apart in time two programs' reports of one alert can be. Programs timestamp by when a
# flow began, when it was seen or when it ended, which can be a minute or two apart.
WINDOW: Final = timedelta(seconds=120)
ALERT: Final = "alert"

Address = IPv4Address | IPv6Address


def _private(address: Address) -> bool:
    return not address.is_global


def same_flow(one: Event, other: Event) -> bool:
    """Whether two alerts are about the same traffic."""
    if one.src_address is None or one.src_address != other.src_address:
        return False
    if one.protocol and other.protocol and one.protocol != other.protocol:
        return False
    same_port = one.dst_port is not None and one.dst_port == other.dst_port
    if one.dst_port is not None and other.dst_port is not None and not same_port:
        return False
    if one.dst_address is None or other.dst_address is None:
        # Nothing to tell them apart by but the port.
        return same_port
    if one.dst_address == other.dst_address:
        return True
    # Different addresses are one flow only if the firewall translated one: the internet's address
    # on one side, the home network's on the other, and the same port.
    return same_port and _private(one.dst_address) != _private(other.dst_address)


def find_originals(candidates: Sequence[Event], new: Event) -> Event | None:
    """The earliest alert of the candidates that ``new`` is a twin of, if any."""
    for earlier in sorted(candidates, key=lambda item: item.id):
        if (
            earlier.id < new.id
            and earlier.source != new.source
            and abs(earlier.occurred_at - new.occurred_at) <= WINDOW
            and same_flow(earlier, new)
        ):
            return earlier
    return None


def mark(db: Session, ids: Sequence[int], first: datetime, last: datetime) -> int:
    """Marks the alerts among the events just stored (their ids, and the times they span) that
    another program had already reported, and returns how many. The caller commits."""
    stored = list(
        db.scalars(
            select(Event).where(
                Event.id.in_(ids),
                Event.occurred_at >= first,
                Event.occurred_at <= last,
                Event.kind == ALERT,
                Event.src_address.is_not(None),
            )
        )
    )
    if not stored:
        return 0
    addresses = {event.src_address for event in stored}
    nearby = list(
        db.scalars(
            select(Event).where(
                Event.kind == ALERT,
                Event.src_address.in_(addresses),
                Event.occurred_at >= first - WINDOW,
                Event.occurred_at <= last + WINDOW,
                Event.twin_of.is_(None),
            )
        )
    )
    marked = 0
    for event in sorted(stored, key=lambda item: item.id):
        original = find_originals(nearby, event)
        if original is None:
            continue
        event.twin_of = original.id
        # Not an original any more: a third program's report is a twin of the first.
        nearby = [item for item in nearby if item.id != event.id]
        marked += 1
    db.flush()
    return marked
