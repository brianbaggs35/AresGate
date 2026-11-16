"""The widgets the dashboard is made of, the presets that arrange them, and what an account may
save of its own arrangement.

The widgets are named here and drawn by the web app; this is what says which there are, how wide
each starts and what a layout may hold, so a layout from an older or newer version still makes
sense: a widget that is gone is dropped, and one that is new is added at the end."""

from dataclasses import dataclass
from typing import Final, Literal

Size = Literal["half", "full"]
SIZES: Final[tuple[Size, ...]] = ("half", "full")


@dataclass(frozen=True)
class Widget:
    id: str
    # How wide it starts: the whole row or half of it (which a phone always shows whole).
    size: Size


@dataclass(frozen=True)
class Place:
    """One widget in a layout: how wide it is, and whether it is left out."""

    id: str
    size: Size
    hidden: bool = False


@dataclass(frozen=True)
class Preset:
    key: str
    title: str
    description: str
    places: tuple[Place, ...]


# In the order the dashboard shows them to someone who has not changed it. The status banner and
# its four numbers are always first and are not a widget. What each is called and drawn as is the
# web app's (src/dashboardLayout.ts), which has to have each of these.
WIDGETS: Final[tuple[Widget, ...]] = (
    Widget("filtered", "full"),
    Widget("review", "full"),
    Widget("needs_you", "full"),
    Widget("traffic", "half"),
    Widget("alerts", "half"),
    Widget("blocked", "full"),
    Widget("noise", "full"),
    Widget("sources", "half"),
    Widget("latest", "half"),
)
WIDGET_IDS: Final = frozenset(widget.id for widget in WIDGETS)


def _all(size: Size | None = None, hide: tuple[str, ...] = ()) -> tuple[Place, ...]:
    return tuple(Place(widget.id, size or widget.size, widget.id in hide) for widget in WIDGETS)


def _ordered(first: tuple[tuple[str, Size], ...]) -> tuple[Place, ...]:
    """These widgets, in this order, then every other widget left out."""
    named = {widget_id for widget_id, _ in first}
    return (
        *(Place(widget_id, size) for widget_id, size in first),
        *(Place(widget.id, widget.size, True) for widget in WIDGETS if widget.id not in named),
    )


PRESETS: Final[tuple[Preset, ...]] = (
    Preset(
        "overview",
        "Overview",
        "Everything the dashboard can show, in the order that fits what matters.",
        _all(),
    ),
    Preset(
        "threat_watch",
        "Threat watch",
        "What needs a decision first, then the alerts as they come, for keeping an eye on it.",
        _ordered(
            (
                ("needs_you", "full"),
                ("latest", "full"),
                ("alerts", "half"),
                ("blocked", "half"),
                ("noise", "full"),
            )
        ),
    ),
    Preset(
        "compact",
        "Compact",
        "Only the charts and lists, two to a row, with the notes and reminders left out.",
        _all("half", hide=("filtered", "review", "blocked", "noise")),
    ),
)
PRESET_KEYS: Final = frozenset(preset.key for preset in PRESETS)


def default_places() -> tuple[Place, ...]:
    return PRESETS[0].places


def complete(places: list[Place]) -> list[Place]:
    """The places a layout holds with each widget once: one that is not known is dropped, one named
    twice is kept where it first is, and one that is missing, such as a widget a newer version
    added, comes last and is shown."""
    seen: set[str] = set()
    kept: list[Place] = []
    for place in places:
        if place.id in WIDGET_IDS and place.id not in seen:
            seen.add(place.id)
            kept.append(place)
    kept.extend(Place(widget.id, widget.size) for widget in WIDGETS if widget.id not in seen)
    return kept


def from_stored(stored: list[dict[str, object]]) -> list[Place]:
    """What the database holds, read back as places. A value that is not what it should be is
    taken as the widget's default, so a hand-edited row cannot break the page."""
    by_id = {widget.id: widget for widget in WIDGETS}
    places: list[Place] = []
    for item in stored:
        widget = by_id.get(str(item.get("id")))
        if widget is None:
            continue
        size = item.get("size")
        places.append(
            Place(
                widget.id,
                size if size in SIZES else widget.size,  # pyright: ignore[reportArgumentType]
                item.get("hidden") is True,
            )
        )
    return complete(places)


def to_stored(places: list[Place]) -> list[dict[str, object]]:
    return [{"id": place.id, "size": place.size, "hidden": place.hidden} for place in places]
