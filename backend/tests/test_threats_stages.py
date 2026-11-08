"""The stage of an attack a signal is: looking, trying to get in, or a sign that it worked."""

import pytest

from app.models import Event
from app.threats import stages


def signal(summary: str, signature: str | None = None) -> Event:
    return Event(source="opnsense", kind="alert", severity=2, summary=summary, signature=signature)


class TestWhatStageASignalIs:
    @pytest.mark.parametrize(
        "summary",
        [
            "ET SCAN Potential SSH Scan",
            "Port scan detected",
            "firewallservices/pf-scan-multi_ports",
        ],
    )
    def test_scanning_is_looking(self, summary: str) -> None:
        assert stages.stage_of(signal(summary)) == stages.RECON

    @pytest.mark.parametrize(
        "summary",
        [
            "ET EXPLOIT Apache Log4j RCE Attempt (CVE-2021-44228)",
            "SQL injection attempt",
            "Remote code execution in a web app",
            "Path traversal",
            "ET WEB_SERVER Shellshock",
        ],
    )
    def test_a_flaw_being_tried_is_trying_to_get_in(self, summary: str) -> None:
        assert stages.stage_of(signal(summary)) == stages.ACCESS

    @pytest.mark.parametrize(
        "summary",
        [
            "ET MALWARE Cobalt Strike Beacon Observed",
            "Possible reverse shell",
            "web shell uploaded",
            "ransomware activity",
            "Connection to a known C2 server",
            "ET CNC Feodo Tracker Reported CnC Server",
            "Multiple authentication failures followed by a success",
        ],
    )
    def test_a_sign_that_it_worked_is_a_foothold(self, summary: str) -> None:
        assert stages.stage_of(signal(summary)) == stages.FOOTHOLD

    def test_the_furthest_wins_when_a_signal_says_several(self) -> None:
        assert stages.stage_of(signal("scan that loaded malware")) == stages.FOOTHOLD
        assert stages.stage_of(signal("scan with an exploit in it")) == stages.ACCESS

    @pytest.mark.parametrize(
        "summary", ["sshd: authentication failed", "Blocked tcp 203.0.113.9", "ordinary"]
    )
    def test_guessing_passwords_and_ordinary_traffic_are_none_of_them(self, summary: str) -> None:
        assert stages.stage_of(signal(summary)) is None

    def test_the_words_are_read_from_the_signature_too(self) -> None:
        assert stages.stage_of(signal("rule fired", "ET MALWARE Trojan")) == stages.FOOTHOLD


class TestTheStagesOfAnIncident:
    def test_a_signal_adds_its_stage_in_the_order_of_the_path(self) -> None:
        found = stages.with_stage([stages.FOOTHOLD], signal("scan"))

        assert found == [stages.RECON, stages.FOOTHOLD]

    def test_a_stage_it_already_has_or_none_changes_nothing(self) -> None:
        known = [stages.RECON]

        assert stages.with_stage(known, signal("scan")) is known
        assert stages.with_stage(known, signal("ordinary")) is known

    def test_a_foothold_or_more_than_one_stage_is_a_chain(self) -> None:
        assert not stages.is_chain([])
        assert not stages.is_chain([stages.RECON])
        assert not stages.is_chain([stages.ACCESS])
        assert stages.is_chain([stages.FOOTHOLD])
        assert stages.is_chain([stages.RECON, stages.ACCESS])


def test_how_far_an_attack_got_is_the_furthest_stage_it_reached() -> None:
    assert stages.depth([]) == 0
    assert stages.depth(["recon"]) == 1
    assert stages.depth(["recon", "access"]) == 2
    assert stages.depth(["recon", "access", "foothold"]) == 3
    assert stages.depth(["foothold"]) == 3
    assert stages.depth(["unheard-of"]) == 0
