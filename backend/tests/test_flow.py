"""Network flow: the firewall's connections as paths from who connected, through the service, to
where they went."""

from ipaddress import ip_address
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import flows
from app.config import Settings
from app.events.event import Severity
from app.models import AddressName, User, utcnow
from e2e import factories
from e2e.factories import EventSpec

BASE = "/api/flow"
LAPTOP = "192.168.1.20"
PHONE = "192.168.1.21"
SERVER = "93.184.216.34"
SCANNER = "8.8.8.8"


def stock(session: Session, settings: Settings) -> None:
    """The laptop reached a server on 443 three times and was refused once on 25. The phone
    reached the same server on 443 twice and the laptop's ssh once. A scanner knocked on the
    laptop's ssh four times and was refused. An alert is not a firewall connection, and a
    connection with no destination has no path."""
    factories.events(
        session,
        settings,
        utcnow(),
        [
            EventSpec(
                src_address=LAPTOP,
                dst_address=SERVER,
                dst_port=443,
                protocol="tcp",
                repeat=3,
                seconds_ago=120,
            ),
            EventSpec(
                src_address=LAPTOP,
                dst_address=SERVER,
                dst_port=25,
                protocol="tcp",
                severity=Severity.LOW,
                seconds_ago=90,
            ),
            EventSpec(
                src_address=PHONE,
                dst_address=SERVER,
                dst_port=443,
                protocol="tcp",
                repeat=2,
                seconds_ago=60,
            ),
            EventSpec(
                src_address=PHONE,
                dst_address=LAPTOP,
                dst_port=22,
                protocol="tcp",
                seconds_ago=30,
            ),
            EventSpec(
                src_address=SCANNER,
                dst_address=LAPTOP,
                dst_port=22,
                protocol="tcp",
                severity=Severity.LOW,
                repeat=4,
                seconds_ago=40,
            ),
            EventSpec(kind="alert", src_address=SCANNER, dst_address=LAPTOP, seconds_ago=50),
            EventSpec(src_address=SCANNER, seconds_ago=50),
        ],
    )
    session.commit()


def get(client: TestClient, query: str = "") -> Any:
    return client.get(f"{BASE}?{query}" if query else BASE)


def by_id(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in body["nodes"]}


def test_it_is_for_someone_signed_in(client: TestClient, account: User) -> None:
    response = client.get(BASE)

    assert response.status_code == 401


def test_nothing_reported_is_an_empty_picture_with_a_quiet_timeline(
    client: TestClient, csrf_token: str
) -> None:
    body = get(client).json()

    assert (body["hours"], body["direction"], body["events"], body["blocked"]) == (24, "all", 0, 0)
    assert body["nodes"] == []
    assert body["links"] == []
    assert body["capped"] is False
    assert len(body["timeline"]) == 24
    assert {(bar["allowed"], bar["blocked"]) for bar in body["timeline"]} == {(0, 0)}
    assert body["stride_seconds"] == 3600


class TestThePaths:
    def test_each_connection_goes_from_who_connected_through_the_service_to_where(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)

        body = get(client).json()
        nodes = by_id(body)

        assert (body["events"], body["blocked"]) == (11, 5)
        assert nodes[f"source:{LAPTOP}"]["events"] == 4
        assert nodes[f"source:{LAPTOP}"]["blocked"] == 1
        assert nodes[f"source:{SCANNER}"]["scope"] == "outside"
        assert nodes[f"source:{PHONE}"]["scope"] == "local"
        assert nodes["service:tcp/443"]["events"] == 5
        assert nodes["service:tcp/443"]["port"] == 443
        assert nodes["service:tcp/22"]["events"] == 5
        assert nodes["service:tcp/25"]["blocked"] == 1
        assert nodes[f"destination:{SERVER}"]["events"] == 6
        assert nodes[f"destination:{LAPTOP}"]["events"] == 5
        assert set(nodes) == {
            f"source:{LAPTOP}",
            f"source:{PHONE}",
            f"source:{SCANNER}",
            "service:tcp/443",
            "service:tcp/25",
            "service:tcp/22",
            f"destination:{SERVER}",
            f"destination:{LAPTOP}",
        }

    def test_the_links_add_up_the_paths_between_neighbouring_columns(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)

        links = {
            (link["source"], link["target"]): (link["events"], link["blocked"])
            for link in get(client).json()["links"]
        }

        assert links[(f"source:{LAPTOP}", "service:tcp/443")] == (3, 0)
        assert links[(f"source:{LAPTOP}", "service:tcp/25")] == (1, 1)
        assert links[(f"source:{SCANNER}", "service:tcp/22")] == (4, 4)
        assert links[("service:tcp/22", f"destination:{LAPTOP}")] == (5, 4)
        assert links[("service:tcp/443", f"destination:{SERVER}")] == (5, 0)

    def test_the_busiest_come_first_in_each_column(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)

        nodes = get(client).json()["nodes"]
        sources = [node["label"] for node in nodes if node["column"] == "source"]

        assert sources == [LAPTOP, SCANNER, PHONE]
        assert [node["column"] for node in nodes] == sorted(
            (node["column"] for node in nodes),
            key=["source", "service", "destination"].index,
        )

    def test_a_name_that_is_kept_for_an_address_on_the_internet_is_given(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)
        session.add(AddressName(address=SERVER, name="example.net", looked_up_at=utcnow()))
        session.add(AddressName(address=SCANNER, name=None, looked_up_at=utcnow()))
        session.commit()

        nodes = by_id(get(client).json())

        assert nodes[f"destination:{SERVER}"]["name"] == "example.net"
        assert nodes[f"source:{SCANNER}"]["name"] is None
        assert nodes[f"source:{LAPTOP}"]["name"] is None


class TestTheDirection:
    @pytest.mark.parametrize(
        ("direction", "events"),
        [("all", 11), ("outgoing", 6), ("incoming", 4), ("inside", 1)],
    )
    def test_it_narrows_the_paths_to_one_way(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        direction: str,
        events: int,
    ) -> None:
        stock(session, settings)

        body = get(client, f"direction={direction}").json()

        assert body["direction"] == direction
        assert body["events"] == events

    def test_what_is_outgoing_is_from_the_home_to_the_internet(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock(session, settings)

        nodes = get(client, "direction=outgoing").json()["nodes"]

        assert {node["label"] for node in nodes if node["column"] == "source"} == {LAPTOP, PHONE}

    def test_it_refuses_a_direction_that_is_not_one(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = get(client, "direction=sideways")

        assert response.status_code == 422


class TestTheWindow:
    def test_it_reads_only_the_hours_asked_for(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        factories.events(
            session,
            settings,
            utcnow(),
            [
                EventSpec(
                    src_address=LAPTOP,
                    dst_address=SERVER,
                    dst_port=443,
                    protocol="tcp",
                    seconds_ago=60 * 30,
                ),
                EventSpec(
                    src_address=LAPTOP,
                    dst_address=SERVER,
                    dst_port=443,
                    protocol="tcp",
                    seconds_ago=60 * 60 * 5,
                ),
                EventSpec(
                    src_address=LAPTOP,
                    dst_address=SERVER,
                    dst_port=443,
                    protocol="tcp",
                    seconds_ago=60 * 60 * 48,
                ),
            ],
        )
        session.commit()

        counts = {
            hours: get(client, f"hours={hours}").json()["events"] for hours in (1, 6, 24, 168)
        }

        assert counts == {1: 1, 6: 2, 24: 2, 168: 3}

    @pytest.mark.parametrize(
        ("hours", "bars", "stride"), [(1, 12, 300), (6, 24, 900), (24, 24, 3600), (168, 28, 21600)]
    )
    def test_the_timeline_has_a_bar_for_each_stretch(
        self, client: TestClient, csrf_token: str, hours: int, bars: int, stride: int
    ) -> None:
        body = get(client, f"hours={hours}").json()

        assert len(body["timeline"]) == bars
        assert body["stride_seconds"] == stride

    def test_the_timeline_counts_what_was_allowed_and_what_was_refused_in_each(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        factories.events(
            session,
            settings,
            utcnow(),
            [
                EventSpec(
                    src_address=LAPTOP,
                    dst_address=SERVER,
                    dst_port=443,
                    protocol="tcp",
                    repeat=2,
                    seconds_ago=10,
                ),
                EventSpec(
                    src_address=SCANNER,
                    dst_address=LAPTOP,
                    dst_port=22,
                    protocol="tcp",
                    severity=Severity.LOW,
                    seconds_ago=10,
                ),
            ],
        )
        session.commit()

        bars = get(client, "hours=1").json()["timeline"]

        assert sum(bar["allowed"] for bar in bars) == 2
        assert sum(bar["blocked"] for bar in bars) == 1
        assert (bars[-1]["allowed"], bars[-1]["blocked"]) == (2, 1)

    def test_it_refuses_a_window_that_is_not_one_of_the_choices(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = get(client, "hours=5")

        assert response.status_code == 422


class TestWhatIsTooSmallToDraw:
    def test_the_busiest_of_a_column_are_drawn_and_the_rest_are_folded_into_others(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        factories.events(
            session,
            settings,
            utcnow(),
            [
                EventSpec(
                    src_address=f"192.168.1.{number + 1}",
                    dst_address=SERVER,
                    dst_port=443,
                    protocol="tcp",
                    repeat=20 - number,
                    seconds_ago=30,
                )
                for number in range(10)
            ],
        )
        session.commit()

        body = get(client).json()
        sources = [node for node in body["nodes"] if node["column"] == "source"]

        assert len(sources) == flows.SHOWN["source"] + 1
        others = sources[-1]
        assert (others["id"], others["label"], others["folded"]) == ("source:others", "Others", 2)
        assert others["events"] == (20 - 8) + (20 - 9)
        assert others["name"] is None
        links = {(link["source"], link["target"]): link["events"] for link in body["links"]}
        assert links[("source:others", "service:tcp/443")] == others["events"]
        assert sum(node["events"] for node in sources) == body["events"]

    def test_a_service_with_no_port_is_named_by_its_protocol(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        factories.events(
            session,
            settings,
            utcnow(),
            [
                EventSpec(src_address=LAPTOP, dst_address=SERVER, protocol="icmp"),
                EventSpec(src_address=LAPTOP, dst_address=SERVER),
            ],
        )
        session.commit()

        nodes = by_id(get(client).json())

        assert nodes["service:icmp"]["port"] == 0
        assert nodes["service:ip"]["protocol"] is None

    def test_it_says_when_there_were_more_paths_than_it_reads(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(flows, "MAX_PATHS", 1)
        stock(session, settings)

        body = get(client).json()

        assert body["capped"] is True
        assert len([node for node in body["nodes"] if node["column"] == "source"]) == 1


def test_an_address_on_the_internet_and_one_that_is_not_are_told_apart() -> None:
    assert flows.scope_of(ip_address("8.8.8.8")) == "outside"
    assert flows.scope_of(ip_address("10.0.0.1")) == "local"
    assert flows.scope_of(ip_address("fe80::1")) == "local"
