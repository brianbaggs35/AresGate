"""What the collectors that measure have in common: the numbers in what a product says, and the
samples one run reads."""

import math
import re

from app.collectors.base import Context
from app.metrics.sample import NewSample

# Digits with an optional fraction, and, for the second, the unit that may follow: "1.2 ms".
_PLAIN = re.compile(r"^-?\d+(?:\.\d+)?$")
_LEADING = re.compile(r"^(-?\d+(?:\.\d+)?)\s*[a-zA-Z%]*$")


def number(value: object) -> float | None:
    """A number that a product gave as one, or as digits in a string (PHP, which OPNsense runs on,
    hands some over as text), or None. A flag, "N/A" and anything that isn't finite are not
    numbers."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    if isinstance(value, str) and not _PLAIN.match(value.strip()):
        return None
    try:
        found = float(value)
    except OverflowError:
        return None
    return found if math.isfinite(found) else None


def leading_number(value: object) -> float | None:
    """The number a reading starts with: 1.2 for "1.2 ms" and 0.0 for "0.0 %". "~", which is what
    OPNsense shows for what it doesn't have, is None."""
    if isinstance(value, str) and (found := _LEADING.match(value.strip())):
        return number(found[1])
    return number(value)


class Readings:
    """The samples a run reads, all as of the moment it began."""

    def __init__(self, context: Context) -> None:
        self._context = context
        self.samples: list[NewSample] = []

    def add(self, name: str, value: float | None, **labels: str) -> None:
        """Keeps a reading, unless there was nothing to read."""
        if value is None:
            return
        target = self._context.target
        self.samples.append(
            NewSample(
                source=target.integration,
                connection=target.connection,
                name=name,
                value=value,
                sampled_at=self._context.now,
                labels=labels,
            )
        )

    async def save(self) -> int:
        """Stores them, and returns how many were new."""
        return await self._context.record_samples(self.samples)
