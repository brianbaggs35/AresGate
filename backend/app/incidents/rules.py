"""How serious an incident is and how sure AresGate is that it is real, worked out from a few
facts about its signals and explained in plain words.

Confidence is a sum of reasons. Each reason has a rule, the points it adds and a sentence a
person can read, so the incident can say why it is as sure as it is, and nothing is a score no
one can account for. It is capped at 100. The points are a judgement, written down here so that
they can be argued with in one place: a signal worth acting on is a serious one that more than
one program agrees on, that keeps happening or that has been acted on.
"""

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Final, Literal

from app.events.event import Severity
from app.integrations import registry

Level = Literal["low", "medium", "high"]

# What the most serious signal is worth on its own.
SEVERITY_POINTS: Final[dict[Severity, int]] = {
    Severity.INFO: 0,
    Severity.LOW: 10,
    Severity.MEDIUM: 25,
    Severity.HIGH: 40,
    Severity.CRITICAL: 55,
}
# Each program beyond the first that saw it, up to two more.
SOURCE_POINTS: Final = 15
MAX_EXTRA_SOURCES: Final = 2
# Once it has happened this many times, and this many.
REPEATED: Final = ((20, 20), (5, 10))
# A ban is a decision by a program that it was an attack.
BAN_POINTS: Final = 20
# It reached or came from this many other addresses.
SPREAD_MINIMUM: Final = 3
SPREAD_POINTS: Final = 10
MAX_CONFIDENCE: Final = 100

# Where the words low, medium and high are drawn, for the list and for alarms.
MEDIUM_FROM: Final = 35
HIGH_FROM: Final = 65

MAX_TITLE: Final = 200


@dataclass(frozen=True)
class Facts:
    """What the signals of an incident add up to: all that scoring needs of them."""

    subject: str
    # The most serious signal's severity, which program reported it and what it said.
    severity: Severity
    top_source: str
    top_summary: str
    # The programs that reported any of the signals.
    sources: Sequence[str]
    signal_count: int
    # Whether any signal was a ban.
    banned: bool
    # How many addresses besides the subject the signals name.
    others: int


@dataclass(frozen=True)
class Reason:
    """One thing that makes AresGate sure."""

    rule: str
    points: int
    text: str


@dataclass(frozen=True)
class Assessment:
    confidence: int
    reasons: list[Reason]

    def as_json(self) -> list[dict[str, str | int]]:
        return [asdict(reason) for reason in self.reasons]


def level_of(confidence: int) -> Level:
    """Low, medium or high: the word for a confidence."""
    if confidence >= HIGH_FROM:
        return "high"
    return "medium" if confidence >= MEDIUM_FROM else "low"


def name_of(source: str) -> str:
    """What an integration is called, or its key for one this version doesn't know."""
    known = registry.INTEGRATIONS.get(source)
    return known.name if known else source


def _list(names: Sequence[str]) -> str:
    """``Wazuh and OPNsense``, ``Wazuh, OPNsense and CrowdSec``: two names or more."""
    return f"{', '.join(names[:-1])} and {names[-1]}"


def assess(facts: Facts) -> Assessment:
    """The reasons for an incident's confidence, and the confidence they add up to."""
    reasons: list[Reason] = []

    reasons.append(
        Reason(
            "strongest",
            SEVERITY_POINTS[facts.severity],
            f"The most serious signal is rated {facts.severity.name.lower()} by "
            f"{name_of(facts.top_source)}: {facts.top_summary}",
        )
    )

    extra = min(len(facts.sources) - 1, MAX_EXTRA_SOURCES)
    if extra > 0:
        reasons.append(
            Reason(
                "corroborated",
                SOURCE_POINTS * extra,
                f"{len(facts.sources)} programs saw it: "
                f"{_list([name_of(source) for source in facts.sources])}.",
            )
        )

    for count, points in REPEATED:
        if facts.signal_count >= count:
            reasons.append(
                Reason("repeated", points, f"It has set off {facts.signal_count} signals.")
            )
            break

    if facts.banned:
        reasons.append(Reason("banned", BAN_POINTS, "A program banned it."))

    if facts.others >= SPREAD_MINIMUM:
        reasons.append(
            Reason("spread", SPREAD_POINTS, f"{facts.others} other addresses are involved.")
        )

    confidence = min(MAX_CONFIDENCE, sum(reason.points for reason in reasons))
    return Assessment(confidence, reasons)


def title_of(facts: Facts) -> str:
    """What the incident is called in a list: what its strongest signal said, and who it is
    about unless that is already in it."""
    said = facts.top_summary
    if facts.subject.startswith("rule:") or facts.subject in said:
        title = said
    else:
        title = f"{said} ({facts.subject})"
    return title if len(title) <= MAX_TITLE else f"{title[: MAX_TITLE - 1]}…"
