from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import DDL, Engine, text
from sqlalchemy.orm import Session

from app import partitions
from app.config import Settings
from app.events.store import record as record_event
from app.metrics.store import record as record_sample
from app.partitions import EVENTS, METRIC_SAMPLES, Partition, Weekly
from tests.helpers import new_event, new_sample

MONDAY = datetime(2026, 10, 19, tzinfo=UTC)

every_table = pytest.mark.parametrize("weeks", partitions.ALL, ids=lambda weeks: weeks.table)


@every_table
class TestWhichWeek:
    @pytest.mark.parametrize(
        "moment",
        [
            MONDAY,
            MONDAY + timedelta(days=3, hours=5),
            MONDAY + timedelta(days=7) - timedelta(microseconds=1),
        ],
    )
    def test_a_week_runs_from_monday_to_the_next(self, weeks: Weekly, moment: datetime) -> None:
        week = weeks.containing(moment)

        assert week.start == MONDAY
        assert week.end == MONDAY + timedelta(days=7)

    def test_the_next_monday_begins_the_next_week(self, weeks: Weekly) -> None:
        assert weeks.containing(MONDAY + timedelta(days=7)).start == MONDAY + timedelta(days=7)

    def test_the_week_is_the_one_in_utc(self, weeks: Weekly) -> None:
        # Sunday evening in Halifax is already Monday in UTC.
        halifax = timezone(timedelta(hours=-3))

        assert weeks.containing(datetime(2026, 10, 18, 22, 0, tzinfo=halifax)).start == MONDAY

    def test_it_is_named_for_the_table_and_the_day_it_begins(self, weeks: Weekly) -> None:
        assert weeks.containing(MONDAY).name == f"{weeks.table}_p20261019"

    def test_a_year_boundary_is_no_trouble(self, weeks: Weekly) -> None:
        week = weeks.containing(datetime(2027, 1, 1, tzinfo=UTC))

        assert week.start == datetime(2026, 12, 28, tzinfo=UTC)
        assert week.name == f"{weeks.table}_p20261228"

    def test_only_its_own_partitions_match_the_name(self, weeks: Weekly) -> None:
        assert weeks.pattern.match(f"{weeks.table}_p20261019")
        assert not weeks.pattern.match(f"{weeks.table}_old")
        assert not weeks.pattern.match(f"other_{weeks.table}_p20261019")


@every_table
class TestMakingAndDropping:
    def test_there_are_none_until_one_is_made(self, session: Session, weeks: Weekly) -> None:
        assert weeks.existing(session) == []

    def test_a_week_is_made_once_and_listed_oldest_first(
        self, session: Session, weeks: Weekly
    ) -> None:
        first = Partition(weeks.table, MONDAY)
        later = Partition(weeks.table, MONDAY + timedelta(days=14))
        weeks.ensure(session, [later, first, later])
        weeks.ensure(session, [first])

        assert weeks.existing(session) == [first, later]

    def test_a_partition_is_dropped_with_what_is_in_it(
        self, session: Session, weeks: Weekly
    ) -> None:
        week = Partition(weeks.table, MONDAY)
        weeks.ensure(session, [week])
        weeks.drop(session, week)
        weeks.drop(session, week)

        assert weeks.existing(session) == []

    def test_a_table_it_didnt_make_is_left_alone(self, session: Session, weeks: Weekly) -> None:
        week = Partition(weeks.table, MONDAY)
        weeks.ensure(session, [week])
        for name, first, last in (
            (f"{weeks.table}_old", "2020-01-01", "2020-02-01"),
            (f"{weeks.table}_p20269999", "2021-01-01", "2021-02-01"),
        ):
            session.execute(
                DDL(
                    "CREATE TABLE %(name)s PARTITION OF %(table)s"
                    " FOR VALUES FROM ('%(first)s') TO ('%(last)s')",
                    context={"name": name, "table": weeks.table, "first": first, "last": last},
                )
            )

        assert weeks.existing(session) == [week]

    def test_a_week_of_one_table_is_not_a_week_of_the_other(
        self, session: Session, weeks: Weekly
    ) -> None:
        other = next(other for other in partitions.ALL if other is not weeks)
        other.ensure(session, [Partition(other.table, MONDAY)])

        assert weeks.existing(session) == []

    def test_the_lock_can_be_taken_again_by_the_same_transaction(
        self, session: Session, weeks: Weekly
    ) -> None:
        weeks.lock(session)
        weeks.lock(session)


class TestTheLocks:
    def test_each_table_has_a_lock_of_its_own(self, session: Session, engine: Engine) -> None:
        EVENTS.lock(session)

        with engine.connect() as other:
            taken = [
                other.scalar(
                    text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": weeks.lock_key}
                )
                for weeks in partitions.ALL
            ]

        # Another transaction can't take the events' lock while this one holds it, but can take
        # the samples'.
        assert taken == [False, True]

    def test_the_locks_are_all_different(self) -> None:
        keys = [weeks.lock_key for weeks in partitions.ALL]

        assert len(set(keys)) == len(keys)


class TestRowsInAWeek:
    def test_events_go_into_the_partition_of_their_week(self, session: Session) -> None:
        EVENTS.ensure(session, [Partition("events", MONDAY)])
        session.execute(
            text(
                "INSERT INTO events (occurred_at, received_at, source, connection, kind,"
                " severity, summary, fingerprint)"
                " VALUES ('2026-10-21 10:00+00', now(), 'wazuh', 'indexer', 'alert', 1, 'x', 'f')"
            )
        )

        assert session.scalar(text("SELECT count(*) FROM events_p20261019")) == 1

    def test_samples_go_into_the_partition_of_their_week(
        self, session: Session, settings: Settings
    ) -> None:
        moment = MONDAY + timedelta(days=2)

        record_sample(session, settings, [new_sample(sampled_at=moment)], moment)

        assert session.scalar(text("SELECT count(*) FROM metric_samples_p20261019")) == 1

    def test_it_says_whether_a_week_of_events_has_any(
        self, session: Session, settings: Settings
    ) -> None:
        week = Partition("events", MONDAY)
        EVENTS.ensure(session, [week, Partition("events", MONDAY + timedelta(days=7))])
        assert not EVENTS.has_rows(session, week)

        record_event(
            session,
            settings,
            [new_event(occurred_at=MONDAY + timedelta(days=2))],
            MONDAY + timedelta(days=3),
        )

        assert EVENTS.has_rows(session, week)
        assert not EVENTS.has_rows(session, Partition("events", MONDAY + timedelta(days=7)))

    def test_it_says_whether_a_week_of_samples_has_any(
        self, session: Session, settings: Settings
    ) -> None:
        week = Partition("metric_samples", MONDAY)
        METRIC_SAMPLES.ensure(
            session, [week, Partition("metric_samples", MONDAY + timedelta(days=7))]
        )
        assert not METRIC_SAMPLES.has_rows(session, week)

        record_sample(
            session,
            settings,
            [new_sample(sampled_at=MONDAY + timedelta(days=2))],
            MONDAY + timedelta(days=3),
        )

        assert METRIC_SAMPLES.has_rows(session, week)
        assert not METRIC_SAMPLES.has_rows(
            session, Partition("metric_samples", MONDAY + timedelta(days=7))
        )
