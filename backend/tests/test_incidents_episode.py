from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import pytest

from app.incidents import episode
from app.models import Event

NOW = datetime(2026, 10, 26, 6, 0, tzinfo=UTC)


class TestWhatKindOfActivityASignalIs:
    @pytest.mark.parametrize(
        ("signature", "summary", "activity"),
        [
            ("ET SCAN Potential SSH Scan", "Alert", episode.SCAN),
            ("firewallservices/pf-scan-multi_ports", "Alert", episode.SCAN),
            (None, "Ban 182.161.66.3 for pf-scan-multi_ports", episode.SCAN),
            ("crowdsecurity/http-probing", "Alert", episode.SCAN),
            ("crowdsecurity/http-crawl-non_statics", "Alert", episode.SCAN),
            ("ET SCAN NMAP -sS", "Alert", episode.SCAN),
            ("Portscan detected", "Alert", episode.SCAN),
            (None, "Port scanning from 1.2.3.4", episode.SCAN),
            ("crowdsecurity/ssh-bf", "Alert", episode.BRUTE_FORCE),
            ("crowdsecurity/ssh-slow-bf", "Alert", episode.BRUTE_FORCE),
            (None, "Ban 1.2.3.4 for ssh-bruteforce", episode.BRUTE_FORCE),
            ("Brute force on ssh", "Alert", episode.BRUTE_FORCE),
            (None, "sshd: authentication failed.", episode.BRUTE_FORCE),
            (None, "Failed password for root", episode.BRUTE_FORCE),
            (None, "PAM: Login attempt for nonexistent user", episode.BRUTE_FORCE),
            (None, "Invalid user admin from 1.2.3.4", episode.BRUTE_FORCE),
            # Said both, it is the worse.
            ("SSH brute force scan", "Alert", episode.BRUTE_FORCE),
            ("ET MALWARE Possible Botnet C2", "Alert", None),
            (None, "A file was changed", None),
            # A word that only contains one is not one.
            ("Scanner is not scandalous", "Alert", episode.SCAN),
            (None, "Scandinavian proboscis", None),
        ],
    )
    def test_it_is_read_from_the_words_of_the_signal(
        self, signature: str | None, summary: str, activity: str | None
    ) -> None:
        event = Event(source="wazuh", kind="alert", signature=signature, summary=summary)

        assert episode.activity_of(event) == activity


class TestHowLongTheQuietMayBe:
    def test_a_scan_is_over_sooner_than_a_brute_force_or_anything_else(self) -> None:
        assert episode.gap_of(episode.SCAN) < episode.gap_of(episode.BRUTE_FORCE)
        assert episode.gap_of(None) == episode.DEFAULT_GAP
        assert episode.gap_of("something else") == episode.DEFAULT_GAP


class TestWhoTheNeighboursAre:
    @pytest.mark.parametrize(
        ("address", "block"),
        [
            ("93.184.216.34", "93.184.216.0/24"),
            ("93.184.216.255", "93.184.216.0/24"),
            ("2606:2800:220:1:248:1893:25c8:1946", "2606:2800:220:1::/64"),
            ("192.168.1.20", None),
            ("10.0.0.1", None),
            ("fe80::1", None),
            ("127.0.0.1", None),
        ],
    )
    def test_they_share_a_24_or_a_64_when_it_is_on_the_internet(
        self, address: str, block: str | None
    ) -> None:
        assert episode.block_of(ip_address(address)) == block

    def test_an_incident_about_a_rule_has_no_block(self) -> None:
        assert episode.block_of_subject("rule:wazuh:Something") is None
        assert episode.block_of_subject("93.184.216.34") == "93.184.216.0/24"

    def test_they_are_counted_without_the_subject_and_the_devices_inside(self) -> None:
        addresses = [
            ip_address(text)
            for text in ("93.184.216.34", "93.184.216.35", "93.184.216.36", "192.168.1.20")
        ]
        elsewhere = [ip_address("8.8.8.8")]

        assert episode.neighbours_of("93.184.216.34", "93.184.216.0/24", addresses) == 2
        assert episode.neighbours_of("93.184.216.34", "93.184.216.0/24", elsewhere) == 0
        assert episode.neighbours_of("192.168.1.20", None, addresses) == 0


class TestWaves:
    def test_signals_close_together_are_one_wave(self) -> None:
        times = [NOW + timedelta(minutes=minute) for minute in (0, 5, 14)]

        assert episode.waves_of(times) == 1

    def test_a_quiet_spell_starts_another(self) -> None:
        times = [NOW + timedelta(minutes=minute) for minute in (0, 5, 21, 25, 60)]

        assert episode.waves_of(times) == 3

    def test_they_are_counted_in_the_order_they_happened(self) -> None:
        times = [NOW + timedelta(hours=1), NOW, NOW + timedelta(minutes=1)]

        assert episode.waves_of(times) == 2

    def test_one_signal_is_one_wave(self) -> None:
        assert episode.waves_of([NOW]) == 1

    def test_a_signal_that_joins_starts_a_wave_after_a_quiet_spell(self) -> None:
        assert episode.next_wave(0, None, NOW) == 1
        assert episode.next_wave(1, NOW, NOW + timedelta(minutes=5)) == 1
        assert episode.next_wave(1, NOW, NOW + timedelta(minutes=16)) == 2
        assert episode.next_wave(3, NOW, NOW - timedelta(hours=1)) == 3
        # An incident that has not been worked out yet is one wave.
        assert episode.next_wave(0, NOW, NOW + timedelta(hours=1)) == 1


class TestPorts:
    def test_a_port_is_added_in_order_once(self) -> None:
        ports = episode.with_ports([], 443)
        ports = episode.with_ports(ports, 22)
        ports = episode.with_ports(ports, 443)

        assert ports == [22, 443]

    def test_a_signal_without_a_port_adds_none(self) -> None:
        known = [22]

        assert episode.with_ports(known, None) is known

    def test_only_so_many_are_kept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(episode, "MAX_PORTS", 2)

        assert episode.with_ports([22, 80], 443) == [22, 80]


class TestWhyTheyAreOne:
    def explain(self, **changes: object) -> list[str]:
        fields: dict[str, object] = {
            "subject": "93.184.216.34",
            "block": "93.184.216.0/24",
            "neighbours": 0,
            "activities": [],
            "waves": 1,
            "signals": 3,
            "port_count": 1,
        }
        return episode.explain(**{**fields, **changes})  # type: ignore[arg-type]

    def test_an_address_is_one_actor_whichever_program_saw_it(self) -> None:
        lines = self.explain()

        assert lines[0] == "Everything in it is about 93.184.216.34, whichever program saw it."
        assert len(lines) == 2
        assert lines[1].startswith("Each signal came less than 6 hours after the one before it.")
        assert "more than 24 hours in all" in lines[1]

    def test_neighbours_are_one_actor_when_a_bot_is_spread_over_a_block(self) -> None:
        lines = self.explain(neighbours=4, activities=[episode.SCAN])

        assert lines[0].startswith("Signals from 5 addresses of 93.184.216.0/24 doing the same")
        assert lines[1].startswith("Each scanning signal came less than 4 hours after")

    def test_a_rule_is_the_actor_where_there_is_no_address(self) -> None:
        lines = self.explain(subject="rule:wazuh:Something", block=None)

        assert lines[0] == "They come from one rule and name no address."

    def test_brute_force_has_its_own_gap(self) -> None:
        lines = self.explain(activities=[episode.BRUTE_FORCE])

        assert lines[1].startswith("Each brute force signal came less than 6 hours after")

    def test_a_scan_is_what_it_is_called_when_both_were_seen(self) -> None:
        lines = self.explain(activities=[episode.BRUTE_FORCE, episode.SCAN])

        assert lines[1].startswith("Each scanning signal came less than 4 hours after")

    def test_waves_and_ports_are_said_when_there_are_several(self) -> None:
        lines = self.explain(waves=3, signals=12, port_count=40)

        assert lines[2] == (
            "It came in 3 waves: 12 signals in bursts with at least 15 minutes of quiet "
            "between them."
        )
        assert lines[3] == "It touched 40 ports."

    def test_one_signal_is_a_signal(self) -> None:
        lines = self.explain(waves=2, signals=1, port_count=2)

        assert "1 signal in bursts" in lines[2]
        assert lines[3] == "It touched 2 ports."

    def test_an_hour_is_an_hour(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(episode.GAPS, episode.SCAN, timedelta(hours=1))

        lines = self.explain(activities=[episode.SCAN])

        assert "less than 1 hour after" in lines[1]
