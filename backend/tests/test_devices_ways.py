import pytest

from app.devices import ways


def test_only_a_listing_that_can_only_hold_what_is_there_now_is_presence() -> None:
    assert {key for key, way in ways.WAYS.items() if way.presence} == {
        ways.ARP,
        ways.HOSTS,
        ways.AGENT,
    }
    # A lease is given out for a day or more, so it outlasts the device that holds it.
    assert not ways.WAYS[ways.DHCP].presence
    # What an agent said an hour ago says nothing of whether the machine is on now.
    assert not ways.WAYS[ways.INVENTORY].presence


def test_every_way_has_words_for_a_page() -> None:
    assert all(way.label for way in ways.WAYS.values())


def test_a_way_that_exists_is_itself() -> None:
    assert ways.check("arp") == "arp"


def test_a_way_that_does_not_is_a_mistake() -> None:
    with pytest.raises(ValueError, match="'carrier-pigeon'"):
        ways.check("carrier-pigeon")
