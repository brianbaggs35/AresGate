"""What kind of thing an asset is and what it is for, in the owner's words.

The integrations list what they can see: a hardware address, a maker, a host name. None of them
says that the box at 192.168.1.1 is the router or that the thing that wakes at seven is the
kitchen radio, and that is what makes an alert about it make sense. The owner says so here, once
per asset. It is the owner's word and nothing a program lists changes it, and where the owner has
not said, a guess from the name and the maker is offered (never applied) so that classifying a
network is one tap a device.
"""

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AssetProfile

MAX_PURPOSE: Final = 200


@dataclass(frozen=True)
class Kind:
    """One kind of asset the owner can pick."""

    key: str
    label: str
    # What a page groups it with.
    group: str
    # Whether it is a piece of the network itself, which carries other things' traffic.
    carries: bool = False


GROUPS: Final = (
    ("network", "The network"),
    ("computers", "Computers"),
    ("phones", "Phones and tablets"),
    ("home", "Around the home"),
    ("other", "Other"),
)

KINDS: Final = (
    Kind("router", "Router", "network", carries=True),
    Kind("firewall", "Firewall", "network", carries=True),
    Kind("modem", "Modem", "network", carries=True),
    Kind("switch", "Network switch", "network", carries=True),
    Kind("access_point", "Wi-Fi access point", "network", carries=True),
    Kind("server", "Server", "computers"),
    Kind("nas", "Storage (NAS)", "computers"),
    Kind("computer", "Desktop computer", "computers"),
    Kind("laptop", "Laptop", "computers"),
    Kind("phone", "Phone", "phones"),
    Kind("tablet", "Tablet", "phones"),
    Kind("tv", "TV", "home"),
    Kind("media_player", "Media player", "home"),
    Kind("speaker", "Speaker or voice assistant", "home"),
    Kind("game_console", "Game console", "home"),
    Kind("camera", "Camera or doorbell", "home"),
    Kind("printer", "Printer", "home"),
    Kind("smart_home", "Smart home device", "home"),
    Kind("guest", "Guest's device", "other"),
    Kind("other", "Something else", "other"),
)
BY_KEY: Final = {kind.key: kind for kind in KINDS}

# What in a host name or a maker's name says what a device is, the first match winning. A word is
# matched whole where it is short enough to be inside another (``tv`` is not in ``activity``).
_GUESSES: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("router", ("router", "gateway", "opnsense", "pfsense", "mikrotik", "edgerouter", "fritz")),
    ("access_point", ("access point", "unifi", "accesspoint")),
    ("nas", ("synology", "qnap", "diskstation", "nas")),
    ("printer", ("printer", "laserjet", "officejet", "brother", "epson", "lexmark", "xerox")),
    ("camera", ("camera", "reolink", "hikvision", "dahua", "wyze", "doorbell", "cam")),
    ("game_console", ("playstation", "ps5", "ps4", "xbox", "nintendo")),
    ("speaker", ("sonos", "echo", "alexa", "homepod", "google-home", "nest-mini")),
    ("media_player", ("chromecast", "appletv", "apple-tv", "roku", "firetv", "shield")),
    ("tv", ("tv", "bravia", "vizio", "webos")),
    ("tablet", ("ipad", "tablet", "kindle")),
    ("phone", ("phone", "iphone", "android", "pixel", "galaxy", "oneplus")),
    ("laptop", ("macbook", "laptop", "thinkpad", "xps")),
    ("computer", ("desktop", "imac", "workstation")),
    ("server", ("server", "proxmox", "esxi", "docker")),
    ("smart_home", ("espressif", "tuya", "shelly", "signify", "ecobee", "esp32", "esp8266")),
)
_SHORT: Final = 6
# What the AI is told of an asset the owner says matters: a clause after what it is.
MATTERS: Final = {
    "important": "; it matters to the owner",
    "critical": "; it is critical to the owner",
}


@dataclass(frozen=True)
class Profile:
    """What the owner said an asset is."""

    kind: str
    purpose: str | None
    updated_at: datetime
    # How much it matters to the owner: ``normal``, ``important`` or ``critical``.
    importance: str = "normal"

    @property
    def label(self) -> str:
        return BY_KEY[self.kind].label

    @property
    def carries(self) -> bool:
        return BY_KEY[self.kind].carries


def suggest(hostname: str | None, vendor: str | None) -> str | None:
    """The kind a host name and a maker's name suggest, or None where they say nothing. A guess:
    it is offered to the owner and never applied."""
    text = f"{hostname or ''} {vendor or ''}".lower()
    words = set(re.split(r"[^a-z0-9]+", text))
    for kind, hints in _GUESSES:
        for hint in hints:
            found = hint in words if len(hint) < _SHORT else hint in text
            if found:
                return kind
    return None


def load(db: Session) -> dict[str, Profile]:
    """Every profile, by the key of the asset it is about."""
    return {
        row.key: Profile(row.kind, row.purpose, row.updated_at, row.importance)
        for row in db.scalars(select(AssetProfile))
    }


def for_devices(db: Session, ids: Iterable[int]) -> dict[int, Profile]:
    """What the owner said of each of these devices, by the device's id."""
    keys = {f"device-{each}": each for each in ids}
    if not keys:
        return {}
    return {
        keys[row.key]: Profile(row.kind, row.purpose, row.updated_at, row.importance)
        for row in db.scalars(select(AssetProfile).where(AssetProfile.key.in_(keys)))
    }


def describe(said: Profile | None, clean: Callable[[str, int], str]) -> str:
    """What the owner said of an asset, as a clause for a line about it: ``, which the owner says
    is a camera (watches the front door)``. ``clean`` makes the owner's words safe to hand on, and
    it is nothing where they said nothing."""
    if said is None:
        return ""
    purpose = f" ({clean(said.purpose, MAX_PURPOSE)})" if said.purpose else ""
    matters = MATTERS.get(said.importance, "")
    return f", which the owner says is a {said.label.lower()}{purpose}{matters}"


def save(
    db: Session, key: str, kind: str, purpose: str | None, now: datetime, importance: str = "normal"
) -> Profile:
    """Says what an asset is and how much it matters, replacing what was said before. The caller
    commits."""
    said = (purpose or "").strip() or None
    row = db.get(AssetProfile, key)
    if row is None:
        row = AssetProfile(key=key, kind=kind, purpose=said, importance=importance, updated_at=now)
        db.add(row)
    else:
        row.kind = kind
        row.purpose = said
        row.importance = importance
        row.updated_at = now
    return Profile(kind, said, now, importance)


def clear(db: Session, key: str) -> bool:
    """Takes back what was said of an asset. False if nothing was. The caller commits."""
    return db.connection().execute(delete(AssetProfile).where(AssetProfile.key == key)).rowcount > 0
