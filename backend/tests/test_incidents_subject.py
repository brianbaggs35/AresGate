from ipaddress import ip_address

import pytest

from app.incidents import subject
from app.models import Event


def signal(src: str | None = None, dst: str | None = None, **changes: object) -> Event:
    fields: dict[str, object] = {
        "source": "wazuh",
        "kind": "alert",
        "signature": "sshd: authentication failed",
        "src_address": ip_address(src) if src else None,
        "dst_address": ip_address(dst) if dst else None,
        **changes,
    }
    return Event(**fields)


@pytest.mark.parametrize(
    "address", ["93.184.216.34", "192.168.1.20", "10.0.0.1", "2606:2800:220:1::1", "fd00::1"]
)
def test_an_address_of_a_machine_says_who_is_involved(address: str) -> None:
    assert subject.usable(ip_address(address))


@pytest.mark.parametrize(
    "address",
    [
        "0.0.0.0",  # noqa: S104
        "127.0.0.1",
        "224.0.0.251",
        "255.255.255.255",
        "169.254.1.1",
        "::",
        "::1",
        "ff02::1",
    ],
)
def test_an_address_everything_shares_says_nothing(address: str) -> None:
    assert not subject.usable(ip_address(address))


class TestWhatASignalIsAbout:
    def test_the_address_outside_the_network_wins_whichever_way_it_went(self) -> None:
        # An attack coming in, and a device calling out to somewhere it shouldn't.
        assert (
            subject.subject_of(signal(src="93.184.216.34", dst="192.168.1.20")) == "93.184.216.34"
        )
        assert (
            subject.subject_of(signal(src="192.168.1.20", dst="93.184.216.34")) == "93.184.216.34"
        )

    def test_where_both_are_outside_it_is_the_source(self) -> None:
        assert subject.subject_of(signal(src="93.184.216.34", dst="8.8.8.8")) == "93.184.216.34"

    def test_where_both_are_inside_it_is_the_source(self) -> None:
        assert subject.subject_of(signal(src="192.168.1.30", dst="192.168.1.20")) == "192.168.1.30"

    def test_a_signal_that_names_one_address_is_about_it(self) -> None:
        assert subject.subject_of(signal(dst="192.168.1.20")) == "192.168.1.20"
        assert subject.subject_of(signal(src="192.168.1.30")) == "192.168.1.30"

    def test_an_address_that_says_nothing_is_passed_over(self) -> None:
        assert subject.subject_of(signal(src="0.0.0.0", dst="192.168.1.20")) == "192.168.1.20"  # noqa: S104
        assert subject.subject_of(signal(src="192.168.1.20", dst="255.255.255.255")) == (
            "192.168.1.20"
        )

    def test_a_signal_with_no_address_is_about_the_rule_that_raised_it(self) -> None:
        assert subject.subject_of(signal()) == "rule:wazuh:sshd: authentication failed"
        assert subject.subject_of(signal(src="224.0.0.251")) == (
            "rule:wazuh:sshd: authentication failed"
        )

    def test_without_a_rule_it_is_the_kind_of_signal(self) -> None:
        assert subject.subject_of(signal(signature=None)) == "rule:wazuh:alert"

    def test_a_very_long_rule_is_cut(self) -> None:
        assert len(subject.subject_of(signal(signature="x" * 400))) == subject.MAX_SUBJECT
