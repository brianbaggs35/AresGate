"""Which device Fingerbank is asked about next, and whether a request may go now."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fingerbank import queue, store
from app.fingerbank.lookup import Identified, Identity, Unknown
from app.fingerbank.queue import Wanted
from app.models import Device, DeviceIdentity
from e2e import factories
from e2e.factories import AssetSpec, Listed
from tests.test_intel_lookups import fresh_incident

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
LAN = "192.168.1.20"
OUTSIDE = "9.9.9.9"
PHONE = "02:aa:bb:cc:dd:ee"
ARP = Listed("opnsense", "arp", 1)


def home(session: Session, *devices: AssetSpec) -> list[int]:
    """Makes the devices, each on the home network by default, and returns their ids in order."""
    factories.assets(session, NOW, list(devices), [])
    session.flush()
    return list(session.scalars(select(Device.id).order_by(Device.id)))


def mac_of(session: Session, device_id: int) -> str:
    return str(session.scalars(select(Device.mac).where(Device.id == device_id)).one())


def keep(
    session: Session,
    device_id: int,
    *,
    state: str = "identified",
    ago: timedelta = timedelta(minutes=1),
    reason: str = "asset",
) -> None:
    session.add(
        DeviceIdentity(
            device_id=device_id,
            source="fingerbank",
            state=state,
            reason=reason,
            name="Phone" if state == "identified" else None,
            checked_at=NOW - ago,
        )
    )
    session.flush()


def wanted(session: Session, *, incidents: bool = False) -> Wanted | None:
    return queue.next_wanted(session, NOW, incidents=incidents)


class TestWhetherARequestMayGo:
    def test_one_may_go_when_none_was_made(self, session: Session) -> None:
        assert queue.may_ask(session, NOW)

    def test_requests_are_ten_seconds_apart(self, session: Session) -> None:
        [first] = home(session, AssetSpec(addresses=(LAN,)))
        keep(session, first, ago=timedelta(seconds=9))

        assert not queue.may_ask(session, NOW)
        assert queue.may_ask(session, NOW + timedelta(seconds=1))

    def test_no_more_than_the_hour_allows_are_made_in_an_hour(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ids = home(session, *(AssetSpec(addresses=(f"192.168.1.{n}",)) for n in range(1, 4)))
        for device_id in ids:
            keep(session, device_id, ago=timedelta(minutes=30))
        assert queue.may_ask(session, NOW)

        # Three in the last hour against a limit of three.
        monkeypatch.setattr(queue, "HOURLY", 3)

        assert not queue.may_ask(session, NOW)
        assert queue.may_ask(session, NOW + timedelta(minutes=31))

    def test_a_device_set_aside_as_private_is_not_a_request(self, session: Session) -> None:
        [phone] = home(session, AssetSpec(mac=PHONE, addresses=(LAN,)))
        keep(session, phone, state="private", ago=timedelta(seconds=1))

        assert queue.may_ask(session, NOW)


class TestWhichDeviceIsNext:
    def test_nothing_is_asked_when_there_is_no_device(self, session: Session) -> None:
        assert wanted(session) is None

    def test_a_device_that_was_never_asked_about_is_asked(self, session: Session) -> None:
        [laptop] = home(session, AssetSpec(addresses=(LAN,)))

        found = wanted(session)

        assert found == Wanted(laptop, mac_of(session, laptop), "asset")

    def test_the_newest_device_on_the_network_comes_first(self, session: Session) -> None:
        old, new = home(
            session,
            AssetSpec(addresses=("192.168.1.2",), first_seen_hours=24 * 20),
            AssetSpec(addresses=("192.168.1.3",), first_seen_hours=2),
        )

        found = wanted(session)

        assert found is not None
        assert found.device_id == new
        keep(session, new)
        found = wanted(session)
        assert found is not None
        assert found.device_id == old

    def test_a_device_a_phone_made_up_an_address_for_is_never_asked_about(
        self, session: Session
    ) -> None:
        [phone] = home(session, AssetSpec(mac=PHONE, addresses=(LAN,)))

        assert wanted(session) is None
        row = session.get(DeviceIdentity, phone)
        assert row is not None
        assert (row.state, row.name) == ("private", None)

    @pytest.mark.parametrize(
        ("state", "ago", "asked"),
        [
            ("identified", timedelta(days=29), False),
            ("identified", timedelta(days=31), True),
            ("unknown", timedelta(days=6), False),
            ("unknown", timedelta(days=8), True),
        ],
    )
    def test_what_was_said_is_asked_again_only_once_it_has_gone_stale(
        self, session: Session, state: str, ago: timedelta, asked: bool
    ) -> None:
        [laptop] = home(session, AssetSpec(addresses=(LAN,)))
        keep(session, laptop, state=state, ago=ago)

        assert (wanted(session) is not None) is asked

    def test_a_device_never_asked_about_comes_before_one_whose_answer_is_stale(
        self, session: Session
    ) -> None:
        stale, fresh = home(
            session,
            AssetSpec(addresses=("192.168.1.2",), first_seen_hours=2),
            AssetSpec(addresses=("192.168.1.3",), first_seen_hours=24 * 20),
        )
        keep(session, stale, ago=timedelta(days=40))

        found = wanted(session)

        assert found is not None
        assert found.device_id == fresh

    def test_a_device_outside_the_home_is_not_asked_about_unless_it_is_in_an_incident(
        self, session: Session
    ) -> None:
        [stranger] = home(session, AssetSpec(addresses=(OUTSIDE,), listed=(ARP,)))

        assert wanted(session) is None
        assert wanted(session, incidents=True) is None

        fresh_incident(session, OUTSIDE)

        assert wanted(session) is None
        found = wanted(session, incidents=True)
        assert found == Wanted(stranger, mac_of(session, stranger), "incident")

    def test_a_device_outside_in_no_recent_incident_is_left_alone(self, session: Session) -> None:
        home(session, AssetSpec(addresses=(OUTSIDE,), listed=(ARP,)))
        fresh_incident(session, "1.1.1.1")

        assert wanted(session, incidents=True) is None

    def test_own_devices_come_before_the_ones_in_incidents(self, session: Session) -> None:
        stranger, mine = home(
            session,
            AssetSpec(addresses=(OUTSIDE,), listed=(ARP,)),
            AssetSpec(addresses=(LAN,)),
        )
        fresh_incident(session, OUTSIDE)

        found = wanted(session, incidents=True)

        assert found is not None
        assert found.device_id == mine
        keep(session, mine)
        found = wanted(session, incidents=True)
        assert found is not None
        assert found.device_id == stranger

    def test_nothing_is_left_to_ask_once_everything_has_an_answer(self, session: Session) -> None:
        [laptop] = home(session, AssetSpec(addresses=(LAN,)))
        keep(session, laptop)

        assert wanted(session) is None


class TestKeepingAnAnswer:
    def test_an_answer_is_kept_with_the_device_and_why_it_was_asked(self, session: Session) -> None:
        [laptop] = home(session, AssetSpec(addresses=(LAN,)))
        identity = Identity("Phone", "Kind/Phone", "Maker", "System", 70, 9)

        store.save(session, Wanted(laptop, "x", "asset"), Identified(identity), NOW)
        session.flush()

        row = session.get(DeviceIdentity, laptop)
        assert row is not None
        assert (row.state, row.reason, row.name, row.path) == (
            "identified",
            "asset",
            "Phone",
            "Kind/Phone",
        )
        assert (row.manufacturer, row.operating_system, row.score, row.external_id) == (
            "Maker",
            "System",
            70,
            9,
        )
        assert row.checked_at == NOW

    def test_no_match_is_kept_too_so_the_device_is_not_asked_again_at_once(
        self, session: Session
    ) -> None:
        [laptop] = home(session, AssetSpec(addresses=(LAN,)))

        store.save(session, Wanted(laptop, "x", "incident"), Unknown(), NOW)
        session.flush()

        row = session.get(DeviceIdentity, laptop)
        assert row is not None
        assert (row.state, row.reason, row.name, row.score) == ("unknown", "incident", None, None)

    def test_a_new_answer_replaces_the_old_one(self, session: Session) -> None:
        [laptop] = home(session, AssetSpec(addresses=(LAN,)))
        keep(session, laptop, state="unknown", ago=timedelta(days=9))
        identity = Identity("Laptop", None, None, None, None, None)

        store.save(session, Wanted(laptop, "x", "asset"), Identified(identity), NOW)
        session.flush()
        session.expire_all()

        rows = session.scalars(select(DeviceIdentity)).all()
        assert [(row.state, row.name) for row in rows] == [("identified", "Laptop")]
