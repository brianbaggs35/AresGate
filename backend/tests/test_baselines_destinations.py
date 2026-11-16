"""Where the devices on the network talk to, and when one talks somewhere it never has."""

from datetime import UTC, datetime, timedelta
from ipaddress import ip_address, ip_network

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.baselines import destinations
from app.config import Settings
from app.events.event import NewEvent, Severity
from app.events.store import record
from app.models import Event, KnownDestination, SystemInfo
from tests.helpers import new_event

NOW = datetime(2026, 11, 16, 12, 30, tzinfo=UTC)
CLIENT = "192.168.1.20"


def talk(
    session: Session,
    settings: Settings,
    to: str,
    *,
    port: int | None = 443,
    client: str = CLIENT,
    at: datetime = NOW - timedelta(minutes=2),
    kind: str = "firewall",
    stored: datetime | None = None,
    name: str | None = None,
) -> None:
    """An outbound connection a program saw, stored a minute or so ago."""
    record(
        session,
        settings,
        [
            new_event(
                source="opnsense",
                connection="api",
                kind=kind,
                severity=Severity.INFO,
                occurred_at=at,
                identity=(name or f"{client}-{to}-{port}-{at.isoformat()}",),
                src_address=client,
                dst_address=to,
                dst_port=port,
                summary="pass",
            )
        ],
        stored or NOW - timedelta(minutes=1),
    )
    session.commit()


def known_for(session: Session, client: str = CLIENT) -> list[KnownDestination]:
    session.expire_all()
    return list(
        session.scalars(
            select(KnownDestination)
            .where(KnownDestination.client == ip_address(client))
            .order_by(KnownDestination.network, KnownDestination.port)
        )
    )


def watched_device(session: Session, client: str = CLIENT, places: int = 25) -> None:
    """A device that has been learned about for ten days and talks to twenty-five places."""
    began = NOW - timedelta(days=10)
    session.add_all(
        KnownDestination(
            client=ip_address(client),
            network=ip_network(f"198.51.{index}.0/24"),
            port=443,
            first_seen_at=began,
            last_seen_at=NOW - timedelta(days=1),
            hits=5,
        )
        for index in range(places)
    )
    session.commit()


def stored_like(event: NewEvent, minutes: int) -> Event:
    """The event as it is when it has been stored, `minutes` minutes after ten before now."""
    return Event(
        occurred_at=NOW - timedelta(minutes=10 - minutes),
        source=event.source,
        connection=event.connection,
        kind=event.kind,
        severity=int(event.severity),
        summary=event.summary,
        src_address=ip_address(event.src_address) if event.src_address else None,
        dst_address=ip_address(event.dst_address) if event.dst_address else None,
        dst_port=event.dst_port,
        fingerprint=str(minutes),
    )


class TestWhatCountsAsADestination:
    def test_a_place_is_a_24_or_a_64_and_a_port(self) -> None:
        assert destinations.network_of(ip_address("93.184.216.77")) == ip_network("93.184.216.0/24")
        assert destinations.network_of(ip_address("2606:4700:1:2:3::4")) == ip_network(
            "2606:4700:1:2::/64"
        )

    def test_a_device_on_the_network_is_a_private_address_that_says_who_it_is(self) -> None:
        assert destinations.is_inside(ip_address("192.168.1.5"))
        assert destinations.is_inside(ip_address("fd00::5"))
        assert not destinations.is_inside(ip_address("8.8.8.8"))
        assert not destinations.is_inside(ip_address("169.254.1.1"))
        assert not destinations.is_inside(ip_address("0.0.0.0"))  # noqa: S104  # nosec B104

    def test_only_what_goes_from_a_device_to_the_internet_is_a_destination(self) -> None:
        events = [
            new_event(src_address="192.168.1.5", dst_address="93.184.216.7", dst_port=443),
            new_event(src_address="192.168.1.5", dst_address="93.184.216.8", dst_port=443),
            new_event(src_address="93.184.216.7", dst_address="192.168.1.5", dst_port=22),
            new_event(src_address="192.168.1.5", dst_address="192.168.1.6", dst_port=22),
            new_event(src_address="192.168.1.5", dst_address=None),
            new_event(src_address="192.168.1.5", dst_address="93.184.216.9", dst_port=None),
        ]
        stored = [stored_like(event, minutes) for minutes, event in enumerate(events)]

        places = destinations._outbound(stored)  # pyright: ignore[reportPrivateUsage]

        assert sorted((str(client), str(network), port) for client, network, port in places) == [
            ("192.168.1.5", "93.184.216.0/24", 0),
            ("192.168.1.5", "93.184.216.0/24", 443),
        ]
        seen = places[(ip_address("192.168.1.5"), ip_network("93.184.216.0/24"), 443)]
        assert seen.hits == 2
        assert (seen.first, seen.last) == (stored[0].occurred_at, stored[1].occurred_at)


class TestLearning:
    def test_a_new_device_only_learns(self, session: Session, settings: Settings) -> None:
        talk(session, settings, "93.184.216.7")
        talk(session, settings, "93.184.216.200", port=80)

        assert destinations.run(session, NOW) == []
        session.commit()

        rows = known_for(session)
        assert [(str(row.network), row.port) for row in rows] == [
            ("93.184.216.0/24", 80),
            ("93.184.216.0/24", 443),
        ]
        assert rows[0].hits == 1

    def test_what_is_seen_again_adds_to_what_is_known_without_moving_when_it_began(
        self, session: Session, settings: Settings
    ) -> None:
        talk(
            session,
            settings,
            "93.184.216.7",
            at=NOW - timedelta(minutes=30),
            stored=NOW - timedelta(minutes=10),
        )
        destinations.run(session, NOW - timedelta(minutes=5))
        session.commit()
        first = known_for(session)[0].first_seen_at
        talk(session, settings, "93.184.216.9", at=NOW - timedelta(minutes=2))

        destinations.run(session, NOW)
        session.commit()

        [row] = known_for(session)
        assert row.hits == 2
        assert row.first_seen_at == first == NOW - timedelta(minutes=30)
        assert row.last_seen_at == NOW - timedelta(minutes=2)

    def test_it_reads_what_it_has_not_read_and_remembers_where_it_got_to(
        self, session: Session, settings: Settings
    ) -> None:
        talk(session, settings, "93.184.216.7")
        destinations.run(session, NOW)
        session.commit()

        destinations.run(session, NOW)
        session.commit()

        assert known_for(session)[0].hits == 1
        assert session.scalar(select(func.count()).select_from(SystemInfo)) == 1

    def test_what_was_stored_a_moment_ago_waits_for_the_next_run(
        self, session: Session, settings: Settings
    ) -> None:
        talk(session, settings, "93.184.216.7", stored=NOW - timedelta(seconds=5))

        destinations.run(session, NOW)

        assert known_for(session) == []

    def test_only_connections_are_read(self, session: Session, settings: Settings) -> None:
        talk(session, settings, "93.184.216.7", kind="alert")

        destinations.run(session, NOW)

        assert known_for(session) == []

    def test_places_not_visited_for_a_long_time_are_forgotten(
        self, session: Session, settings: Settings
    ) -> None:
        watched_device(session, places=2)
        session.add(
            KnownDestination(
                client=ip_address(CLIENT),
                network=ip_network("192.0.2.0/24"),
                port=22,
                first_seen_at=NOW - timedelta(days=200),
                last_seen_at=NOW - timedelta(days=100),
                hits=1,
            )
        )
        session.commit()

        destinations.run(session, NOW)
        session.commit()

        assert "192.0.2.0/24" not in {str(row.network) for row in known_for(session)}
        assert len(known_for(session)) == 2


class TestWhatIsNew:
    def test_a_device_that_reaches_somewhere_new_is_a_deviation(
        self, session: Session, settings: Settings
    ) -> None:
        watched_device(session)
        talk(session, settings, "93.184.216.7", port=8443)

        [event] = destinations.run(session, NOW)

        assert event.severity is Severity.LOW
        assert event.src_address == CLIENT
        assert event.dst_address is None
        assert event.signature == "A device reached somewhere new"
        assert event.summary == (
            "192.168.1.20 reached 1 place it never has: 93.184.216.0/24 port 8443. "
            "It is known to talk to 25 others."
        )
        assert event.raw is not None
        assert event.raw["confidence"] == 35
        assert event.raw["new_places"] == [{"network": "93.184.216.0/24", "port": 8443}]

    def test_a_place_it_has_been_to_is_not(self, session: Session, settings: Settings) -> None:
        watched_device(session)
        talk(session, settings, "198.51.3.99", port=443)

        assert destinations.run(session, NOW) == []

    def test_a_known_place_on_a_new_port_is(self, session: Session, settings: Settings) -> None:
        watched_device(session)
        talk(session, settings, "198.51.3.99", port=22)

        [event] = destinations.run(session, NOW)

        assert "198.51.3.0/24 port 22" in event.summary

    def test_a_device_reaching_many_places_at_once_is_a_more_serious_deviation(
        self, session: Session, settings: Settings
    ) -> None:
        watched_device(session)
        for index in range(12):
            talk(session, settings, f"52.{index}.0.7", port=22)

        [event] = destinations.run(session, NOW)

        assert event.severity is Severity.MEDIUM
        assert "reached 12 places it never has" in event.summary
        assert "and 9 more" in event.summary
        assert event.summary.count("port 22") == 3
        assert event.raw is not None
        assert event.raw["new_count"] == 12
        assert event.raw["confidence"] == 90

    def test_a_connection_without_a_port_is_said_without_one(
        self, session: Session, settings: Settings
    ) -> None:
        watched_device(session)
        talk(session, settings, "93.184.216.7", port=None)

        [event] = destinations.run(session, NOW)

        assert "93.184.216.0/24." in event.summary
        assert "port" not in event.summary

    def test_a_device_not_yet_watched_for_a_week_is_not_judged(
        self, session: Session, settings: Settings
    ) -> None:
        watched_device(session)
        session.execute(update(KnownDestination).values(first_seen_at=NOW - timedelta(days=3)))
        session.commit()
        talk(session, settings, "93.184.216.7")

        assert destinations.run(session, NOW) == []

    def test_a_device_that_talks_to_few_places_is_not_judged(
        self, session: Session, settings: Settings
    ) -> None:
        watched_device(session, places=5)
        talk(session, settings, "93.184.216.7")

        assert destinations.run(session, NOW) == []

    def test_what_happened_before_the_last_hour_only_teaches(
        self, session: Session, settings: Settings
    ) -> None:
        watched_device(session)
        talk(session, settings, "93.184.216.7", at=NOW - timedelta(hours=3))

        assert destinations.run(session, NOW) == []
        session.commit()
        assert "93.184.216.0/24" in {str(row.network) for row in known_for(session)}

    def test_each_device_has_its_own_places(self, session: Session, settings: Settings) -> None:
        watched_device(session)
        talk(session, settings, "198.51.3.99", client="192.168.1.30")

        assert destinations.run(session, NOW) == []

    def test_a_place_is_new_to_a_device_only_once(
        self, session: Session, settings: Settings
    ) -> None:
        watched_device(session)
        talk(session, settings, "93.184.216.7")
        assert len(destinations.run(session, NOW)) == 1
        session.commit()
        talk(session, settings, "93.184.216.9", at=NOW - timedelta(minutes=1))

        assert destinations.run(session, NOW) == []

    def test_ipv6_places_are_64s(self, session: Session, settings: Settings) -> None:
        watched_device(session, client="fd00::20")
        talk(session, settings, "2606:4700:5:6::1", client="fd00::20")

        [event] = destinations.run(session, NOW)

        assert "2606:4700:5:6::/64 port 443" in event.summary
