from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

from sqlalchemy.orm import Session

from app import dashboard
from app.config import Settings
from app.events.event import NewEvent, Severity
from app.events.store import record as record_events
from app.metrics.store import record as record_samples
from app.models import Device
from tests.helpers import new_event, new_sample

# A little after six in the evening, UTC.
NOW = datetime(2026, 10, 26, 18, 20, tzinfo=UTC)
HOUR = timedelta(hours=1)


def blocked_event(address: str, at: datetime, identity: str, **changes: object) -> NewEvent:
    return new_event(
        **{
            "source": "opnsense",
            "connection": "api",
            "kind": "firewall",
            "severity": Severity.LOW,
            "src_address": address,
            "occurred_at": at,
            "identity": (identity,),
            **changes,
        }
    )


def alert(severity: Severity, at: datetime, identity: str, **changes: object) -> NewEvent:
    return new_event(severity=severity, occurred_at=at, identity=(identity,), **changes)


def store(session: Session, settings: Settings, *events: NewEvent) -> None:
    record_events(session, settings, list(events), NOW)
    session.commit()


class TestWindows:
    def test_a_day_ends_with_the_hour_that_is_filling_and_is_cut_into_hours(self) -> None:
        win = dashboard.window("24h", NOW)

        assert win.end == datetime(2026, 10, 26, 19, 0, tzinfo=UTC)
        assert win.start == datetime(2026, 10, 25, 19, 0, tzinfo=UTC)
        assert win.previous_start == datetime(2026, 10, 24, 19, 0, tzinfo=UTC)
        buckets = win.buckets()
        assert len(buckets) == 24
        assert buckets[0] == win.start
        assert buckets[-1] == datetime(2026, 10, 26, 18, 0, tzinfo=UTC)
        # The traffic is cut finer.
        assert len(win.buckets(win.traffic_bucket)) == 96

    def test_a_week_is_cut_into_quarters_of_a_day(self) -> None:
        win = dashboard.window("7d", NOW)

        assert win.end == datetime(2026, 10, 27, 0, 0, tzinfo=UTC)
        assert win.length == timedelta(days=7)
        assert len(win.buckets()) == 28
        assert len(win.buckets(win.traffic_bucket)) == 168

    def test_a_moment_that_is_on_a_bucket_ends_its_window_there(self) -> None:
        on_the_hour = datetime(2026, 10, 26, 18, 0, tzinfo=UTC)

        assert dashboard.window("24h", on_the_hour).end == on_the_hour

    def test_there_are_two_windows(self) -> None:
        assert dashboard.WINDOWS == ("24h", "7d")


class TestAlerts:
    def test_they_are_counted_by_severity_and_by_hour(
        self, session: Session, settings: Settings
    ) -> None:
        win = dashboard.window("24h", NOW)
        store(
            session,
            settings,
            alert(Severity.HIGH, NOW - timedelta(minutes=5), "a"),
            alert(Severity.HIGH, NOW - timedelta(minutes=30), "b"),
            alert(Severity.LOW, NOW - timedelta(minutes=40), "c"),
            alert(Severity.CRITICAL, NOW - timedelta(hours=5, minutes=10), "d"),
        )

        found = dashboard.alerts(session, win)

        assert found.total == 4
        assert found.highest == Severity.CRITICAL
        assert len(found.by_severity[Severity.HIGH]) == 24
        assert found.by_severity[Severity.HIGH][23] == 1
        assert found.by_severity[Severity.HIGH][22] == 1
        assert found.by_severity[Severity.LOW][22] == 1
        assert found.by_severity[Severity.CRITICAL][18] == 1
        assert sum(found.by_severity[Severity.INFO]) == 0
        assert [level for level, counts in found.by_severity.items() if any(counts)] == [
            Severity.LOW,
            Severity.HIGH,
            Severity.CRITICAL,
        ]

    def test_the_window_before_it_is_counted_for_comparison_and_older_ones_are_not(
        self, session: Session, settings: Settings
    ) -> None:
        win = dashboard.window("24h", NOW)
        store(
            session,
            settings,
            alert(Severity.LOW, NOW - timedelta(hours=1), "now"),
            alert(Severity.LOW, win.start - timedelta(minutes=1), "before-1"),
            alert(Severity.LOW, win.start - timedelta(hours=23), "before-2"),
            alert(Severity.LOW, win.start - timedelta(hours=30), "too-old"),
        )

        found = dashboard.alerts(session, win)

        assert (found.total, found.previous) == (1, 2)

    def test_only_alerts_are_alerts(self, session: Session, settings: Settings) -> None:
        win = dashboard.window("24h", NOW)
        store(
            session,
            settings,
            blocked_event("203.0.113.9", NOW - HOUR, "firewall"),
            new_event(kind="decision", severity=Severity.HIGH, occurred_at=NOW, identity=("d",)),
        )

        found = dashboard.alerts(session, win)

        assert found.total == 0
        assert found.highest is None

    def test_with_none_everything_is_zero(self, session: Session) -> None:
        found = dashboard.alerts(session, dashboard.window("7d", NOW))

        assert (found.total, found.previous, found.highest) == (0, 0, None)
        assert found.by_severity[Severity.HIGH] == [0] * 28

    def test_the_latest_come_first_and_only_so_many(
        self, session: Session, settings: Settings
    ) -> None:
        win = dashboard.window("24h", NOW)
        store(
            session,
            settings,
            *[
                alert(Severity.MEDIUM, NOW - timedelta(minutes=number), f"a{number}")
                for number in range(1, 13)
            ],
            alert(Severity.HIGH, win.start - HOUR, "outside"),
            blocked_event("203.0.113.9", NOW, "not-an-alert"),
        )

        latest = dashboard.recent_alerts(session, win)

        assert len(latest) == dashboard.RECENT_ALERTS
        assert [(NOW - event.occurred_at).seconds // 60 for event in latest] == list(range(1, 9))
        assert len(dashboard.recent_alerts(session, win, limit=3)) == 3


class TestBlocked:
    def test_only_what_the_firewall_refused_counts(
        self, session: Session, settings: Settings
    ) -> None:
        win = dashboard.window("24h", NOW)
        passed = blocked_event("198.51.100.4", NOW - HOUR, "pass", severity=Severity.INFO)
        store(
            session,
            settings,
            blocked_event("203.0.113.9", NOW - timedelta(minutes=10), "b1"),
            blocked_event("203.0.113.9", NOW - timedelta(minutes=20), "b2"),
            blocked_event("203.0.113.10", NOW - timedelta(hours=3, minutes=5), "b3"),
            blocked_event("203.0.113.10", win.start - timedelta(hours=2), "b4"),
            passed,
            alert(Severity.HIGH, NOW - HOUR, "not-a-block"),
        )

        found = dashboard.blocked(session, win)

        assert (found.total, found.previous) == (3, 1)
        assert found.per_bucket[23] == 2
        assert found.per_bucket[20] == 1
        assert sum(found.per_bucket) == 3

    def test_the_most_refused_addresses_come_first(
        self, session: Session, settings: Settings
    ) -> None:
        win = dashboard.window("24h", NOW)
        store(
            session,
            settings,
            *[
                blocked_event("203.0.113.9", NOW - timedelta(minutes=n), f"x{n}")
                for n in range(1, 4)
            ],
            *[
                blocked_event("198.51.100.4", NOW - timedelta(minutes=n), f"y{n}")
                for n in range(1, 4)
            ],
            blocked_event("192.0.2.1", NOW - timedelta(minutes=1), "z1"),
            blocked_event("2001:db8::1", NOW - timedelta(minutes=1), "z2"),
            blocked_event("2001:db8::1", NOW - timedelta(minutes=2), "z3"),
            blocked_event("203.0.113.77", win.start - HOUR, "old"),
            new_event(
                source="opnsense",
                connection="api",
                kind="firewall",
                severity=Severity.LOW,
                occurred_at=NOW,
                identity=("no-address",),
            ),
            alert(Severity.HIGH, NOW, "alert", src_address="203.0.113.9"),
        )

        top = dashboard.top_blocked_sources(session, win)

        assert [(str(item.address), item.count) for item in top] == [
            ("198.51.100.4", 3),
            ("203.0.113.9", 3),
            ("2001:db8::1", 2),
            ("192.0.2.1", 1),
        ]
        assert top[0].address == ip_address("198.51.100.4")
        assert len(dashboard.top_blocked_sources(session, win, limit=2)) == 2


class TestTraffic:
    SECOND = timedelta(seconds=1)

    def counters(
        self,
        session: Session,
        settings: Settings,
        readings: list[tuple[datetime, float]],
        *,
        interface: str = "igc0",
        name: str = "interface.bytes_in",
        source: str = "opnsense",
    ) -> None:
        record_samples(
            session,
            settings,
            [
                new_sample(
                    source=source,
                    name=name,
                    value=value,
                    sampled_at=at,
                    labels={"interface": interface},
                )
                for at, value in readings
            ],
            NOW,
        )
        session.commit()

    def test_a_speed_is_the_bytes_between_the_last_readings_of_two_buckets_over_their_time(
        self, session: Session, settings: Settings
    ) -> None:
        win = dashboard.window("24h", NOW)
        quarter = win.traffic_bucket
        last = win.start + 60 * quarter
        before = last - quarter
        self.counters(
            session,
            settings,
            [
                (before + 14 * self.SECOND, 1_000),
                (before + 59 * self.SECOND, 1_500),
                (last + 30 * self.SECOND, 1_500 + 56_250_000),
                # A megabit a second over the 900 seconds since the last reading before it.
                (last + 59 * self.SECOND, 1_500 + 112_500_000),
            ],
        )

        (found,) = dashboard.traffic(session, win)

        assert found.interface == "igc0"
        count = len(win.buckets(quarter))
        assert len(found.received) == count == len(found.sent)
        assert found.received[60] == 1_000_000
        # The bucket before has nothing before it to compare with, and the sent counter was
        # not read at all.
        assert [index for index, speed in enumerate(found.received) if speed is not None] == [60]
        assert all(speed is None for speed in found.sent)
        assert found.bytes == 1_000_000 * 900 / 8

    def test_it_starts_from_a_reading_before_the_window(
        self, session: Session, settings: Settings
    ) -> None:
        win = dashboard.window("24h", NOW)
        quarter = win.traffic_bucket
        self.counters(
            session,
            settings,
            [
                (win.start - 60 * self.SECOND, 1_000),
                (win.start + 540 * self.SECOND, 1_000 + 540 * 1_000),
            ],
        )

        (found,) = dashboard.traffic(session, win)

        assert found.received[0] == (540 * 1_000) * 8 / 600
        assert found.received[1] is None
        assert quarter == timedelta(minutes=15)

    def test_a_counter_that_goes_back_is_a_gap_and_not_a_speed(
        self, session: Session, settings: Settings
    ) -> None:
        win = dashboard.window("24h", NOW)
        quarter = win.traffic_bucket
        start = win.start + quarter * 10
        self.counters(
            session,
            settings,
            [
                (start, 9_000_000),
                (start + quarter, 12_000_000),
                (start + 2 * quarter, 500),
                (start + 3 * quarter, 125_500),
            ],
        )

        (found,) = dashboard.traffic(session, win)

        assert found.received[11] == 3_000_000 * 8 / quarter.total_seconds()
        assert found.received[12] is None
        assert found.received[13] == 125_000 * 8 / quarter.total_seconds()

    def test_a_bucket_with_no_reading_before_it_has_no_speed(
        self, session: Session, settings: Settings
    ) -> None:
        win = dashboard.window("24h", NOW)
        quarter = win.traffic_bucket
        start = win.start + quarter * 10
        self.counters(session, settings, [(start, 1_000), (start + 2 * quarter, 9_000_000)])

        (found,) = dashboard.traffic(session, win)

        assert all(speed is None for speed in found.received)

    def test_received_and_sent_and_each_interface_are_apart_with_the_busiest_first(
        self, session: Session, settings: Settings
    ) -> None:
        win = dashboard.window("24h", NOW)
        quarter = win.traffic_bucket
        at = win.start + quarter * 20
        for interface, rate in (("igc0", 1_000), ("igc1", 9_000)):
            for name, factor in (("interface.bytes_in", 1), ("interface.bytes_out", 2)):
                self.counters(
                    session,
                    settings,
                    [(at, 0), (at + quarter, rate * factor * 900)],
                    interface=interface,
                    name=name,
                )

        found = dashboard.traffic(session, win)

        assert [item.interface for item in found] == ["igc1", "igc0"]
        assert found[0].received[21] == 9_000 * 8
        assert found[0].sent[21] == 18_000 * 8
        assert found[1].received[21] == 1_000 * 8

    def test_only_the_firewalls_own_counters_are_used(
        self, session: Session, settings: Settings
    ) -> None:
        win = dashboard.window("24h", NOW)
        quarter = win.traffic_bucket
        at = win.start + quarter * 20
        self.counters(session, settings, [(at, 0), (at + quarter, 9_000)], source="ntopng")
        self.counters(
            session,
            settings,
            [(at, 0), (at + quarter, 9_000)],
            name="interface.packets_in",
        )

        assert dashboard.traffic(session, win) == []

    def test_a_series_without_an_interface_is_still_told_apart(
        self, session: Session, settings: Settings
    ) -> None:
        win = dashboard.window("24h", NOW)
        quarter = win.traffic_bucket
        at = win.start + quarter * 20
        record_samples(
            session,
            settings,
            [
                new_sample(name="interface.bytes_in", value=0, sampled_at=at),
                new_sample(name="interface.bytes_in", value=900, sampled_at=at + quarter),
            ],
            NOW,
        )
        session.commit()

        (found,) = dashboard.traffic(session, win)

        assert found.interface == ""
        assert found.received[21] == 8

    def test_with_nothing_read_there_is_nothing(self, session: Session) -> None:
        assert dashboard.traffic(session, dashboard.window("24h", NOW)) == []


class TestDevices:
    def test_it_counts_all_and_those_first_seen_in_the_window(self, session: Session) -> None:
        win = dashboard.window("24h", NOW)
        for number, first in enumerate(
            [NOW - HOUR, NOW - timedelta(hours=20), win.start - HOUR, win.start - timedelta(days=9)]
        ):
            session.add(
                Device(mac=f"aa:bb:cc:00:00:0{number}", first_seen_at=first, last_seen_at=NOW)
            )
        session.commit()

        found = dashboard.devices(session, win)

        assert (found.total, found.new) == (4, 2)

    def test_with_none_there_are_none(self, session: Session) -> None:
        found = dashboard.devices(session, dashboard.window("24h", NOW))

        assert (found.total, found.new) == (0, 0)
