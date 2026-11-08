"""What a message says of an incident at each level of detail, and of a summary."""

from datetime import UTC, datetime
from typing import Any, cast

from app.alerts import message
from app.alerts.discord import AMBER, BLUE, GREY, RED
from app.models import Incident

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
ORIGIN = "https://aresgate.example"


def incident(**changes: Any) -> Incident:
    fields: dict[str, Any] = {
        "id": 7,
        "subject": "93.184.216.5",
        "title": "ET SCAN Potential SSH Scan (93.184.216.5)",
        "severity": 3,
        "confidence": 80,
        "status": "open",
        "first_seen_at": NOW,
        "last_seen_at": NOW,
        "signal_count": 12,
        "sources": ["opnsense", "wazuh"],
        "activities": ["scan"],
        "top_source": "wazuh",
        "top_summary": "ET SCAN Potential SSH Scan from 93.184.216.5 to 192.168.1.20",
        "verdict": None,
    }
    fields.update(changes)
    return Incident(**fields)


def embed(payload: dict[str, object]) -> dict[str, Any]:
    return cast("dict[str, Any]", cast("list[object]", payload["embeds"])[0])


def say(found: Incident, **changes: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "reason": "new",
        "detail": "standard",
        "origin": ORIGIN,
        "at": NOW,
    }
    arguments.update(changes)
    return embed(message.incident_message(found, **arguments))


class TestAnIncident:
    def test_brief_says_what_and_how_sure_with_a_link_and_no_address(self) -> None:
        shown = say(incident(), detail="brief")

        text = f"{shown['title']} {shown['description']}"
        assert shown["title"] == "High-severity scanning"
        assert "80% sure" in shown["description"]
        assert shown["url"] == f"{ORIGIN}/incidents/7"
        assert f"({ORIGIN}/incidents/7)" in shown["description"]
        assert "93.184.216.5" not in text
        assert "192.168.1.20" not in text
        assert "OPNsense" not in text
        assert shown["color"] == RED

    def test_standard_adds_the_address_on_the_internet_and_the_programs(self) -> None:
        shown = say(incident())

        assert shown["title"] == "High-severity scanning from 93.184.216.5"
        assert "Reported by OPNsense and Wazuh, 12 signals so far." in shown["description"]
        assert "192.168.1.20" not in shown["description"]

    def test_standard_leaves_out_a_subject_that_is_on_the_network_or_is_a_rule(self) -> None:
        for subject in ("192.168.1.20", "rule:5710", "fe80::1"):
            shown = say(incident(subject=subject))
            assert subject not in f"{shown['title']} {shown['description']}", subject

    def test_full_adds_what_the_strongest_alert_said_and_the_devices_by_name(self) -> None:
        shown = say(incident(), detail="full", devices=[("192.168.1.20", "laptop")])

        assert "The strongest alert said: `ET SCAN Potential SSH Scan from" in shown["description"]
        assert "On your network: `laptop (192.168.1.20)`." in shown["description"]

    def test_full_without_devices_names_none(self) -> None:
        assert "On your network" not in say(incident(), detail="full")["description"]

    def test_what_the_network_says_cannot_format_or_link_or_end_its_code_span(self) -> None:
        sneaky = "[click](https://evil.example) `**@everyone**`\n# heading"

        shown = say(incident(top_summary=sneaky), detail="full", devices=[("192.168.1.20", sneaky)])

        said = shown["description"]
        assert "`[click](https://evil.example) '**@everyone**' # heading`" in said
        assert said.count("`") == 4

    def test_a_long_alert_is_cut_short(self) -> None:
        shown = say(incident(top_summary="x" * 500), detail="full")

        assert "x" * 199 + "…`" in shown["description"]

    def test_a_worse_or_reopened_incident_says_so(self) -> None:
        worse = say(incident(), reason="worse")
        reopened = say(incident(), reason="reopened")

        assert worse["title"].startswith("Got worse: ")
        assert "got worse since the last message" in worse["description"]
        assert reopened["title"].startswith("Reopened: ")
        assert "open again" in reopened["description"]

    def test_a_threat_the_owner_called_says_so(self) -> None:
        shown = say(incident(verdict="threat"))

        assert shown["description"].startswith("You said it is a real threat. AresGate is 80%")

    def test_the_colour_follows_the_severity(self) -> None:
        assert say(incident(severity=1))["color"] == BLUE
        assert say(incident(severity=2))["color"] == AMBER
        assert say(incident(severity=4))["color"] == RED
        assert say(incident(severity=0))["color"] == BLUE

    def test_an_incident_without_a_kind_of_activity_is_suspicious_activity(self) -> None:
        shown = say(incident(activities=[], severity=0), detail="brief")

        assert shown["title"] == "Unusual-severity suspicious activity"

    def test_both_kinds_of_activity_are_named(self) -> None:
        shown = say(incident(activities=["scan", "brute_force"]), detail="brief")

        assert shown["title"] == "High-severity scanning and brute force"

    def test_the_programs_are_listed_in_words(self) -> None:
        assert (
            "Reported by OPNsense, 12 signals" in say(incident(sources=["opnsense"]))["description"]
        )
        three = say(incident(sources=["crowdsec", "opnsense", "wazuh"]))["description"]
        assert "Reported by CrowdSec, OPNsense and Wazuh," in three
        assert "Reported by a program," in say(incident(sources=[]))["description"]
        assert "Reported by mystery," in say(incident(sources=["mystery"]))["description"]

    def test_nobody_can_be_pinged(self) -> None:
        sent = message.incident_message(
            incident(), reason="new", detail="full", origin=ORIGIN, at=NOW
        )

        assert sent["allowed_mentions"] == {"parse": []}


class TestASummary:
    def test_it_says_how_many_were_held_back_and_names_a_few(self) -> None:
        many = [incident(id=number, subject=f"93.184.216.{number}") for number in range(1, 5)]

        shown = embed(
            message.summary_message(
                reason="limit",
                covers=9,
                named=many,
                detail="standard",
                origin=ORIGIN,
                max_per_hour=3,
                at=NOW,
            )
        )

        assert shown["title"] == "9 incidents held back"
        assert "allows 3 messages an hour" in shown["description"]
        assert (
            f"• High-severity scanning from 93.184.216.1: [open]({ORIGIN}/incidents/1)"
            in (shown["description"])
        )
        assert "…and 5 more." in shown["description"]
        assert f"[Open the incidents]({ORIGIN}/incidents)" in shown["description"]
        assert shown["url"] == f"{ORIGIN}/incidents"

    def test_it_names_no_more_than_five(self) -> None:
        many = [incident(id=number) for number in range(1, 9)]

        shown = embed(
            message.summary_message(
                reason="limit",
                covers=8,
                named=many,
                detail="brief",
                origin=ORIGIN,
                max_per_hour=3,
                at=NOW,
            )
        )

        assert shown["description"].count("• ") == message.SUMMARY_NAMES
        assert "…and 3 more." in shown["description"]
        assert "93.184.216.5" not in shown["description"]

    def test_a_quiet_hours_summary_says_why(self) -> None:
        shown = embed(
            message.summary_message(
                reason="quiet",
                covers=1,
                named=[incident()],
                detail="brief",
                origin=ORIGIN,
                max_per_hour=3,
                at=NOW,
            )
        )

        assert shown["title"] == "1 incident came in during quiet hours"
        assert "while quiet hours were on" in shown["description"]
        assert "…and" not in shown["description"]


def threat_of(found: Incident, **changes: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "reason": "new",
        "detail": "standard",
        "origin": ORIGIN,
        "why": ["It is more than scanning: it went through 2 stages (recon then access)."],
        "at": NOW,
    }
    arguments.update(changes)
    return embed(message.threat_message(found, **arguments))


def field_values(shown: dict[str, Any]) -> dict[str, str]:
    return {item["name"]: item["value"] for item in shown["fields"]}


class TestAThreat:
    def chain(self, **changes: Any) -> Incident:
        return incident(stages=["recon", "access"], **changes)

    def test_it_says_how_far_the_attack_got_and_why_it_is_believed(self) -> None:
        shown = threat_of(self.chain())

        assert shown["title"] == "Attack in progress: High-severity scanning from 93.184.216.5"
        assert shown["description"].startswith(
            "AresGate is 80% sure this is a real attack, and it is going on now."
        )
        assert "**Why AresGate thinks so**\n• It is more than scanning" in shown["description"]
        assert f"[Open the incident]({ORIGIN}/incidents/7)" in shown["description"]
        assert shown["url"] == f"{ORIGIN}/incidents/7"
        assert shown["footer"] == {"text": "AresGate · threat alert"}
        assert shown["color"] == RED
        assert field_values(shown) == {
            "How far it got": "Looking around → **Trying to get in**",
            "How sure": "80%",
            "How serious": "High",
            "Seen from": "`93.184.216.5`",
        }

    def test_the_title_goes_by_the_furthest_stage(self) -> None:
        reached = [
            [],
            ["recon"],
            ["recon", "access"],
            ["recon", "access", "foothold"],
        ]

        titles = [threat_of(incident(stages=stages))["title"].split(":")[0] for stages in reached]

        assert titles == ["Threat", "Threat", "Attack in progress", "Possible break-in"]

    def test_a_threat_with_no_stage_has_no_path(self) -> None:
        shown = threat_of(incident(stages=[]), why=[])

        assert "How far it got" not in field_values(shown)
        assert "Why AresGate thinks so" not in shown["description"]

    def test_brief_leaves_out_the_address(self) -> None:
        shown = threat_of(self.chain(), detail="brief")

        assert "93.184.216.5" not in str(shown)
        assert "Seen from" not in field_values(shown)

    def test_full_adds_the_alert_and_the_devices_by_name(self) -> None:
        shown = threat_of(self.chain(), detail="full", devices=[("192.168.1.20", "laptop")])

        values = field_values(shown)
        assert values["On your network"] == "`laptop (192.168.1.20)`"
        assert values["The strongest alert said"].startswith("`ET SCAN Potential SSH Scan from")

    def test_full_without_devices_names_none(self) -> None:
        assert "On your network" not in field_values(threat_of(self.chain(), detail="full"))

    def test_what_the_network_says_cannot_format_or_link(self) -> None:
        sneaky = "[click](https://evil.example) `**@everyone**`"

        shown = threat_of(self.chain(top_summary=sneaky), detail="full")

        assert (
            "`[click](https://evil.example) '**@everyone**'`"
            in field_values(shown)["The strongest alert said"]
        )
        assert "evil.example" not in f"{shown['title']} {shown['description']}"

    def test_a_subject_on_the_network_is_not_said(self) -> None:
        shown = threat_of(self.chain(subject="192.168.1.20"))

        assert "Seen from" not in field_values(shown)

    def test_an_escalation_and_a_reopening_say_so(self) -> None:
        worse = threat_of(self.chain(), reason="worse")
        again = threat_of(self.chain(), reason="reopened")

        assert worse["title"].startswith("Escalated: Attack in progress")
        assert "gone further since the last message" in worse["description"]
        assert again["title"].startswith("Reopened: Attack in progress")
        assert "stood down earlier, and it is a threat again" in again["description"]

    def test_the_owners_word_comes_first(self) -> None:
        shown = threat_of(self.chain(verdict="threat"))

        assert shown["description"].startswith("You said it is a real threat. AresGate is 80%")

    def test_nobody_can_be_pinged(self) -> None:
        sent = message.threat_message(
            self.chain(), reason="new", detail="full", origin=ORIGIN, why=[], at=NOW
        )

        assert sent["allowed_mentions"] == {"parse": []}


class TestStandingDown:
    def stood(self, found: Incident, **changes: Any) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "detail": "standard",
            "origin": ORIGIN,
            "why": ["You called it not suspicious or low priority, so it never raises an alarm."],
            "at": NOW,
        }
        arguments.update(changes)
        return embed(message.stood_down_message(found, **arguments))

    def test_it_says_it_is_no_longer_a_threat_and_why(self) -> None:
        shown = self.stood(incident())

        assert shown["title"] == "Stood down: High-severity scanning from 93.184.216.5"
        assert "This is no longer a threat" in shown["description"]
        assert "• You called it not suspicious or low priority" in shown["description"]
        assert "will not alert on it again unless that changes" in shown["description"]
        assert f"[Open the incident]({ORIGIN}/incidents/7)" in shown["description"]
        assert (shown["color"], shown["footer"]) == (GREY, {"text": "AresGate · stood down"})
        assert "fields" not in shown

    def test_it_holds_nothing_the_first_message_did_not(self) -> None:
        shown = self.stood(incident(), detail="brief", why=[])

        assert "93.184.216.5" not in str(shown)
        assert "•" not in shown["description"]


class TestASample:
    def test_it_is_made_up_and_marked_as_one(self) -> None:
        found = message.sample_incident(NOW)

        assert (found.id, found.subject) == (0, "93.184.216.34")
        assert found.stages == ["recon", "access"]

    def test_a_threat_sample_is_made_by_the_code_that_makes_real_ones(self) -> None:
        shown = embed(
            message.sample_message(
                mode="threats", reason="new", detail="standard", origin=ORIGIN, at=NOW
            )
        )

        assert shown["title"] == "Attack in progress: High-severity scanning from 93.184.216.34"
        assert shown["footer"] == {"text": "AresGate · sample alert"}
        assert "• It is more than scanning" in shown["description"]
        # It is made up, so it links to the list and not to an incident that is not there.
        assert shown["url"] == f"{ORIGIN}/incidents"

    def test_a_sample_of_the_floors_is_the_plain_message(self) -> None:
        shown = embed(
            message.sample_message(
                mode="custom", reason="worse", detail="brief", origin=ORIGIN, at=NOW
            )
        )

        assert shown["title"].startswith("Got worse: High-severity scanning")
        assert shown["footer"] == {"text": "AresGate · sample alert"}
        assert "93.184.216.34" not in str(shown)

    def test_the_full_sample_names_a_device(self) -> None:
        shown = embed(
            message.sample_message(
                mode="threats", reason="new", detail="full", origin=ORIGIN, at=NOW
            )
        )

        assert field_values(shown)["On your network"] == "`living-room-tv (192.168.1.24)`"
        full = embed(
            message.sample_message(
                mode="custom", reason="new", detail="full", origin=ORIGIN, at=NOW
            )
        )
        assert "living-room-tv" in full["description"]


def test_a_link_is_to_the_incident_or_the_list() -> None:
    assert message.link_to(ORIGIN, 3) == f"{ORIGIN}/incidents/3"
    assert message.link_to(ORIGIN) == f"{ORIGIN}/incidents"
