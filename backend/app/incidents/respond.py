"""The Incident Response page: what was done about the incidents of the last few days, and which
of them still wait for an answer.

``response.py`` says, for one incident, what CrowdSec, the firewall and Suricata did about its
address. This answers the question above it: of everything that went on lately and is serious
enough to matter, what has been dealt with, and what has not? Each incident is put in one group,
the first that is true:

- ``needs_response``: it is still going on and nothing stops it, or only some of its addresses are
  banned, or it came back after its ban ended.
- ``banned``: CrowdSec's ban holds, or, for a closed incident, held for part of it.
- ``blocked``: the firewall or Suricata turned the address away, and nothing banned it.
- ``ban_ended``: the ban ran out and nothing has been seen since.
- ``closed``: it is resolved and nothing was done, which is fine.
- ``no_address``: it names no address, only an alert, so there is nothing to ban or block.

Only incidents of medium severity or higher count, and not those the owner called not suspicious
or low priority, or dismissed: a page that lists everything answers nothing.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.events.event import Severity
from app.incidents import attention, episode, response
from app.incidents.verdicts import MUTING
from app.models import Incident, IntegrationConnection
from app.models.base import utcnow

GroupKey = Literal["needs_response", "banned", "blocked", "ban_ended", "closed", "no_address"]

# The groups in the order they are shown, with what each is called and what it means.
GROUPS: Final[dict[GroupKey, tuple[str, str]]] = {
    "needs_response": ("Needs a response", "Still going on, and nothing has stopped it."),
    "banned": ("Banned", "CrowdSec has banned the address."),
    "blocked": ("Turned away", "The firewall or Suricata turned the address away."),
    "ban_ended": ("Ban ended", "The ban ran out, and nothing has been seen since."),
    "closed": ("Closed without a response", "Resolved, and nothing was done about it."),
    "no_address": ("Nothing to block", "It names no address, only an alert."),
}
# How far back a page may look, in days.
DAYS: Final = (1, 7, 30)
# The least serious an incident can be to count here.
MINIMUM: Final = Severity.MEDIUM
# How many incidents the page reads at most. A page of more than this has more than anyone can act
# on, and says so.
MAX_INCIDENTS: Final = 200


@dataclass(frozen=True)
class Item:
    """One incident, the group it is in and what was done about it."""

    incident: Incident
    done: response.Response
    group: GroupKey
    # Why it needs a response, in words, when it does.
    why: str | None
    # How many addresses are banned now, when the last of those bans runs out (None where none says
    # how long it lasts), and how many addresses the incident has to have banned.
    banned_now: int
    ban_ends_at: datetime | None
    attackers: int


@dataclass(frozen=True)
class Overview:
    """What the page shows."""

    days: int
    # How many incidents were found, and how many of them the page holds (the most serious first).
    total: int
    items: Sequence[Item]
    # Whether what CrowdSec and OPNsense did can be seen at all: without them "no response" may
    # only mean that nobody can tell.
    crowdsec_connected: bool
    opnsense_connected: bool

    def count(self, group: GroupKey) -> int:
        return sum(1 for item in self.items if item.group == group)


def _holding(done: response.Response, now: datetime) -> list[response.Ban]:
    return [ban for ban in done.bans if ban.in_force(now)]


def _last_ban_end(done: response.Response) -> datetime | None:
    ends = [ban.ends_at for ban in done.bans if ban.real and ban.ends_at is not None]
    return max(ends, default=None)


def _group(
    incident: Incident, done: response.Response, now: datetime
) -> tuple[GroupKey, str | None]:
    active = incident.status in attention.ACTIVE
    state = done.state
    if state == "no_address":
        return "no_address", None
    if state in ("banned", "blocked"):
        return state, None
    if state == "none":
        if active:
            return "needs_response", "Nothing has banned it or turned it away."
        return "closed", None
    if state == "partly":
        if not active:
            return "banned", None
        held = len({ban.address for ban in _holding(done, now)})
        attackers = 1 + episode.neighbours_of(incident.subject, incident.block, incident.addresses)
        return "needs_response", f"Only {held} of its {attackers} addresses are banned."
    # Its ban ended, and it needs a response again only if it went on after that.
    ended = _last_ban_end(done)
    if active and ended is not None and incident.last_seen_at > ended:
        return "needs_response", "It came back after its ban ended."
    return "ban_ended", None


def _item(incident: Incident, done: response.Response, now: datetime) -> Item:
    group, why = _group(incident, done, now)
    holding = _holding(done, now)
    ends = [ban.ends_at for ban in holding if ban.ends_at is not None]
    return Item(
        incident=incident,
        done=done,
        group=group,
        why=why,
        banned_now=len({ban.address for ban in holding}),
        # A ban that says nothing of how long it lasts could last forever, so no end is given.
        ban_ends_at=max(ends) if ends and len(ends) == len(holding) else None,
        attackers=1 + episode.neighbours_of(incident.subject, incident.block, incident.addresses),
    )


def overview(db: Session, days: int, now: datetime | None = None) -> Overview:
    """The incidents of the last ``days`` days that count, grouped by what was done about them,
    those that need a response first and then the most serious."""
    now = now or utcnow()
    where = [
        Incident.last_seen_at >= now - timedelta(days=days),
        Incident.severity >= MINIMUM,
        Incident.status != "dismissed",
        # An incident with no verdict is not in ``MUTING``, which a NULL would also fail.
        Incident.verdict.is_(None) | Incident.verdict.not_in(MUTING),
    ]
    total = db.scalar(select(func.count()).select_from(Incident).where(*where)) or 0
    found = list(
        db.scalars(
            select(Incident)
            .where(*where)
            .order_by(
                Incident.severity.desc(),
                Incident.confidence.desc(),
                Incident.last_seen_at.desc(),
                Incident.id.desc(),
            )
            .limit(MAX_INCIDENTS)
        )
    )
    done = response.of(db, found, now)
    order = list(GROUPS)
    items = sorted(
        (_item(incident, done[incident.id], now) for incident in found),
        # Python's sort is stable, so inside a group the most serious stay first.
        key=lambda item: order.index(item.group),
    )
    connected = set(db.scalars(select(IntegrationConnection.integration).distinct()))
    return Overview(
        days=days,
        total=total,
        items=items,
        crowdsec_connected="crowdsec" in connected,
        opnsense_connected="opnsense" in connected,
    )
