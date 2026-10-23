from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import DDL, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.events import partitions
from app.events.partitions import Partition
from app.events.store import record
from tests.helpers import new_event

MONDAY = datetime(2026, 10, 19, tzinfo=UTC)


class TestWhichWeek:
    @pytest.mark.parametrize(
        "moment",
        [
            MONDAY,
            MONDAY + timedelta(days=3, hours=5),
            MONDAY + timedelta(days=7) - timedelta(microseconds=1),
        ],
    )
    def test_a_week_runs_from_monday_to_the_next(self, moment: datetime) -> None:
        week = partitions.containing(moment)

        assert week.start == MONDAY
        assert week.end == MONDAY + timedelta(days=7)

    def test_the_next_monday_begins_the_next_week(self) -> None:
        assert partitions.containing(MONDAY + timedelta(days=7)).start == MONDAY + timedelta(days=7)

    def test_the_week_is_the_one_in_utc(self) -> None:
        # Sunday evening in Halifax is already Monday in UTC.
        halifax = timezone(timedelta(hours=-3))

        assert partitions.containing(datetime(2026, 10, 18, 22, 0, tzinfo=halifax)).start == MONDAY

    def test_it_is_named_for_the_day_it_begins(self) -> None:
        assert Partition(MONDAY).name == "events_p20261019"

    def test_a_year_boundary_is_no_trouble(self) -> None:
        week = partitions.containing(datetime(2027, 1, 1, tzinfo=UTC))

        assert week.start == datetime(2026, 12, 28, tzinfo=UTC)
        assert week.name == "events_p20261228"


class TestMakingAndDropping:
    def test_there_are_none_until_one_is_made(self, session: Session) -> None:
        assert partitions.existing(session) == []

    def test_a_week_is_made_once_and_listed_oldest_first(self, session: Session) -> None:
        later = Partition(MONDAY + timedelta(days=14))
        partitions.ensure(session, [later, Partition(MONDAY), later])
        partitions.ensure(session, [Partition(MONDAY)])

        assert partitions.existing(session) == [Partition(MONDAY), later]

    def test_events_go_into_the_partition_of_their_week(self, session: Session) -> None:
        partitions.ensure(session, [Partition(MONDAY)])
        session.execute(
            text(
                "INSERT INTO events (occurred_at, received_at, source, connection, kind,"
                " severity, summary, fingerprint)"
                " VALUES ('2026-10-21 10:00+00', now(), 'wazuh', 'indexer', 'alert', 1, 'x', 'f')"
            )
        )

        count = session.scalar(text("SELECT count(*) FROM events_p20261019"))

        assert count == 1

    def test_a_partition_is_dropped_with_what_is_in_it(self, session: Session) -> None:
        partitions.ensure(session, [Partition(MONDAY)])
        partitions.drop(session, Partition(MONDAY))
        partitions.drop(session, Partition(MONDAY))

        assert partitions.existing(session) == []

    def test_it_says_whether_a_week_has_events(self, session: Session, settings: Settings) -> None:
        week = Partition(MONDAY)
        partitions.ensure(session, [week, Partition(MONDAY + timedelta(days=7))])
        assert not partitions.has_events(session, week)

        record(
            session,
            settings,
            [new_event(occurred_at=MONDAY + timedelta(days=2))],
            MONDAY + timedelta(days=3),
        )

        assert partitions.has_events(session, week)
        assert not partitions.has_events(session, Partition(MONDAY + timedelta(days=7)))

    def test_a_table_it_didnt_make_is_left_alone(self, session: Session) -> None:
        partitions.ensure(session, [Partition(MONDAY)])
        session.execute(
            DDL(
                "CREATE TABLE events_old PARTITION OF events"
                " FOR VALUES FROM ('2020-01-01') TO ('2020-02-01')"
            )
        )
        session.execute(
            DDL(
                "CREATE TABLE events_p20269999 PARTITION OF events"
                " FOR VALUES FROM ('2021-01-01') TO ('2021-02-01')"
            )
        )

        assert partitions.existing(session) == [Partition(MONDAY)]

    def test_the_lock_can_be_taken_again_by_the_same_transaction(self, session: Session) -> None:
        partitions.lock(session)
        partitions.lock(session)
