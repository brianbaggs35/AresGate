from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv6Address

import pytest

from app.devices.sighting import MAX_HOSTNAME, MAX_VENDOR, NewSighting, mac_address

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
MAC = "00:11:22:0a:0b:0c"


class TestMacAddress:
    @pytest.mark.parametrize(
        ("shown", "kept"),
        [
            ("00:11:22:0a:0b:0c", MAC),
            ("00:11:22:0A:0B:0C", MAC),
            ("00-11-22-0a-0b-0c", MAC),
            ("0:11:22:a:b:c", MAC),
            ("0-11-22-a-b-c", MAC),
            ("0011220a0b0c", MAC),
            ("0011220A0B0C", MAC),
            ("  00:11:22:0a:0b:0c\n", MAC),
            ("ac:de:48:00:00:02", "ac:de:48:00:00:02"),
        ],
    )
    def test_it_is_kept_in_lowercase_with_every_byte_in_two_digits(
        self, shown: str, kept: str
    ) -> None:
        assert mac_address(shown) == kept

    @pytest.mark.parametrize(
        "shown",
        [
            "",
            "(incomplete)",
            "00:11:22:0a:0b",
            "00:11:22:0a:0b:0c:0d",
            "00:11:22:0a:0b:0g",
            "00:11:22:0a:0b:0cc",
            "00:11-22:0a-0b:0c",
            "0011220a0b0",
            "0011220a0b0c0",
            "001122.0a0b0c",
            "mac",
        ],
    )
    def test_text_that_is_not_six_bytes_is_not_an_address(self, shown: str) -> None:
        assert mac_address(shown) is None

    @pytest.mark.parametrize(
        "shown",
        [
            "00:00:00:00:00:00",
            "0:0:0:0:0:0",
            "ff:ff:ff:ff:ff:ff",
            "01:00:5e:00:00:fb",
            "33:33:00:00:00:01",
        ],
    )
    def test_the_empty_the_broadcast_and_multicast_addresses_are_no_ones(self, shown: str) -> None:
        assert mac_address(shown) is None

    def test_an_address_that_is_locally_administered_is_a_device_like_any_other(self) -> None:
        # What a phone uses when it keeps its hardware address to itself.
        assert mac_address("da:a1:19:00:00:01") == "da:a1:19:00:00:01"


class TestMakingASighting:
    def test_it_holds_what_was_listed(self) -> None:
        sighting = NewSighting.of(
            "0:11:22:a:b:c",
            NOW,
            address="192.168.1.20",
            hostname="laptop",
            vendor="Example Devices Inc.",
        )

        assert sighting == NewSighting(
            MAC, NOW, IPv4Address("192.168.1.20"), "laptop", "Example Devices Inc."
        )

    def test_it_needs_nothing_but_the_hardware_address_and_the_time(self) -> None:
        assert NewSighting.of(MAC, NOW) == NewSighting(MAC, NOW)

    @pytest.mark.parametrize("mac", ["", "(incomplete)", "00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"])
    def test_what_is_not_a_device_is_no_sighting(self, mac: str) -> None:
        assert NewSighting.of(mac, NOW, address="192.168.1.20") is None

    @pytest.mark.parametrize(
        ("shown", "kept"),
        [
            ("192.168.1.20", IPv4Address("192.168.1.20")),
            (" 192.168.1.20 ", IPv4Address("192.168.1.20")),
            ("fd00::1234", IPv6Address("fd00::1234")),
            ("fe80::1%igb1", IPv6Address("fe80::1")),
            ("FD00:0:0:0:0:0:0:ABCD", IPv6Address("fd00::abcd")),
            ("", None),
            ("unknown", None),
            ("192.168.1", None),
            ("192.168.1.256", None),
            ("host.lan", None),
        ],
    )
    def test_an_address_is_kept_if_it_is_one(
        self, shown: str, kept: IPv4Address | IPv6Address | None
    ) -> None:
        sighting = NewSighting.of(MAC, NOW, address=shown)

        assert sighting is not None
        assert sighting.address == kept

    @pytest.mark.parametrize(
        ("shown", "kept"),
        [
            ("laptop", "laptop"),
            ("  laptop\n", "laptop"),
            ("Brians-iPhone", "Brians-iPhone"),
            ("camera.lan.", "camera.lan"),
            ("lap\ttop\x00", "lap top"),
            ("", None),
            ("   ", None),
            ("*", None),
            ("?", None),
            ("-", None),
            (".", None),
            (None, None),
        ],
    )
    def test_a_name_is_kept_if_the_device_has_one(
        self, shown: str | None, kept: str | None
    ) -> None:
        sighting = NewSighting.of(MAC, NOW, hostname=shown)

        assert sighting is not None
        assert sighting.hostname == kept

    def test_a_name_that_is_not_text_is_made_text(self) -> None:
        sighting = NewSighting.of(MAC, NOW, hostname="caf\udce9")

        assert sighting is not None
        assert sighting.hostname == "caf?"

    def test_a_name_and_a_maker_are_cut_to_fit(self) -> None:
        sighting = NewSighting.of(MAC, NOW, hostname="h" * 400, vendor="v" * 400)

        assert sighting is not None
        assert sighting.hostname == "h" * MAX_HOSTNAME
        assert sighting.vendor == "v" * MAX_VENDOR

    @pytest.mark.parametrize(
        ("shown", "kept"), [("Example Devices", "Example Devices"), ("", None)]
    )
    def test_a_maker_is_kept_if_it_is_known(self, shown: str, kept: str | None) -> None:
        sighting = NewSighting.of(MAC, NOW, vendor=shown)

        assert sighting is not None
        assert sighting.vendor == kept


class TestWhatASightingNeeds:
    @pytest.mark.parametrize("mac", ["", "0:11:22:a:b:c", "00:11:22:0A:0B:0C", "00:00:00:00:00:00"])
    def test_the_hardware_address_is_in_the_form_it_is_kept_in(self, mac: str) -> None:
        with pytest.raises(ValueError, match="MAC address"):
            NewSighting(mac, NOW)

    def test_the_time_needs_a_time_zone(self) -> None:
        with pytest.raises(ValueError, match="time zone"):
            NewSighting(MAC, datetime(2026, 10, 25, 12, 0))
