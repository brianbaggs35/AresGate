"""The widgets the dashboard is made of, the presets, and what is read back of a saved layout."""

from app import dashboard_layout
from app.dashboard_layout import PRESETS, WIDGETS, Place


def ids(places: list[Place] | tuple[Place, ...]) -> list[str]:
    return [place.id for place in places]


def test_each_widget_is_named_once() -> None:
    assert len({widget.id for widget in WIDGETS}) == len(WIDGETS)
    assert {widget.id for widget in WIDGETS} == dashboard_layout.WIDGET_IDS


def test_each_preset_places_every_widget_once_and_the_first_is_the_default() -> None:
    for preset in PRESETS:
        assert sorted(ids(preset.places)) == sorted(dashboard_layout.WIDGET_IDS)
    assert dashboard_layout.default_places() == PRESETS[0].places
    assert [place.size for place in PRESETS[0].places] == [widget.size for widget in WIDGETS]
    assert not any(place.hidden for place in PRESETS[0].places)
    assert {"overview", "threat_watch", "compact"} == dashboard_layout.PRESET_KEYS


def test_threat_watch_leads_with_what_needs_a_decision_and_leaves_the_rest_out() -> None:
    watch = next(preset for preset in PRESETS if preset.key == "threat_watch")

    shown = [place.id for place in watch.places if not place.hidden]

    assert shown == ["needs_you", "latest", "alerts", "blocked", "noise"]
    assert all(place.hidden for place in watch.places[len(shown) :])


def test_compact_shows_two_to_a_row() -> None:
    compact = next(preset for preset in PRESETS if preset.key == "compact")

    assert {place.size for place in compact.places} == {"half"}
    assert {place.id for place in compact.places if place.hidden} == {
        "filtered",
        "review",
        "blocked",
        "noise",
    }


def test_a_layout_is_made_whole_by_adding_what_it_lacks_at_the_end() -> None:
    kept = dashboard_layout.complete([Place("latest", "full", True), Place("traffic", "half")])

    assert ids(kept)[:2] == ["latest", "traffic"]
    assert sorted(ids(kept)) == sorted(dashboard_layout.WIDGET_IDS)
    assert kept[0] == Place("latest", "full", True)
    # What was added is shown, as wide as it starts.
    added = {place.id: place for place in kept[2:]}
    assert all(not place.hidden for place in added.values())
    assert added["blocked"].size == "full"


def test_a_layout_drops_what_is_not_known_and_what_is_named_twice() -> None:
    kept = dashboard_layout.complete(
        [Place("gone", "half"), Place("traffic", "full"), Place("traffic", "half")]
    )

    assert "gone" not in ids(kept)
    assert ids(kept).count("traffic") == 1
    assert kept[0] == Place("traffic", "full")


def test_what_was_stored_is_read_back_whatever_state_it_is_in() -> None:
    read = dashboard_layout.from_stored(
        [
            {"id": "latest", "size": "full", "hidden": True},
            {"id": "traffic", "size": "huge", "hidden": "yes"},
            {"id": "gone", "size": "half", "hidden": False},
            {"size": "half"},
        ]
    )

    assert read[0] == Place("latest", "full", True)
    # A size it does not know is the widget's own, and anything but true is not hidden.
    assert read[1] == Place("traffic", "half", False)
    assert sorted(ids(read)) == sorted(dashboard_layout.WIDGET_IDS)


def test_a_layout_is_stored_as_plain_values() -> None:
    stored = dashboard_layout.to_stored([Place("traffic", "half", True)])

    assert stored == [{"id": "traffic", "size": "half", "hidden": True}]
    assert dashboard_layout.from_stored(stored)[0] == Place("traffic", "half", True)
