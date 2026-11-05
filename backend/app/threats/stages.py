"""The stage of an attack a signal belongs to, said from its words.

Most of what a home network sees is the internet knocking: scans, and guessing at logins. Those
are *attempts*. What matters is when an attempt becomes something else, so each signal is placed
on a short path, the way Microsoft Sentinel's Fusion and Splunk's risk-based alerting look for
several weak signs that add up instead of one loud one:

- ``recon``: looking for what is there (scans, probes).
- ``access``: trying to get in by a flaw (an exploit, an injection, a known vulnerability).
- ``foothold``: signs that it worked (malware, a command server, a web shell, a login that
  succeeded after many failures).

Guessing passwords is none of them: botnets do it all day to everything, and it only matters
once it succeeds, which is a foothold. An incident with a foothold, or with more than one stage,
is a chain: it is never set aside as background, whatever an AI thinks of its kind.
"""

import re
from typing import Final

from app.incidents.episode import SCAN, activity_of
from app.incidents.subject import Signal

RECON: Final = "recon"
ACCESS: Final = "access"
FOOTHOLD: Final = "foothold"
STAGES: Final = (RECON, ACCESS, FOOTHOLD)

_FOOTHOLD = re.compile(
    r"\bmalware\b|\btrojan\b|\bbackdoor\b|\bransom(?:ware)?\b|\bbotnet\b|\bc2\b|\bcnc\b"
    r"|command[\s_-]and[\s_-]control|reverse[\s_-]shell|\bweb[\s_-]?shell\b|\bexfiltrat"
    r"|\bcrypto[\s_-]?miner\b|\brootkit\b|\bbeacon(?:ing)?\b"
    r"|failures?\s+followed\s+by\s+(?:a\s+)?success|authentication\s+success\s+after",
    re.IGNORECASE,
)
_ACCESS = re.compile(
    r"\bexploit|\bcve-\d{4}-\d+|\brce\b|remote\s+code\s+execution|\binjection\b|\btraversal\b"
    r"|buffer\s+overflow|\bshellshock\b|\blog4(?:j|shell)\b|\bdeserializ",
    re.IGNORECASE,
)


def stage_of(signal: Signal) -> str | None:
    """The stage a signal is, or None for one that is none of them. The furthest wins: an alert
    about a scan that loaded malware is a foothold."""
    words = f"{signal.signature or ''} {signal.summary}"
    if _FOOTHOLD.search(words):
        return FOOTHOLD
    if _ACCESS.search(words):
        return ACCESS
    return RECON if activity_of(signal) == SCAN else None


def with_stage(known: list[str], signal: Signal) -> list[str]:
    """The stages an incident has, with a signal's added, in the order of the path."""
    found = stage_of(signal)
    if found is None or found in known:
        return known
    return sorted([*known, found], key=STAGES.index)


def is_chain(stages: list[str]) -> bool:
    """Whether the stages are more than scanning: a foothold, or more than one stage."""
    return FOOTHOLD in stages or len(stages) > 1
