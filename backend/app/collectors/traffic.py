"""What the collectors have in common when they read a line of traffic: the strings and numbers a
JSON object holds, how to write an address with its port, and how to tell lines apart that agree
on everything they say."""

from collections import Counter
from collections.abc import Mapping


def text(entry: Mapping[str, object], key: str) -> str:
    """A member as text: what a product gives as a string or a number, or nothing."""
    value = entry.get(key)
    return str(value) if isinstance(value, str | int) else ""


def number(entry: Mapping[str, object], key: str) -> int | None:
    """A member that is a whole number, such as a port, as one, or None."""
    shown = text(entry, key)
    return int(shown) if shown.isascii() and shown.isdigit() else None


def endpoint(address: str, port: int | None) -> str:
    """``198.51.100.7:443``, or ``[2001:db8::7]:443`` for an address that has colons itself."""
    if not address:
        return ""
    if port is None:
        return address
    return f"[{address}]:{port}" if ":" in address else f"{address}:{port}"


def route(source: str, destination: str) -> str:
    """Where traffic went, with whichever ends are known."""
    if source and destination:
        return f"{source} to {destination}"
    return f"to {destination}" if destination else source


class Occurrences:
    """Tells apart lines that agree on every fact. Counting from the newest, the first of them is
    the same whichever window of the log it is read in, so a window that has moved on neither
    stores a line twice nor loses one."""

    def __init__(self) -> None:
        self._seen: Counter[tuple[str, ...]] = Counter()

    def identity(self, facts: tuple[str, ...]) -> tuple[str | int, ...]:
        """The facts and how many lines with the same facts came before this one."""
        count = self._seen[facts]
        self._seen[facts] += 1
        return (*facts, count)
