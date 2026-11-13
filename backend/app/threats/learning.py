"""Learning from what the owner decides: offering to set a kind aside when they keep dismissing it.

The best security tools learn what their user decides: an analyst who closes the same sort of alert
as benign ten times is offered an end to it. AresGate remembers what the owner says of each
incident (a verdict, dismissing it, taking it up) and groups incidents into kinds
(``app/threats/families.py``), so the two meet here.

Two suggestions are made about a kind, and never by themselves: nothing changes until the owner
says yes, and one they say not now to is not offered again until they have decided twice as many
incidents of that kind.

- **Always background**: most of the incidents the owner has decided were closed as not suspicious,
  low priority or dismissed. Never offered for a kind that has had a chain of stages in it, or any
  sign that it worked, because a scan that turned into more is not one to stop hearing about.
- **Never set aside**: the AI set the kind aside, and the owner keeps taking its incidents up,
  calling them threats or disagreeing with the AI about it.

What the owner has decided also goes into the AI's brief for the kind (``app/ai/families.py``).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal, cast

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.orm import Session

from app.models import Incident, IncidentFamily, ReviewFeedback
from app.threats import calls, overview
from app.threats.settings import Tuning

# What the owner gave an incident that sets it aside: a verdict, or dismissing it.
BENIGN: Final = ("not_suspicious", "low_priority")
BACKGROUND: Final = "background"
WATCH: Final = "watch"
# How many incidents the owner has to have decided before a kind is offered to be set aside, and
# what share of them has to be benign (4 in 5).
MIN_DECIDED: Final = 5
BENIGN_SHARE: Final = (4, 5)
# How many they have to have taken up before a kind the AI cleared is offered to be watched.
MIN_LOUD: Final = 3
# How many suggestions the Threats page shows, and how many kinds are looked at for them.
SHOWN: Final = 3
LOOKED_AT: Final = 20

Call = Literal["background", "watch"]


@dataclass(frozen=True)
class Pattern:
    """What the owner has decided of the incidents of a kind: how many they closed as benign, and
    how many they took up (a verdict that it is a threat, investigating it) or disagreed with the AI
    about."""

    benign: int = 0
    loud: int = 0

    @property
    def decided(self) -> int:
        return self.benign + self.loud


@dataclass(frozen=True)
class Suggestion:
    """What to offer the owner about a kind, why in numbers, and how many incidents it moves."""

    call: Call
    benign: int
    loud: int
    # How many incidents that are going on it would set aside, or bring back out of the background.
    moves: int

    @property
    def decided(self) -> int:
        return self.benign + self.loud

    @property
    def reason(self) -> str:
        if self.call == BACKGROUND:
            return (
                f"You have closed {self.benign} of the {self.decided} incidents of this kind you "
                "decided as not suspicious, low priority or dismissed."
            )
        return (
            f"The AI set this kind aside, and you have taken up {self.loud} of the "
            f"{self.decided} incidents of it you decided, or disagreed with it."
        )


def patterns(db: Session, ids: Sequence[int] | None = None) -> dict[int, Pattern]:
    """What the owner has decided of each kind: the given ones, or those they have decided enough
    of to be offered something. Every incident counts, whether it is going on or not, because a
    dismissed one is over."""
    taken_up = or_(
        Incident.verdict.is_not_distinct_from("threat"),
        and_(Incident.status == "investigating", Incident.status_changed_at.is_not(None)),
    )
    closed = and_(not_(taken_up), or_(Incident.verdict.in_(BENIGN), Incident.status == "dismissed"))
    query = (
        select(
            Incident.family_id,
            func.count().filter(closed),
            func.count().filter(taken_up),
        )
        .where(Incident.family_id.is_not(None))
        .group_by(Incident.family_id)
    )
    if ids is not None:
        query = query.where(Incident.family_id.in_(ids))
    else:
        query = query.having(func.count().filter(or_(closed, taken_up)) >= MIN_LOUD)
    found = {
        cast("int", family): Pattern(benign, loud)
        for family, benign, loud in db.execute(query).tuples()
    }
    disagreed = (
        select(ReviewFeedback.subject_id, func.count())
        .where(
            ReviewFeedback.subject == "family",
            ReviewFeedback.answer == "disagree",
            ReviewFeedback.subject_id.in_(list(found) if ids is None else ids),
        )
        .group_by(ReviewFeedback.subject_id)
    )
    for family, count in db.execute(disagreed).tuples():
        before = found.get(family, Pattern())
        found[family] = Pattern(before.benign, before.loud + count)
    return found


def chained(db: Session, ids: Sequence[int]) -> set[int]:
    """The kinds that have had a chain of stages in them, or a sign that it worked, whether it is
    going on or not."""
    if not ids:
        return set()
    return {
        int(family)
        for family in db.scalars(
            select(Incident.family_id)
            .where(
                Incident.family_id.in_(ids),
                or_(
                    Incident.chain_id.is_not(None),
                    func.cardinality(Incident.stages) > 1,
                    Incident.stages.contains(["foothold"]),
                ),
            )
            .distinct()
        )
        if family is not None
    }


def _set_aside(family: IncidentFamily) -> bool:
    """Whether the AI's judgement of the kind sets it aside, which counts only while it is in
    effect."""
    return family.ai_class in calls.QUIET and calls.counts(family.review, family.ai_class)


def suggestion_for(item: overview.Kind, pattern: Pattern, chain: bool) -> Suggestion | None:
    """What to offer the owner about a kind that is going on, if anything: nothing for a kind they
    have called already, or said not now to and not decided much more of since."""
    family = item.family
    if family.owner_call is not None:
        return None
    offer: Suggestion | None = None
    share, of = BENIGN_SHARE
    if (
        not chain
        and pattern.decided >= MIN_DECIDED
        and pattern.benign * of >= pattern.decided * share
        and item.threats + item.suspects > 0
    ):
        offer = Suggestion(BACKGROUND, pattern.benign, pattern.loud, item.threats + item.suspects)
    elif _set_aside(family) and pattern.loud >= MIN_LOUD and pattern.loud * 2 >= pattern.decided:
        offer = Suggestion(WATCH, pattern.benign, pattern.loud, item.background)
    if (
        offer is not None
        and family.suggestion_dismissed == offer.call
        and offer.decided < 2 * (family.suggestion_dismissed_count or 0)
    ):
        return None
    return offer


def of_kind(db: Session, item: overview.Kind) -> Suggestion | None:
    """What to offer the owner about one kind."""
    family_id = item.family.id
    return suggestion_for(
        item,
        patterns(db, [family_id]).get(family_id, Pattern()),
        family_id in chained(db, [family_id]),
    )


def offers(db: Session, floor: int, tuning: Tuning) -> list[tuple[overview.Kind, Suggestion]]:
    """The suggestions to show on the Threats page: the kinds with the most decided first."""
    found = patterns(db)
    ranked = sorted(found, key=lambda family: (-found[family].decided, family))[:LOOKED_AT]
    chain = chained(db, ranked)
    shown: list[tuple[overview.Kind, Suggestion]] = []
    for family_id in ranked:
        kinds = overview.kinds(db, floor, tuning, family_id=family_id, limit=1).items
        if not kinds:
            continue
        offer = suggestion_for(kinds[0], found[family_id], family_id in chain)
        if offer is not None:
            shown.append((kinds[0], offer))
        if len(shown) == SHOWN:
            break
    return shown


def dismiss(family: IncidentFamily, offer: Suggestion) -> None:
    """The owner said not now: it is not offered again until they have decided twice as many."""
    family.suggestion_dismissed = offer.call
    family.suggestion_dismissed_count = offer.decided
