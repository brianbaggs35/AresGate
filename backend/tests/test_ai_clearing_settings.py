"""What the owner lets the AI clear: the settings, the rules they make, the cap and the preview."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import clearing, clearing_settings, limits
from app.ai.clearing_settings import Policy
from app.config import Settings
from app.events.event import Severity
from app.models import Incident, VerdictRule
from app.threats.settings import Tuning
from tests.test_ai_clearing import ON, read, scan
from tests.test_ai_usage import call
from tests.test_incidents_engine import NOW


class TestTheSettings:
    def test_until_the_owner_saves_the_ai_suggests_and_clears_nothing_by_itself(
        self, session: Session
    ) -> None:
        policy = clearing_settings.load(session)

        assert policy == Policy()
        assert (policy.mode, policy.minimum, policy.ceiling, policy.daily_cap) == (
            "suggest",
            80,
            "medium",
            25,
        )
        assert policy.kinds == ("noise", "probe", "unclear")
        assert policy.sources == ()

    def test_what_is_saved_is_what_is_loaded(self, session: Session) -> None:
        asked = Policy("automatic", 90, ("noise",), ("ntopng",), "high", 5)

        assert clearing_settings.save(session, asked, NOW) is True
        session.commit()

        assert clearing_settings.load(session) == asked

    def test_saving_it_again_changes_nothing(self, session: Session) -> None:
        asked = replace(Policy(), mode="off")
        clearing_settings.save(session, asked, NOW)

        assert clearing_settings.save(session, asked, NOW) is False
        assert clearing_settings.save(session, replace(asked, daily_cap=3), NOW) is True
        assert clearing_settings.load(session).daily_cap == 3

    @pytest.mark.parametrize(
        ("minimum", "name"),
        [(90, "careful"), (80, "balanced"), (65, "thorough"), (72, "custom")],
    )
    def test_how_sure_it_must_be_is_careful_balanced_thorough_or_the_owners_own(
        self, minimum: int, name: str
    ) -> None:
        assert replace(Policy(), minimum=minimum).aggressiveness == name


class TestWhatItMayClear:
    def blocked(self, session: Session, settings: Settings, policy: Policy, **changes: object):
        found = scan(session, settings)
        return clearing_settings.blocked(found, read(found, **changes), policy, Tuning())

    def test_a_reading_that_fits_is_not_blocked(self, session: Session, settings: Settings) -> None:
        assert self.blocked(session, settings, ON) is None

    def test_a_reading_that_is_not_a_false_positive_is_blocked(
        self, session: Session, settings: Settings
    ) -> None:
        assert "did not say" in str(self.blocked(session, settings, ON, verdict=None))

    def test_only_the_kinds_the_owner_allows(self, session: Session, settings: Settings) -> None:
        only_noise = replace(ON, kinds=("noise",))

        assert self.blocked(session, settings, only_noise) is None
        why = self.blocked(session, settings, only_noise, classification="probe")
        assert why == "The AI called it probe, which it may not clear."

    def test_never_an_attack_or_a_compromise_whatever_the_owner_allows(
        self, session: Session, settings: Settings
    ) -> None:
        for kind in ("attack", "compromise"):
            assert self.blocked(session, settings, ON, classification=kind) is not None

    @pytest.mark.parametrize(("confidence", "blocked"), [(79, True), (80, False), (95, False)])
    def test_only_as_sure_as_the_owner_asks(
        self, session: Session, settings: Settings, confidence: int, blocked: bool
    ) -> None:
        why = self.blocked(session, settings, ON, confidence=confidence)

        assert (why is not None) is blocked
        if blocked:
            assert why == "The AI was only 79% sure, and 80% is asked."

    def test_only_the_programs_the_owner_names(self, session: Session, settings: Settings) -> None:
        found = scan(session, settings)
        reading = read(found)

        everything = clearing_settings.blocked(found, reading, ON, Tuning())
        named = clearing_settings.blocked(
            found, reading, replace(ON, sources=("wazuh", "ntopng")), Tuning()
        )
        another = clearing_settings.blocked(
            found, reading, replace(ON, sources=("ntopng",)), Tuning()
        )

        assert (everything, named) == (None, None)
        assert another == "It involves wazuh, which the AI may not clear."

    @pytest.mark.parametrize(
        ("severity", "ceiling", "blocked"),
        [
            (Severity.MEDIUM, "medium", False),
            (Severity.HIGH, "medium", True),
            (Severity.HIGH, "high", False),
            (Severity.CRITICAL, "high", True),
            (Severity.MEDIUM, "low", True),
        ],
    )
    def test_nothing_more_serious_than_the_ceiling_and_never_a_critical_one(
        self,
        session: Session,
        settings: Settings,
        severity: Severity,
        ceiling: str,
        blocked: bool,
    ) -> None:
        found = scan(session, settings, severity=severity)

        why = clearing_settings.blocked(found, read(found), replace(ON, ceiling=ceiling), Tuning())

        assert (why is not None) is blocked

    def test_nothing_that_is_more_than_scanning(self, session: Session, settings: Settings) -> None:
        found = scan(session, settings, stages=["recon", "exploit"])

        why = clearing_settings.blocked(found, read(found), ON, Tuning())

        assert why is not None
        assert "more than scanning" in why


class TestHowManyAndHowLong:
    def clear_one(self, session: Session, settings: Settings, policy: Policy) -> VerdictRule | None:
        found = scan(session, settings)
        return clearing.clear(session, found, read(found), Tuning(), NOW, policy)

    def test_it_counts_what_it_cleared_in_the_last_day(
        self, session: Session, settings: Settings
    ) -> None:
        assert clearing_settings.cleared_lately(session, NOW) == 0

        assert self.clear_one(session, settings, ON) is not None

        assert clearing_settings.cleared_lately(session, NOW) == 1
        assert clearing_settings.cleared_lately(session, NOW + timedelta(hours=25)) == 0

    def test_it_stops_at_the_cap_and_says_so(self, session: Session, settings: Settings) -> None:
        capped = replace(ON, daily_cap=1)
        assert self.clear_one(session, settings, capped) is not None
        assert clearing_settings.held(session, capped, NOW) is not None

        assert "1 incidents in the last 24 hours" in str(
            clearing_settings.held(session, capped, NOW)
        )
        assert self.clear_one(session, settings, capped) is None
        # The first stays, and the second was left for the owner.
        assert len(session.scalars(select(VerdictRule)).all()) == 1

    def test_a_cap_of_none_clears_nothing_by_itself(
        self, session: Session, settings: Settings
    ) -> None:
        assert self.clear_one(session, settings, replace(ON, daily_cap=0)) is None

    def test_it_stops_when_the_ai_spending_limit_is_used_up_and_says_so(
        self, session: Session, settings: Settings
    ) -> None:
        limits.set_limits(session, Decimal("0.01"), None, NOW)
        call(session, NOW - timedelta(hours=1), cost=20_000)
        session.flush()

        held = clearing_settings.held(session, ON, NOW)

        assert held is not None
        assert held.startswith("The AI has stopped clearing. The daily AI spending limit")
        assert self.clear_one(session, settings, ON) is None

    @pytest.mark.parametrize("mode", ["off", "suggest"])
    def test_nothing_holds_it_when_it_does_not_clear_by_itself(
        self, session: Session, mode: str
    ) -> None:
        assert clearing_settings.held(session, replace(ON, mode=mode, daily_cap=0), NOW) is None


class TestThePreview:
    def read_lately(self, session: Session, settings: Settings) -> Incident:
        found = scan(session, settings)
        session.add(read(found))
        session.flush()
        return found

    def test_it_counts_what_the_settings_would_have_cleared_of_what_the_ai_read(
        self, session: Session, settings: Settings
    ) -> None:
        self.read_lately(session, settings)

        found = clearing.preview(session, ON, Tuning(), NOW)

        assert (found.read, found.would_clear) == (1, 1)
        assert clearing.preview(
            session, replace(ON, minimum=95), Tuning(), NOW
        ) == clearing.Preview(1, 0)

    def test_it_leaves_out_what_the_owner_has_already_decided(
        self, session: Session, settings: Settings
    ) -> None:
        self.read_lately(session, settings).verdict = "threat"
        session.flush()

        found = clearing.preview(session, ON, Tuning(), NOW)

        assert (found.read, found.would_clear) == (1, 0)

    def test_it_counts_what_the_ai_has_cleared_already(
        self, session: Session, settings: Settings
    ) -> None:
        found = self.read_lately(session, settings)
        clearing.clear(session, found, read(found), Tuning(), NOW, ON)
        session.flush()

        assert clearing.preview(session, ON, Tuning(), NOW).would_clear == 1

    def test_it_looks_back_a_week_and_no_further(
        self, session: Session, settings: Settings
    ) -> None:
        self.read_lately(session, settings)

        assert clearing.preview(session, ON, Tuning(), NOW + timedelta(days=8)).read == 0
