"""What was sent, and between whom: the alerts of an incident as the conversations they are about.

An alert says who it is about and a few words about what happened. The program that raised it
often knows a good deal more about the flow it was about: what the other end is called and where
it is, whether it is on a blacklist, what kind of traffic it was, for how long and how much it
carried. Several programs may describe the same flow, and one may know what another does not.

The alerts of an incident are grouped here by the two addresses, the port and the protocol, which
is what makes a conversation, and everything the programs said of each is put together once:
the first thing any of them said of each member is kept, so two programs that describe the same
flow are one description, and what one program knows of an address (its name, its country, its
blacklist) is told of that address in every conversation. A flow that was reported again and again
is one conversation with that many alerts.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from app.incidents import evidence, occurrences
from app.incidents.occurrences import Occurrence

# How many conversations are told of, the busiest first, and how many names of what was asked for
# each has room for.
LIMIT: Final = 8
NAMES_PER: Final = 3
# The kinds of thing an alert names that say what the traffic asked for.
ASKED_FOR: Final = ("hostname", "dns", "sni", "url")


@dataclass(frozen=True)
class End:
    """One end of a conversation: the address, and what the programs said of it."""

    address: str
    name: str | None
    port: int | None
    # What the port is for, as a program names it (the other pages know the well-known ones).
    service: str | None
    country: str | None
    # ``local`` or ``remote``, as a program says it.
    location: str | None
    blacklisted: bool


@dataclass(frozen=True)
class Conversation:
    """The alerts of one flow's kind: from this address to that one, to a port, over a protocol."""

    client: End
    server: End
    protocol: str | None
    # What kind of traffic a program recognised, such as ``dns``.
    app: str | None
    # How many alerts there were, of how many kinds, and when the first and the last were.
    alerts: int
    kinds: int
    first_at: datetime
    last_at: datetime
    # How serious the worst of them was, on the scale of ``Severity``.
    severity: int
    # The biggest flow any program counted: what the client sent and what it got back, and how long
    # the longest went on, in seconds. None where no program said.
    bytes_out: int | None
    bytes_in: int | None
    duration: int | None
    # What the traffic asked for, such as the name looked up.
    names: list[evidence.Indicator]
    # The programs that reported it, the one that reported most first.
    programs: list[str]


@dataclass(frozen=True)
class Conversations:
    items: list[Conversation]
    # How many there were, which is more than ``items`` where it is cut to fit.
    total: int


type _Key = tuple[str, str, int | None, str | None]


def _larger(known: int | None, found: int | None) -> int | None:
    if known is None or (found is not None and found > known):
        return found
    return known


class _Draft:
    """What is known of one conversation, while the alerts are being read."""

    def __init__(self, key: _Key, occurrence: Occurrence) -> None:
        signal = occurrence.first
        self.key = key
        self.alerts = 0
        self.kinds = 0
        self.first_at = signal.occurred_at
        self.last_at = occurrence.last_at
        self.severity = signal.severity
        self.bytes_out: int | None = None
        self.bytes_in: int | None = None
        self.duration: int | None = None
        self.app: str | None = None
        self.service: str | None = None
        self.names: dict[tuple[str, str], None] = {}
        self.programs: Counter[str] = Counter()

    def count(self, occurrence: Occurrence) -> None:
        signal = occurrence.first
        self.alerts += occurrence.count
        self.kinds += 1
        self.first_at = min(self.first_at, signal.occurred_at)
        self.last_at = max(self.last_at, occurrence.last_at)
        self.severity = max(self.severity, signal.severity)

    def learn(self, source: str, count: int, said: evidence.Evidence | None) -> None:
        """Takes in what one program said of one alert of the conversation."""
        self.programs[source] += count
        if said is None:
            return
        volume = said.get("traffic", {})
        self.bytes_out = _larger(self.bytes_out, volume.get("bytes_out"))
        self.bytes_in = _larger(self.bytes_in, volume.get("bytes_in"))
        flow = said.get("flow", {})
        self.duration = _larger(self.duration, flow.get("duration"))
        self.app = self.app or said.get("app") or None
        self.service = self.service or flow.get("server", {}).get("service")
        for each in said["indicators"]:
            if each["kind"] in ASKED_FOR:
                self.names.setdefault((each["kind"], each["value"]))


def _remember(known: dict[str, evidence.Endpoint], found: evidence.Endpoint) -> None:
    """What a program said of an address, added to what is known of it: the first word on each
    thing stands, and an address on any blacklist is on one."""
    address = found.get("address")
    if not address:
        return
    here = known.setdefault(address, {})
    for key in ("name", "country", "location"):
        if key in found and key not in here:
            here[key] = found[key]  # type: ignore[literal-required]
    if found.get("blacklisted"):
        here["blacklisted"] = True


def _end(
    address: str, port: int | None, service: str | None, known: dict[str, evidence.Endpoint]
) -> End:
    said = known.get(address, {})
    return End(
        address=address,
        name=said.get("name"),
        port=port,
        service=service,
        country=said.get("country"),
        location=said.get("location"),
        blacklisted=said.get("blacklisted", False),
    )


def of(found: Sequence[Occurrence]) -> Conversations:
    """The conversations of an incident's occurrences, with what the programs said of them put
    together: the busiest first."""
    known: dict[str, evidence.Endpoint] = {}
    drafts: dict[_Key, _Draft] = {}
    for occurrence in found:
        signal = occurrence.first
        if signal.src_address is None or signal.dst_address is None:
            continue
        key: _Key = (
            str(signal.src_address),
            str(signal.dst_address),
            signal.dst_port,
            signal.protocol,
        )
        draft = drafts.setdefault(key, _Draft(key, occurrence))
        draft.count(occurrence)
        for source, count, said in occurrences.reports(occurrence):
            draft.learn(source, count, said)
            for side in ("client", "server"):
                if said is not None and (end := said.get("flow", {}).get(side)):
                    _remember(known, end)
    ranked = sorted(
        drafts.values(), key=lambda draft: (-draft.alerts, draft.first_at, draft.key[:2])
    )
    return Conversations(
        items=[
            Conversation(
                client=_end(draft.key[0], None, None, known),
                server=_end(draft.key[1], draft.key[2], draft.service, known),
                protocol=draft.key[3],
                app=draft.app,
                alerts=draft.alerts,
                kinds=draft.kinds,
                first_at=draft.first_at,
                last_at=draft.last_at,
                severity=draft.severity,
                bytes_out=draft.bytes_out,
                bytes_in=draft.bytes_in,
                duration=draft.duration,
                names=[
                    evidence.Indicator(kind=kind, value=value)
                    for kind, value in list(draft.names)[:NAMES_PER]
                ],
                programs=[source for source, _ in draft.programs.most_common()],
            )
            for draft in ranked[:LIMIT]
        ],
        total=len(ranked),
    )
