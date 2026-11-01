"""Suggestions for where feeds belong, worked out by rules from what the sources call their ports.
They are only suggestions: nothing is placed until the owner says so, because a wrong guess about
which port is the Internet would mislabel every threat that comes in on it.

The rules, in the order they are tried:

1. A name that says what the port is for (``wan``, ``guest``, ``wg0``, ``mgmt``) names the part of
   the network and its role. It joins the interface of that name, or the only interface that has
   that role.
2. A name an interface already has (any capitals) joins that interface.
3. The same name in more than one program (OPNsense and ntopng both say ``igc0``) is one port, so
   they are suggested together.
"""

import re
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.incidents.rules import name_of
from app.interfaces.service import listing
from app.models import Interface, InterfaceFeed


@dataclass(frozen=True)
class Hint:
    """Words that say what a port is for, and the name and role to suggest for it."""

    role: str
    name: str
    words: frozenset[str]


# Tried in this order, so a name with two words (``guest_vpn``) is the first that fits.
HINTS: tuple[Hint, ...] = (
    Hint("guest", "Guests", frozenset({"guest", "guests", "visitor", "visitors"})),
    Hint("iot", "IoT", frozenset({"iot", "smart", "camera", "cameras", "cctv"})),
    Hint("dmz", "DMZ", frozenset({"dmz"})),
    Hint("management", "Management", frozenset({"mgmt", "management", "admin", "oob"})),
    Hint(
        "vpn",
        "VPN",
        frozenset(
            {"vpn", "wg", "wireguard", "ovpn", "ovpns", "ovpnc", "openvpn", "ipsec", "tailscale"}
        ),
    ),
    Hint("internet", "Internet", frozenset({"wan", "internet", "isp", "pppoe", "uplink"})),
    Hint("home", "Home", frozenset({"lan", "home", "family", "trusted", "private"})),
)

_WORDS = re.compile(r"[a-z]+")


@dataclass(frozen=True)
class Suggestion:
    """Feeds that go together, with a name and role to give them and why they were put together.
    ``interface_id`` is the interface they would join, if one with that name exists."""

    name: str
    role: str
    feed_ids: tuple[int, ...]
    reason: str
    interface_id: int | None


def words_of(text: str) -> set[str]:
    """The words in a port name: ``Guest_WiFi2`` is guest and wifi, and ``ovpns1`` is ovpns."""
    return set(_WORDS.findall(text.lower()))


def hint_for(*texts: str) -> Hint | None:
    """The first hint any of the texts matches."""
    found: set[str] = set()
    for text in texts:
        found |= words_of(text)
    return next((hint for hint in HINTS if hint.words & found), None)


def _join(texts: list[str]) -> str:
    """``a``, ``a and b``, ``a, b and c``."""
    return texts[0] if len(texts) == 1 else f"{', '.join(texts[:-1])} and {texts[-1]}"


def _where(feeds: list[InterfaceFeed]) -> str:
    """Where the names were seen: ``igc0 in OPNsense and eno1 in ntopng``."""
    return _join([f"{feed.native_name} in {name_of(feed.integration)}" for feed in feeds])


@dataclass
class _Group:
    """Feeds that are suggested together: what to call them, the interface they would join if
    there is one, and the rule that put them there."""

    name: str
    role: str
    match: Interface | None
    why: str
    feeds: list[InterfaceFeed]


def _joining(hint: Hint, interfaces: list[Interface]) -> Interface | None:
    """The interface a hint's feeds would join: the one called what the hint is, or the only one
    that has the hint's role (a WAN that is called Fibre is still the way out)."""
    named = next((item for item in interfaces if item.name.lower() == hint.name.lower()), None)
    if named is not None:
        return named
    same = [item for item in interfaces if item.role == hint.role]
    return same[0] if len(same) == 1 else None


def suggestions(db: Session) -> list[Suggestion]:
    """Where the feeds that aren't placed could go. Ports that are set aside are left alone, and so
    are whole connections, which have no port name to go by."""
    taken = listing(db)
    interfaces = [item for item, _ in taken.interfaces]
    by_name = {item.name.lower(): item for item in interfaces}

    ports: dict[str, list[InterfaceFeed]] = defaultdict(list)
    for feed in taken.unplaced:
        if feed.native_name:
            ports[feed.native_name.lower()].append(feed)

    groups: dict[tuple[str, str], _Group] = {}
    for key, feeds in ports.items():
        hint = hint_for(*[text for feed in feeds for text in (feed.native_name, feed.label)])
        if hint is not None:
            match = _joining(hint, interfaces)
            group = _Group(hint.name, hint.role, match, f"“{key}” says what it is for", [])
        elif key in by_name:
            match = by_name[key]
            group = _Group(match.name, match.role, match, "It has the name of an interface", [])
        elif len({feed.integration for feed in feeds}) > 1:
            group = _Group(feeds[0].native_name, "other", None, "Several programs name it", [])
        else:
            continue
        place = ("interface", str(group.match.id)) if group.match else ("new", group.name.lower())
        groups.setdefault(place, group).feeds.extend(feeds)

    return [
        Suggestion(
            name=group.match.name if group.match else group.name,
            role=group.match.role if group.match else group.role,
            feed_ids=tuple(sorted(feed.id for feed in group.feeds)),
            reason=f"{group.why}: {_where(group.feeds)}.",
            interface_id=group.match.id if group.match else None,
        )
        for _, group in sorted(groups.items())
    ]
