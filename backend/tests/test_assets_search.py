from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.assets import inventory
from app.assets.inventory import Inventory
from app.assets.search import Counts, Query, search
from app.models import Interface
from e2e import factories
from e2e.factories import AssetSpec, HostSpec, Listed

NOW = datetime(2026, 11, 1, 18, 0, tzinfo=UTC)
LAPTOP = "00:11:22:0a:0b:0c"
PHONE = "02:aa:bb:cc:dd:ee"
CAMERA = "00:11:22:0a:0b:0d"


def arp(minutes: float = 1) -> Listed:
    return Listed("opnsense", "arp", minutes)


def build(session: Session) -> Inventory:
    """Four devices and an agent: a laptop that is on and that Wazuh and OPNsense list, a phone
    with a private address that has a lease only, a camera that has been away, and nothing
    known of the last device but its hardware address."""
    home = Interface(name="Home", role="home", networks=["192.168.1.0/24"], position=0)
    iot = Interface(name="IoT", role="iot", networks=["192.168.20.0/24"], position=1)
    session.add_all([home, iot])
    factories.assets(
        session,
        NOW,
        [
            AssetSpec(
                hostname="Laptop",
                mac=LAPTOP,
                vendor="Example Devices Inc.",
                addresses=("192.168.1.20",),
                listed=(arp(1), Listed("ntopng", "hosts", 1)),
                first_seen_hours=24 * 60,
            ),
            AssetSpec(
                hostname="phone",
                mac=PHONE,
                addresses=("192.168.1.9",),
                listed=(Listed("opnsense", "dhcp", 30),),
                first_seen_hours=30,
            ),
            AssetSpec(
                hostname="camera",
                mac=CAMERA,
                vendor="Example Cameras Corp.",
                addresses=("192.168.20.40", "fd00:20::40"),
                listed=(arp(3 * 24 * 60),),
                first_seen_hours=24 * 50,
            ),
            AssetSpec(mac="00:11:22:0a:0b:0e", first_seen_hours=24 * 40, listed=(arp(2 * 60),)),
        ],
        [HostSpec("002", hostname="laptop", address="192.168.1.20")],
    )
    session.flush()
    return inventory.load(session, NOW)


@pytest.fixture
def found(session: Session) -> Inventory:
    return build(session)


def find(found: Inventory, **changes: Any) -> list[str]:
    page = search(found, Query(**changes), limit=50)
    return [asset.name for asset in page.assets]


class TestFindingByWords:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("laptop", ["Laptop"]),
            ("LAPTOP", ["Laptop"]),
            ("cameras", ["camera"]),
            ("192.168.1.2", ["Laptop"]),
            ("192.168.20", ["camera"]),
            ("fd00:20", ["camera"]),
            ("00:11:22:0a:0b:0c", ["Laptop"]),
            ("00-11-22-0a-0b-0c", ["Laptop"]),
            ("0011220a0b0c", ["Laptop"]),
            ("ntopng", ["Laptop"]),
            ("wazuh", ["Laptop"]),
            ("opnsense", ["Laptop", "camera", "phone", "00:11:22:0a:0b:0e"]),
            ("nothing like this", []),
        ],
    )
    def test_a_word_is_looked_for_everywhere_an_asset_says_who_it_is(
        self, found: Inventory, text: str, expected: list[str]
    ) -> None:
        assert sorted(find(found, text=text)) == sorted(expected)

    def test_a_machine_with_no_hardware_address_is_found_by_its_name_and_address(
        self, session: Session
    ) -> None:
        factories.assets(
            session, NOW, [], [HostSpec("005", hostname="build-server", address="10.9.9.9")]
        )
        found = inventory.load(session, NOW)

        assert find(found, text="build") == ["build-server"]
        assert find(found, text="10.9.9") == ["build-server"]
        assert find(found, text="wazuh") == ["build-server"]
        assert find(found, text="00:11") == []

    def test_every_word_has_to_be_there(self, found: Inventory) -> None:
        assert find(found, text="laptop ntopng") == ["Laptop"]
        assert find(found, text="laptop camera") == []

    def test_no_words_find_everything(self, found: Inventory) -> None:
        assert len(find(found, text="  ")) == 4


class TestFindingByChoices:
    def test_a_state_narrows_to_it(self, found: Inventory) -> None:
        assert find(found, status="online") == ["Laptop"]
        assert find(found, status="recent") == ["phone", "00:11:22:0a:0b:0e"]
        assert find(found, status="away") == ["camera"]

    def test_the_counts_follow_every_choice_but_the_state(self, found: Inventory) -> None:
        everything = search(found, Query(), limit=50).counts
        narrowed = search(found, Query(status="online", text="camera"), limit=50)

        assert everything == Counts(online=1, recent=2, away=1)
        assert everything.all == 4
        assert narrowed.counts == Counts(online=0, recent=0, away=1)
        assert narrowed.total == 0

    def test_listed_by_any_of_the_sources_chosen(self, found: Inventory) -> None:
        assert sorted(find(found, sources=("ntopng",))) == ["Laptop"]
        assert sorted(find(found, sources=("ntopng", "wazuh"))) == ["Laptop"]
        assert len(find(found, sources=("opnsense",))) == 4
        assert find(found, sources=("crowdsec",)) == []

    def test_an_interface_narrows_to_what_is_on_its_networks(self, found: Inventory) -> None:
        home, iot = (item.id for item in found.networks)

        assert sorted(
            asset.name for asset in search(found, Query(interface=home), limit=9).assets
        ) == [
            "Laptop",
            "phone",
        ]
        assert [asset.name for asset in search(found, Query(interface=iot), limit=9).assets] == [
            "camera"
        ]
        assert search(found, Query(interface=99), limit=9).total == 0

    def test_new_finds_what_was_first_listed_after_the_first_day_in_the_last_week(
        self, found: Inventory
    ) -> None:
        assert sorted(find(found, new=True)) == ["phone"]

    def test_unidentified_finds_what_says_nothing_of_itself(self, found: Inventory) -> None:
        assert find(found, unidentified=True) == ["00:11:22:0a:0b:0e"]

    def test_choices_and_words_all_have_to_hold(self, found: Inventory) -> None:
        assert find(found, text="phone", status="recent", new=True) == ["phone"]
        assert find(found, text="phone", status="online") == []


class TestOrder:
    def test_the_most_recently_listed_come_first(self, found: Inventory) -> None:
        assert find(found) == ["Laptop", "phone", "00:11:22:0a:0b:0e", "camera"]

    def test_by_name_without_regard_to_capitals(self, found: Inventory) -> None:
        assert find(found, sort="name") == ["00:11:22:0a:0b:0e", "camera", "Laptop", "phone"]

    def test_by_address_in_the_order_of_their_numbers_with_none_last(
        self, found: Inventory
    ) -> None:
        # 192.168.1.9 comes before 192.168.1.20; the one with no address is last.
        assert find(found, sort="address") == ["phone", "Laptop", "camera", "00:11:22:0a:0b:0e"]

    def test_by_when_it_was_first_listed_newest_first(self, found: Inventory) -> None:
        assert find(found, sort="first") == ["phone", "00:11:22:0a:0b:0e", "camera", "Laptop"]

    def test_ties_fall_back_to_the_name_so_the_order_does_not_shuffle(
        self, session: Session
    ) -> None:
        factories.assets(
            session,
            NOW,
            [AssetSpec(hostname=name, listed=(arp(5),)) for name in ("b", "a", "c")],
            [],
        )
        found = inventory.load(session, NOW)

        assert [asset.name for asset in search(found, Query(), limit=9).assets] == ["a", "b", "c"]


class TestPages:
    def test_a_page_is_part_of_the_total(self, found: Inventory) -> None:
        first = search(found, Query(), limit=3)
        rest = search(found, Query(), limit=3, offset=3)

        assert (first.total, len(first.assets), rest.total, len(rest.assets)) == (4, 3, 4, 1)
        assert not {asset.key for asset in first.assets} & {asset.key for asset in rest.assets}

    def test_a_page_past_the_end_is_empty(self, found: Inventory) -> None:
        page = search(found, Query(), limit=3, offset=30)

        assert (page.total, page.assets) == (4, [])


class TestWhatEachChoiceWouldFind:
    def test_they_are_counted_over_everything_whatever_was_chosen(self, found: Inventory) -> None:
        home, iot = (item.id for item in found.networks)

        page = search(found, Query(text="camera"), limit=9)

        assert page.facets.sources == {"opnsense": 4, "ntopng": 1, "wazuh": 1}
        assert page.facets.interfaces == {home: 2, iot: 1}
        assert (page.facets.new, page.facets.unidentified) == (1, 1)
