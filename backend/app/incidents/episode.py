"""What makes signals one episode: one actor doing one kind of thing in one stretch of time.

A bot that sweeps a network's ports three times in an afternoon, or from five neighbouring
addresses of one hosting company, is one incident with several waves, not several incidents. The
same bot coming back the next day is another. Three things decide it, and the incident says
which applied (``explain``):

- **The actor.** The same address always. For scans and brute force, which botnets spread over
  the addresses they rent, also the neighbours: the other addresses of the same block (a /24 for
  IPv4, a /64 for IPv6) that do the same thing.
- **The kind of activity.** What a signal says it is (``activity_of``). A scan comes in bursts, so
  it is over sooner than a brute force, which is steadier.
- **The time.** A signal belongs while the quiet between signals is shorter than the gap for
  its activity (``gap_of``), and an episode doesn't go on for longer than ``MAX_SPAN``: a new
  day is a new incident, however steady the activity.
"""

import re
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from itertools import pairwise
from typing import Final

from app.incidents.subject import Signal

Address = IPv4Address | IPv6Address

SCAN: Final = "scan"
BRUTE_FORCE: Final = "brute_force"
# What neighbouring addresses are grouped by: the activities a botnet is spread over.
GROUPED: Final = (SCAN, BRUTE_FORCE)
ACTIVITY_NAMES: Final = {SCAN: "scanning", BRUTE_FORCE: "brute force"}

# How long the quiet between two signals may be before the next one is a new incident. A scan
# is bursty, so a few hours of quiet end it; a brute force is steadier, and so are the rest.
GAPS: Final = {SCAN: timedelta(hours=4), BRUTE_FORCE: timedelta(hours=6)}
DEFAULT_GAP: Final = timedelta(hours=6)
# The longest an incident goes on for, from its first signal to the one that joins it.
MAX_SPAN: Final = timedelta(hours=24)
# A quiet this long inside an incident ends one wave and the next signal starts another.
WAVE_GAP: Final = timedelta(minutes=15)
# How many different destination ports an incident keeps. A sweep of every port is many.
MAX_PORTS: Final = 1000

# What the words of a signal say. Brute force is asked first: "ssh brute force scan" is one.
_BRUTE_FORCE = re.compile(
    r"brute[\s_-]?force|\bbf\b|authentication\s+(?:fail|attempt)|failed\s+(?:password|login)"
    r"|login\s+(?:attempt|failure)|invalid\s+user|password\s+(?:guess|spray)"
    r"|credential\s+stuffing",
    re.IGNORECASE,
)
_SCAN = re.compile(
    r"\b(?:port[\s_-]?)?scan(?:s|ning|ner|ners)?\b|\bprob(?:e|es|ed|ing)\b|\bnmap\b|\bmasscan\b"
    r"|\bcrawl(?:s|ing|er)?\b|\brecon(?:naissance)?\b",
    re.IGNORECASE,
)


def activity_of(signal: Signal) -> str | None:
    """What a signal says it is: scanning, brute force, or neither of those. It is read from its
    signature and what it says, since every program words them its own way (Suricata's
    ``ET SCAN ...``, CrowdSec's ``firewallservices/pf-scan-multi_ports`` and ``ssh-bf``,
    Wazuh's ``sshd: authentication failed``)."""
    words = f"{signal.signature or ''} {signal.summary}"
    if _BRUTE_FORCE.search(words):
        return BRUTE_FORCE
    if _SCAN.search(words):
        return SCAN
    return None


def gap_of(activity: str | None) -> timedelta:
    """How long the quiet may be before a signal of this activity is a new incident."""
    return GAPS.get(activity or "", DEFAULT_GAP)


def block_of(address: Address) -> str | None:
    """The block an address's neighbours are in: its /24 or /64, or none for one that is not on
    the internet, whose neighbours are the owner's own devices and say nothing about an actor."""
    if not address.is_global:
        return None
    prefix = 24 if address.version == 4 else 64
    return str(ip_network(f"{address}/{prefix}", strict=False))


def block_of_subject(subject: str) -> str | None:
    """The block of an incident's subject, or none where it is a rule rather than an address."""
    try:
        return block_of(ip_address(subject))
    except ValueError:
        return None


def neighbours_of(subject: str, block: str | None, addresses: Iterable[Address]) -> int:
    """How many addresses other than the subject an incident names that are in its block: the
    neighbours that were grouped with it."""
    if block is None:
        return 0
    return sum(1 for address in addresses if str(address) != subject and block_of(address) == block)


def waves_of(times: Sequence[datetime]) -> int:
    """How many bursts the signals came in, with at least ``WAVE_GAP`` of quiet between them."""
    ordered = sorted(times)
    return 1 + sum(later - earlier > WAVE_GAP for earlier, later in pairwise(ordered))


def next_wave(waves: int, previous: datetime | None, at: datetime) -> int:
    """How many waves there are once a signal at ``at`` joins an incident whose latest signal was
    at ``previous`` (none for a new one) and which had ``waves``."""
    if previous is None or waves == 0:
        return 1
    return waves + (1 if at - previous > WAVE_GAP else 0)


def with_ports(known: list[int], port: int | None) -> list[int]:
    """The ports an incident names, with another added in order, up to ``MAX_PORTS``."""
    if port is None or port in known or len(known) >= MAX_PORTS:
        return known
    return sorted([*known, port])


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _hours(span: timedelta) -> str:
    hours = int(span.total_seconds() // 3600)
    return "1 hour" if hours == 1 else f"{hours} hours"


def explain(
    *,
    subject: str,
    block: str | None,
    neighbours: int,
    activities: Sequence[str],
    waves: int,
    signals: int,
    port_count: int,
) -> list[str]:
    """Why the signals of an incident are one incident, in plain words, one fact to a line."""
    lines: list[str] = []
    if neighbours > 0 and block is not None:
        lines.append(
            f"Signals from {neighbours + 1} addresses of {block} doing the same thing are "
            "grouped: a bot spread over a block is one actor."
        )
    elif subject.startswith("rule:"):
        lines.append("They come from one rule and name no address.")
    else:
        lines.append(f"Everything in it is about {subject}, whichever program saw it.")
    activity = next((item for item in GROUPED if item in activities), None)
    gap = gap_of(activity)
    named = f" {ACTIVITY_NAMES[activity]}" if activity else ""
    lines.append(
        f"Each{named} signal came less than {_hours(gap)} after the one before it. "
        f"A longer quiet, or more than {_hours(MAX_SPAN)} in all, starts another incident."
    )
    if waves > 1:
        lines.append(
            f"It came in {waves} waves: {_count(signals, 'signal')} in bursts with at least "
            f"{int(WAVE_GAP.total_seconds() // 60)} minutes of quiet between them."
        )
    if port_count > 1:
        lines.append(f"It touched {_count(port_count, 'port')}.")
    return lines
