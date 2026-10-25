from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.metrics import retention
from app.metrics.retention import Retention
from app.metrics.store import record
from app.models import MetricRetention, MetricSample, MetricSeries
from app.partitions import METRIC_SAMPLES, Partition
from tests.helpers import new_sample

# A Sunday, in the week that begins on Monday 19 October.
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
THIS_WEEK = Partition("metric_samples", datetime(2026, 10, 19, tzinfo=UTC))


def add(session: Session, source: str, age: timedelta, name: str = "system.load_1m") -> None:
    """Stores a sample of this age, even one past its retention period, which ``record`` would
    refuse."""
    sample = new_sample(source=source, name=name, sampled_at=NOW - age)
    series = session.scalar(
        select(MetricSeries).where(MetricSeries.fingerprint == sample.fingerprint)
    )
    if series is None:
        series = MetricSeries(
            source=sample.source,
            connection=sample.connection,
            name=sample.name,
            labels=sample.clean_labels,
            fingerprint=sample.fingerprint,
        )
        session.add(series)
        session.flush()
    METRIC_SAMPLES.lock(session)
    METRIC_SAMPLES.ensure(session, [METRIC_SAMPLES.containing(sample.sampled_at)])
    session.add(
        MetricSample(series_id=series.id, sampled_at=sample.sampled_at, source=source, value=1.0)
    )
    session.flush()


def sources(session: Session) -> list[tuple[str, int]]:
    session.expire_all()
    rows = session.scalars(
        select(MetricSample).order_by(MetricSample.source, MetricSample.sampled_at)
    )
    return [(row.source, (NOW - row.sampled_at).days) for row in rows]


def series_names(session: Session) -> list[tuple[str, str]]:
    session.expire_all()
    return [
        (series.source, series.name)
        for series in session.scalars(
            select(MetricSeries).order_by(MetricSeries.source, MetricSeries.name)
        )
    ]


class TestTheSettings:
    def test_every_source_keeps_samples_for_the_default_until_told_otherwise(
        self, session: Session, settings: Settings
    ) -> None:
        loaded = retention.load(session, settings)

        assert loaded == Retention(default=30, own={})
        assert loaded.days("opnsense") == 30
        assert loaded.longest == 30

    def test_the_default_can_be_set_in_the_environment(self, session: Session) -> None:
        loaded = retention.load(session, Settings(metric_retention_days=14))

        assert loaded.days("opnsense") == 14

    def test_a_source_can_keep_them_for_longer_or_shorter(
        self, session: Session, settings: Settings
    ) -> None:
        retention.set_days(session, "opnsense", 365)
        retention.set_days(session, "ntopng", 7)
        session.commit()

        loaded = retention.load(session, settings)

        assert loaded.days("opnsense") == 365
        assert loaded.days("ntopng") == 7
        assert loaded.days("wazuh") == 30
        assert loaded.longest == 365

    def test_samples_and_events_are_kept_for_times_of_their_own(
        self, session: Session, settings: Settings
    ) -> None:
        from app.events import retention as events

        retention.set_days(session, "opnsense", 365)
        session.commit()

        assert events.load(session, settings).own == {}
        assert retention.load(session, settings).own == {"opnsense": 365}

    def test_setting_it_again_changes_it(self, session: Session, settings: Settings) -> None:
        retention.set_days(session, "opnsense", 365)
        session.commit()
        retention.set_days(session, "opnsense", 90)
        session.commit()

        assert retention.load(session, settings).own == {"opnsense": 90}

    def test_clearing_it_goes_back_to_the_default(
        self, session: Session, settings: Settings
    ) -> None:
        retention.set_days(session, "opnsense", 365)
        session.commit()

        retention.set_days(session, "opnsense", None)
        retention.set_days(session, "ntopng", None)
        session.commit()

        assert retention.load(session, settings).own == {}

    @pytest.mark.parametrize("days", [0, -1, 3651])
    def test_the_database_refuses_a_period_out_of_range(self, session: Session, days: int) -> None:
        session.add(MetricRetention(source="opnsense", days=days))

        with pytest.raises(IntegrityError):
            session.flush()


class TestWhatIsStored:
    def test_it_counts_each_sources_samples_and_finds_its_oldest(self, session: Session) -> None:
        add(session, "opnsense", timedelta(days=5))
        add(session, "opnsense", timedelta(days=2))
        add(session, "ntopng", timedelta(days=1))

        found = retention.stored(session)

        assert found == {
            "opnsense": retention.Stored(2, NOW - timedelta(days=5)),
            "ntopng": retention.Stored(1, NOW - timedelta(days=1)),
        }

    def test_nothing_stored_is_nothing(self, session: Session) -> None:
        assert retention.stored(session) == {}


class TestPurging:
    def test_samples_past_the_default_are_deleted_and_the_rest_stay(
        self, session: Session, settings: Settings
    ) -> None:
        add(session, "opnsense", timedelta(days=31))
        add(session, "opnsense", timedelta(days=29))
        add(session, "ntopng", timedelta(days=45))

        purged = retention.purge_expired(session, settings, NOW)

        assert sources(session) == [("opnsense", 29)]
        # The one 31 days old shares its week with a newer sample, so it is deleted; the 45 days
        # old one had a week of its own, which was dropped without counting its samples.
        assert purged == retention.Purged(deleted=1, partitions_dropped=1)

    def test_a_source_with_its_own_period_is_held_to_it(
        self, session: Session, settings: Settings
    ) -> None:
        retention.set_days(session, "opnsense", 90)
        retention.set_days(session, "ntopng", 3)
        add(session, "opnsense", timedelta(days=60))
        add(session, "opnsense", timedelta(days=100))
        add(session, "ntopng", timedelta(days=2))
        add(session, "ntopng", timedelta(days=4))
        add(session, "wazuh", timedelta(days=29))
        add(session, "wazuh", timedelta(days=31))

        purged = retention.purge_expired(session, settings, NOW)

        assert sources(session) == [("ntopng", 2), ("opnsense", 60), ("wazuh", 29)]
        # OPNsense's 100 days old sample is in a week that ended before its 90 days began.
        assert purged == retention.Purged(deleted=2, partitions_dropped=1)

    def test_a_week_that_ended_before_every_period_began_is_dropped_whole(
        self, session: Session, settings: Settings
    ) -> None:
        add(session, "opnsense", timedelta(days=100))
        add(session, "opnsense", timedelta(days=1))

        purged = retention.purge_expired(session, settings, NOW)

        assert METRIC_SAMPLES.existing(session) == [THIS_WEEK]
        # It went with its table, so it wasn't deleted row by row.
        assert purged == retention.Purged(deleted=0, partitions_dropped=1)

    def test_a_week_holding_a_source_with_a_longer_period_is_kept(
        self, session: Session, settings: Settings
    ) -> None:
        retention.set_days(session, "opnsense", 365)
        add(session, "opnsense", timedelta(days=100))
        add(session, "ntopng", timedelta(days=100))

        purged = retention.purge_expired(session, settings, NOW)

        # The week stays for OPNsense's sake, and ntopng's sample in it is deleted.
        assert sources(session) == [("opnsense", 100)]
        assert purged == retention.Purged(deleted=1, partitions_dropped=0)

    def test_a_past_week_the_delete_emptied_is_dropped(
        self, session: Session, settings: Settings
    ) -> None:
        # OPNsense's long period keeps the old week from being dropped whole.
        retention.set_days(session, "opnsense", 365)
        add(session, "ntopng", timedelta(days=100))
        add(session, "opnsense", timedelta(days=1))

        purged = retention.purge_expired(session, settings, NOW)

        assert purged == retention.Purged(deleted=1, partitions_dropped=1)
        assert METRIC_SAMPLES.existing(session) == [THIS_WEEK]

    def test_the_week_now_is_kept_even_when_it_is_empty(
        self, session: Session, settings: Settings
    ) -> None:
        add(session, "opnsense", timedelta(days=1))
        session.execute(delete(MetricSample))

        retention.purge_expired(session, settings, NOW)

        assert METRIC_SAMPLES.existing(session) == [THIS_WEEK]

    def test_a_week_ahead_is_not_dropped(self, session: Session, settings: Settings) -> None:
        ahead = Partition("metric_samples", datetime(2026, 11, 2, tzinfo=UTC))
        METRIC_SAMPLES.ensure(session, [ahead])

        retention.purge_expired(session, settings, NOW)

        assert METRIC_SAMPLES.existing(session) == [ahead]

    def test_there_is_nothing_to_do_without_samples(
        self, session: Session, settings: Settings
    ) -> None:
        assert retention.purge_expired(session, settings, NOW) == retention.Purged(0, 0)

    def test_what_it_did_is_committed(self, session: Session, settings: Settings) -> None:
        add(session, "opnsense", timedelta(days=40))
        session.commit()

        retention.purge_expired(session, settings, NOW)
        session.rollback()

        assert sources(session) == []

    def test_recording_and_purging_agree_about_what_is_old(
        self, session: Session, settings: Settings
    ) -> None:
        old = new_sample(sampled_at=NOW - timedelta(days=29, hours=23))

        assert record(session, settings, [old], NOW) == 1
        retention.purge_expired(session, settings, NOW)
        assert len(sources(session)) == 1

        retention.purge_expired(session, settings, NOW + timedelta(hours=2))
        assert sources(session) == []


class TestTheSeriesOfWhatWasPurged:
    def test_a_series_with_samples_left_stays(self, session: Session, settings: Settings) -> None:
        add(session, "opnsense", timedelta(days=40))
        add(session, "opnsense", timedelta(days=1))

        retention.purge_expired(session, settings, NOW)

        assert series_names(session) == [("opnsense", "system.load_1m")]

    def test_a_series_whose_samples_are_all_gone_goes_with_them(
        self, session: Session, settings: Settings
    ) -> None:
        add(session, "opnsense", timedelta(days=40))
        add(session, "opnsense", timedelta(days=40), name="system.load_5m")
        add(session, "ntopng", timedelta(days=1))

        retention.purge_expired(session, settings, NOW)

        assert series_names(session) == [("ntopng", "system.load_1m")]

    def test_a_series_whose_week_was_dropped_whole_goes_too(
        self, session: Session, settings: Settings
    ) -> None:
        add(session, "opnsense", timedelta(days=100))

        purged = retention.purge_expired(session, settings, NOW)

        assert purged == retention.Purged(deleted=0, partitions_dropped=1)
        assert series_names(session) == []

    def test_a_series_that_never_had_samples_goes_too(
        self, session: Session, settings: Settings
    ) -> None:
        session.add(
            MetricSeries(
                source="opnsense", connection="api", name="empty", labels={}, fingerprint="f" * 64
            )
        )
        session.flush()

        retention.purge_expired(session, settings, NOW)

        assert series_names(session) == []

    def test_it_is_made_again_when_a_sample_of_it_turns_up(
        self, session: Session, settings: Settings
    ) -> None:
        add(session, "opnsense", timedelta(days=40))
        retention.purge_expired(session, settings, NOW)
        assert series_names(session) == []

        record(session, settings, [new_sample(sampled_at=NOW)], NOW)

        assert series_names(session) == [("opnsense", "system.load_1m")]
        assert sources(session) == [("opnsense", 0)]
