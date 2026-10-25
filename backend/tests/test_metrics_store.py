from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.metrics import retention
from app.metrics.store import FUTURE_TOLERANCE, record
from app.models import MetricSample, MetricSeries
from app.partitions import METRIC_SAMPLES, Partition
from tests.helpers import new_sample

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
THIS_WEEK = Partition("metric_samples", datetime(2026, 10, 19, tzinfo=UTC))


def stored(session: Session) -> list[MetricSample]:
    session.expire_all()
    return list(session.scalars(select(MetricSample).order_by(MetricSample.sampled_at)))


def all_series(session: Session) -> list[MetricSeries]:
    session.expire_all()
    return list(session.scalars(select(MetricSeries).order_by(MetricSeries.id)))


def test_a_sample_is_stored_with_the_series_it_is_of(session: Session, settings: Settings) -> None:
    sample = new_sample(
        sampled_at=NOW - timedelta(seconds=30),
        value=0.75,
        labels={"interface": "igc0", "zone": " wan\n"},
    )

    assert record(session, settings, [sample], NOW) == 1
    session.commit()

    (series,) = all_series(session)
    assert (series.source, series.connection, series.name) == ("opnsense", "api", "system.load_1m")
    assert series.labels == {"interface": "igc0", "zone": "wan"}
    assert series.fingerprint == sample.fingerprint
    (row,) = stored(session)
    assert row.series_id == series.id
    assert row.sampled_at == NOW - timedelta(seconds=30)
    assert row.source == "opnsense"
    assert row.value == 0.75


def test_nothing_to_store_stores_nothing(session: Session, settings: Settings) -> None:
    assert record(session, settings, [], NOW) == 0
    assert METRIC_SAMPLES.existing(session) == []
    assert all_series(session) == []


def test_reading_the_same_moment_again_stores_it_once(session: Session, settings: Settings) -> None:
    sample = new_sample(sampled_at=NOW)

    assert record(session, settings, [sample, sample], NOW) == 1
    assert record(session, settings, [sample], NOW) == 0
    session.commit()

    assert len(stored(session)) == 1
    assert len(all_series(session)) == 1


def test_a_second_reading_of_the_same_moment_with_another_value_keeps_the_first(
    session: Session, settings: Settings
) -> None:
    record(session, settings, [new_sample(sampled_at=NOW, value=1.0)], NOW)
    record(session, settings, [new_sample(sampled_at=NOW, value=2.0)], NOW)

    assert [row.value for row in stored(session)] == [1.0]


def test_samples_that_differ_are_each_stored(session: Session, settings: Settings) -> None:
    samples = [
        new_sample(sampled_at=NOW),
        new_sample(sampled_at=NOW - timedelta(seconds=1)),
        new_sample(sampled_at=NOW, labels={"interface": "igc0"}),
        new_sample(sampled_at=NOW, name="system.load_5m"),
        new_sample(sampled_at=NOW, connection="other"),
        new_sample(sampled_at=NOW, source="ntopng"),
    ]

    assert record(session, settings, samples, NOW) == 6
    assert len(all_series(session)) == 5


def test_a_series_is_made_once_and_every_later_sample_goes_to_it(
    session: Session, settings: Settings
) -> None:
    record(session, settings, [new_sample(sampled_at=NOW - timedelta(minutes=2))], NOW)
    first = all_series(session)
    record(session, settings, [new_sample(sampled_at=NOW - timedelta(minutes=1))], NOW)
    record(session, settings, [new_sample(sampled_at=NOW)], NOW)

    assert all_series(session) == first
    assert {row.series_id for row in stored(session)} == {first[0].id}
    assert len(stored(session)) == 3


def test_samples_of_different_series_in_one_batch_each_find_theirs(
    session: Session, settings: Settings
) -> None:
    samples = [
        new_sample(sampled_at=NOW, labels={"interface": "igc0"}, value=1.0),
        new_sample(sampled_at=NOW, labels={"interface": "igc1"}, value=2.0),
        new_sample(sampled_at=NOW - timedelta(minutes=1), labels={"interface": "igc0"}, value=3.0),
    ]

    record(session, settings, samples, NOW)

    by_interface = {series.id: series.labels["interface"] for series in all_series(session)}
    assert sorted((by_interface[row.series_id], row.value) for row in stored(session)) == [
        ("igc0", 1.0),
        ("igc0", 3.0),
        ("igc1", 2.0),
    ]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_something_that_isnt_a_number_is_skipped(
    session: Session, settings: Settings, value: float
) -> None:
    samples = [new_sample(sampled_at=NOW, value=value), new_sample(sampled_at=NOW, name="ok")]

    assert record(session, settings, samples, NOW) == 1
    assert [row.value for row in stored(session)] == [0.42]
    # The series it would have belonged to isn't made for nothing.
    assert [series.name for series in all_series(session)] == ["ok"]


@pytest.mark.parametrize("value", [0.0, -3.5, 1e300, 2, 0.1 + 0.2])
def test_any_number_is_kept_as_it_is(session: Session, settings: Settings, value: float) -> None:
    record(session, settings, [new_sample(sampled_at=NOW, value=value)], NOW)

    assert [row.value for row in stored(session)] == [value]


def test_a_week_gets_a_partition_when_its_first_sample_arrives(
    session: Session, settings: Settings
) -> None:
    last_week = NOW - timedelta(days=7)

    record(session, settings, [new_sample(sampled_at=NOW), new_sample(sampled_at=last_week)], NOW)
    session.commit()

    assert METRIC_SAMPLES.existing(session) == [
        Partition("metric_samples", THIS_WEEK.start - timedelta(days=7)),
        THIS_WEEK,
    ]


def test_a_later_batch_for_a_week_that_exists_makes_nothing_more(
    session: Session, settings: Settings
) -> None:
    record(session, settings, [new_sample(sampled_at=NOW)], NOW)
    record(session, settings, [new_sample(sampled_at=NOW + timedelta(seconds=1))], NOW)

    assert METRIC_SAMPLES.existing(session) == [THIS_WEEK]


def test_a_sample_from_a_little_in_the_future_keeps_its_time(
    session: Session, settings: Settings
) -> None:
    ahead = NOW + FUTURE_TOLERANCE

    record(session, settings, [new_sample(sampled_at=ahead)], NOW)

    assert [row.sampled_at for row in stored(session)] == [ahead]


def test_a_sample_from_far_in_the_future_is_stored_as_of_now(
    session: Session, settings: Settings
) -> None:
    # A time years ahead mustn't make a week to hold it.
    record(session, settings, [new_sample(sampled_at=datetime(2099, 1, 1, tzinfo=UTC))], NOW)

    assert [row.sampled_at for row in stored(session)] == [NOW]
    assert METRIC_SAMPLES.existing(session) == [THIS_WEEK]


def test_a_sample_older_than_the_retention_period_is_not_stored(
    session: Session, settings: Settings
) -> None:
    days = settings.metric_retention_days
    samples = [
        new_sample(sampled_at=NOW - timedelta(days=days, seconds=1), name="past"),
        new_sample(sampled_at=NOW - timedelta(days=days - 1), name="kept"),
    ]

    assert record(session, settings, samples, NOW) == 1
    assert [row.sampled_at for row in stored(session)] == [NOW - timedelta(days=days - 1)]
    # Its series wasn't made either.
    assert [series.name for series in all_series(session)] == ["kept"]


def test_nothing_is_made_when_everything_is_too_old(session: Session, settings: Settings) -> None:
    old = new_sample(sampled_at=NOW - timedelta(days=settings.metric_retention_days + 5))

    assert record(session, settings, [old], NOW) == 0
    assert METRIC_SAMPLES.existing(session) == []
    assert all_series(session) == []


def test_each_source_is_held_to_its_own_retention_period(
    session: Session, settings: Settings
) -> None:
    retention.set_days(session, "opnsense", 2)
    retention.set_days(session, "ntopng", 90)
    session.flush()
    three_days = NOW - timedelta(days=3)
    samples = [
        new_sample(sampled_at=three_days),
        new_sample(sampled_at=three_days, source="ntopng"),
        new_sample(sampled_at=three_days, source="crowdsec"),
    ]

    record(session, settings, samples, NOW)

    assert [row.source for row in stored(session)] == ["ntopng", "crowdsec"]


def test_the_count_is_of_the_new_samples_across_batches_larger_than_one_statement(
    session: Session, settings: Settings
) -> None:
    samples = [
        new_sample(sampled_at=NOW - timedelta(seconds=index), value=float(index))
        for index in range(2500)
    ]

    assert record(session, settings, samples, NOW) == 2500
    assert session.scalar(select(func.count()).select_from(MetricSample)) == 2500
    assert len(all_series(session)) == 1
