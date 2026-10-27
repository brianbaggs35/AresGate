"""What was done about an incident: whether its address was banned, and how often it was turned
away.

Three things are read, all of them events AresGate already keeps, so nothing here asks a program
anything. CrowdSec's decisions (``kind`` ``decision``) are the bans: what they say of how long is
left (``duration``, a Go duration such as ``3h59m12s``), the scenario and the origin is in their
record, and a ban is dated by the minute AresGate first read it, so it may have been made a little
earlier. The firewall's blocks of the address (``kind`` ``firewall``) and the alerts Suricata
stopped (``alert_action`` of ``blocked``, in an alert's record) say it was turned away.

What counts is only said as far as it is known. A ban whose length can't be read is in force as
far as anyone can tell, a simulated one or one that is not a ban (a captcha, say) is listed but is
no response, and a program that isn't connected is named, since then nothing can be seen of what it
did.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any, Final, Literal

from sqlalchemy import BigInteger, and_, cast, column, func, or_, select, values
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Session

from app.events.event import Severity
from app.incidents import episode
from app.incidents.queries import CONTEXT
from app.models import Event, Incident, IntegrationConnection
from app.models.base import UTCDateTime, utcnow

State = Literal["banned", "partly", "ban_ended", "blocked", "none", "no_address"]

# What each state is called, on a card and in the incident's page.
LABELS: Final[dict[State, str]] = {
    "banned": "Banned",
    "partly": "Partly banned",
    "ban_ended": "Ban ended",
    "blocked": "Blocked",
    "none": "No response yet",
    "no_address": "Nothing to block",
}
# Where a CrowdSec decision came from, in words. An origin it doesn't list is shown as it is.
ORIGINS: Final = {
    "crowdsec": "CrowdSec's own detection",
    "cscli": "Added by hand",
    "cscli-import": "Imported from a file",
    "console": "The CrowdSec Console",
}
# The most bans one incident shows, and the most decisions one page of incidents is checked against.
MAX_BANS: Final = 10
MAX_DECISIONS: Final = 5000
MAX_TEXT: Final = 80

_UNITS: Final = {
    "ns": 1e-9,
    "us": 1e-6,
    "µs": 1e-6,
    "μs": 1e-6,
    "ms": 1e-3,
    "s": 1,
    "m": 60,
    "h": 3600,
}
_PART: Final = re.compile(r"(\d+(?:\.\d+)?)(ns|us|µs|μs|ms|s|m|h)")
_WHOLE: Final = re.compile(r"-?(?:\d+(?:\.\d+)?(?:ns|us|µs|μs|ms|s|m|h))+")


@dataclass(frozen=True)
class Ban:
    """One decision of CrowdSec about an address of the incident."""

    address: str
    # What kind of remedy it was (``ban``), the scenario that made it and where it came from.
    kind: str
    scenario: str | None
    origin: str | None
    # When AresGate first read it, and when it runs out, if the time left it read is understood.
    seen_at: datetime
    ends_at: datetime | None
    simulated: bool

    @property
    def real(self) -> bool:
        """Whether it is a ban that was meant: not a simulated one, nor another remedy."""
        return self.kind == "ban" and not self.simulated

    def in_force(self, now: datetime) -> bool:
        """Whether it still holds, as far as is known: one whose length isn't known does."""
        return self.real and (self.ends_at is None or self.ends_at > now)


@dataclass(frozen=True)
class Tally:
    """How the incident's address was turned away in the time that counts."""

    blocked: int = 0
    last_blocked_at: datetime | None = None
    # How many of the blocks came after the first ban was read (0 when there was no ban).
    after_ban: int = 0
    dropped: int = 0


@dataclass(frozen=True)
class Response:
    """What was done about one incident."""

    state: State
    bans: tuple[Ban, ...]
    tally: Tally
    # What can't be told, in words.
    unknown: tuple[str, ...]

    @property
    def label(self) -> str:
        return LABELS[self.state]


def time_left(text: str) -> timedelta | None:
    """The time a Go duration such as ``3h59m12s`` or ``23h59m59.9s`` is, or None for text that
    isn't one. CrowdSec gives how long is left of a ban that way."""
    if not _WHOLE.fullmatch(text):
        return None
    seconds = sum(float(number) * _UNITS[unit] for number, unit in _PART.findall(text))
    try:
        return timedelta(seconds=-seconds if text.startswith("-") else seconds)
    except OverflowError:
        return None


def _ends_at(seen_at: datetime, text: str) -> datetime | None:
    left = time_left(text)
    if left is None:
        return None
    try:
        return seen_at + left
    except OverflowError:
        return None


def _text(record: Mapping[str, Any] | None, key: str) -> str:
    value = record.get(key) if record else None
    return value.strip()[:MAX_TEXT] if isinstance(value, str) else ""


def _ban(
    seen_at: datetime,
    address: IPv4Address | IPv6Address,
    scenario: str | None,
    record: Mapping[str, Any] | None,
) -> Ban:
    origin = _text(record, "origin")
    return Ban(
        address=str(address),
        kind=_text(record, "type").lower() or "ban",
        scenario=scenario,
        origin=ORIGINS.get(origin, origin) or None,
        seen_at=seen_at,
        ends_at=_ends_at(seen_at, _text(record, "duration")),
        simulated=record is not None and record.get("simulated") is True,
    )


def _decisions(db: Session, incidents: Sequence[Incident]) -> list[Ban]:
    """The decisions made in the time the incidents span, about any address, oldest first."""
    rows = db.execute(
        select(Event.occurred_at, Event.src_address, Event.signature, Event.raw)
        .where(
            Event.source == "crowdsec",
            Event.kind == "decision",
            Event.src_address.is_not(None),
            Event.occurred_at >= min(incident.first_seen_at for incident in incidents),
            Event.occurred_at <= max(incident.last_seen_at for incident in incidents),
        )
        .order_by(Event.occurred_at, Event.id)
        .limit(MAX_DECISIONS)
    ).all()
    return [_ban(at, address, scenario, raw) for at, address, scenario, raw in rows if address]


def _bans_of(incident: Incident, decisions: Sequence[Ban]) -> list[Ban]:
    """The decisions about the incident's addresses made while it was going on, those about the
    subject first and the newest first, so the most telling are the ones kept."""
    addresses = {str(address) for address in incident.addresses}
    found = [
        ban
        for ban in decisions
        if ban.address in addresses
        and incident.first_seen_at <= ban.seen_at <= incident.last_seen_at
    ]
    found.sort(key=lambda ban: ban.seen_at, reverse=True)
    found.sort(key=lambda ban: ban.address != incident.subject)
    return found


def _window_end(incident: Incident, bans: Sequence[Ban], now: datetime) -> datetime:
    """How late a block still counts: soon after the incident, or as long as a ban lasted, since
    the firewall's blocks are no part of an incident and so don't lengthen it."""
    end = incident.last_seen_at + CONTEXT
    lasted = [min(ban.ends_at, now) for ban in bans if ban.real and ban.ends_at is not None]
    return max([end, *lasted])


_BLOCK = and_(Event.kind == "firewall", Event.severity >= Severity.LOW)
_DROP = and_(Event.kind == "alert", Event.raw["alert_action"].astext == "blocked")


# An incident's id, its address, the time that counts as the start and the end of it, and when
# its first ban was read.
Window = tuple[int, IPv4Address | IPv6Address, datetime, datetime, datetime | None]


def _tallies(db: Session, windows: Sequence[Window]) -> dict[int, Tally]:
    """For each incident, by its id: how often its address was blocked in a window of time and
    when last, how often since a time, and how many alerts Suricata stopped."""
    if not windows:
        return {}
    asked = values(
        column("id", BigInteger),
        column("address", INET),
        column("start", UTCDateTime),
        column("stop", UTCDateTime),
        column("ban_at", UTCDateTime),
        name="windows",
    ).data(list(windows))  # a first ban that is None is a NULL of no type, hence the cast below
    rows = db.execute(
        select(
            asked.c.id,
            func.count().filter(_BLOCK),
            func.max(Event.occurred_at).filter(_BLOCK),
            func.count().filter(
                and_(_BLOCK, Event.occurred_at > cast(asked.c.ban_at, UTCDateTime))
            ),
            func.count().filter(_DROP),
        )
        .select_from(asked)
        .join(
            Event,
            and_(
                Event.src_address == asked.c.address,
                Event.occurred_at >= asked.c.start,
                Event.occurred_at <= asked.c.stop,
            ),
        )
        .where(or_(_BLOCK, _DROP))
        .group_by(asked.c.id)
    ).all()
    return {
        incident_id: Tally(blocked, last, after, dropped)
        for incident_id, blocked, last, after, dropped in rows
    }


def of(
    db: Session, incidents: Sequence[Incident], now: datetime | None = None
) -> dict[int, Response]:
    """What was done about each incident, by its id."""
    if not incidents:
        return {}
    now = now or utcnow()
    decisions = _decisions(db, incidents)
    bans = {incident.id: _bans_of(incident, decisions) for incident in incidents}
    windows: list[Window] = []
    for incident in incidents:
        if not incident.subject.startswith("rule:"):
            first = [ban.seen_at for ban in bans[incident.id] if ban.real]
            windows.append(
                (
                    incident.id,
                    ip_address(incident.subject),
                    incident.first_seen_at - CONTEXT,
                    _window_end(incident, bans[incident.id], now),
                    min(first, default=None),
                )
            )
    tallies = _tallies(db, windows)
    connected = set(db.scalars(select(IntegrationConnection.integration).distinct()))
    return {
        incident.id: _response(
            incident, bans[incident.id], tallies.get(incident.id), connected, now
        )
        for incident in incidents
    }


def _response(
    incident: Incident,
    bans: list[Ban],
    tally: Tally | None,
    connected: set[str],
    now: datetime,
) -> Response:
    if incident.subject.startswith("rule:"):
        return Response("no_address", (), Tally(), ())
    tally = tally or Tally()
    state = _state(incident, bans, tally, now)
    return Response(state, tuple(bans[:MAX_BANS]), tally, _unknown(state, bans, tally, connected))


def _state(incident: Incident, bans: Sequence[Ban], tally: Tally, now: datetime) -> State:
    real = [ban for ban in bans if ban.real]
    holding = {ban.address for ban in real if ban.in_force(now)}
    if holding:
        # A block of addresses doing the same thing is one incident: all of them have to be banned.
        attackers = 1 + episode.neighbours_of(incident.subject, incident.block, incident.addresses)
        return "banned" if len(holding) >= attackers else "partly"
    if real:
        return "ban_ended"
    # A program banned it, but its decision has gone with the events that were kept for a while.
    if incident.banned and not bans:
        return "banned"
    return "blocked" if tally.blocked or tally.dropped else "none"


def _unknown(
    state: State, bans: Sequence[Ban], tally: Tally, connected: set[str]
) -> tuple[str, ...]:
    found: list[str] = []
    if not any(ban.real for ban in bans):
        if "crowdsec" not in connected:
            found.append("CrowdSec isn't connected, so AresGate can't see whether it banned it.")
        elif state == "banned":
            found.append("The ban was made too long ago for its details to be kept.")
    else:
        found.append("A ban is dated by when AresGate first read it, which may be a little later.")
    if not tally.blocked and not tally.dropped and "opnsense" not in connected:
        found.append(
            "OPNsense isn't connected, so AresGate can't see whether its firewall or Suricata "
            "turned it away."
        )
    return tuple(found)
