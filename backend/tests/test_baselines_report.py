"""What was learned of what is normal, read as the Baselines page and the assistant read it, and
what the owner can correct: expected places, and places to forget."""

from datetime import datetime, timedelta
from ipaddress import ip_address, ip_network
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import baselines
from app.audit import Action
from app.baselines import destinations, report, traffic
from app.config import Settings
from app.events.event import Severity
from app.events.store import record as record_events
from app.models import AuditEvent, Device, DeviceAddress, KnownDestination, User, utcnow
from tests.helpers import new_event
from tests.test_baselines_destinations import CLIENT, NOW, watched_device
from tests.test_baselines_traffic import MEGABYTE, feed

OTHER = "192.168.1.30"
BASE = "/api/baselines"


def inventory(session: Session, address: str, hostname: str | None = "laptop") -> Device:
    """A device in the inventory with this address."""
    found = Device(
        mac="aa:bb:cc:00:00:01",
        hostname=hostname,
        first_seen_at=NOW - timedelta(days=30),
        last_seen_at=NOW,
    )
    session.add(found)
    session.flush()
    session.add(
        DeviceAddress(
            device_id=found.id,
            address=ip_address(address),
            first_seen_at=NOW - timedelta(days=30),
            last_seen_at=NOW,
        )
    )
    session.commit()
    return found


def deviate(
    session: Session,
    settings: Settings,
    *,
    interface: str = "igc0",
    direction: str = "received",
    at: datetime = NOW - timedelta(days=1),
    observed: float = 900 * MEGABYTE,
) -> None:
    """An hour that carried far more than usual, as it was raised."""
    record_events(
        session,
        settings,
        [
            new_event(
                source=baselines.SOURCE,
                connection=baselines.CONNECTION,
                kind=baselines.KIND,
                severity=Severity.LOW,
                occurred_at=at,
                identity=("traffic", interface, direction, at.isoformat()),
                summary="Unusual traffic",
                iface=interface,
                raw={
                    "baseline": "traffic",
                    "direction": direction,
                    "observed_bytes": observed,
                    "usual_bytes": 200 * MEGABYTE,
                },
            )
        ],
        at,
    )
    session.commit()


class TestTheInterfaces:
    def test_nothing_is_counted_until_a_counter_is_collected(self, session: Session) -> None:
        found = report.interfaces(session, NOW)

        assert found.counted is False
        assert found.series == ()

    def test_a_counter_with_nothing_learned_yet_is_counted_but_not_listed(
        self, session: Session, settings: Settings
    ) -> None:
        feed(session, settings, days=2)

        found = report.interfaces(session, NOW)

        assert found.counted is True
        assert found.series == ()

    def test_what_is_learned_is_each_hour_with_its_spread_and_the_hours_that_strayed(
        self, session: Session, settings: Settings
    ) -> None:
        feed(session, settings, days=15)
        traffic.learn(session, NOW)
        deviate(session, settings)
        deviate(session, settings, direction="sent")
        deviate(session, settings, interface="other")

        found = report.interfaces(session, NOW)

        series = next(item for item in found.series if item.direction == "received")
        assert series.interface == "igc0"
        assert series.name is None
        assert series.samples >= traffic.MIN_HOURS
        assert series.learned_at is not None
        assert {hour.hour for hour in series.hours} >= set(range(24))
        assert round(series.hours[3].median / MEGABYTE) == 200
        assert [item.observed for item in series.deviations] == [900 * MEGABYTE]
        assert series.deviations[0].summary == "Unusual traffic"

    def test_only_the_last_few_deviations_of_a_month_are_kept(
        self, session: Session, settings: Settings
    ) -> None:
        feed(session, settings, days=15)
        traffic.learn(session, NOW)
        for index in range(report.DEVIATIONS_SHOWN + 2):
            deviate(session, settings, at=NOW - timedelta(hours=index + 1))

        series = next(
            item for item in report.interfaces(session, NOW).series if item.direction == "received"
        )

        assert len(series.deviations) == report.DEVIATIONS_SHOWN

    def test_a_series_with_no_hours_has_no_samples(self) -> None:
        empty = report.Series("igc0", None, "sent", (), None, ())

        assert empty.samples == 0


class TestTheDevices:
    def test_there_are_none_before_anything_is_learned(self, session: Session) -> None:
        found = report.talkers(session, NOW)

        assert (found.items, found.total) == ((), 0)

    def test_each_is_counted_with_its_places_its_expected_ones_and_whether_it_is_judged(
        self, session: Session
    ) -> None:
        watched_device(session, places=25)
        watched_device(session, OTHER, places=2)
        row = session.scalars(
            select(KnownDestination).where(KnownDestination.client == ip_address(CLIENT))
        ).first()
        assert row is not None
        row.expected = True
        inventory(session, CLIENT)

        found = report.talkers(session, NOW)

        first, second = found.items
        assert (first.address, first.name, first.places, first.expected, first.hits) == (
            ip_address(CLIENT),
            "laptop",
            25,
            1,
            125,
        )
        assert first.judged is True
        assert (second.address, second.name, second.places, second.judged) == (
            ip_address(OTHER),
            None,
            2,
            False,
        )
        assert found.total == 2

    def test_it_names_a_device_from_the_inventory(self, session: Session) -> None:
        inventory(session, CLIENT)

        assert report.name_of(session, ip_address(CLIENT)) == "laptop"
        assert report.name_of(session, ip_address(OTHER)) is None


class TestThePlaces:
    def test_the_expected_come_first_then_the_most_visited(self, session: Session) -> None:
        watched_device(session, places=3)
        row = session.get(KnownDestination, (ip_address(CLIENT), ip_network("198.51.2.0/24"), 443))
        assert row is not None
        row.expected = True
        session.commit()

        found = report.places(session, ip_address(CLIENT), limit=2)

        assert [(place.network, place.expected) for place in found] == [
            ("198.51.2.0/24", True),
            ("198.51.0.0/24", False),
        ]

    def test_a_place_is_a_network_kept_as_a_24_or_a_64_and_a_port(self) -> None:
        assert report.place_key("198.51.100.0/24", 443) == (ip_network("198.51.100.0/24"), 443)
        assert report.place_key("2606:4700:1:2::/64", 0) == (ip_network("2606:4700:1:2::/64"), 0)

    @pytest.mark.parametrize(
        ("network", "port", "said"),
        [
            ("nonsense", 443, "That is not a network."),
            ("198.51.100.0/16", 443, "Places are kept as a /24."),
            ("2606:4700::/32", 443, "Places are kept as a /64."),
            ("198.51.100.0/24", 70000, "A port is a number from 0 to 65535."),
        ],
    )
    def test_anything_else_is_refused(self, network: str, port: int, said: str) -> None:
        with pytest.raises(report.BadPlace, match=said):
            report.place_key(network, port)


class TestCorrectingWhatWasLearned:
    def test_a_place_is_marked_expected_and_the_mark_is_taken_off(self, session: Session) -> None:
        watched_device(session, places=1)
        network = ip_network("198.51.0.0/24")

        made = report.mark(session, ip_address(CLIENT), network, 443, expected=True, now=NOW)
        session.commit()
        marked = session.get(KnownDestination, (ip_address(CLIENT), network, 443))
        assert marked is not None and marked.expected is True
        unmarked = report.mark(session, ip_address(CLIENT), network, 443, expected=False, now=NOW)
        session.commit()
        session.refresh(marked)

        assert (made, unmarked) == (False, False)
        assert marked.expected is False

    def test_a_place_never_learned_is_made_so_it_is_not_new_when_a_device_goes_there(
        self, session: Session
    ) -> None:
        network = ip_network("203.0.113.0/24")

        made = report.mark(session, ip_address(CLIENT), network, 22, expected=True, now=NOW)
        session.commit()

        row = session.get(KnownDestination, (ip_address(CLIENT), network, 22))
        assert made is True
        assert row is not None
        assert (row.hits, row.expected, row.first_seen_at) == (0, True, NOW)

    def test_there_is_nothing_to_take_the_mark_off_of_a_place_never_learned(
        self, session: Session
    ) -> None:
        network = ip_network("203.0.113.0/24")

        assert (
            report.mark(session, ip_address(CLIENT), network, 22, expected=False, now=NOW) is None
        )
        assert session.get(KnownDestination, (ip_address(CLIENT), network, 22)) is None

    def test_a_place_is_forgotten_so_the_next_visit_is_new_again(self, session: Session) -> None:
        watched_device(session, places=1)
        network = ip_network("198.51.0.0/24")

        assert report.forget(session, ip_address(CLIENT), network, 443) is True
        session.commit()
        assert report.forget(session, ip_address(CLIENT), network, 443) is False
        assert session.get(KnownDestination, (ip_address(CLIENT), network, 443)) is None

    def test_an_expected_place_is_not_forgotten_by_the_clean_up_of_old_places(
        self, session: Session
    ) -> None:
        watched_device(session, places=2)
        long_ago = NOW - destinations.FORGET_AFTER - timedelta(days=1)
        for row in session.scalars(select(KnownDestination)):
            row.last_seen_at = long_ago
            row.expected = row.network == ip_network("198.51.0.0/24")
        session.commit()

        destinations.run(session, NOW)
        session.commit()

        kept = session.scalars(select(KnownDestination)).all()
        assert [str(row.network) for row in kept] == ["198.51.0.0/24"]


# ---------------------------------------------------------------------------------------------
# The API


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def known_now(session: Session, client: str = CLIENT, places: int = 3) -> None:
    session.add_all(
        KnownDestination(
            client=ip_address(client),
            network=ip_network(f"198.51.{index}.0/24"),
            port=443,
            first_seen_at=utcnow() - timedelta(days=10),
            last_seen_at=utcnow() - timedelta(days=1),
            hits=5,
        )
        for index in range(places)
    )
    session.commit()


def audited(session: Session, action: Action) -> list[AuditEvent]:
    session.expire_all()
    return list(session.scalars(select(AuditEvent).where(AuditEvent.action == action)))


class TestTheApi:
    def test_it_is_for_someone_signed_in(self, client: TestClient, account: User) -> None:
        responses = [
            client.get(f"{BASE}/interfaces"),
            client.get(f"{BASE}/devices"),
            client.get(f"{BASE}/devices/{CLIENT}"),
            client.put(f"{BASE}/devices/{CLIENT}/places", json={}),
            client.post(f"{BASE}/devices/{CLIENT}/forget", json={}),
        ]

        assert [response.status_code for response in responses] == [401] * 5

    def test_the_interfaces_say_what_is_needed_to_learn(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        empty = client.get(f"{BASE}/interfaces").json()
        feed(session, settings, days=15, until=utcnow())
        traffic.learn(session, utcnow())
        deviate(session, settings, at=utcnow() - timedelta(hours=3), observed=900)

        body = client.get(f"{BASE}/interfaces").json()

        assert (empty["counted"], empty["series"]) == (False, [])
        assert (empty["weeks"], empty["min_hours"]) == (traffic.WINDOW.days // 7, traffic.MIN_HOURS)
        assert body["counted"] is True
        received = next(item for item in body["series"] if item["direction"] == "received")
        assert received["interface"] == "igc0"
        assert len(received["hours"]) >= 24
        assert received["deviations"][0]["observed"] == 900

    def test_the_devices_are_listed_with_what_it_takes_to_judge_them(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        known_now(session, places=25)

        body = client.get(f"{BASE}/devices").json()

        assert body["total"] == 1
        assert body["items"][0]["address"] == CLIENT
        assert body["items"][0]["places"] == 25
        assert body["items"][0]["judged"] is True
        assert (body["watched_days"], body["min_places"], body["forget_days"]) == (
            destinations.WATCHED_FOR.days,
            destinations.MIN_PLACES,
            destinations.FORGET_AFTER.days,
        )

    def test_the_places_of_a_device_are_listed(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        known_now(session)

        body: dict[str, Any] = client.get(f"{BASE}/devices/{CLIENT}").json()

        assert body["address"] == CLIENT
        assert body["name"] is None
        assert [place["network"] for place in body["places"]] == [
            "198.51.0.0/24",
            "198.51.1.0/24",
            "198.51.2.0/24",
        ]

    def test_a_device_nothing_is_known_of_is_not_found(
        self, client: TestClient, csrf_token: str
    ) -> None:
        unknown = client.get(f"{BASE}/devices/{OTHER}")
        nonsense = client.get(f"{BASE}/devices/nonsense")

        assert (unknown.status_code, nonsense.status_code) == (404, 404)

    def test_a_place_is_marked_expected_and_it_is_audited(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        known_now(session)

        response = client.put(
            f"{BASE}/devices/{CLIENT}/places",
            headers=headers(csrf_token),
            json={"network": "198.51.1.0/24", "port": 443},
        )

        assert response.status_code == 200
        assert response.json()["expected"] is True
        [entry] = audited(session, Action.BASELINE_PLACE_EXPECTED)
        assert entry.detail == {
            "address": CLIENT,
            "network": "198.51.1.0/24",
            "port": 443,
            "expected": True,
            "made": False,
        }

    def test_a_place_not_learned_is_made_expected(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        response = client.put(
            f"{BASE}/devices/{CLIENT}/places",
            headers=headers(csrf_token),
            json={"network": "203.0.113.0/24", "port": 22, "expected": True},
        )

        assert response.status_code == 200
        assert (response.json()["hits"], response.json()["expected"]) == (0, True)

    def test_a_mark_is_taken_off_only_where_there_is_one(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        body = {"network": "203.0.113.0/24", "port": 22, "expected": False}

        response = client.put(
            f"{BASE}/devices/{CLIENT}/places", headers=headers(csrf_token), json=body
        )

        assert response.status_code == 404
        assert audited(session, Action.BASELINE_PLACE_EXPECTED) == []

    def test_a_place_that_cannot_be_kept_is_refused(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.put(
            f"{BASE}/devices/{CLIENT}/places",
            headers=headers(csrf_token),
            json={"network": "198.51.0.0/16", "port": 443},
        )
        nonsense = client.put(
            f"{BASE}/devices/nonsense/places",
            headers=headers(csrf_token),
            json={"network": "198.51.0.0/24", "port": 443},
        )

        assert response.status_code == 422
        assert nonsense.status_code == 404

    def test_a_place_is_forgotten_and_it_is_audited(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        known_now(session)
        body = {"network": "198.51.1.0/24", "port": 443}

        gone = client.post(
            f"{BASE}/devices/{CLIENT}/forget", headers=headers(csrf_token), json=body
        )
        again = client.post(
            f"{BASE}/devices/{CLIENT}/forget", headers=headers(csrf_token), json=body
        )

        assert (gone.status_code, again.status_code) == (204, 404)
        assert len(audited(session, Action.BASELINE_PLACE_FORGOTTEN)) == 1
        assert (
            session.get(KnownDestination, (ip_address(CLIENT), ip_network("198.51.1.0/24"), 443))
            is None
        )

    def test_a_change_needs_the_token_and_a_valid_place(
        self, client: TestClient, csrf_token: str
    ) -> None:
        without = client.post(
            f"{BASE}/devices/{CLIENT}/forget", json={"network": "198.51.1.0/24", "port": 443}
        )
        invalid = client.post(
            f"{BASE}/devices/{CLIENT}/forget",
            headers=headers(csrf_token),
            json={"network": "198.51.1.0/24", "port": 99999},
        )

        assert (without.status_code, invalid.status_code) == (403, 422)
