"""The Devices page: every address in the connections the integrations reported, as the list and the
page of one of them tell it."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.events.event import Severity
from app.intel import store as intel_store
from app.intel import subjects, virustotal
from app.models import (
    AddressName,
    Device,
    DeviceIdentity,
    Event,
    IntegrationConnection,
    Interface,
    User,
    utcnow,
)
from e2e import factories
from e2e.factories import AssetSpec, EventSpec, IncidentSpec, Listed

BASE = "/api/devices"
LAPTOP_IP = "192.168.1.20"
CAMERA_IP = "192.168.1.30"
SERVER = "93.184.216.34"
SCANNER = "8.8.8.8"


def stock(session: Session, settings: Settings) -> None:
    """A laptop and a camera on the home network. The laptop connected to a server and was refused
    by a scanner's block, and the scanner knocked on the camera twice."""
    session.add(Interface(name="Home", role="home", networks=["192.168.1.0/24"], position=0))
    session.add(
        IntegrationConnection(integration="opnsense", connection="api", base_url="https://fw.lan")
    )
    factories.assets(
        session,
        utcnow(),
        [
            AssetSpec(
                hostname="laptop",
                mac="00:11:22:0a:0b:0c",
                vendor="Example Devices Inc.",
                addresses=(LAPTOP_IP,),
                listed=(Listed("opnsense", "arp", 1),),
            ),
            AssetSpec(
                hostname="camera",
                mac="00:11:22:0a:0b:0d",
                addresses=(CAMERA_IP,),
                listed=(Listed("opnsense", "arp", 1),),
            ),
        ],
        [],
    )
    factories.events(
        session,
        settings,
        utcnow(),
        [
            EventSpec(
                src_address=LAPTOP_IP,
                src_port=51000,
                dst_address=SERVER,
                dst_port=443,
                protocol="tcp",
                repeat=3,
                seconds_ago=120,
            ),
            EventSpec(
                src_address=SCANNER,
                src_port=40000,
                dst_address=CAMERA_IP,
                dst_port=23,
                protocol="tcp",
                repeat=2,
                seconds_ago=60,
            ),
        ],
    )
    session.commit()


def get(client: TestClient, query: str = "") -> Any:
    return client.get(f"{BASE}?{query}" if query else BASE)


def addresses(client: TestClient, query: str = "") -> list[str]:
    return [item["address"] for item in get(client, query).json()["items"]]


def test_it_is_for_someone_signed_in(client: TestClient, account: User) -> None:
    assert client.get(BASE).status_code == 401
    assert client.get(f"{BASE}/{SERVER}").status_code == 401


def test_nothing_reported_is_an_empty_list(client: TestClient, csrf_token: str) -> None:
    body = get(client).json()

    assert body["items"] == []
    assert body["total"] == 0
    assert body["counts"] == {"all": 0, "yours": 0, "local": 0, "outside": 0}
    assert (body["days"], body["capped"]) == (7, False)


class TestTheList:
    def test_it_has_every_address_in_a_connection_with_how_many_each_way(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)

        body = get(client).json()
        found = {item["address"]: item for item in body["items"]}

        assert set(found) == {LAPTOP_IP, SERVER, SCANNER, CAMERA_IP}
        assert (found[LAPTOP_IP]["incoming"], found[LAPTOP_IP]["outgoing"]) == (0, 3)
        assert (found[SERVER]["incoming"], found[SERVER]["outgoing"]) == (3, 0)
        assert (found[SCANNER]["incoming"], found[SCANNER]["outgoing"]) == (0, 2)
        assert (found[CAMERA_IP]["incoming"], found[CAMERA_IP]["outgoing"]) == (2, 0)
        assert body["counts"] == {"all": 4, "yours": 2, "local": 0, "outside": 2}
        assert [(item["address"], item["scope"]) for item in body["items"]][:2] == [
            (SCANNER, "outside"),
            (CAMERA_IP, "yours"),
        ]

    def test_an_address_on_both_sides_of_connections_adds_them_and_spans_the_time(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)
        factories.events(
            session,
            settings,
            utcnow(),
            [
                EventSpec(
                    src_address=SERVER,
                    src_port=443,
                    dst_address=LAPTOP_IP,
                    dst_port=51000,
                    protocol="tcp",
                    repeat=4,
                    seconds_ago=30,
                )
            ],
        )
        session.commit()

        found = {item["address"]: item for item in get(client).json()["items"]}

        assert (found[SERVER]["incoming"], found[SERVER]["outgoing"]) == (3, 4)
        assert (found[LAPTOP_IP]["incoming"], found[LAPTOP_IP]["outgoing"]) == (4, 3)
        # The earliest of the first sightings and the latest of the last.
        assert found[SERVER]["first_seen_at"] < found[SERVER]["last_seen_at"]

    def test_an_address_of_the_home_is_the_asset_it_is(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)

        found = {item["address"]: item for item in get(client).json()["items"]}

        laptop = found[LAPTOP_IP]["asset"]
        assert (laptop["name"], laptop["vendor"], laptop["key"][:7]) == (
            "laptop",
            "Example Devices Inc.",
            "device-",
        )
        assert found[SERVER]["asset"] is None

    def test_it_lists_the_ports_and_protocols_of_the_connections(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)

        found = {item["address"]: item for item in get(client).json()["items"]}

        assert found[SERVER]["ports"] == [{"port": 443, "protocol": "tcp", "events": 3}]
        assert found[SERVER]["protocols"] == ["tcp"]
        assert found[CAMERA_IP]["ports"][0]["port"] == 23

    def test_it_can_be_narrowed_to_a_scope_and_counts_each_in_the_search(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)

        assert sorted(addresses(client, "scope=outside")) == sorted([SERVER, SCANNER])
        assert sorted(addresses(client, "scope=yours")) == sorted([LAPTOP_IP, CAMERA_IP])
        assert addresses(client, "scope=local") == []
        searched = get(client, "q=laptop").json()
        assert [item["address"] for item in searched["items"]] == [LAPTOP_IP]
        assert searched["counts"] == {"all": 1, "yours": 1, "local": 0, "outside": 0}

    def test_it_can_be_narrowed_to_those_connected_to_or_that_connected(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)

        assert sorted(addresses(client, "direction=incoming")) == sorted([SERVER, CAMERA_IP])
        assert sorted(addresses(client, "direction=outgoing")) == sorted([LAPTOP_IP, SCANNER])

    def test_it_is_searched_by_address_and_by_name(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)
        session.add(AddressName(address=SERVER, name="example.test", looked_up_at=utcnow()))
        session.commit()

        assert addresses(client, "q=93.184") == [SERVER]
        assert addresses(client, "q=EXAMPLE.test") == [SERVER]
        assert addresses(client, "q=camera") == [CAMERA_IP]
        assert addresses(client, "q=nothing+like+it") == []
        assert get(client).json()["items"][0]["name"] is None
        found = {item["address"]: item for item in get(client).json()["items"]}
        assert found[SERVER]["name"] == "example.test"

    def test_it_is_ordered_by_what_was_asked(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)

        assert addresses(client, "sort=address") == [SCANNER, SERVER, LAPTOP_IP, CAMERA_IP]
        busiest = addresses(client, "sort=busiest")
        assert busiest[0] in {LAPTOP_IP, SERVER}
        assert busiest[-1] in {SCANNER, CAMERA_IP}

    def test_it_pages_through_the_devices(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)

        first = get(client, "limit=3&sort=address").json()
        rest = get(client, "limit=3&offset=3&sort=address").json()

        assert (len(first["items"]), first["total"]) == (3, 4)
        assert len(rest["items"]) == 1
        assert get(client, "limit=0").status_code == 422
        assert get(client, "scope=moon").status_code == 422

    def test_it_says_when_more_addresses_were_seen_than_are_read(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        stock(session, settings)
        monkeypatch.setattr("app.devices.seen.MOST", 2)

        assert get(client).json()["capped"] is True

    def test_it_marks_the_devices_that_are_in_an_incident(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)
        factories.incidents(
            session,
            settings,
            utcnow(),
            [IncidentSpec(address=SCANNER, device=CAMERA_IP, severity=Severity.CRITICAL)],
        )
        session.commit()

        flagged = get(client, "flagged=true").json()
        found = {item["address"]: item for item in flagged["items"]}

        assert SCANNER in found
        assert found[SCANNER]["incidents"] == {"count": 1, "worst": "critical"}
        assert LAPTOP_IP not in found

    def test_what_threat_intelligence_kept_of_an_outside_address_is_shown_with_it(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)
        intel_store.keep(
            session,
            virustotal.PROVIDER,
            subjects.parse(SERVER),
            virustotal.Reported(
                virustotal.Report(
                    malicious=4,
                    suspicious=1,
                    harmless=60,
                    undetected=20,
                    reputation=-9,
                    analysed_at=utcnow(),
                )
            ),
            utcnow(),
        )
        session.commit()

        found = {item["address"]: item for item in get(client).json()["items"]}

        assert found[SERVER]["standing"]["judgement"] in {"malicious", "suspicious"}
        assert found[SCANNER]["standing"] is None
        assert found[LAPTOP_IP]["standing"] is None

    def test_what_fingerbank_says_of_a_device_is_shown_with_it(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)
        laptop = session.scalars(select(Device).where(Device.mac == "00:11:22:0a:0b:0c")).one()
        session.add(
            DeviceIdentity(
                device_id=laptop.id,
                source="fingerbank",
                state="identified",
                reason="asset",
                name="Dell Laptop",
                score=70,
                checked_at=utcnow(),
            )
        )
        session.commit()

        found = {item["address"]: item for item in get(client).json()["items"]}

        assert found[LAPTOP_IP]["asset"]["identity"]["name"] == "Dell Laptop"


class TestOneDevice:
    def test_it_says_what_the_device_did_with_whom(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)

        body = client.get(f"{BASE}/{LAPTOP_IP}").json()

        assert body["device"]["address"] == LAPTOP_IP
        assert body["device"]["asset"]["name"] == "laptop"
        assert (body["events_day"], body["events_week"]) == (3, 3)
        assert body["connections"] == [
            {
                "direction": "outgoing",
                "peer": SERVER,
                "port": 443,
                "protocol": "tcp",
                "events": 3,
                "first_seen_at": body["connections"][0]["first_seen_at"],
                "last_seen_at": body["connections"][0]["last_seen_at"],
            }
        ]
        assert [(item["src_address"], item["outbound"]) for item in body["events"]] == [
            (LAPTOP_IP, True)
        ] * 3

    def test_a_device_that_was_connected_to_lists_who_connected(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)

        body = client.get(f"{BASE}/{CAMERA_IP}").json()

        assert [
            (item["direction"], item["peer"], item["port"]) for item in body["connections"]
        ] == [("incoming", SCANNER, 23)]
        assert body["events"][0]["outbound"] is False

    def test_it_links_the_incidents_the_device_is_in_and_their_kinds_of_threat(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)
        factories.incidents(
            session,
            settings,
            utcnow(),
            [IncidentSpec(address=SCANNER, device=CAMERA_IP, severity=Severity.CRITICAL)],
        )
        session.commit()

        body = client.get(f"{BASE}/{SCANNER}").json()

        [incident] = body["incidents"]
        assert incident["severity"] == "critical"
        assert incident["id"] > 0
        assert incident["family_id"] is not None
        assert incident["family_label"]
        assert body["device"]["incidents"] == {"count": 1, "worst": "critical"}

    def test_an_address_in_an_incident_is_known_even_with_nothing_this_week(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        factories.incidents(
            session,
            settings,
            utcnow(),
            [IncidentSpec(address=SCANNER, device=CAMERA_IP, idle_days=20)],
        )
        session.execute(delete(Event))
        session.commit()

        response = client.get(f"{BASE}/{SCANNER}")

        assert response.status_code == 200
        assert response.json()["connections"] == []
        assert response.json()["device"]["incoming"] == 0

    def test_an_asset_with_no_connections_this_week_is_still_a_device(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        session.add(Interface(name="Home", role="home", networks=["192.168.1.0/24"], position=0))
        factories.assets(
            session,
            utcnow(),
            [
                AssetSpec(
                    hostname="quiet", addresses=(LAPTOP_IP,), listed=(Listed("opnsense", "arp", 1),)
                )
            ],
            [],
        )
        session.commit()

        body = client.get(f"{BASE}/{LAPTOP_IP}").json()

        assert body["device"]["asset"]["name"] == "quiet"
        assert (body["device"]["incoming"], body["device"]["outgoing"]) == (0, 0)

    def test_an_address_nothing_is_known_of_is_not_found(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)

        assert client.get(f"{BASE}/203.0.113.77").status_code == 404
        assert client.get(f"{BASE}/not-an-address").status_code == 404

    def test_an_event_older_than_a_week_is_not_counted(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        factories.events(
            session,
            settings,
            utcnow(),
            [
                EventSpec(
                    src_address=SCANNER,
                    dst_address=SERVER,
                    seconds_ago=int(timedelta(days=8).total_seconds()),
                )
            ],
        )
        session.commit()

        assert get(client).json()["items"] == []
        assert client.get(f"{BASE}/{SCANNER}").status_code == 404

    def test_a_connection_that_does_not_say_where_the_other_end_was_is_listed_as_such(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        factories.events(
            session, settings, utcnow(), [EventSpec(src_address=SERVER, dst_address=None)]
        )
        session.commit()

        body = client.get(f"{BASE}/{SERVER}").json()

        assert [(item["direction"], item["peer"]) for item in body["connections"]] == [
            ("outgoing", None)
        ]
