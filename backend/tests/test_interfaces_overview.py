from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import dashboard
from app.config import Settings
from app.events.event import Severity
from app.events.store import record as record_events
from app.interfaces import overview
from app.metrics.store import record as record_samples
from app.models import Device, DeviceAddress, Interface, InterfaceFeed, User
from tests.helpers import new_event, new_sample

BASE = "/api/interfaces/overview"
# A little after six in the evening, UTC.
NOW = datetime(2026, 10, 26, 18, 20, tzinfo=UTC)
WINDOW = dashboard.window("24h", NOW)
SECOND = timedelta(seconds=1)


def interface(session: Session, name: str = "Internet", **changes: object) -> Interface:
    fields: dict[str, object] = {"name": name, "role": "internet"} | changes
    made = Interface(**fields)
    session.add(made)
    session.commit()
    return made


def feed(
    session: Session,
    place: Interface | None,
    name: str = "igc0",
    **changes: object,
) -> InterfaceFeed:
    fields: dict[str, object] = {
        "integration": "opnsense",
        "connection": "api",
        "native_name": name,
        "interface_id": place.id if place else None,
    } | changes
    made = InterfaceFeed(**fields)
    session.add(made)
    session.commit()
    return made


def counters(
    session: Session,
    settings: Settings,
    source: str,
    port: str,
    bytes_in: int,
    bytes_out: int = 0,
) -> None:
    """Two readings of a port's counters a quarter of an hour apart, so that the second bucket
    has a speed: what came in and went out between them."""
    later = WINDOW.start + WINDOW.traffic_bucket + SECOND
    record_samples(
        session,
        settings,
        [
            new_sample(
                source=source,
                name=name,
                value=value,
                sampled_at=when,
                labels={"interface": port},
            )
            for name, total in (
                ("interface.bytes_in", bytes_in),
                ("interface.bytes_out", bytes_out),
            )
            for when, value in ((WINDOW.start + SECOND, 0), (later, total))
        ],
        NOW,
    )
    session.commit()


def alerts_on(
    session: Session,
    settings: Settings,
    count: int,
    *,
    source: str = "opnsense",
    connection: str = "api",
    port: str | None = "igc0",
    at: datetime = NOW,
) -> None:
    record_events(
        session,
        settings,
        [
            new_event(
                source=source,
                connection=connection,
                iface=port,
                occurred_at=at,
                severity=Severity.HIGH,
                identity=(source, connection, str(port), str(at), str(number)),
            )
            for number in range(count)
        ],
        NOW,
    )
    session.commit()


def device(session: Session, mac: str, *addresses: str) -> Device:
    made = Device(mac=mac, first_seen_at=NOW, last_seen_at=NOW)
    session.add(made)
    session.flush()
    for address in addresses:
        session.add(
            DeviceAddress(
                device_id=made.id,
                address=ip_address(address),
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
        )
    session.commit()
    return made


class TestWithNothingToShow:
    def test_nothing_is_nothing(self, session: Session) -> None:
        taken = overview.overview(session, WINDOW)

        assert taken.stats == []
        assert len(taken.times) == 96

    def test_an_interface_with_no_feeds_has_nothing_yet(self, session: Session) -> None:
        made = interface(session)

        [stats] = overview.overview(session, WINDOW).stats

        assert stats == overview.Stats(made.id, None, 0, 0, None, None)


class TestSpeed:
    def test_it_is_the_firewalls_counters_of_the_port_placed_on_the_interface(
        self, session: Session, settings: Settings
    ) -> None:
        made = interface(session)
        feed(session, made)
        counters(session, settings, "opnsense", "igc0", 900_000)
        counters(session, settings, "opnsense", "igc1", 123_456)

        [stats] = overview.overview(session, WINDOW).stats

        assert stats.speed is not None
        assert stats.speed.source == "opnsense"
        assert stats.speed.received[1] == 8_000.0
        assert stats.speed.received[0] is None
        assert stats.speed.sent[1] == 0.0

    def test_two_ports_on_one_interface_are_added_up(
        self, session: Session, settings: Settings
    ) -> None:
        made = interface(session)
        feed(session, made, "igc0")
        feed(session, made, "igc1")
        counters(session, settings, "opnsense", "igc0", 900_000)
        counters(session, settings, "opnsense", "igc1", 450_000)

        [stats] = overview.overview(session, WINDOW).stats

        assert stats.speed is not None
        assert stats.speed.received[1] == 12_000.0
        assert stats.speed.received[2] is None

    def test_a_bucket_one_port_has_and_the_other_has_not_is_that_ports_speed(self) -> None:
        assert overview.added([1.0, None, None], [None, 2.0, None]) == [1.0, 2.0, None]

    def test_the_firewall_is_preferred_to_ntopng_which_sees_the_same_traffic(
        self, session: Session, settings: Settings
    ) -> None:
        made = interface(session)
        feed(session, made, "igc0")
        feed(session, made, "eth0", integration="ntopng")
        counters(session, settings, "opnsense", "igc0", 900_000)
        counters(session, settings, "ntopng", "eth0", 90_000)

        [stats] = overview.overview(session, WINDOW).stats

        assert stats.speed is not None
        assert stats.speed.source == "opnsense"
        assert stats.speed.received[1] == 8_000.0

    def test_ntopng_is_used_when_the_firewall_measured_nothing_of_it(
        self, session: Session, settings: Settings
    ) -> None:
        made = interface(session)
        feed(session, made, "igc0")
        feed(session, made, "eth0", integration="ntopng")
        counters(session, settings, "ntopng", "eth0", 90_000)

        [stats] = overview.overview(session, WINDOW).stats

        assert stats.speed is not None
        assert stats.speed.source == "ntopng"
        assert stats.speed.received[1] == 800.0

    def test_a_port_that_was_not_measured_has_no_speed(
        self, session: Session, settings: Settings
    ) -> None:
        made = interface(session)
        feed(session, made, "igc0")
        counters(session, settings, "opnsense", "igc9", 900_000)

        [stats] = overview.overview(session, WINDOW).stats

        assert stats.speed is None

    def test_a_feed_that_is_a_whole_connection_names_no_port_to_measure(
        self, session: Session, settings: Settings
    ) -> None:
        made = interface(session)
        feed(session, made, "", integration="crowdsec", connection="lapi")
        counters(session, settings, "opnsense", "igc0", 900_000)

        [stats] = overview.overview(session, WINDOW).stats

        assert stats.speed is None

    def test_a_port_placed_on_another_interface_is_not_counted(
        self, session: Session, settings: Settings
    ) -> None:
        mine = interface(session, "Internet")
        other = interface(session, "Guests", role="guest")
        feed(session, mine, "igc0")
        feed(session, other, "igc1")
        counters(session, settings, "opnsense", "igc0", 900_000)
        counters(session, settings, "opnsense", "igc1", 90_000)

        first, second = overview.overview(session, WINDOW).stats

        assert first.speed is not None
        assert first.speed.received[1] == 8_000.0
        assert second.speed is not None
        assert second.speed.received[1] == 800.0


class TestAlerts:
    def test_alerts_are_counted_on_the_interface_their_port_was_placed_on(
        self, session: Session, settings: Settings
    ) -> None:
        made = interface(session)
        feed(session, made, "igc0")
        alerts_on(session, settings, 3)
        alerts_on(session, settings, 2, port="igc1")

        [stats] = overview.overview(session, WINDOW).stats

        assert stats.alerts == 3
        assert stats.alerts_previous == 0

    def test_those_of_the_window_before_are_counted_apart(
        self, session: Session, settings: Settings
    ) -> None:
        made = interface(session)
        feed(session, made, "igc0")
        alerts_on(session, settings, 1)
        alerts_on(session, settings, 4, at=WINDOW.start - timedelta(hours=3))

        [stats] = overview.overview(session, WINDOW).stats

        assert (stats.alerts, stats.alerts_previous) == (1, 4)

    def test_an_alert_from_a_program_that_names_no_port_goes_with_its_whole_connection(
        self, session: Session, settings: Settings
    ) -> None:
        made = interface(session)
        feed(session, made, "", integration="wazuh", connection="indexer")
        alerts_on(session, settings, 2, source="wazuh", connection="indexer", port=None)

        [stats] = overview.overview(session, WINDOW).stats

        assert stats.alerts == 2

    def test_what_was_set_aside_or_never_placed_is_counted_nowhere(
        self, session: Session, settings: Settings
    ) -> None:
        interface(session)
        feed(session, None, "igc0", ignored=True)
        feed(session, None, "igc1")
        alerts_on(session, settings, 2, port="igc0")
        alerts_on(session, settings, 2, port="igc1")
        alerts_on(session, settings, 2, port="igc7")

        [stats] = overview.overview(session, WINDOW).stats

        assert stats.alerts == 0

    def test_only_alerts_are_counted(self, session: Session, settings: Settings) -> None:
        made = interface(session)
        feed(session, made, "igc0")
        record_events(
            session,
            settings,
            [
                new_event(
                    source="opnsense",
                    connection="api",
                    iface="igc0",
                    kind="firewall",
                    occurred_at=NOW,
                )
            ],
            NOW,
        )
        session.commit()

        [stats] = overview.overview(session, WINDOW).stats

        assert stats.alerts == 0


class TestDevices:
    def test_they_are_the_devices_with_an_address_on_the_networks(self, session: Session) -> None:
        interface(session, networks=["192.168.1.0/24", "fd00::/64"])
        device(session, "00:00:5e:00:53:01", "192.168.1.20", "192.168.1.21")
        device(session, "00:00:5e:00:53:02", "fd00::7")
        device(session, "00:00:5e:00:53:03", "10.0.0.5")

        [stats] = overview.overview(session, WINDOW).stats

        assert stats.devices == 2

    def test_with_no_networks_there_is_nowhere_to_look(self, session: Session) -> None:
        interface(session)
        device(session, "00:00:5e:00:53:01", "192.168.1.20")

        [stats] = overview.overview(session, WINDOW).stats

        assert stats.devices is None

    def test_a_network_with_no_devices_has_none(self, session: Session) -> None:
        interface(session, networks=["192.168.9.0/24"])

        [stats] = overview.overview(session, WINDOW).stats

        assert stats.devices == 0


class TestLastReport:
    def test_it_is_the_latest_of_its_feeds(self, session: Session) -> None:
        made = interface(session)
        feed(session, made, "igc0", last_seen_at=NOW - timedelta(hours=3))
        feed(session, made, "igc1", last_seen_at=NOW - timedelta(minutes=2))
        feed(session, None, "igc2", last_seen_at=NOW)

        [stats] = overview.overview(session, WINDOW).stats

        assert stats.last_seen_at == NOW - timedelta(minutes=2)


class TestTheApi:
    def test_it_is_only_for_someone_signed_in(self, client: TestClient, account: User) -> None:
        assert client.get(BASE).status_code == 401

    def test_an_install_with_no_interfaces_has_an_empty_overview(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = client.get(BASE).json()

        assert body["window"] == "24h"
        assert len(body["times"]) == 96
        assert body["stats"] == []

    def test_a_week_is_cut_into_hours(self, client: TestClient, csrf_token: str) -> None:
        body = client.get(BASE, params={"window": "7d"}).json()

        assert body["window"] == "7d"
        assert len(body["times"]) == 168

    def test_a_window_nobody_offers_is_refused(self, client: TestClient, csrf_token: str) -> None:
        assert client.get(BASE, params={"window": "30d"}).status_code == 422

    def test_each_interface_has_its_numbers_and_the_program_that_measured_its_speed(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        made = interface(session, networks=["192.168.1.0/24"])
        feed(session, made, "igc0")
        win = dashboard.window("24h", datetime.now(UTC))
        quarter = win.traffic_bucket
        record_samples(
            session,
            settings,
            [
                new_sample(
                    name="interface.bytes_in",
                    value=value,
                    sampled_at=win.start + quarter + offset * SECOND,
                    labels={"interface": "igc0"},
                )
                for offset, value in ((1, 0.0), (901, 900_000.0))
            ],
            datetime.now(UTC),
        )
        session.commit()
        device(session, "00:00:5e:00:53:01", "192.168.1.20")

        [stats] = client.get(BASE).json()["stats"]

        assert stats["interface_id"] == made.id
        assert stats["speed"]["source"] == "opnsense"
        assert stats["speed"]["source_name"] == "OPNsense"
        assert 8_000.0 in stats["speed"]["received"]
        assert stats["alerts"] == 0
        assert stats["devices"] == 1
        assert stats["last_seen_at"] is not None

    def test_an_interface_with_nothing_measured_says_so(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        made = interface(session)

        [stats] = client.get(BASE).json()["stats"]

        assert stats == {
            "interface_id": made.id,
            "speed": None,
            "alerts": 0,
            "alerts_previous": 0,
            "devices": None,
            "last_seen_at": None,
        }
