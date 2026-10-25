"""What a sample is when a collector hands it over, before it is stored: one number read from a
connection at a moment, with the name of what it measures and the labels that tell it apart from
the same thing measured elsewhere."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256

from app.audit import clean
from app.events.event import KEY

MAX_LABELS = 8
MAX_LABEL_VALUE = 128

# Lowercase words, digits, underscores and dots: system.load_1m, interface.bytes_in.
_NAME = re.compile(r"^[a-z][a-z0-9_.]{0,63}$")
_LABEL = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


@dataclass(frozen=True)
class NewSample:
    """A sample as a collector found it. The names (the source, the connection, what is measured
    and the labels' names) are the collector's own words and are checked; a label's value came
    from the other system, and is cleaned up on the way in."""

    # The integration and the connection it was read from, such as opnsense and api.
    source: str
    connection: str
    # What is measured: system.load_1m, interface.bytes_in.
    name: str
    value: float
    # When it was read.
    sampled_at: datetime
    # What tells this from the same thing measured elsewhere, such as {"interface": "igc0"}.
    labels: Mapping[str, str] = field(default_factory=dict[str, str])

    def __post_init__(self) -> None:
        for what, value in (("source", self.source), ("connection", self.connection)):
            if not KEY.match(value):
                raise ValueError(f"A sample's {what} is a short lowercase name, not {value!r}.")
        if not _NAME.match(self.name):
            raise ValueError(
                f"What a sample measures is lowercase words joined by dots or underscores, "
                f"not {self.name!r}."
            )
        if self.sampled_at.tzinfo is None:
            raise ValueError("A sample's time must have a time zone.")
        if len(self.labels) > MAX_LABELS:
            raise ValueError(f"A sample has at most {MAX_LABELS} labels.")
        for label in self.labels:
            if not _LABEL.match(label):
                raise ValueError(f"A label's name is a short lowercase name, not {label!r}.")

    @property
    def clean_labels(self) -> dict[str, str]:
        """The labels with each value made safe to keep. One with nothing in it is left out."""
        cleaned = {label: _text(value) for label, value in self.labels.items()}
        return {label: value for label, value in sorted(cleaned.items()) if value is not None}

    @property
    def fingerprint(self) -> str:
        """A hash of which series this is a sample of: the same each time it is read."""
        return fingerprint(self.source, self.connection, self.name, self.clean_labels)


def fingerprint(source: str, connection: str, name: str, labels: Mapping[str, str]) -> str:
    """A hash of what is measured, for telling one series from another."""
    return sha256(
        json.dumps([source, connection, name, sorted(labels.items())]).encode()
    ).hexdigest()


def _text(value: str) -> str | None:
    """Text from a program, made safe to keep: control characters become spaces, anything that
    isn't text is replaced, and it's cut to fit."""
    cleaned = clean(value, MAX_LABEL_VALUE)
    return None if cleaned is None else cleaned.encode("utf-8", "replace").decode("utf-8")
