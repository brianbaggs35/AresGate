"""A kind of incident that has changed since it was judged.

An AI judges a kind once and the answer covers every incident of it (``app/ai/families.py``).
That is what keeps the cost low, and its risk is a kind that was harmless last month and now
includes an exploit attempt, or comes from somewhere new. So when a kind is judged, what its
incidents were like is kept (its ``Profile``), and as incidents come and go it is compared with
what they are like now. When it differs enough the kind is marked changed, with the reasons in
words, and the AI is asked about it again at the next opportunity its usage level allows
(``app/ai/families.py``). A kind the owner has called stays the owner's, and is not judged
again, but it is marked all the same, so the page can say that it changed.

What counts as enough is deliberately narrow, so the mark means something:

- a stage of an attack it did not have (looking around, trying to get in, a sign it worked),
- a destination port or a device of the owner's it did not touch, but only for a kind that
  touched few: one that already touches every port or every device learns nothing from one more,
- many more addresses behind it than there were.
"""

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final, Self, cast

from sqlalchemy import cast as sql_cast
from sqlalchemy import column as sql_column
from sqlalchemy import exists, func, or_, select, true
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Session

from app.incidents.attention import ACTIVE
from app.models import Incident, IncidentFamily
from app.threats import stages

# How many ports or devices a profile keeps, and how many a change names.
KEPT: Final = 50
SHOWN: Final = 10
# A kind that touched more ports or devices than this is not told by a new one.
FEW: Final = 20
# Addresses behind a kind have to be this many times what they were, and this many more.
RISE: Final = 3
MORE: Final = 20
# A kind is looked at again no sooner than this, and this many are looked at in a run.
EVERY: Final = timedelta(minutes=5)
BATCH: Final = 25
# Where a person's own devices are: private IPv4 networks and unique local IPv6 addresses.
OWN_NETWORKS: Final = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")

STAGES: Final = "stages"
PORTS: Final = "ports"
DEVICES: Final = "devices"
ACTORS: Final = "actors"


@dataclass(frozen=True)
class Profile:
    """What the incidents of a kind that are going on are like."""

    stages: tuple[str, ...] = ()
    ports: tuple[int, ...] = ()
    devices: tuple[str, ...] = ()
    actors: int = 0

    def as_json(self) -> dict[str, Any]:
        return {
            STAGES: list(self.stages),
            PORTS: list(self.ports),
            DEVICES: list(self.devices),
            ACTORS: self.actors,
        }

    @classmethod
    def of(cls, kept: dict[str, Any]) -> Self:
        return cls(
            tuple(kept.get(STAGES, ())),
            tuple(kept.get(PORTS, ())),
            tuple(kept.get(DEVICES, ())),
            int(kept.get(ACTORS, 0)),
        )


def profiles(db: Session, ids: Sequence[int]) -> dict[int, Profile]:
    """What each of the kinds is like now, by its incidents that are going on. A kind with none is
    left out."""
    ids = list(ids)
    if not ids:
        return {}
    going = (Incident.family_id.in_(ids), Incident.status.in_(ACTIVE))
    actors = {
        cast("int", family_id): count
        for family_id, count in db.execute(
            select(Incident.family_id, func.count(Incident.subject.distinct()))
            .where(*going)
            .group_by(Incident.family_id)
        ).tuples()
    }
    found: dict[str, dict[int, set[Any]]] = {
        name: defaultdict(set) for name in (STAGES, PORTS, DEVICES)
    }
    for name, column in (
        (STAGES, Incident.stages),
        (PORTS, Incident.ports),
        (DEVICES, Incident.addresses),
    ):
        each = func.unnest(column).table_valued(sql_column("each")).render_derived().lateral()
        query = select(Incident.family_id, each.c.each).join(each, true()).where(*going)
        if name == DEVICES:
            query = query.where(
                or_(*(each.c.each.op("<<=")(sql_cast(network, INET)) for network in OWN_NETWORKS))
            )
        for family_id, value in db.execute(query.distinct()).tuples():
            found[name][cast("int", family_id)].add(str(value) if name == DEVICES else value)
    return {
        family_id: Profile(
            tuple(name for name in stages.STAGES if name in found[STAGES][family_id]),
            tuple(sorted(found[PORTS][family_id])[:KEPT]),
            tuple(sorted(found[DEVICES][family_id])[:KEPT]),
            count,
        )
        for family_id, count in actors.items()
    }


def compare(before: Profile, now: Profile) -> dict[str, Any]:
    """What is different about a kind now: only what is worth saying, and nothing when it is as it
    was. The result is what is kept on the kind and what ``describe`` puts into words."""
    changed: dict[str, Any] = {}
    if new := [name for name in now.stages if name not in before.stages]:
        changed[STAGES] = new
    if len(before.ports) <= FEW and (new_ports := sorted(set(now.ports) - set(before.ports))):
        changed[PORTS] = new_ports[:SHOWN]
    if len(before.devices) <= FEW and (
        new_devices := sorted(set(now.devices) - set(before.devices))
    ):
        changed[DEVICES] = new_devices[:SHOWN]
    if now.actors >= before.actors * RISE and now.actors - before.actors >= MORE:
        changed[ACTORS] = [before.actors, now.actors]
    return changed


def describe(changes: dict[str, Any], hide: Callable[[str], str] = str) -> list[str]:
    """What changed in words, a line each. ``hide`` is what an address goes through before it is
    said (the AI never sees one)."""
    lines: list[str] = []
    if STAGES in changes:
        names = ", ".join(str(stages.NAMES.get(name, name)).lower() for name in changes[STAGES])
        lines.append(f"It has a stage of an attack it did not have before: {names}.")
    if PORTS in changes:
        lines.append(
            "It now reaches destination ports it did not before: "
            f"{', '.join(str(port) for port in changes[PORTS])}."
        )
    if DEVICES in changes:
        lines.append(
            "It now targets devices it did not before: "
            f"{', '.join(hide(device) for device in changes[DEVICES])}."
        )
    if ACTORS in changes:
        was, now = changes[ACTORS]
        lines.append(f"It comes from many more addresses: {was} when it was judged, {now} now.")
    return lines


def keep(family: IncidentFamily, profile: Profile, now: datetime) -> None:
    """Takes ``profile`` as what the kind is like: it has just been judged, so nothing about it has
    changed since."""
    family.judged_profile = profile.as_json()
    family.changes = None
    family.changed_at = None
    family.drift_checked_at = now


def due(db: Session, now: datetime) -> list[IncidentFamily]:
    """The kinds to compare: judged, or called by the owner, with incidents going on that have
    moved since they were last compared (a kind is compared every few minutes at most)."""
    moved = (
        exists()
        .where(
            Incident.family_id == IncidentFamily.id,
            Incident.status.in_(ACTIVE),
            or_(
                IncidentFamily.drift_checked_at.is_(None),
                Incident.updated_at >= IncidentFamily.drift_checked_at,
                Incident.last_seen_at >= IncidentFamily.drift_checked_at,
            ),
        )
        .correlate(IncidentFamily)
    )
    return list(
        db.scalars(
            select(IncidentFamily)
            .where(
                or_(IncidentFamily.judged_at.is_not(None), IncidentFamily.owner_call.is_not(None)),
                or_(
                    IncidentFamily.drift_checked_at.is_(None),
                    IncidentFamily.drift_checked_at < now - EVERY,
                ),
                moved,
            )
            .order_by(IncidentFamily.drift_checked_at.asc().nulls_first(), IncidentFamily.id)
            .limit(BATCH)
        )
    )


def detect(db: Session, now: datetime) -> int:
    """Compares the kinds that are due with what they were like when they were judged, and marks
    the ones that have changed (or no longer have). A kind with nothing kept to compare with, one
    judged before this was kept, takes what it is like now. Returns how many are marked changed.
    The caller commits."""
    waiting = due(db, now)
    now_like = profiles(db, [family.id for family in waiting])
    marked = 0
    for family in waiting:
        profile = now_like.get(family.id, Profile())
        family.drift_checked_at = now
        if family.judged_profile is None:
            family.judged_profile = profile.as_json()
            continue
        changed = compare(Profile.of(family.judged_profile), profile)
        family.changes = changed or None
        family.changed_at = (family.changed_at or now) if changed else None
        marked += bool(changed)
    db.flush()
    return marked


def lines_of(family: IncidentFamily, hide: Callable[[str], str] = str) -> list[str]:
    """What has changed about a kind, in words: none when it is as it was."""
    return describe(family.changes, hide) if family.changes else []
