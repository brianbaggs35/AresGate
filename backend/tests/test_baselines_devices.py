"""When a device that was not on the network before appears."""

from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.baselines import devices
from app.events.event import Severity
from app.models import Device, DeviceAddress, SystemInfo

NOW = datetime(2026, 11, 16, 12, 30, tzinfo=UTC)


def add_device(
    session: Session,
    number: int,
    *,
    age: timedelta = timedelta(days=30),
    hostname: str | None = None,
    vendor: str | None = None,
    address: str | None = None,
) -> Device:
    found = Device(
        mac=f"aa:bb:cc:00:00:{number:02x}",
        hostname=hostname,
        vendor=vendor,
        first_seen_at=NOW - age,
        last_seen_at=NOW,
    )
    session.add(found)
    session.flush()
    if address is not None:
        session.add(
            DeviceAddress(
                device_id=found.id,
                address=ip_address(address),
                first_seen_at=NOW - age,
                last_seen_at=NOW,
            )
        )
    session.commit()
    return found


def established(session: Session) -> None:
    """A network that has had four devices for a month, and has been looked at once."""
    for number in range(1, 5):
        add_device(session, number)
    assert devices.run(session, NOW - timedelta(minutes=5)) == []
    session.commit()


class TestTheFirstLook:
    def test_it_only_takes_note_of_the_devices_there_are(self, session: Session) -> None:
        add_device(session, 1, age=timedelta(minutes=1))

        assert devices.run(session, NOW) == []
        session.commit()

        assert session.scalar(select(SystemInfo.value).where(SystemInfo.key == devices.CURSOR_KEY))

    def test_it_has_nothing_to_note_on_a_network_with_no_devices(self, session: Session) -> None:
        assert devices.run(session, NOW) == []

        session.commit()
        value = session.scalar(select(SystemInfo.value).where(SystemInfo.key == devices.CURSOR_KEY))
        assert value == "0"


class TestANewDevice:
    def test_a_device_that_appears_is_a_deviation(self, session: Session) -> None:
        established(session)
        new = add_device(
            session,
            9,
            age=timedelta(minutes=3),
            hostname="espressif",
            vendor="Espressif",
            address="192.168.1.77",
        )

        [event] = devices.run(session, NOW)

        assert event.severity is Severity.LOW
        assert event.source == "baseline"
        assert event.src_address == "192.168.1.77"
        assert event.signature == "A new device"
        assert event.occurred_at == NOW
        assert event.summary == (
            "A device that has not been on the network before appeared: espressif."
        )
        assert event.raw is not None
        assert event.raw["device_id"] == new.id
        assert event.raw["confidence"] == devices.CONFIDENCE
        assert event.raw["mac"] == "aa:bb:cc:00:00:09"

    def test_it_is_called_by_its_maker_or_else_its_hardware_address(self, session: Session) -> None:
        established(session)
        add_device(session, 9, age=timedelta(minutes=3), vendor="Espressif")
        add_device(session, 10, age=timedelta(minutes=2))

        events = devices.run(session, NOW)

        assert [event.summary.rsplit(": ", 1)[1] for event in events] == [
            "Espressif device.",
            "aa:bb:cc:00:00:0a.",
        ]
        assert [event.src_address for event in events] == [None, None]

    def test_the_address_it_was_last_seen_at_is_the_one_named(self, session: Session) -> None:
        established(session)
        new = add_device(session, 9, age=timedelta(minutes=3), address="192.168.1.77")
        session.add(
            DeviceAddress(
                device_id=new.id,
                address=ip_address("192.168.1.88"),
                first_seen_at=NOW,
                last_seen_at=NOW + timedelta(minutes=1),
            )
        )
        session.commit()

        [event] = devices.run(session, NOW)

        assert event.src_address == "192.168.1.88"

    def test_a_device_is_said_once(self, session: Session) -> None:
        established(session)
        add_device(session, 9, age=timedelta(minutes=3))
        assert len(devices.run(session, NOW)) == 1
        session.commit()

        assert devices.run(session, NOW + timedelta(minutes=5)) == []

    def test_a_young_network_has_every_device_new_and_says_nothing(self, session: Session) -> None:
        for number in range(1, 5):
            add_device(session, number, age=timedelta(days=2))
        devices.run(session, NOW - timedelta(minutes=5))
        session.commit()
        add_device(session, 9, age=timedelta(minutes=3))

        assert devices.run(session, NOW) == []

    def test_a_network_with_few_devices_says_nothing(self, session: Session) -> None:
        add_device(session, 1)
        devices.run(session, NOW - timedelta(minutes=5))
        session.commit()
        add_device(session, 9, age=timedelta(minutes=3))

        assert devices.run(session, NOW) == []

    def test_a_device_listed_with_an_old_date_is_not_new(self, session: Session) -> None:
        established(session)
        add_device(session, 9, age=timedelta(days=20))

        assert devices.run(session, NOW) == []

    def test_a_device_that_appeared_while_it_was_not_established_is_not_said_later(
        self, session: Session
    ) -> None:
        add_device(session, 1, age=timedelta(days=2))
        devices.run(session, NOW - timedelta(minutes=10))
        session.commit()
        add_device(session, 9, age=timedelta(minutes=8))
        devices.run(session, NOW - timedelta(minutes=5))
        session.commit()
        for number in range(2, 5):
            add_device(session, number)

        assert devices.run(session, NOW) == []
