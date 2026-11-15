"""Whether what an agent says it found is what it was shown.

A model can write an address or a CVE that nobody gave it, and a finding built on one reads as
well as one built on a fact. After the model has answered, each finding is held up to what the run
really looked at: every IPv4 address and CVE number in its title, its detail and its evidence has
to be in what the run read, in what the agent reported last time or in the owner's own
instructions. A finding that names something that is in none of them is kept, because the owner
still wants to know, but it can no longer say it is sure of it: its confidence is lowered to
``low``, and the run says so. This is a rule and not a request to the model, so a model that is
wrong about being right cannot get past it, and it only ever lowers a confidence.
"""

import re
from collections.abc import Iterable, Sequence
from typing import NamedTuple

_ADDRESS = re.compile(r"(?<!\w)(?<!\d\.)(?:\d{1,3}\.){3}\d{1,3}(?!\w|\.\d)")
_CVE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)


class Claim(NamedTuple):
    """What a finding says, which can be checked: its title, detail and lines of evidence."""

    title: str
    text: str


def names_in(text: str) -> set[str]:
    """The addresses and CVE numbers in a text, each as it is compared: an address of four numbers
    up to 255, a CVE in capitals."""
    found = {
        match
        for match in _ADDRESS.findall(text)
        if all(int(part) <= 255 for part in match.split("."))
    }
    return found | {match.upper() for match in _CVE.findall(text)}


def unseen(claims: Sequence[Claim], seen: Iterable[str]) -> dict[str, list[str]]:
    """For each claim that names something that is not in ``seen``, what it names that is not. A
    claim that names nothing, or only what was seen, is not in the answer."""
    known = names_in("\n".join(seen))
    found: dict[str, list[str]] = {}
    for claim in claims:
        missing = sorted(names_in(claim.text) - known)
        if missing:
            found.setdefault(claim.title, missing)
    return found
