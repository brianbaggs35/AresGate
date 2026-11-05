"""Repeats: the same thing happening again and again is one thing that happened many times.

A scanner that sweeps a port 3,000 times raises 3,000 alerts, and every one of them says the same
words about the same two addresses. Listing them, counting them and sending them to an AI one at
a time is how a small network drowns in "alerts". They are grouped here: signals that agree on the
program, the words, the severity, the two ends and the port are one occurrence, with a count and
the time of its first and last.
"""

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.models import IncidentSignal


@dataclass(frozen=True)
class Occurrence:
    """One kind of signal in an incident's timeline, and how often it happened."""

    first: IncidentSignal
    count: int
    last_at: datetime
    # How many of them another program also reported (see ``Event.twin_of``).
    duplicates: int


def key_of(signal: IncidentSignal) -> Hashable:
    """What makes two signals the same thing: everything but the time and the source port, which
    is different for every connection."""
    return (
        signal.source,
        signal.kind,
        signal.severity,
        signal.signature or signal.summary,
        signal.src_address,
        signal.dst_address,
        signal.dst_port,
        signal.protocol,
        signal.verdict,
    )


def group(signals: Sequence[IncidentSignal]) -> list[Occurrence]:
    """The signals, which are oldest first, as occurrences in the order each first happened."""
    found: dict[Hashable, Occurrence] = {}
    for signal in signals:
        key = key_of(signal)
        known = found.get(key)
        if known is None:
            found[key] = Occurrence(signal, 1, signal.occurred_at, int(signal.duplicate))
        else:
            found[key] = Occurrence(
                known.first,
                known.count + 1,
                max(known.last_at, signal.occurred_at),
                known.duplicates + int(signal.duplicate),
            )
    return list(found.values())
