"""What is usual for the traffic through an interface, and the hours that were far above it."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.baselines import traffic
from app.config import Settings
from app.events.event import Severity
from app.metrics.sample import NewSample
from app.metrics.store import record
from app.models import MetricSeries, SystemInfo, TrafficBaseline
from tests.helpers import new_sample

# A Monday, half past noon, with whole days before it.
NOW = datetime(2026, 11, 16, 12, 30, tzinfo=UTC)
GIGABYTE = 1024**3
MEGABYTE = 1024**2


def feed(
    session: Session,
    settings: Settings,
    *,
    days: int,
    hourly: float = 200 * MEGABYTE,
    name: str = "interface.bytes_in",
    interface: str = "igc0",
    odd: Mapping[datetime, float] | None = None,
    step: int = 2,
    until: datetime = NOW,
) -> None:
    """A counter that rises by ``hourly`` bytes in every hour, read every ``step`` minutes, for
    ``days`` days up to ``until``; the hours in ``odd`` rise by what it says instead."""
    odd = odd or {}
    start = (until - timedelta(days=days)).replace(minute=0, second=0, microsecond=0)
    counter = 1_000_000.0
    at = start
    samples: list[NewSample] = []
    while at <= until:
        hour = at.replace(minute=0, second=0, microsecond=0)
        # The first and last readings of an hour are 60 - step minutes apart.
        counter += odd.get(hour, hourly) * step / (60 - step)
        samples.append(
            new_sample(
                name=name,
                value=counter,
                sampled_at=at,
                labels={"interface": interface},
            )
        )
        at += timedelta(minutes=step)
    record(session, settings, samples, until)
    session.commit()


def baselines(session: Session) -> list[TrafficBaseline]:
    session.expire_all()
    return list(session.scalars(select(TrafficBaseline).order_by(TrafficBaseline.bucket)))


class TestTheBuckets:
    def test_a_weekday_hour_is_its_hour_and_a_weekend_hour_is_a_day_later(self) -> None:
        assert traffic.bucket_of(datetime(2026, 11, 16, 14, tzinfo=UTC)) == 14
        assert traffic.bucket_of(datetime(2026, 11, 14, 14, tzinfo=UTC)) == 38

    def test_the_spread_is_never_less_than_a_share_of_the_median(self) -> None:
        middle, spread = traffic._stats([100.0] * 10)  # pyright: ignore[reportPrivateUsage]

        assert (middle, spread) == (100.0, 10.0)

    def test_the_spread_follows_how_far_the_hours_stray(self) -> None:
        middle, spread = traffic._stats([80.0, 90.0, 100.0, 110.0, 120.0])  # pyright: ignore[reportPrivateUsage]

        assert middle == 100.0
        assert round(spread, 1) == 14.8

    def test_sizes_are_said_in_words(self) -> None:
        sizes = [
            traffic._size(value)  # pyright: ignore[reportPrivateUsage]
            for value in (12, 2048, 5 * MEGABYTE, 3 * GIGABYTE, 2048 * GIGABYTE)
        ]

        assert sizes == ["12 bytes", "2.0 KB", "5.0 MB", "3.0 GB", "2.0 TB"]

    def test_the_more_spreads_beyond_the_line_the_surer_up_to_95(self) -> None:
        assert traffic.confidence_of(traffic.SPREADS) == 50
        assert traffic.confidence_of(traffic.SPREADS + 4) == 70
        assert traffic.confidence_of(1000) == 95


class TestLearning:
    def test_it_learns_what_is_usual_for_each_hour_of_the_day(
        self, session: Session, settings: Settings
    ) -> None:
        feed(session, settings, days=15)

        assert traffic.learn(session, NOW) == 1

        rows = baselines(session)
        assert {row.bucket for row in rows} >= set(range(0, 24)) | set(range(48, 72))
        weekday = next(row for row in rows if row.bucket == 3)
        assert weekday.samples >= traffic.MIN_HOURS
        assert round(weekday.median / MEGABYTE) == 200
        assert weekday.spread == weekday.median * traffic.MIN_SPREAD_SHARE

    def test_a_weekend_is_learned_apart_once_there_are_enough_of_them(
        self, session: Session, settings: Settings
    ) -> None:
        busy = {
            hour: 900 * MEGABYTE
            for hour in (
                NOW.replace(minute=0) - timedelta(hours=hours) for hours in range(0, 24 * 29)
            )
            if hour.weekday() >= 5
        }
        feed(session, settings, days=29, odd=busy)

        traffic.learn(session, NOW)

        rows = {row.bucket: row for row in baselines(session)}
        assert round(rows[3].median / MEGABYTE) == 200
        assert round(rows[27].median / MEGABYTE) == 900

    def test_it_does_not_learn_from_hours_that_are_too_few_or_that_began_again(
        self, session: Session, settings: Settings
    ) -> None:
        feed(session, settings, days=15, step=10)

        assert traffic.learn(session, NOW) == 0
        assert baselines(session) == []

    def test_it_learns_nothing_from_a_series_with_too_little_history(
        self, session: Session, settings: Settings
    ) -> None:
        feed(session, settings, days=3)

        assert traffic.learn(session, NOW) == 0
        assert baselines(session) == []

    def test_a_counter_that_began_again_from_nothing_leaves_its_hour_out(
        self, session: Session, settings: Settings
    ) -> None:
        reset = NOW.replace(minute=0) - timedelta(hours=40)
        feed(session, settings, days=15, odd={reset: -1000 * GIGABYTE})

        volumes = traffic._volumes(  # pyright: ignore[reportPrivateUsage]
            session, NOW - timedelta(days=15), NOW - timedelta(hours=2)
        )

        [hours] = volumes.values()
        assert reset not in hours
        assert len(hours) > 300

    def test_it_is_learned_again_only_when_it_is_old(
        self, session: Session, settings: Settings
    ) -> None:
        feed(session, settings, days=15)
        traffic.learn(session, NOW)
        session.execute(delete(TrafficBaseline))
        session.commit()

        assert traffic.learn(session, NOW + timedelta(hours=1)) == 0
        assert baselines(session) == []
        assert traffic.learn(session, NOW + traffic.REFRESH + timedelta(minutes=1)) == 1
        assert baselines(session) != []

    def test_what_it_learned_before_is_replaced_not_added_to(
        self, session: Session, settings: Settings
    ) -> None:
        feed(session, settings, days=15)
        traffic.learn(session, NOW)
        first = len(baselines(session))

        traffic.learn(session, NOW + traffic.REFRESH + timedelta(minutes=1))

        assert len(baselines(session)) == first
        assert session.scalar(select(func.count()).select_from(SystemInfo)) == 1


TOP = NOW.replace(minute=0)


def fed_and_learned(
    session: Session, settings: Settings, busy: Mapping[int, float] | None = None, **feeding: object
) -> None:
    """Two weeks of a steady 200 MB an hour, with the hours in ``busy`` (hours before the top of
    the current hour, and how much they carried) as they are said to be, and what is usual learned
    from the hours before them."""
    odd = {TOP - timedelta(hours=hours): volume for hours, volume in (busy or {}).items()}
    feed(session, settings, days=15, odd=odd, **feeding)  # type: ignore[arg-type]
    traffic.learn(session, NOW - timedelta(hours=3))


class TestTheHoursThatAreFarAboveWhatIsUsual:
    def test_an_hour_far_above_the_usual_is_a_deviation_with_the_reasons_in_it(
        self, session: Session, settings: Settings
    ) -> None:
        fed_and_learned(session, settings, {1: 3 * GIGABYTE})

        [event] = traffic.detect(session, NOW)

        assert event.severity is Severity.MEDIUM
        assert event.source == "baseline"
        assert event.kind == "alert"
        assert event.iface == "igc0"
        assert event.signature == "Traffic far above what is usual"
        assert event.occurred_at == TOP
        assert "Interface igc0 received 3.0 GB between 11:00 and 12:00 UTC on Monday" in (
            event.summary
        )
        assert "15 times the 200.0 MB" in event.summary
        assert event.raw is not None
        assert event.raw["confidence"] == 95
        assert event.raw["direction"] == "received"
        assert event.raw["usual_bytes"] == pytest.approx(200 * MEGABYTE)

    def test_a_smaller_rise_is_a_low_severity_one(
        self, session: Session, settings: Settings
    ) -> None:
        fed_and_learned(session, settings, {1: 1000 * MEGABYTE})

        [event] = traffic.detect(session, NOW)

        assert event.severity is Severity.LOW

    def test_an_hour_that_is_only_busier_is_not(self, session: Session, settings: Settings) -> None:
        # Twice the usual is not three times.
        fed_and_learned(session, settings, {1: 400 * MEGABYTE})

        assert traffic.detect(session, NOW) == []

    def test_an_hour_over_the_factor_and_under_the_floor_is_not(
        self, session: Session, settings: Settings
    ) -> None:
        fed_and_learned(session, settings, {1: 40 * MEGABYTE}, hourly=2 * MEGABYTE)

        assert traffic.detect(session, NOW) == []

    def test_an_hour_beyond_the_factor_but_within_the_spread_is_not(
        self, session: Session, settings: Settings
    ) -> None:
        # A link that is erratic: its spread is wide, so three times the median is ordinary.
        wild = {hours: (60 if hours // 24 % 2 else 600) * MEGABYTE for hours in range(4, 24 * 15)}
        fed_and_learned(session, settings, {**wild, 1: 1900 * MEGABYTE})

        assert traffic.detect(session, NOW) == []

    def test_nothing_is_said_of_a_series_that_has_not_been_learned(
        self, session: Session, settings: Settings
    ) -> None:
        odd = {TOP - timedelta(hours=1): 5 * GIGABYTE}
        feed(session, settings, days=1, odd=odd)

        assert traffic.detect(session, NOW) == []

    def test_an_hour_is_judged_once(self, session: Session, settings: Settings) -> None:
        fed_and_learned(session, settings, {1: 3 * GIGABYTE})
        assert len(traffic.detect(session, NOW)) == 1

        assert traffic.detect(session, NOW + timedelta(minutes=5)) == []

    def test_the_hours_since_the_last_run_are_all_judged_but_not_more_than_a_few(
        self, session: Session, settings: Settings
    ) -> None:
        busy = {hours: 3 * GIGABYTE for hours in (1, 2, 5)}
        fed_and_learned(session, settings, busy)

        events = traffic.detect(session, NOW)

        # The hour before them is further back than it looks.
        assert [event.occurred_at for event in events] == [TOP - timedelta(hours=1), TOP]

    def test_a_series_that_sends_is_said_to_have_sent(
        self, session: Session, settings: Settings
    ) -> None:
        fed_and_learned(
            session, settings, {1: 3 * GIGABYTE}, name="interface.bytes_out", interface="igc1"
        )

        [event] = traffic.detect(session, NOW)

        assert event.summary.startswith("Interface igc1 sent 3.0 GB")

    def test_a_series_with_no_interface_is_still_said(
        self, session: Session, settings: Settings
    ) -> None:
        fed_and_learned(session, settings, {1: 3 * GIGABYTE})
        for series in session.scalars(select(MetricSeries)):
            series.labels = {}
        session.commit()

        [event] = traffic.detect(session, NOW)

        assert event.summary.startswith("A network interface received 3.0 GB")
        assert event.iface is None

    def test_a_weekend_hour_is_judged_against_the_weekend_when_it_has_enough(
        self, session: Session, settings: Settings
    ) -> None:
        sunday = datetime(2026, 11, 15, 12, 30, tzinfo=UTC)
        top = sunday.replace(minute=0)
        odd = {
            hour: 900 * MEGABYTE
            for hour in (top - timedelta(hours=h) for h in range(24 * 30))
            if hour.weekday() >= 5
        }
        # 1 GB would be five times a weekday's hour and is not far above a weekend's.
        odd[top - timedelta(hours=1)] = 1000 * MEGABYTE
        feed(session, settings, days=29, odd=odd, until=sunday)
        traffic.learn(session, sunday - timedelta(hours=3))

        assert traffic.detect(session, sunday) == []
