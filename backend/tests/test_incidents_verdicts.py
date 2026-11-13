from datetime import UTC, datetime, timedelta
from ipaddress import ip_address, ip_network

import pytest
from sqlalchemy.orm import Session

from app.incidents import verdicts
from app.models import Incident, IncidentSignal, VerdictRule

ATTACKER = "93.184.216.34"
DEVICE = "192.168.1.20"
NOW = datetime(2026, 10, 26, 6, 0, tzinfo=UTC)


def rule(verdict: str = "not_suspicious", **about: str | None) -> VerdictRule:
    fields = {"address": None, "destination": None, "source": None, "signature": None, **about}
    address, destination = fields["address"], fields["destination"]
    return VerdictRule(
        id=1,
        verdict=verdict,
        address=ip_address(address) if address else None,
        destination=ip_network(destination) if destination else None,
        source=fields["source"],
        signature=fields["signature"],
    )


def signal(
    src: str | None = ATTACKER, dst: str | None = DEVICE, **changes: object
) -> IncidentSignal:
    fields: dict[str, object] = {
        "source": "wazuh",
        "kind": "alert",
        "signature": "ET SCAN Potential SSH Scan",
        "src_address": ip_address(src) if src else None,
        "dst_address": ip_address(dst) if dst else None,
        **changes,
    }
    return IncidentSignal(**fields)


class TestWhatARuleMatches:
    def test_a_rule_on_an_address_matches_what_is_about_it(self) -> None:
        assert verdicts.matches(rule(address=ATTACKER), signal())

    def test_and_what_came_from_it(self) -> None:
        # Between two devices on the network the signal is about the one it came from.
        assert verdicts.matches(rule(address=DEVICE), signal(src=DEVICE, dst="192.168.1.30"))

    def test_but_not_what_was_only_going_to_it(self) -> None:
        # Saying a device is fine must not hide an attack on it.
        assert not verdicts.matches(rule(address=DEVICE), signal())

    def test_it_matches_what_came_from_an_address_even_where_that_says_nothing(self) -> None:
        # A link-local address is no one's subject, but it is where the signal came from.
        assert verdicts.matches(
            rule(address="169.254.1.1"), signal(src="169.254.1.1", dst="93.184.216.34")
        )

    def test_a_signal_about_a_rule_has_no_address_to_match(self) -> None:
        assert not verdicts.matches(rule(address=ATTACKER), signal(src=None, dst=None))

    def test_a_rule_on_a_program_matches_what_it_saw(self) -> None:
        assert verdicts.matches(rule(source="wazuh"), signal())
        assert not verdicts.matches(rule(source="opnsense"), signal())

    def test_a_rule_on_a_signature_matches_it_exactly(self) -> None:
        assert verdicts.matches(rule(signature="ET SCAN Potential SSH Scan"), signal())
        assert not verdicts.matches(rule(signature="ET SCAN"), signal())
        assert not verdicts.matches(rule(signature="ET SCAN"), signal(signature=None))

    def test_a_rule_on_more_than_one_thing_needs_all_of_them(self) -> None:
        both = rule(address=ATTACKER, signature="ET SCAN Potential SSH Scan")

        assert verdicts.matches(both, signal())
        assert not verdicts.matches(both, signal(signature="something else"))
        assert not verdicts.matches(both, signal(src="8.8.8.8", dst=DEVICE))


CLOUD = "52.1.2.0/24"
CLOUD_HOST = "52.1.2.9"


class TestWhereADeviceSends:
    def test_it_matches_what_the_device_sends_to_that_network(self) -> None:
        camera = rule(address=DEVICE, destination=CLOUD)
        assert verdicts.matches(camera, signal(src=DEVICE, dst=CLOUD_HOST))

    def test_but_not_what_it_sends_anywhere_else(self) -> None:
        camera = rule(address=DEVICE, destination=CLOUD)
        assert not verdicts.matches(camera, signal(src=DEVICE, dst=ATTACKER))

    def test_nor_what_is_sent_back_to_it_from_there(self) -> None:
        # An attack that comes from the service still counts, whatever the device is excused.
        camera = rule(address=DEVICE, destination=CLOUD)
        assert not verdicts.matches(camera, signal(src=CLOUD_HOST, dst=DEVICE))

    def test_nor_what_another_device_sends_there(self) -> None:
        camera = rule(address=DEVICE, destination=CLOUD)
        assert not verdicts.matches(camera, signal(src="192.168.1.30", dst=CLOUD_HOST))

    def test_nor_a_signal_that_names_no_destination(self) -> None:
        camera = rule(address=DEVICE, destination=CLOUD)
        assert not verdicts.matches(camera, signal(src=DEVICE, dst=None))

    def test_a_single_address_is_a_network_of_one(self) -> None:
        host = rule(address=DEVICE, destination=CLOUD_HOST)
        assert verdicts.matches(host, signal(src=DEVICE, dst=CLOUD_HOST))
        assert not verdicts.matches(host, signal(src=DEVICE, dst="52.1.2.8"))

    def test_the_signature_and_the_program_narrow_it_as_well(self) -> None:
        # The signal's defaults are a Wazuh alert with the SSH scan signature.
        camera = rule(address=DEVICE, destination=CLOUD, source="wazuh")
        assert verdicts.matches(camera, signal(src=DEVICE, dst=CLOUD_HOST))
        assert not verdicts.matches(
            rule(address=DEVICE, destination=CLOUD, source="ntopng"),
            signal(src=DEVICE, dst=CLOUD_HOST),
        )
        assert not verdicts.matches(
            rule(address=DEVICE, destination=CLOUD, signature="ET POLICY Something"),
            signal(src=DEVICE, dst=CLOUD_HOST),
        )

    def test_it_is_more_specific_than_a_rule_for_the_device_alone(self) -> None:
        device = rule("threat", address=DEVICE)
        camera = rule(address=DEVICE, destination=CLOUD)
        assert verdicts.judge(signal(src=DEVICE, dst=CLOUD_HOST), [device, camera]) is camera
        # Everything else the device does still has the rule for the device.
        assert verdicts.judge(signal(src=DEVICE, dst=ATTACKER), [device, camera]) is device

    def test_a_rule_that_names_a_device_is_never_the_standing_of_an_alert(self) -> None:
        camera = rule(address=DEVICE, destination=CLOUD)
        assert verdicts.standing([camera], "wazuh", "ET SCAN Potential SSH Scan") is None


class TestWhichRuleDecides:
    def test_it_is_none_when_nothing_has_been_said(self) -> None:
        assert verdicts.judge(signal(), []) is None
        assert verdicts.judge(signal(), [rule(address="8.8.8.8")]) is None

    def test_the_rule_that_names_more_is_the_more_specific_and_wins(self) -> None:
        broad = rule("not_suspicious", address=ATTACKER)
        narrow = rule("threat", address=ATTACKER, signature="ET SCAN Potential SSH Scan")
        narrow.id = 2

        assert verdicts.judge(signal(), [broad, narrow]) is narrow
        assert verdicts.judge(signal(), [narrow, broad]) is narrow

    def test_what_a_signal_is_about_is_worked_out_once_however_many_rules_there_are(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked: list[IncidentSignal] = []
        about = verdicts._about  # pyright: ignore[reportPrivateUsage]

        def counting(found: IncidentSignal) -> set[str]:
            asked.append(found)
            return about(found)

        monkeypatch.setattr(verdicts, "_about", counting)
        many = [rule(address=f"8.8.8.{n}") for n in range(1, 6)]
        many.append(rule(source="wazuh"))
        wanted = rule("threat", address=ATTACKER)
        wanted.id = 2

        assert verdicts.judge(signal(), [*many, wanted]) is wanted
        assert len(asked) == 1

    def test_it_is_not_worked_out_at_all_when_no_rule_names_an_address(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:

        def refusing(found: IncidentSignal) -> set[str]:
            pytest.fail(f"asked about {found}")

        monkeypatch.setattr(verdicts, "_about", refusing)

        assert verdicts.judge(signal(), [rule(source="wazuh")]) is not None

    def test_a_general_rule_gives_way_to_a_specific_one_that_says_the_opposite(self) -> None:
        everything_here = rule("threat", address=ATTACKER)
        this_alert = rule("not_suspicious", address=ATTACKER, source="wazuh")
        this_alert.id = 2

        assert verdicts.judge(signal(), [everything_here, this_alert]) is this_alert

    def test_of_the_same_weight_the_one_that_would_raise_an_alarm_wins(self) -> None:
        quiet = rule("not_suspicious", address=ATTACKER)
        low = rule("low_priority", source="wazuh")
        low.id = 2
        loud = rule("threat", signature="ET SCAN Potential SSH Scan")
        loud.id = 3

        assert verdicts.judge(signal(), [quiet, low]) is low
        assert verdicts.judge(signal(), [low, quiet]) is low
        assert verdicts.judge(signal(), [quiet, low, loud]) is loud


class TestWhatTheOwnerThinksOfAnAlert:
    def test_it_is_none_when_nothing_has_been_said(self) -> None:
        assert verdicts.standing([], "ntopng", "Blacklisted flow") is None
        assert verdicts.standing([rule(source="wazuh")], "ntopng", "Blacklisted flow") is None

    def test_a_rule_for_the_signature_says_it_of_every_alert_like_it(self) -> None:
        by_signature = rule("low_priority", signature="Blacklisted flow")
        by_both = rule("not_suspicious", source="ntopng", signature="Blacklisted flow")
        by_both.id = 2
        by_source = rule("low_priority", source="ntopng")
        by_source.id = 3

        assert verdicts.standing([by_signature], "ntopng", "Blacklisted flow") is by_signature
        assert verdicts.standing([by_signature], "wazuh", "Blacklisted flow") is by_signature
        assert verdicts.standing([by_source], "ntopng", "Blacklisted flow") is by_source
        # The one that names more is the one that is meant.
        assert verdicts.standing([by_signature, by_both], "ntopng", "Blacklisted flow") is by_both

    def test_a_rule_for_one_address_does_not_say_it_of_all_of_them(self) -> None:
        here = rule("not_suspicious", address=ATTACKER, signature="Blacklisted flow")

        assert verdicts.standing([here], "ntopng", "Blacklisted flow") is None

    def test_an_alert_without_a_signature_is_only_what_a_rule_for_the_program_is_about(
        self,
    ) -> None:
        named = rule("low_priority", source="ntopng", signature="Blacklisted flow")
        everything = rule("low_priority", source="ntopng")
        everything.id = 2

        assert verdicts.standing([named], "ntopng", None) is None
        assert verdicts.standing([named, everything], "ntopng", None) is everything


class TestWhatTheVerdictsSayOfAnIncident:
    def test_muted_counts_the_signals_that_are_not_suspicious_or_low_priority(self) -> None:
        assert verdicts.muted({}) == 0
        assert verdicts.muted({"not_suspicious": 2, "low_priority": 1, "threat": 4}) == 3

    def test_a_threat_in_it_makes_it_one(self) -> None:
        assert verdicts.rollup({"threat": 1, "not_suspicious": 4}, 5) == "threat"

    def test_signals_that_are_all_muted_make_it_not_suspicious_or_low_priority(self) -> None:
        assert verdicts.rollup({"not_suspicious": 3}, 3) == "not_suspicious"
        assert verdicts.rollup({"not_suspicious": 2, "low_priority": 1}, 3) == "low_priority"

    def test_it_says_nothing_while_a_signal_has_no_verdict(self) -> None:
        assert verdicts.rollup({}, 3) is None
        assert verdicts.rollup({"not_suspicious": 2}, 3) is None
        assert verdicts.rollup({}, 0) is None


class TestHowOftenARuleWasUsed:
    def test_it_counts_the_signals_a_rule_was_applied_to_and_when_the_last_was(
        self, session: Session
    ) -> None:
        used = VerdictRule(verdict="not_suspicious", source="wazuh")
        unused = VerdictRule(verdict="threat", source="crowdsec")
        session.add_all([used, unused])
        session.flush()
        applied(session, used, NOW)
        applied(session, used, NOW + timedelta(hours=1))

        found = verdicts.hits(session, [used.id, unused.id])

        assert found == {used.id: (2, NOW + timedelta(hours=1))}

    def test_there_is_nothing_to_count_for_no_rules(self, session: Session) -> None:
        assert verdicts.hits(session, []) == {}


def applied(session: Session, used: VerdictRule, at: datetime) -> None:
    """Stores a signal of an incident that the rule was applied to."""
    incident = Incident(
        subject=ATTACKER,
        title="x",
        severity=2,
        confidence=0,
        first_seen_at=at,
        last_seen_at=at,
        top_source="wazuh",
        top_summary="x",
        signal_count=1,
        sources=[],
        addresses=[],
        banned=False,
        verdict_counts={},
    )
    session.add(incident)
    session.flush()
    session.add(
        IncidentSignal(
            incident_id=incident.id,
            event_id=int(at.timestamp()),
            occurred_at=at,
            source="wazuh",
            kind="alert",
            severity=2,
            summary="x",
            verdict=used.verdict,
            verdict_rule_id=used.id,
        )
    )
    session.flush()
