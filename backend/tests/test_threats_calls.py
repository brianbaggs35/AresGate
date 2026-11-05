"""What is thought of an incident beyond the rules, and whose word it is."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.models import AiTriage, Incident, IncidentFamily
from app.threats import calls

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
NO_FAMILY: tuple[str | None, int | None] = (None, None)


class TestWhoseWordItIs:
    def test_the_owner_calling_a_family_background_comes_before_anything(self) -> None:
        said = calls.resolve("background", ("attack", 99), ("attack", 99))

        assert said == calls.Call("noise", 100, "owner")

    def test_a_reading_of_the_incident_comes_before_its_family(self) -> None:
        said = calls.resolve(None, ("attack", 80), ("probe", 95))

        assert said == calls.Call("attack", 80, "reading")

    def test_the_family_is_what_there_is_when_nothing_read_the_incident(self) -> None:
        assert calls.resolve(None, None, ("probe", 95)) == calls.Call("probe", 95, "family")

    @pytest.mark.parametrize("family", [(None, None), ("probe", None), (None, 90)])
    def test_a_family_half_judged_says_nothing(self, family: tuple[str | None, int | None]) -> None:
        assert calls.resolve(None, None, family) == calls.NONE

    @pytest.mark.parametrize("kind", ["noise", "probe"])
    def test_watching_means_a_quiet_call_is_not_taken_on_trust(self, kind: str) -> None:
        assert calls.resolve("watch", (kind, 99), NO_FAMILY) == calls.Call(None, None, "owner")
        assert calls.resolve("watch", None, (kind, 99)) == calls.Call(None, None, "owner")

    @pytest.mark.parametrize("kind", ["attack", "compromise", "unclear"])
    def test_watching_does_not_hide_a_call_that_is_not_quiet(self, kind: str) -> None:
        assert calls.resolve("watch", (kind, 70), NO_FAMILY) == calls.Call(kind, 70, "reading")

    def test_watching_with_nothing_said_says_nothing(self) -> None:
        assert calls.resolve("watch", None, NO_FAMILY) == calls.NONE


class TestKeepingIt:
    def incident(self, session: Session, family: IncidentFamily | None, **more: Any) -> Incident:
        found = Incident(
            subject=f"8.8.8.{more.pop('n', 1)}",
            title="x",
            severity=2,
            confidence=50,
            first_seen_at=NOW,
            last_seen_at=NOW,
            top_source="wazuh",
            top_summary="x",
            family_id=family.id if family else None,
            **more,
        )
        session.add(found)
        session.flush()
        return found

    def family(self, session: Session, **changes: Any) -> IncidentFamily:
        found = IncidentFamily(key="k" * 40, source="wazuh", label="x", reach="internet", **changes)
        session.add(found)
        session.flush()
        return found

    def test_an_incident_is_told_what_its_family_was_judged(self, session: Session) -> None:
        family = self.family(session, ai_class="probe", ai_confidence=90)
        found = self.incident(session, family)

        assert calls.sync(session) == 1
        session.expire_all()

        assert (found.ai_class, found.ai_confidence, found.ai_basis) == ("probe", 90, "family")

    def test_a_reading_of_it_wins(self, session: Session) -> None:
        family = self.family(session, ai_class="probe", ai_confidence=90)
        found = self.incident(session, family)
        session.add(
            AiTriage(
                incident_id=found.id,
                read_at=NOW,
                signals_read=1,
                classification="attack",
                confidence=75,
                headline="h",
                story="s",
                checks=[],
                provider="anthropic",
                model="m",
            )
        )
        session.flush()

        calls.sync(session)
        session.expire_all()

        assert (found.ai_class, found.ai_confidence, found.ai_basis) == ("attack", 75, "reading")

    def test_what_has_not_changed_is_not_counted(self, session: Session) -> None:
        family = self.family(session, ai_class="probe", ai_confidence=90)
        self.incident(session, family)
        calls.sync(session)

        assert calls.sync(session) == 0

    def test_a_judgement_that_goes_is_taken_back(self, session: Session) -> None:
        family = self.family(session, ai_class="probe", ai_confidence=90)
        found = self.incident(session, family)
        calls.sync(session)
        family.ai_class = None
        family.ai_confidence = None

        assert calls.sync(session) == 1
        session.expire_all()

        assert (found.ai_class, found.ai_confidence, found.ai_basis) == (None, None, None)

    def test_it_can_be_for_some_incidents_or_one_family(self, session: Session) -> None:
        judged = self.family(session, ai_class="probe", ai_confidence=90)
        other = IncidentFamily(
            key="o" * 40,
            source="wazuh",
            label="y",
            reach="internet",
            ai_class="noise",
            ai_confidence=85,
        )
        session.add(other)
        session.flush()
        one = self.incident(session, judged, n=1)
        two = self.incident(session, judged, n=2)
        three = self.incident(session, other, n=3)

        assert calls.sync(session, [one.id]) == 1
        session.expire_all()
        assert (one.ai_class, two.ai_class) == ("probe", None)
        assert calls.sync(session, family_id=other.id) == 1
        session.expire_all()
        assert (three.ai_class, two.ai_class) == ("noise", None)
        assert calls.sync(session, [two.id], judged.id) == 1

    def test_a_big_change_is_made_in_pieces(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(calls, "CHUNK", 2)
        family = self.family(session, ai_class="probe", ai_confidence=90)
        found = [self.incident(session, family, n=number) for number in range(1, 6)]

        assert calls.sync(session) == 5
        session.expire_all()

        assert {each.ai_class for each in found} == {"probe"}

    def test_the_owner_calling_a_family_background_sets_all_of_it_aside(
        self, session: Session
    ) -> None:
        family = self.family(session, owner_call="background")
        found = self.incident(session, family)

        calls.sync(session)
        session.expire_all()

        assert (found.ai_class, found.ai_confidence, found.ai_basis) == ("noise", 100, "owner")
