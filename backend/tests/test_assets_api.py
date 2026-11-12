from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import Action
from app.models import AuditEvent, IntegrationConnection, Interface, User, utcnow
from e2e import factories
from e2e.factories import AssetSpec, HostSpec, Listed

BASE = "/api/assets"
LAPTOP = "00:11:22:0a:0b:0c"
PHONE = "02:aa:bb:cc:dd:ee"


def stock(session: Session) -> None:
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
                mac=LAPTOP,
                vendor="Example Devices Inc.",
                addresses=("192.168.1.20",),
                listed=(Listed("opnsense", "arp", 1), Listed("opnsense", "dhcp", 4)),
            ),
            AssetSpec(hostname="phone", mac=PHONE, listed=(Listed("opnsense", "dhcp", 30),)),
        ],
        [HostSpec("002", hostname="laptop", address="192.168.1.20")],
    )
    session.commit()


def get(client: TestClient, query: str = "") -> Any:
    return client.get(f"{BASE}?{query}" if query else BASE)


def test_it_is_for_someone_signed_in(client: TestClient, account: User) -> None:
    assert client.get(BASE).status_code == 401


def test_nothing_listed_is_an_empty_inventory_that_says_who_could_list_devices(
    client: TestClient, csrf_token: str
) -> None:
    body = get(client).json()

    assert (body["total"], body["items"], body["watching_since"]) == (0, [], None)
    assert body["counts"] == {"all": 0, "online": 0, "recent": 0, "away": 0}
    assert [(item["key"], item["connected"], item["assets"]) for item in body["suppliers"]] == [
        ("opnsense", False, 0),
        ("ntopng", False, 0),
        ("wazuh", False, 0),
    ]
    assert body["interfaces"] == []


def test_it_lists_the_devices_merged_with_who_listed_each(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    stock(session)

    body = get(client).json()

    assert body["total"] == 2
    laptop = next(item for item in body["items"] if item["name"] == "laptop")
    assert laptop["kind"] == "device"
    assert laptop["key"].startswith("device-")
    assert (laptop["mac"], laptop["vendor"], laptop["status"]) == (
        LAPTOP,
        "Example Devices Inc.",
        "online",
    )
    assert (laptop["addresses"], laptop["current_addresses"]) == (["192.168.1.20"], 1)
    assert (laptop["private_mac"], laptop["identified"], laptop["is_new"]) == (False, True, False)
    assert [
        (item["source_name"], item["via_label"], item["presence"], item["matched_by"])
        for item in laptop["listings"]
    ] == [
        ("OPNsense", "ARP table", True, None),
        ("OPNsense", "DHCP leases", False, None),
        ("Wazuh", "Agent", True, "address"),
    ]
    assert laptop["listings"][2]["state"] == "active"
    home = body["interfaces"][0]
    assert (home["name"], home["assets"]) == ("Home", 1)
    assert laptop["interfaces"] == [home["id"]]
    assert body["counts"] == {"all": 2, "online": 1, "recent": 1, "away": 0}
    assert body["watching_since"] is not None


def test_each_integration_says_whether_it_is_connected_and_how_many_assets_it_lists(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    stock(session)

    suppliers = {item["key"]: item for item in get(client).json()["suppliers"]}

    assert suppliers["opnsense"] == {
        "key": "opnsense",
        "name": "OPNsense",
        "connected": True,
        "ways": ["ARP table", "DHCP leases"],
        "assets": 2,
    }
    assert (suppliers["wazuh"]["connected"], suppliers["wazuh"]["assets"]) == (False, 1)


@pytest.mark.parametrize(
    ("query", "names"),
    [
        ("q=laptop", ["laptop"]),
        ("q=aa:bb", ["phone"]),
        ("status=online", ["laptop"]),
        ("status=recent", ["phone"]),
        ("status=away", []),
        ("source=wazuh", ["laptop"]),
        ("source=wazuh&source=opnsense", ["laptop", "phone"]),
        ("unidentified=true", []),
        ("new=true", []),
        ("sort=name", ["laptop", "phone"]),
        ("limit=1", ["laptop"]),
        ("limit=1&offset=1", ["phone"]),
    ],
)
def test_it_is_narrowed_and_ordered_by_what_is_asked(
    client: TestClient, csrf_token: str, session: Session, query: str, names: list[str]
) -> None:
    stock(session)

    assert [item["name"] for item in get(client, query).json()["items"]] == names


def test_the_total_is_of_everything_found_and_not_of_the_page(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    stock(session)

    body = get(client, "limit=1").json()

    assert (body["total"], len(body["items"])) == (2, 1)


def test_an_interface_narrows_to_what_is_on_its_networks(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    stock(session)
    home = get(client).json()["interfaces"][0]["id"]

    assert [item["name"] for item in get(client, f"interface={home}").json()["items"]] == ["laptop"]
    assert get(client, "interface=9999").json()["total"] == 0


def test_a_neighbour_on_the_internet_side_is_left_out_and_counted(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    stock(session)
    factories.assets(
        session,
        utcnow(),
        [
            AssetSpec(
                hostname="firewall",
                mac="00:11:22:0a:0b:0d",
                addresses=("9.9.9.10",),
                listed=(Listed("opnsense", "arp", 1, own=True),),
            ),
            AssetSpec(
                vendor="Example Cable Inc.",
                mac="00:11:22:0a:0b:0f",
                addresses=("9.9.9.1", "9.9.9.2"),
                listed=(Listed("opnsense", "arp", 1),),
            ),
        ],
        [],
    )
    session.commit()

    body = get(client).json()

    assert (body["total"], body["outside"]) == (3, 1)
    assert sorted(item["name"] for item in body["items"]) == ["firewall", "laptop", "phone"]


@pytest.mark.parametrize(
    "query",
    [
        "status=sleeping",
        "sort=colour",
        "limit=0",
        "limit=101",
        "offset=-1",
        "interface=0",
        "q=" + "x" * 201,
        "source=a&source=b&source=c&source=d&source=e&source=f&source=g&source=h&source=i",
    ],
)
def test_a_request_it_cannot_make_sense_of_is_refused(
    client: TestClient, csrf_token: str, query: str
) -> None:
    assert get(client, query).status_code == 422


def key_of(client: TestClient, name: str) -> str:
    return next(item["key"] for item in get(client).json()["items"] if item["name"] == name)


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


class TestKinds:
    def test_the_kinds_to_pick_from_come_in_groups(
        self, client: TestClient, csrf_token: str
    ) -> None:
        groups = client.get(f"{BASE}/kinds").json()

        assert [group["key"] for group in groups] == [
            "network",
            "computers",
            "phones",
            "home",
            "other",
        ]
        network = groups[0]["kinds"]
        assert network[0] == {
            "key": "router",
            "label": "Router",
            "group": "network",
            "carries": True,
        }
        assert groups[-1]["kinds"][0]["key"] == "other"

    def test_it_is_for_someone_signed_in(self, client: TestClient, account: User) -> None:
        assert client.get(f"{BASE}/kinds").status_code == 401


class TestClassifying:
    def test_what_the_owner_says_is_kept_and_listed_with_the_asset(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        stock(session)
        key = key_of(client, "laptop")

        response = client.put(
            f"{BASE}/{key}/profile",
            json={"kind": "laptop", "purpose": "Dad's work laptop"},
            headers=headers(csrf_token),
        )

        assert response.status_code == 200
        assert response.json()["kind_label"] == "Laptop"
        listed = next(item for item in get(client).json()["items"] if item["key"] == key)
        assert listed["profile"]["purpose"] == "Dad's work laptop"
        assert listed["profile"]["carries"] is False
        detail = client.get(f"{BASE}/{key}").json()["asset"]
        assert detail["profile"]["kind"] == "laptop"

    def test_a_name_can_suggest_what_it_is_without_saying_it_is(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        stock(session)

        listed = {item["name"]: item for item in get(client).json()["items"]}

        assert listed["laptop"]["profile"] is None
        assert (listed["laptop"]["suggested_kind"], listed["laptop"]["suggested_label"]) == (
            "laptop",
            "Laptop",
        )
        assert listed["phone"]["suggested_label"] == "Phone"
        assert listed["laptop"]["own"] is False

    def test_it_is_said_in_the_audit_log_and_can_be_taken_back(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        stock(session)
        key = key_of(client, "phone")
        client.put(f"{BASE}/{key}/profile", json={"kind": "phone"}, headers=headers(csrf_token))
        said = session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc())).first()

        gone = client.delete(f"{BASE}/{key}/profile", headers=headers(csrf_token))
        taken = session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc())).first()
        again = client.delete(f"{BASE}/{key}/profile", headers=headers(csrf_token))

        assert said is not None
        assert said.action == Action.ASSET_CLASSIFIED
        assert gone.status_code == 204
        assert taken is not None
        assert taken.action == Action.ASSET_CLASSIFICATION_CLEARED
        assert again.status_code == 404
        assert (
            next(item for item in get(client).json()["items"] if item["key"] == key)["profile"]
            is None
        )

    def test_an_asset_that_is_not_there_is_not_classified(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        stock(session)

        response = client.put(
            f"{BASE}/device-9999/profile", json={"kind": "tv"}, headers=headers(csrf_token)
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "body",
        [{"kind": "toaster"}, {}, {"kind": "tv", "purpose": "x" * 201}],
    )
    def test_a_kind_it_does_not_know_or_too_many_words_is_refused(
        self, client: TestClient, csrf_token: str, session: Session, body: dict[str, str]
    ) -> None:
        stock(session)
        key = key_of(client, "phone")

        response = client.put(f"{BASE}/{key}/profile", json=body, headers=headers(csrf_token))

        assert response.status_code == 422

    def test_it_needs_a_token_to_change_anything(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        stock(session)
        key = key_of(client, "phone")

        assert client.put(f"{BASE}/{key}/profile", json={"kind": "phone"}).status_code == 403

    def test_the_list_can_be_narrowed_to_a_kind_and_counts_each(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        stock(session)
        key = key_of(client, "phone")
        client.put(f"{BASE}/{key}/profile", json={"kind": "phone"}, headers=headers(csrf_token))

        body = get(client, "kind=phone").json()
        rest = get(client, "kind=unclassified").json()

        assert [item["name"] for item in body["items"]] == ["phone"]
        assert [item["name"] for item in rest["items"]] == ["laptop"]
        assert body["kinds"] == [{"key": "phone", "label": "Phone", "count": 1}]
        assert body["unclassified"] == 1
        assert get(client, "kind=toaster").status_code == 422
