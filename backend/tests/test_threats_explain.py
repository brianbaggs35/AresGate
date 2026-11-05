"""Why an incident is in the lane it is in."""

from typing import Any

import pytest

from app.incidents import attention
from app.incidents.attention import Lane
from app.threats import explain
from app.threats.settings import Tuning
from tests.test_threats_lanes import incident


def said(floor: int = 35, tuning: Tuning | None = None, **changes: Any) -> list[str]:
    return explain.why(incident(**changes), floor, tuning or Tuning())


class TestWhyItIsWhereItIs:
    def test_one_that_is_over_says_so(self) -> None:
        assert said(status="resolved") == ["It is resolved: someone has dealt with it."]

    def test_one_the_owner_called_quiet_says_so(self) -> None:
        [line] = said(verdict="low_priority")

        assert "You called it not suspicious or low priority" in line

    def test_one_the_rules_are_unsure_of_says_how_unsure(self) -> None:
        [line] = said(confidence=20)

        assert "20% sure" in line and "below the 35%" in line

    def test_one_the_ai_set_aside_says_who_and_how_sure(self) -> None:
        first, second = said(confidence=80, ai_class="probe", ai_confidence=91, ai_basis="family")

        assert first == "The AI judged this kind of incident: it is a probe, 91% sure."
        assert "at least the 80%" in second

    def test_what_the_owner_said_is_said_to_be_theirs(self) -> None:
        [line, _] = said(confidence=80, ai_class="noise", ai_confidence=100, ai_basis="owner")

        assert line.startswith("You said so: it is noise")

    def test_a_reading_of_the_incident_is_said_to_be_the_ais_reading(self) -> None:
        [line, _] = said(confidence=80, ai_class="probe", ai_confidence=85, ai_basis="reading")

        assert line.startswith("The AI read this incident")

    def test_a_threat_the_owner_named_says_so(self) -> None:
        assert said(confidence=50, verdict="threat") == ["You said it is a real threat."]

    def test_a_chain_says_what_stages_it_went_through(self) -> None:
        [line] = said(confidence=50, stages=["recon", "access"])

        assert "more than scanning" in line and "recon then access" in line

    def test_a_foothold_says_the_attack_worked(self) -> None:
        [line] = said(confidence=50, stages=["foothold"])

        assert "an attack worked" in line

    def test_an_ai_that_is_sure_it_is_an_attack_is_a_reason(self) -> None:
        lines = said(confidence=50, ai_class="attack", ai_confidence=80, ai_basis="reading")

        assert lines == ["The AI read this incident: it is an attack, 80% sure."]

    def test_sure_rules_are_a_reason_when_no_ai_has_to_agree(self) -> None:
        assert said(confidence=80) == ["AresGate's rules are 80% sure it is a real attack."]

    def test_a_critical_one_does_not_wait_for_the_ai(self) -> None:
        [line] = said(confidence=80, severity=4, tuning=Tuning(confirming=True))

        assert "it is critical" in line and "does not wait" in line

    def test_a_suspect_says_how_sure_the_rules_are(self) -> None:
        assert said(confidence=50) == ["AresGate's rules are 50% sure it is a real attack."]

    def test_a_suspect_waiting_for_the_ai_says_so(self) -> None:
        lines = said(confidence=80, tuning=Tuning(confirming=True))

        assert lines[1] == "It becomes a threat when the AI agrees, and it hasn't judged this yet."

    def test_a_suspect_the_ai_could_not_decide_on_says_what_it_made_of_it(self) -> None:
        lines = said(
            confidence=80,
            tuning=Tuning(confirming=True),
            ai_class="unclear",
            ai_confidence=40,
            ai_basis="reading",
        )

        assert lines[1] == "The AI read this incident: it is unclear, 40% sure."
        assert lines[2] == "That isn't enough to call it a threat, or to set it aside."

    def test_a_suspect_the_ai_judged_unclear_without_waiting_says_it_anyway(self) -> None:
        lines = said(confidence=50, ai_class="unclear", ai_confidence=40, ai_basis="family")

        assert lines[1] == "The AI judged this kind of incident: it is unclear, 40% sure."

    def test_a_kind_the_owner_asked_to_watch_is_said_to_be_kept(self) -> None:
        lines = said(confidence=50, ai_basis="owner")

        assert lines[-1] == "You asked to keep an eye on this kind, so it is never set aside."


class TestItAgreesWithTheLane:
    @pytest.mark.parametrize("tuning", [Tuning(), Tuning(confirming=True)])
    def test_every_incident_that_is_in_a_lane_has_a_reason(self, tuning: Tuning) -> None:
        for confidence in (10, 50, 80):
            for stages in ([], ["recon"], ["foothold"]):
                for kind in (None, "probe", "attack", "unclear"):
                    for severity in (2, 4):
                        found = incident(
                            confidence=confidence,
                            stages=stages,
                            severity=severity,
                            ai_class=kind,
                            ai_confidence=90 if kind else None,
                            ai_basis="reading" if kind else None,
                        )
                        lines = explain.why(found, 35, tuning)

                        assert lines, (confidence, stages, kind, severity)
                        assert all(isinstance(line, str) and line for line in lines)

    def test_the_lane_is_named_the_way_the_api_says_it(self) -> None:
        assert explain.lane_name(None) == "none"
        assert explain.lane_name(Lane.THREAT) == "threat"
        assert attention.lane_of(incident(confidence=90)) is Lane.THREAT
