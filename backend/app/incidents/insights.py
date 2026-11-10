"""What the programs, between them, knew of an incident.

Each program reports its own kind of detail (see ``evidence.py``), and an incident that several of
them saw has all of it: the techniques Wazuh matched, the host names Suricata read out of the
traffic, the application ntopng recognised. Here it is added up, one alert at a time: an alert
that happened four hundred times counts its techniques four hundred times, one that two programs
reported counts what both said once, and a program that said nothing more than the basics is
listed as one that did.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from app.incidents import evidence
from app.incidents.occurrences import Occurrence

# How many of each there are room to show.
LIMIT: Final = 12

# What a program can add to an incident, in the order it is listed, by what it is called.
ADDS: Final = (
    ("mitre", "MITRE ATT&CK techniques"),
    ("tags", "Rule groups and categories"),
    ("host", "The machine it was about"),
    ("app", "The application"),
    ("indicators", "Hosts, URLs and users it named"),
    ("traffic", "How much traffic it was"),
    ("excerpt", "The log line"),
    ("facts", "The rule's details"),
)


@dataclass(frozen=True)
class Technique:
    id: str
    tactic: str
    name: str
    count: int


@dataclass(frozen=True)
class Counted:
    """A word, and how many alerts it was said of."""

    value: str
    count: int


@dataclass(frozen=True)
class Named:
    """What an alert named (``kind`` says what sort of thing), and how many alerts did."""

    kind: str
    value: str
    count: int


@dataclass(frozen=True)
class Contribution:
    """What one program told of the incident: how many of its alerts it reported, and what kinds
    of detail it gave besides the basics."""

    source: str
    reports: int
    adds: list[str]


@dataclass(frozen=True)
class Insights:
    techniques: list[Technique]
    tags: list[Counted]
    hosts: list[Counted]
    apps: list[Counted]
    named: list[Named]
    programs: list[Contribution]

    @property
    def empty(self) -> bool:
        """Whether no program said anything beyond the basics."""
        return not (self.techniques or self.tags or self.hosts or self.apps or self.named) and all(
            not each.adds for each in self.programs
        )


def _top[T](counts: Counter[T]) -> list[tuple[T, int]]:
    """The commonest first, and alike ones in the order they are said, which is stable."""
    return sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))[:LIMIT]


def _each(occurrence: Occurrence) -> Iterable[tuple[str, int, evidence.Evidence | None]]:
    """The reports of an occurrence by program: the program, how many of its alerts, what it said.
    The first report is the occurrence's own; the others are the programs that agreed."""
    yield occurrence.first.source, occurrence.count, evidence.load(occurrence.first)
    for confirmation in occurrence.confirmations:
        yield confirmation.source, confirmation.count, confirmation.evidence


class _Seen:
    """What the programs said of one alert, each thing once, however many of them said it."""

    def __init__(self) -> None:
        self.techniques: dict[str, tuple[str, str]] = {}
        self.tags: set[str] = set()
        self.named: set[tuple[str, str]] = set()
        self.hosts: set[str] = set()
        self.apps: set[str] = set()

    def add(self, said: evidence.Evidence) -> None:
        for each in said.get("mitre", []):
            self.techniques.setdefault(each["id"], (each["tactic"], each["technique"]))
        self.tags.update(said.get("tags", []))
        self.named.update((each["kind"], each["value"]) for each in said.get("indicators", []))
        if host := said.get("host"):
            self.hosts.add(host)
        if app := said.get("app"):
            self.apps.add(app)


def _count[T](counts: Counter[T], found: Iterable[T], weight: int) -> None:
    for each in found:
        counts[each] += weight


class _Tally:
    """What the alerts said between them: each thing and how many alerts it was said of."""

    def __init__(self) -> None:
        self.techniques: dict[str, tuple[str, str]] = {}
        self.technique_counts: Counter[str] = Counter()
        self.tags: Counter[str] = Counter()
        self.named: Counter[tuple[str, str]] = Counter()
        self.hosts: Counter[str] = Counter()
        self.apps: Counter[str] = Counter()

    def add(self, seen: _Seen, weight: int) -> None:
        """Counts what was said of an alert that happened ``weight`` times."""
        self.techniques.update(seen.techniques)
        _count(self.technique_counts, seen.techniques, weight)
        _count(self.tags, seen.tags, weight)
        _count(self.named, seen.named, weight)
        _count(self.hosts, seen.hosts, weight)
        _count(self.apps, seen.apps, weight)


def of(occurrences: Sequence[Occurrence]) -> Insights:
    """Adds up what the programs said, for the occurrences of an incident."""
    tally = _Tally()
    reports: Counter[str] = Counter()
    adds: dict[str, set[str]] = {}
    for occurrence in occurrences:
        # What two programs both said of an alert is said once.
        seen = _Seen()
        for source, count, said in _each(occurrence):
            reports[source] += count
            gave = adds.setdefault(source, set())
            if said is not None:
                gave.update(key for key, _ in ADDS if said.get(key))
                seen.add(said)
        tally.add(seen, occurrence.count)
    return Insights(
        techniques=[
            Technique(ident, *tally.techniques[ident], count)
            for ident, count in _top(tally.technique_counts)
        ],
        tags=[Counted(word, count) for word, count in _top(tally.tags)],
        hosts=[Counted(word, count) for word, count in _top(tally.hosts)],
        apps=[Counted(word, count) for word, count in _top(tally.apps)],
        named=[Named(kind, value, count) for (kind, value), count in _top(tally.named)],
        programs=[
            Contribution(source, count, [label for key, label in ADDS if key in adds[source]])
            for source, count in sorted(reports.items(), key=lambda item: (-item[1], item[0]))
        ],
    )
