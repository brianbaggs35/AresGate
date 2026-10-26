import dataclasses
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.events import retention
from app.events.event import NewEvent, Severity
from app.events.store import FUTURE_TOLERANCE, record, record_unseen
from app.models import Event
from app.partitions import EVENTS, Partition
from tests.helpers import new_event

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
THIS_WEEK = Partition("events", datetime(2026, 10, 19, tzinfo=UTC))


def stored(session: Session) -> list[Event]:
    session.expire_all()
    return list(session.scalars(select(Event).order_by(Event.occurred_at, Event.id)))


def test_an_event_is_stored_with_everything_about_it(session: Session, settings: Settings) -> None:
    event = new_event(
        occurred_at=NOW - timedelta(minutes=2),
        severity=Severity.HIGH,
        signature="ET SCAN Nmap",
        src_address="203.0.113.9",
        src_port=51514,
        dst_address="192.168.1.20",
        dst_port=22,
        protocol="TCP",
        raw={"rule": {"id": 5710}},
    )

    assert record(session, settings, [event], NOW) == 1
    session.commit()

    (row,) = stored(session)
    assert (row.source, row.connection, row.kind) == ("wazuh", "indexer", "alert")
    assert row.severity == Severity.HIGH
    assert row.summary == "sshd: authentication failed"
    assert row.signature == "ET SCAN Nmap"
    assert (row.src_address, row.src_port) == (IPv4Address("203.0.113.9"), 51514)
    assert (row.dst_address, row.dst_port) == (IPv4Address("192.168.1.20"), 22)
    assert row.protocol == "tcp"
    assert row.occurred_at == NOW - timedelta(minutes=2)
    assert row.received_at == NOW
    assert row.fingerprint == event.fingerprint
    assert row.raw == {"rule": {"id": 5710}}
    assert row.id > 0


def test_nothing_to_store_stores_nothing(session: Session, settings: Settings) -> None:
    assert record(session, settings, [], NOW) == 0
    assert EVENTS.existing(session) == []


def test_reading_the_same_event_again_stores_it_once(session: Session, settings: Settings) -> None:
    event = new_event(occurred_at=NOW)

    assert record(session, settings, [event, event], NOW) == 1
    assert record(session, settings, [event], NOW) == 0
    session.commit()

    assert len(stored(session)) == 1


def test_events_that_differ_are_each_stored(session: Session, settings: Settings) -> None:
    events = [
        new_event(occurred_at=NOW, identity=("a",)),
        new_event(occurred_at=NOW, identity=("b",)),
        new_event(occurred_at=NOW, identity=("a",), source="ntopng", connection="api"),
        new_event(occurred_at=NOW - timedelta(seconds=1), identity=("a",)),
    ]

    assert record(session, settings, events, NOW) == 4


def test_the_event_a_second_time_with_a_new_batch_is_still_skipped(
    session: Session, settings: Settings
) -> None:
    first = [new_event(occurred_at=NOW, identity=(index,)) for index in range(3)]
    second = [*first, new_event(occurred_at=NOW, identity=(3,))]

    assert record(session, settings, first, NOW) == 3
    assert record(session, settings, second, NOW) == 1


def test_a_week_gets_a_partition_when_its_first_event_arrives(
    session: Session, settings: Settings
) -> None:
    last_week = NOW - timedelta(days=7)
    events = [new_event(occurred_at=NOW), new_event(occurred_at=last_week, identity=("old",))]

    record(session, settings, events, NOW)
    session.commit()

    assert EVENTS.existing(session) == [
        Partition("events", THIS_WEEK.start - timedelta(days=7)),
        THIS_WEEK,
    ]


def test_a_later_batch_for_a_week_that_exists_makes_nothing_more(
    session: Session, settings: Settings
) -> None:
    record(session, settings, [new_event(occurred_at=NOW)], NOW)
    record(session, settings, [new_event(occurred_at=NOW, identity=("b",))], NOW)

    assert EVENTS.existing(session) == [THIS_WEEK]


def test_an_event_from_a_little_in_the_future_keeps_its_time(
    session: Session, settings: Settings
) -> None:
    ahead = NOW + FUTURE_TOLERANCE

    record(session, settings, [new_event(occurred_at=ahead)], NOW)

    assert [row.occurred_at for row in stored(session)] == [ahead]


def test_an_event_from_far_in_the_future_is_stored_as_of_now(
    session: Session, settings: Settings
) -> None:
    # A time years ahead mustn't make a week to hold it.
    record(session, settings, [new_event(occurred_at=datetime(2099, 1, 1, tzinfo=UTC))], NOW)

    assert [row.occurred_at for row in stored(session)] == [NOW]
    assert EVENTS.existing(session) == [THIS_WEEK]


def test_an_event_older_than_the_retention_period_is_not_stored(
    session: Session, settings: Settings
) -> None:
    days = settings.event_retention_days
    events = [
        new_event(occurred_at=NOW - timedelta(days=days, seconds=1), identity=("past",)),
        new_event(occurred_at=NOW - timedelta(days=days - 1), identity=("kept",)),
    ]

    assert record(session, settings, events, NOW) == 1
    assert [row.fingerprint for row in stored(session)] == [events[1].fingerprint]


def test_nothing_is_made_when_everything_is_too_old(session: Session, settings: Settings) -> None:
    old = new_event(occurred_at=NOW - timedelta(days=settings.event_retention_days + 5))

    assert record(session, settings, [old], NOW) == 0
    assert EVENTS.existing(session) == []


def test_each_source_is_held_to_its_own_retention_period(
    session: Session, settings: Settings
) -> None:
    retention.set_days(session, "wazuh", 2)
    retention.set_days(session, "ntopng", 90)
    session.flush()
    three_days = NOW - timedelta(days=3)
    events = [
        new_event(occurred_at=three_days, identity=("a",)),
        new_event(occurred_at=three_days, identity=("b",), source="ntopng", connection="api"),
        new_event(occurred_at=three_days, identity=("c",), source="crowdsec", connection="api"),
    ]

    record(session, settings, events, NOW)

    assert [row.source for row in stored(session)] == ["ntopng", "crowdsec"]


def test_the_count_is_of_the_new_events_across_batches_larger_than_one_statement(
    session: Session, settings: Settings
) -> None:
    events = [new_event(occurred_at=NOW, identity=(index,)) for index in range(2500)]

    assert record(session, settings, events, NOW) == 2500
    assert session.scalar(select(func.count()).select_from(Event)) == 2500


class TestRecordingWhatWasntSeen:
    def test_an_event_seen_before_is_skipped_whenever_it_was_dated(
        self, session: Session, settings: Settings
    ) -> None:
        ban = new_event(occurred_at=NOW, identity=("ban", 1))

        assert record_unseen(session, settings, [ban], NOW) == 1
        later = new_event(occurred_at=NOW + timedelta(minutes=1), identity=("ban", 1))
        assert record_unseen(session, settings, [later], NOW + timedelta(minutes=1)) == 0
        session.commit()

        assert [row.occurred_at for row in stored(session)] == [NOW]

    def test_events_that_differ_are_each_stored_and_only_the_new_ones_are_counted(
        self, session: Session, settings: Settings
    ) -> None:
        first = [new_event(occurred_at=NOW, identity=(number,)) for number in range(2)]
        later = NOW + timedelta(minutes=1)
        second = [new_event(occurred_at=later, identity=(number,)) for number in range(3)]
        other = new_event(occurred_at=later, identity=(0,), source="ntopng", connection="api")

        assert record_unseen(session, settings, first, NOW) == 2
        assert record_unseen(session, settings, [*second, other], later) == 2
        session.commit()

        assert len(stored(session)) == 4

    def test_nothing_to_store_stores_nothing(self, session: Session, settings: Settings) -> None:
        assert record_unseen(session, settings, [], NOW) == 0
        assert EVENTS.existing(session) == []

    def test_an_event_whose_stored_copy_is_past_its_retention_is_new_again(
        self, session: Session, settings: Settings
    ) -> None:
        ban = new_event(occurred_at=NOW, identity=("ban", 1))
        later = NOW + timedelta(days=settings.event_retention_days + 1)
        again = new_event(occurred_at=later, identity=("ban", 1))

        assert record_unseen(session, settings, [ban], NOW) == 1
        assert record_unseen(session, settings, [again], later) == 1

    def test_it_looks_back_over_the_retention_of_the_sources_in_the_batch(
        self, session: Session, settings: Settings
    ) -> None:
        retention.set_days(session, "wazuh", 2)
        retention.set_days(session, "ntopng", 90)
        session.flush()
        later = NOW + timedelta(days=60)
        first = [
            new_event(occurred_at=NOW, identity=("a",), source="ntopng", connection="api"),
            new_event(occurred_at=NOW, identity=("b",)),
        ]
        assert record_unseen(session, settings, first, NOW) == 2

        # Sixty days on, what ntopng kept for 90 days is still known, and what wazuh kept for 2
        # is not, wherever the old copy happens still to be.
        ntopng, wazuh = (replace_time(event, later) for event in first)
        assert record_unseen(session, settings, [wazuh], later) == 1
        assert record_unseen(session, settings, [ntopng], later) == 0

    def test_each_source_in_a_batch_is_looked_back_over_for_as_long_as_it_keeps_events(
        self, session: Session, settings: Settings
    ) -> None:
        retention.set_days(session, "wazuh", 2)
        retention.set_days(session, "ntopng", 90)
        session.flush()
        later = NOW + timedelta(days=60)
        first = [
            new_event(occurred_at=NOW, identity=("a",), source="ntopng", connection="api"),
            new_event(occurred_at=NOW, identity=("b",)),
        ]
        assert record_unseen(session, settings, first, NOW) == 2

        # In one batch, ntopng's copy is still known and wazuh's, kept for only 2 days, is not.
        assert record_unseen(session, settings, [replace_time(e, later) for e in first], later) == 1


def replace_time(event: NewEvent, occurred_at: datetime) -> NewEvent:
    return dataclasses.replace(event, occurred_at=occurred_at)
