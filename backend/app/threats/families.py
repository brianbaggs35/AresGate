"""Families: incidents that say the same thing the same way.

Hundreds of scanners from hundreds of addresses each make an incident of their own, because they
are different actors, but they are one *kind* of thing: the same program reported the same words
about the same sort of place. Counting them one at a time is how a home network ends up with
"70,000 alerts"; asking an AI about them one at a time is how a bill gets large. A family groups
them, so a person sees one line ("Internet scanning: ET SCAN Potential SSH Scan, 412 incidents")
and the AI judges the kind once (``app/ai/families.py``), the way a threat feed such as GreyNoise
says an address is background noise once and every alert from it is read that way.

A family is not an incident and sets nothing aside by itself: what the AI or the owner says of it
reaches an incident through ``calls.py``, and an incident that is more than scanning (a chain of
stages, a foothold) is never set aside, whatever its family is.
"""

import re
from hashlib import sha256
from ipaddress import ip_address
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incident, IncidentFamily
from app.threats import calls

INTERNET: Final = "internet"
NETWORK: Final = "network"
RULE: Final = "rule"
REACHES: Final = (INTERNET, NETWORK, RULE)
OWNER_CALLS: Final = ("background", "watch")
MAX_LABEL: Final = 200
# How many incidents a pass gives a family to.
BATCH: Final = 2000

_V4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# Something that looks like an IPv6 address, which is then checked to be one.
_V6 = re.compile(r"(?<![\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f.]{0,45}(?![\w:])", re.IGNORECASE)
_NUMBER = re.compile(r"\b\d+\b")
_SPACES = re.compile(r"\s+")


def _address(found: re.Match[str]) -> str:
    try:
        ip_address(found.group(0))
    except ValueError:
        return found.group(0)
    return "<address>"


def label_of(text: str) -> str:
    """What a family is called: the words of its incidents without the parts that differ from one
    to the next, which are addresses and numbers."""
    plain = _NUMBER.sub("#", _V4.sub("<address>", _V6.sub(_address, text)))
    return _SPACES.sub(" ", plain).strip()[:MAX_LABEL]


def reach_of(subject: str) -> str:
    """Where an incident is from: the internet, the owner's own network, or a rule that names no
    address."""
    try:
        return INTERNET if ip_address(subject).is_global else NETWORK
    except ValueError:
        return RULE


def key_of(incident: Incident) -> str:
    """What makes an incident part of a family: the program that reported it most seriously, the
    words, and where from."""
    words = label_of(incident.top_summary).lower()
    text = f"{incident.top_source}|{reach_of(incident.subject)}|{words}"
    return sha256(text.encode()).hexdigest()[:40]


def assign(db: Session) -> int:
    """Gives the incidents that have no family one, making the family where it is new, and tells
    the incidents what their family has been judged. Returns how many were given one. The caller
    commits."""
    waiting = list(
        db.scalars(
            select(Incident).where(Incident.family_id.is_(None)).order_by(Incident.id).limit(BATCH)
        )
    )
    if not waiting:
        return 0
    for incident in waiting:
        incident.family_key = incident.family_key or key_of(incident)
    keys = {incident.family_key for incident in waiting if incident.family_key}
    known = {
        key: family_id
        for key, family_id in db.execute(
            select(IncidentFamily.key, IncidentFamily.id).where(IncidentFamily.key.in_(keys))
        )
    }
    for incident in waiting:
        key = incident.family_key
        if key is None:  # pragma: no cover - set just above
            continue
        if key not in known:
            family = IncidentFamily(
                key=key,
                source=incident.top_source,
                label=label_of(incident.top_summary) or incident.top_source,
                reach=reach_of(incident.subject),
            )
            db.add(family)
            db.flush()
            known[key] = family.id
        incident.family_id = known[key]
    db.flush()
    calls.sync(db, [incident.id for incident in waiting])
    return len(waiting)
