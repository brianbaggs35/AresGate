"""What a threat-intelligence service answered about a subject, whichever service it was.

A report is counts: how many of the service's sources flag the subject as malicious, how many as
suspicious, how many as harmless and how many found nothing. For VirusTotal the sources are its
engines. For AlienVault OTX they are the pulses that name the subject: those that also name a
malware family, an adversary or an attack technique are the malicious ones, and the rest are the
suspicious ones. Each service decides what the counts come to (``judge`` in its own module).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

type Judgement = Literal["malicious", "suspicious", "clean", "unknown"]


@dataclass(frozen=True)
class Report:
    """What the service said of one subject."""

    malicious: int
    suspicious: int
    harmless: int
    undetected: int
    reputation: int
    analysed_at: datetime
    country: str | None = None
    owner: str | None = None
    asn: int | None = None
    # The categories the engines gave the subject, each once, in order.
    categories: tuple[str, ...] = ()
    # What the answer says beyond the counts, as a label and its text.
    details: tuple[tuple[str, str], ...] = ()

    @property
    def engines(self) -> int:
        """How many engines gave a verdict on the subject."""
        return self.malicious + self.suspicious + self.harmless + self.undetected


@dataclass(frozen=True)
class Reported:
    """the service has a report on the subject."""

    report: Report


@dataclass(frozen=True)
class Unknown:
    """the service has no report on the subject."""


@dataclass(frozen=True)
class Failed:
    """The lookup didn't give a report. The message says why, for the log and for the person."""

    message: str


@dataclass(frozen=True)
class Limited:
    """the service's daily quota is used up. Nothing is asked until it resets, at ``until``."""

    until: datetime


@dataclass(frozen=True)
class Throttled:
    """the service asked for fewer requests for a minute. Nothing is asked until ``until``."""

    until: datetime


Answer = Reported | Unknown | Failed | Limited | Throttled
