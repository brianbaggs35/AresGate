"""Finding the CVEs an incident names. They are named where a program says so (a Wazuh
vulnerability alert's ``cve``) and, far more often, in the text of a signature or an alert
("ET EXPLOIT Apache Log4j RCE (CVE-2021-44228)"), so all of what a signal kept is read for them."""

import json
import re
from collections.abc import Iterable, Mapping
from typing import Final

# CVE numbers are four digits at least, and began in 1999.
PATTERN: Final = re.compile(r"\bCVE-(\d{4})-(\d{4,7})\b", re.IGNORECASE)
FIRST_YEAR: Final = 1999
# How many a single signal can name before the rest is ignored, so that a log line that lists
# thousands (a scanner's report) can't fill the queue.
PER_SIGNAL: Final = 10


def ids_in(*texts: str | None) -> list[str]:
    """The CVE identifiers the texts name, in capitals, each once, in the order they appear."""
    found: dict[str, None] = {}
    for text in texts:
        for match in PATTERN.finditer(text or ""):
            if int(match.group(1)) >= FIRST_YEAR:
                found[match.group(0).upper()] = None
    return list(found)[:PER_SIGNAL]


def named_by(
    summary: str | None, signature: str | None, evidence: Mapping[str, object] | None
) -> list[str]:
    """The CVEs one signal names: in what it says, in its signature and in the evidence it kept."""
    kept = json.dumps(evidence, default=str) if evidence else None
    return ids_in(summary, signature, kept)


def is_cve(text: str) -> bool:
    """Whether the text is exactly one CVE identifier."""
    match = PATTERN.fullmatch(text.strip())
    return match is not None and int(match.group(1)) >= FIRST_YEAR


def merge(groups: Iterable[Iterable[str]]) -> list[str]:
    """The identifiers of every group, each once, in the order they first appear."""
    return list(dict.fromkeys(item for group in groups for item in group))
