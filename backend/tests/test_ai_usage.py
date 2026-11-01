from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.ai import usage
from app.models import AiCall

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
HALIFAX = ZoneInfo("America/Halifax")
UTC_ZONE = ZoneInfo("UTC")


def call(
    session: Session,
    when: datetime = NOW - timedelta(hours=1),
    *,
    purpose: str = "triage",
    about: str | None = None,
    provider: str = "anthropic",
    model: str = "claude-haiku-5-5",
    ok: bool = True,
    tokens: tuple[int, int] = (1000, 200),
    cached: int = 0,
    cost: int | None = 1500,
    error: str | None = None,
) -> AiCall:
    """A call that was made, as the record keeps it."""
    row = AiCall(
        occurred_at=when,
        purpose=purpose,
        about=about,
        provider=provider,
        model=model,
        level="balanced",
        ok=ok,
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        cached_tokens=cached,
        cost_micros=cost,
        duration_ms=1234,
        error=error,
        prompt="HOST_1 was scanned",
        answer=None if error else "HOST_1 is a scanner",
    )
    session.add(row)
    session.commit()
    return row


class TestTheSpan:
    def test_it_is_whole_days_ending_with_today(self) -> None:
        window = usage.span("7d", NOW, UTC_ZONE)

        assert window.dates[0] == date(2026, 11, 9)
        assert window.dates[-1] == date(2026, 11, 15)
        assert len(window.days) == 7
        assert window.start == datetime(2026, 11, 9, tzinfo=UTC)
        assert window.end == datetime(2026, 11, 16, tzinfo=UTC)
        assert window.previous_start == datetime(2026, 11, 2, tzinfo=UTC)

    def test_a_day_is_counted_in_the_zone_it_is_asked_for(self) -> None:
        # 01:00 UTC on the 16th is still the 15th in Halifax, where it is 21:00 (UTC-4).
        window = usage.span("30d", datetime(2026, 11, 16, 1, 0, tzinfo=UTC), HALIFAX)

        assert window.dates[-1] == date(2026, 11, 15)
        assert window.end == datetime(2026, 11, 16, 4, 0, tzinfo=UTC)
        assert len(window.days) == 30

    def test_there_are_three_ranges(self) -> None:
        assert [len(usage.span(key, NOW, UTC_ZONE).days) for key in usage.RANGES] == [7, 30, 90]

    def test_a_zone_that_does_not_exist_is_none(self) -> None:
        assert usage.zone_of("America/Halifax") == HALIFAX
        assert usage.zone_of("Mars/Olympus") is None
        assert usage.zone_of("../etc/passwd") is None
        assert usage.zone_of("") is None


class TestTotals:
    def test_calls_tokens_and_cost_are_added_up(self, session: Session) -> None:
        call(session, tokens=(1000, 200), cached=400, cost=1500)
        call(session, tokens=(500, 100), cached=0, cost=500)
        call(session, ok=False, tokens=(0, 0), cost=0, error="It didn't answer in time.")
        call(session, tokens=(10, 10), cost=None)

        found = usage.totals(session, NOW - timedelta(days=1), NOW)

        assert found == usage.Totals(
            calls=4,
            failed=1,
            input_tokens=1510,
            cached_tokens=400,
            output_tokens=310,
            cost_micros=2000,
            unpriced=1,
        )

    def test_nothing_is_nothing(self, session: Session) -> None:
        assert usage.totals(session, NOW - timedelta(days=1), NOW) == usage.Totals(
            0, 0, 0, 0, 0, 0, 0
        )

    def test_only_the_moments_asked_for_count(self, session: Session) -> None:
        call(session, NOW - timedelta(days=3))
        call(session, NOW - timedelta(hours=1))
        call(session, NOW)

        found = usage.totals(session, NOW - timedelta(days=1), NOW)

        assert found.calls == 1


class TestByDay:
    def test_each_use_is_counted_on_the_day_it_happened_in_the_zone(self, session: Session) -> None:
        # 02:00 UTC on the 15th is the evening of the 14th in Halifax.
        call(session, datetime(2026, 11, 15, 2, 0, tzinfo=UTC), purpose="triage", cost=1000)
        call(session, datetime(2026, 11, 15, 9, 0, tzinfo=UTC), purpose="triage", cost=2000)
        call(session, datetime(2026, 11, 15, 9, 30, tzinfo=UTC), purpose="chat", cost=500)

        in_halifax = usage.by_day(session, usage.span("7d", NOW, HALIFAX))
        in_utc = usage.by_day(session, usage.span("7d", NOW, UTC_ZONE))

        assert in_halifax[date(2026, 11, 14)] == [usage.Day("triage", 1, 1200, 1000)]
        assert in_halifax[date(2026, 11, 15)] == [
            usage.Day("chat", 1, 1200, 500),
            usage.Day("triage", 1, 1200, 2000),
        ]
        assert list(in_utc) == [date(2026, 11, 15)]

    def test_calls_before_the_span_are_left_out(self, session: Session) -> None:
        call(session, NOW - timedelta(days=20))

        assert usage.by_day(session, usage.span("7d", NOW, UTC_ZONE)) == {}


class TestGroups:
    def test_they_are_listed_by_what_they_cost_then_by_tokens(self, session: Session) -> None:
        call(session, provider="openai", model="gpt-6-luna", cost=300, tokens=(100, 10))
        call(session, provider="anthropic", model="claude-haiku-5-5", cost=900)
        call(session, provider="anthropic", model="claude-haiku-5-5", cost=100)
        call(session, provider="ollama", model="llama3", cost=0, tokens=(5000, 500))
        call(session, provider="ollama", model="mystery", cost=None, tokens=(1, 1))
        window = usage.span("7d", NOW, UTC_ZONE)

        providers = usage.by_provider(session, window)
        models = usage.by_model(session, window)

        assert [(g.key, g.calls, g.cost_micros) for g in providers] == [
            ("anthropic", 2, 1000),
            ("openai", 1, 300),
            ("ollama", 2, 0),
        ]
        assert providers[0].provider is None
        assert providers[2].unpriced == 1
        assert [(g.key, g.provider) for g in models] == [
            ("claude-haiku-5-5", "anthropic"),
            ("gpt-6-luna", "openai"),
            ("llama3", "ollama"),
            ("mystery", "ollama"),
        ]

    def test_uses_are_grouped_by_what_they_were_for(self, session: Session) -> None:
        call(session, purpose="triage")
        call(session, purpose="chat", cost=9000)

        found = usage.by_purpose(session, usage.span("7d", NOW, UTC_ZONE))

        assert [(g.key, g.calls) for g in found] == [("chat", 1), ("triage", 1)]


class TestTopConsumers:
    def test_what_took_the_most_comes_first_and_calls_about_nothing_are_left_out(
        self, session: Session
    ) -> None:
        call(session, about="incident 1", cost=100)
        call(session, about="incident 2", cost=900)
        call(session, about="incident 2", cost=100)
        call(session, about=None, cost=99999)

        found = usage.top_consumers(session, usage.span("7d", NOW, UTC_ZONE))

        assert [(c.about, c.calls, c.cost_micros) for c in found] == [
            ("incident 2", 2, 1000),
            ("incident 1", 1, 100),
        ]

    def test_there_are_at_most_a_few(self, session: Session) -> None:
        for number in range(usage.TOP_CONSUMERS + 3):
            call(session, about=f"incident {number}")

        assert (
            len(usage.top_consumers(session, usage.span("7d", NOW, UTC_ZONE)))
            == usage.TOP_CONSUMERS
        )


class TestTheMonth:
    def test_it_is_projected_from_the_pace_so_far(self, session: Session) -> None:
        # 15 and a half days of a 30-day month: 3,000,000 spent is 5,806,452 by the end.
        call(session, datetime(2026, 11, 2, tzinfo=UTC), cost=2_000_000)
        call(session, datetime(2026, 11, 10, tzinfo=UTC), cost=1_000_000)
        call(session, datetime(2026, 10, 31, 23, 0, tzinfo=UTC), cost=7_000_000)
        call(session, datetime(2026, 11, 4, tzinfo=UTC), cost=None)

        found = usage.month(session, NOW)

        assert found.start == datetime(2026, 11, 1, tzinfo=UTC)
        assert found.end == datetime(2026, 12, 1, tzinfo=UTC)
        assert found.spent_micros == 3_000_000
        assert found.unpriced == 1
        assert found.projected_micros == round(3_000_000 * 30 / 14.5)

    def test_there_is_nothing_to_project_in_the_first_day_or_before_anything_is_spent(
        self, session: Session
    ) -> None:
        early = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)
        call(session, datetime(2026, 11, 1, 1, 0, tzinfo=UTC), cost=500)

        assert usage.month(session, early).projected_micros is None
        assert usage.month(session, NOW).projected_micros is not None
        session.query(AiCall).delete()
        session.commit()
        assert usage.month(session, NOW).projected_micros is None


class TestTheCalls:
    def test_they_come_newest_first_a_page_at_a_time_with_the_total(self, session: Session) -> None:
        for number in range(5):
            call(session, NOW - timedelta(hours=number + 1), about=f"incident {number}")
        window = usage.span("7d", NOW, UTC_ZONE)

        first, total = usage.calls(session, window, 2, 0)
        second, _ = usage.calls(session, window, 2, 2)

        assert total == 5
        assert [c.about for c in first] == ["incident 0", "incident 1"]
        assert [c.about for c in second] == ["incident 2", "incident 3"]

    def test_what_was_asked_is_not_read_until_it_is_wanted(self, session: Session) -> None:
        call(session)
        session.expunge_all()

        found, _ = usage.calls(session, usage.span("7d", NOW, UTC_ZONE), 10, 0)

        assert "prompt" not in found[0].__dict__
        assert "answer" not in found[0].__dict__

    def test_an_export_has_them_all_oldest_first(self, session: Session) -> None:
        call(session, NOW - timedelta(hours=1), about="incident 2")
        call(session, NOW - timedelta(hours=3), about="incident 1")

        found = usage.export(session, usage.span("7d", NOW, UTC_ZONE))

        assert [c.about for c in found] == ["incident 1", "incident 2"]
