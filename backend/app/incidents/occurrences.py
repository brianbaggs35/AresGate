"""Repeats: the same thing happening again and again is one thing that happened many times.

A scanner that sweeps a port 3,000 times raises 3,000 alerts, and every one of them says the same
words about the same two addresses. Listing them, counting them and sending them to an AI one at
a time is how a small network drowns in "alerts". They are grouped here: signals that agree on the
program, the words, the severity, the two ends and the port are one occurrence, with a count and
the time of its first and last.
"""

from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from app.incidents import evidence
from app.models import IncidentSignal


@dataclass(frozen=True)
class Confirmation:
    """Another program that reported the same alert moments after the first did: it agrees, and it
    may have seen more. It is not another alert, so it is counted once, with the first."""

    source: str
    signature: str | None
    severity: int
    # How many times it reported it, and when it first and last did.
    count: int
    first_at: datetime
    last_at: datetime
    # What it said besides the basics, from the first of its reports that said any.
    evidence: evidence.Evidence | None


@dataclass(frozen=True)
class Occurrence:
    """One kind of signal in an incident's timeline, and how often it happened."""

    first: IncidentSignal
    count: int
    last_at: datetime
    # How many reports of it another program also made (see ``Event.twin_of``).
    duplicates: int
    # Which programs those were, and what each said.
    confirmations: tuple[Confirmation, ...] = ()


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


def _confirm(known: Sequence[Confirmation], signal: IncidentSignal) -> tuple[Confirmation, ...]:
    """The confirmations with this signal's report added: to its program's, if that program had
    already agreed in the same words, or as a new one."""
    kept = evidence.load(signal)
    for index, one in enumerate(known):
        if (one.source, one.signature) == (signal.source, signal.signature):
            more = replace(
                one,
                severity=max(one.severity, signal.severity),
                count=one.count + 1,
                first_at=min(one.first_at, signal.occurred_at),
                last_at=max(one.last_at, signal.occurred_at),
                evidence=one.evidence or kept,
            )
            return (*known[:index], more, *known[index + 1 :])
    return (
        *known,
        Confirmation(
            signal.source,
            signal.signature,
            signal.severity,
            1,
            signal.occurred_at,
            signal.occurred_at,
            kept,
        ),
    )


def group(signals: Sequence[IncidentSignal]) -> list[Occurrence]:
    """The signals, which are oldest first, as occurrences in the order each first happened. A
    signal that is a twin of another one in the list (the same alert, reported by a program that
    didn't report the first) is no occurrence of its own: it is added to the first's, as a
    confirmation."""
    found: dict[Hashable, Occurrence] = {}
    by_event: dict[int, Hashable] = {}
    twins: list[tuple[int, IncidentSignal]] = []
    originals = {signal.event_id for signal in signals if not signal.duplicate}
    for signal in signals:
        if signal.duplicate and signal.twin_of is not None and signal.twin_of in originals:
            twins.append((signal.twin_of, signal))
            continue
        key = key_of(signal)
        known = found.get(key)
        if known is None:
            found[key] = Occurrence(signal, 1, signal.occurred_at, int(signal.duplicate))
        else:
            found[key] = replace(
                known,
                count=known.count + 1,
                last_at=max(known.last_at, signal.occurred_at),
                duplicates=known.duplicates + int(signal.duplicate),
            )
        if not signal.duplicate:
            by_event.setdefault(signal.event_id, key)
    for original, twin in twins:
        key = by_event[original]
        known = found[key]
        found[key] = replace(
            known,
            duplicates=known.duplicates + 1,
            confirmations=_confirm(known.confirmations, twin),
        )
    return list(found.values())


def reports(occurrence: Occurrence) -> Iterable[tuple[str, int, evidence.Evidence | None]]:
    """What each program said of an occurrence: the program, how many of its alerts, and what it
    said besides the basics. The first report is the occurrence's own; the others are the programs
    that agreed."""
    yield occurrence.first.source, occurrence.count, evidence.load(occurrence.first)
    for confirmation in occurrence.confirmations:
        yield confirmation.source, confirmation.count, confirmation.evidence
