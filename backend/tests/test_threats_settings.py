"""What the owner has set for telling threats from noise."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.models import AiProvider, AiSettings, ThreatSettings
from app.threats import settings
from app.threats.settings import Tuning

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def ai(session: Session, **changes: Any) -> None:
    fields: dict[str, Any] = {"enabled": True, "provider": "anthropic", "usage_level": "medium"}
    fields.update(changes)
    row = session.get(AiSettings, 1)
    if fields.get("provider") is not None and session.get(AiProvider, fields["provider"]) is None:
        session.add(AiProvider(provider=fields["provider"], model="m"))
        session.flush()
    if row is None:
        session.add(AiSettings(id=1, **fields))
    else:
        for name, value in fields.items():
            setattr(row, name, value)
    session.commit()


class TestWhetherAnAiIsWatching:
    def test_with_nothing_set_up_it_is_not(self, session: Session) -> None:
        assert not settings.watching(session)

    def test_it_is_when_on_with_a_provider_and_reading_by_itself(self, session: Session) -> None:
        ai(session)

        assert settings.watching(session)

    @pytest.mark.parametrize(
        "changes", [{"enabled": False}, {"provider": None}, {"usage_level": "very_low"}]
    )
    def test_it_is_not_when_off_or_without_a_provider_or_reading_nothing(
        self, session: Session, changes: dict[str, Any]
    ) -> None:
        ai(session, **changes)

        assert not settings.watching(session)


class TestLoadingAndSaving:
    def test_until_saved_everything_is_the_default(self, session: Session) -> None:
        assert settings.load(session) == Tuning()

    def test_what_is_saved_is_loaded(self, session: Session) -> None:
        asked = Tuning(
            threat_from=80,
            ai_may_clear=False,
            clear_from=90,
            ai_confirms=False,
            exposure="some",
            exposed_ports=(22, 443),
            notes="A web server in the garage.",
        )

        assert settings.save(session, asked)
        session.commit()

        assert settings.load(session) == asked

    def test_saving_what_is_already_saved_changes_nothing(self, session: Session) -> None:
        assert not settings.save(session, Tuning())
        assert session.get(ThreatSettings, 1) is None

        assert settings.save(session, Tuning(threat_from=70))
        assert not settings.save(session, Tuning(threat_from=70))

    def test_saving_again_changes_the_one_row(self, session: Session) -> None:
        settings.save(session, Tuning(threat_from=70))
        settings.save(session, Tuning(threat_from=75, notes="x"))
        session.commit()

        row = session.get(ThreatSettings, 1)
        assert row is not None
        assert (row.threat_from, row.notes) == (75, "x")

    def test_the_ai_agreeing_is_needed_only_when_asked_for_and_the_ai_is_watching(
        self, session: Session
    ) -> None:
        assert not settings.load(session).confirming

        ai(session)
        assert settings.load(session).confirming

        settings.save(session, Tuning(ai_confirms=False))
        assert not settings.load(session).confirming

    def test_what_is_saved_does_not_include_whether_it_is_confirming(
        self, session: Session
    ) -> None:
        ai(session)

        assert not settings.save(session, Tuning(confirming=True))


class TestSayingItToTheAnalyst:
    def test_nothing_is_reachable(self) -> None:
        said = settings.describe(Tuning(exposure="none"))

        assert said == "Nothing on this network is meant to be reachable from the internet."

    def test_some_services_are_with_their_ports(self) -> None:
        said = settings.describe(Tuning(exposure="some", exposed_ports=(22, 443)))

        assert said == ("Some services are reachable from the internet, on these ports: 22, 443.")

    def test_some_without_ports_says_so(self) -> None:
        assert "unspecified ports" in settings.describe(Tuning(exposure="some"))

    def test_not_having_said_is_said(self) -> None:
        assert "hasn't said" in settings.describe(Tuning())
