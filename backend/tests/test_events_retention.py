from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.events import partitions, retention
from app.events.partitions import Partition
from app.events.retention import Retention
from app.events.store import record
from app.models import Event, EventRetention
from tests.helpers import new_event

# A Friday, in the week that begins on Monday 19 October.
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def add(session: Session, source: str, age: timedelta) -> None:
    """Stores an event of this age, even one past its retention period, which ``record`` would
    refuse."""
    event = new_event(
        source=source,
        connection="api",
        occurred_at=NOW - age,
        identity=(source, str(age)),
    )
    partitions.lock(session)
    partitions.ensure(session, [partitions.containing(event.occurred_at)])
    session.add(Event(**event.row(NOW)))
    session.flush()


def sources(session: Session) -> list[tuple[str, int]]:
    session.expire_all()
    rows = session.scalars(select(Event).order_by(Event.source, Event.occurred_at))
    return [(row.source, (NOW - row.occurred_at).days) for row in rows]


class TestTheSettings:
    def test_every_source_keeps_events_for_the_default_until_told_otherwise(
        self, session: Session, settings: Settings
    ) -> None:
        loaded = retention.load(session, settings)

        assert loaded == Retention(default=30, own={})
        assert loaded.days("wazuh") == 30
        assert loaded.longest == 30

    def test_the_default_can_be_set_in_the_environment(self, session: Session) -> None:
        loaded = retention.load(session, Settings(event_retention_days=14))

        assert loaded.days("wazuh") == 14

    def test_a_source_can_keep_them_for_longer_or_shorter(
        self, session: Session, settings: Settings
    ) -> None:
        retention.set_days(session, "wazuh", 365)
        retention.set_days(session, "ntopng", 7)
        session.commit()

        loaded = retention.load(session, settings)

        assert loaded.days("wazuh") == 365
        assert loaded.days("ntopng") == 7
        assert loaded.days("opnsense") == 30
        assert loaded.longest == 365

    def test_setting_it_again_changes_it(self, session: Session, settings: Settings) -> None:
        retention.set_days(session, "wazuh", 365)
        session.commit()
        retention.set_days(session, "wazuh", 90)
        session.commit()

        assert retention.load(session, settings).own == {"wazuh": 90}

    def test_clearing_it_goes_back_to_the_default(
        self, session: Session, settings: Settings
    ) -> None:
        retention.set_days(session, "wazuh", 365)
        session.commit()

        retention.set_days(session, "wazuh", None)
        retention.set_days(session, "ntopng", None)
        session.commit()

        assert retention.load(session, settings).own == {}

    @pytest.mark.parametrize("days", [0, -1, 3651])
    def test_the_database_refuses_a_period_out_of_range(self, session: Session, days: int) -> None:
        session.add(EventRetention(source="wazuh", days=days))

        with pytest.raises(IntegrityError):
            session.flush()


class TestWhatIsStored:
    def test_it_counts_each_sources_events_and_finds_its_oldest(
        self, session: Session, settings: Settings
    ) -> None:
        add(session, "wazuh", timedelta(days=5))
        add(session, "wazuh", timedelta(days=2))
        add(session, "ntopng", timedelta(days=1))

        found = retention.stored(session)

        assert found == {
            "wazuh": retention.Stored(2, NOW - timedelta(days=5)),
            "ntopng": retention.Stored(1, NOW - timedelta(days=1)),
        }

    def test_nothing_stored_is_nothing(self, session: Session) -> None:
        assert retention.stored(session) == {}


class TestPurging:
    def test_events_past_the_default_are_deleted_and_the_rest_stay(
        self, session: Session, settings: Settings
    ) -> None:
        add(session, "wazuh", timedelta(days=31))
        add(session, "wazuh", timedelta(days=29))
        add(session, "ntopng", timedelta(days=45))

        purged = retention.purge_expired(session, settings, NOW)

        assert sources(session) == [("wazuh", 29)]
        # The one 31 days old shares its week with a newer event, so it is deleted; the 45 days
        # old one had a week of its own, which was dropped without counting its events.
        assert purged == retention.Purged(deleted=1, partitions_dropped=1)

    def test_a_source_with_its_own_period_is_held_to_it(
        self, session: Session, settings: Settings
    ) -> None:
        retention.set_days(session, "wazuh", 90)
        retention.set_days(session, "ntopng", 3)
        add(session, "wazuh", timedelta(days=60))
        add(session, "wazuh", timedelta(days=100))
        add(session, "ntopng", timedelta(days=2))
        add(session, "ntopng", timedelta(days=4))
        add(session, "opnsense", timedelta(days=29))
        add(session, "opnsense", timedelta(days=31))

        purged = retention.purge_expired(session, settings, NOW)

        assert sources(session) == [("ntopng", 2), ("opnsense", 29), ("wazuh", 60)]
        # Wazuh's 100 days old event is in a week that ended before its 90 days began.
        assert purged == retention.Purged(deleted=2, partitions_dropped=1)

    def test_a_week_that_ended_before_every_period_began_is_dropped_whole(
        self, session: Session, settings: Settings
    ) -> None:
        add(session, "wazuh", timedelta(days=100))
        add(session, "wazuh", timedelta(days=1))

        purged = retention.purge_expired(session, settings, NOW)

        assert partitions.existing(session) == [Partition(datetime(2026, 10, 19, tzinfo=UTC))]
        # It went with its table, so it wasn't deleted row by row.
        assert purged == retention.Purged(deleted=0, partitions_dropped=1)

    def test_a_week_holding_a_source_with_a_longer_period_is_kept(
        self, session: Session, settings: Settings
    ) -> None:
        retention.set_days(session, "wazuh", 365)
        add(session, "wazuh", timedelta(days=100))
        add(session, "ntopng", timedelta(days=100))

        purged = retention.purge_expired(session, settings, NOW)

        # The week stays for wazuh's sake, and ntopng's event in it is deleted.
        assert sources(session) == [("wazuh", 100)]
        assert purged == retention.Purged(deleted=1, partitions_dropped=0)

    def test_a_past_week_the_delete_emptied_is_dropped(
        self, session: Session, settings: Settings
    ) -> None:
        # Wazuh's long period keeps the old week from being dropped whole.
        retention.set_days(session, "wazuh", 365)
        add(session, "ntopng", timedelta(days=100))
        add(session, "wazuh", timedelta(days=1))

        purged = retention.purge_expired(session, settings, NOW)

        assert purged == retention.Purged(deleted=1, partitions_dropped=1)
        assert partitions.existing(session) == [Partition(datetime(2026, 10, 19, tzinfo=UTC))]

    def test_the_week_now_is_kept_even_when_it_is_empty(
        self, session: Session, settings: Settings
    ) -> None:
        add(session, "wazuh", timedelta(days=1))
        session.execute(delete(Event))

        retention.purge_expired(session, settings, NOW)

        assert partitions.existing(session) == [Partition(datetime(2026, 10, 19, tzinfo=UTC))]

    def test_a_week_ahead_is_not_dropped(self, session: Session, settings: Settings) -> None:
        partitions.ensure(session, [Partition(datetime(2026, 10, 26, tzinfo=UTC))])

        retention.purge_expired(session, settings, NOW)

        assert partitions.existing(session) == [Partition(datetime(2026, 10, 26, tzinfo=UTC))]

    def test_there_is_nothing_to_do_without_events(
        self, session: Session, settings: Settings
    ) -> None:
        assert retention.purge_expired(session, settings, NOW) == retention.Purged(0, 0)

    def test_what_it_did_is_committed(self, session: Session, settings: Settings) -> None:
        add(session, "wazuh", timedelta(days=40))
        session.commit()

        retention.purge_expired(session, settings, NOW)
        session.rollback()

        assert sources(session) == []

    def test_recording_and_purging_agree_about_what_is_old(
        self, session: Session, settings: Settings
    ) -> None:
        old = new_event(occurred_at=NOW - timedelta(days=29, hours=23))

        assert record(session, settings, [old], NOW) == 1
        retention.purge_expired(session, settings, NOW)
        assert len(sources(session)) == 1

        retention.purge_expired(session, settings, NOW + timedelta(hours=2))
        assert sources(session) == []
