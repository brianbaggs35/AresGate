"""Purpose: what a conversation was for, in plain words, from what a program recognised."""

import pytest

from app.incidents import purpose


class TestWhatItWasFor:
    def test_a_known_port_says_what_it_is_used_for(self) -> None:
        assert purpose.of(app=None, port=22, protocol="tcp") == "Logging in to a computer (SSH)"

    def test_an_application_a_program_recognised_wins_over_the_port(self) -> None:
        found = purpose.of(app="DNS", port=8443, protocol="udp")

        assert found == "Looking up a name (DNS)"

    @pytest.mark.parametrize("app", ["tls", "ssl", "quic"])
    def test_encrypted_web_traffic_has_one_description(self, app: str) -> None:
        assert purpose.of(app=app, port=None, protocol=None) == purpose.of(
            app=None, port=443, protocol=None
        )

    def test_what_it_asked_for_is_added(self) -> None:
        found = purpose.of(app="dns", port=53, protocol="udp", asked_for="example.org")

        assert found == "Looking up a name (DNS): example.org"

    def test_a_ping_is_a_ping(self) -> None:
        assert purpose.of(app=None, port=None, protocol="ICMP") == "Pinging a device (ICMP)"

    def test_nothing_is_said_where_nothing_is_known(self) -> None:
        assert purpose.of(app=None, port=40123, protocol="tcp") is None
        assert purpose.of(app="somethingnew", port=None, protocol=None, asked_for="x") is None
