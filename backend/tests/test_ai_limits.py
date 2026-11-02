from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.ai import catalog, gateway, limits, service
from app.ai.gateway import Prepared, Unavailable
from app.config import Settings
from app.models import AiProvider
from tests.test_ai_gateway import Log, context, question, turned_on
from tests.test_ai_service import saved
from tests.test_ai_usage import NOW, call


class TestALimit:
    @pytest.mark.parametrize(
        ("limit", "spent", "state"),
        [
            (None, 5_000_000, "none"),
            (1_000_000, 0, "ok"),
            (1_000_000, 799_999, "ok"),
            (1_000_000, 800_000, "warning"),
            (1_000_000, 999_999, "warning"),
            (1_000_000, 1_000_000, "reached"),
            (1_000_000, 3_000_000, "reached"),
        ],
    )
    def test_its_state_follows_how_much_is_gone(
        self, limit: int | None, spent: int, state: str
    ) -> None:
        assert limits.Limit("day", limit, spent).state == state


class TestMoney:
    @pytest.mark.parametrize(
        ("micros", "written"),
        [
            (0, "$0.00"),
            (1_500_000, "$1.50"),
            (1_234_567_000, "$1,234.57"),
            (2_500, "$0.0025"),
            (10_000, "$0.01"),
            (9_999, "$0.0100"),
        ],
    )
    def test_an_amount_is_written_with_the_places_it_needs(self, micros: int, written: str) -> None:
        assert limits.dollars(micros) == written

    def test_dollars_become_millionths_and_nothing_stays_none(self) -> None:
        assert limits.to_micros(Decimal("1.25")) == 1_250_000
        assert limits.to_micros(None) is None


class TestTheMonthsEdges:
    def test_a_month_starts_on_the_first_and_ends_on_the_next(self) -> None:
        assert limits.month_start(NOW) == datetime(2026, 11, 1, tzinfo=UTC)
        assert limits.next_month(NOW) == datetime(2026, 12, 1, tzinfo=UTC)

    def test_december_is_followed_by_january(self) -> None:
        december = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)

        assert limits.next_month(december) == datetime(2027, 1, 1, tzinfo=UTC)


class TestWhatIsSpent:
    def test_only_calls_since_then_with_a_price_count(self, session: Session) -> None:
        call(session, NOW - timedelta(hours=30), cost=1_000_000)
        call(session, NOW - timedelta(hours=2), cost=250_000)
        call(session, NOW - timedelta(hours=1), cost=None)

        assert limits.spent(session, NOW - timedelta(hours=24)) == 250_000
        assert limits.spent(session, NOW - timedelta(days=30)) == 1_250_000
        assert limits.spent(session, NOW) == 0

    def test_the_limits_are_set_and_their_state_follows(self, session: Session) -> None:
        call(session, NOW - timedelta(hours=2), cost=900_000)

        day, month = limits.set_limits(session, Decimal("1"), None, NOW)

        assert (day.limit_micros, day.spent_micros, day.state) == (1_000_000, 900_000, "warning")
        assert (month.limit_micros, month.state) == (None, "none")
        assert service.usage(session, NOW).daily_limit_micros == 1_000_000

    def test_a_limit_can_be_taken_away(self, session: Session) -> None:
        limits.set_limits(session, Decimal("1"), Decimal("5"), NOW)

        limits.set_limits(session, None, None, NOW)

        assert limits.status(session, NOW)[0].limit_micros is None
        assert limits.status(session, NOW)[1].limit_micros is None


class TestWhatStopsRequests:
    def test_nothing_stops_them_while_no_limit_is_used_up(self, session: Session) -> None:
        call(session, NOW - timedelta(hours=1), cost=900_000)
        limits.set_limits(session, Decimal("1"), Decimal("5"), NOW)

        assert limits.reached(session, NOW) is None

    def test_the_day_says_so_and_when_it_ends(self, session: Session) -> None:
        call(session, NOW - timedelta(hours=1), cost=1_000_000)
        limits.set_limits(session, Decimal("1"), None, NOW)

        said = limits.reached(session, NOW)

        assert said == (
            "The daily AI spending limit ($1.00) is used up. Requests start again when spending "
            "in the last 24 hours falls below it. Raise it on the AI usage page."
        )

    def test_the_month_says_so_and_when_it_ends(self, session: Session) -> None:
        call(session, datetime(2026, 11, 3, tzinfo=UTC), cost=5_000_000)
        limits.set_limits(session, None, Decimal("5"), NOW)

        said = limits.reached(session, NOW)

        assert said == (
            "The monthly AI spending limit ($5.00) is used up. Requests start again next month. "
            "Raise it on the AI usage page."
        )


class TestTheGateway:
    def ready(self, session: Session, settings: Settings, provider: catalog.ProviderDef) -> None:
        saved(session, settings, provider)
        turned_on(session, provider.key)

    def test_a_provider_that_charges_is_not_asked_once_a_limit_is_used_up(
        self, session: Session, settings: Settings
    ) -> None:
        self.ready(session, settings, catalog.ANTHROPIC)
        call(session, NOW - timedelta(hours=1), cost=2_000_000)
        limits.set_limits(session, Decimal("2"), None, NOW)

        said = gateway.prepare(session, context(settings, Log()), question(), NOW)

        assert isinstance(said, Unavailable)
        assert "daily AI spending limit ($2.00)" in said.reason

    def test_the_same_provider_is_asked_while_it_is_below_the_limit(
        self, session: Session, settings: Settings
    ) -> None:
        self.ready(session, settings, catalog.ANTHROPIC)
        call(session, NOW - timedelta(hours=1), cost=1_000_000)
        limits.set_limits(session, Decimal("2"), None, NOW)

        said = gateway.prepare(session, context(settings, Log()), question(), NOW)

        assert isinstance(said, Prepared)

    def test_a_provider_on_the_owners_own_computer_is_never_stopped(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.OLLAMA)
        row = session.get(AiProvider, "ollama")
        assert row is not None
        row.model = "llama3"
        turned_on(session, "ollama", "local")
        call(session, NOW - timedelta(hours=1), cost=9_000_000)
        limits.set_limits(session, Decimal("1"), Decimal("1"), NOW)

        said = gateway.prepare(session, context(settings, Log(), key="ollama"), question(), NOW)

        assert isinstance(said, Prepared)
