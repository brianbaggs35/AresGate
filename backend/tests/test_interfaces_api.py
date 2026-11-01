import json
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import Action
from app.config import Settings, get_settings
from app.events.store import record as record_events
from app.integrations import probes
from app.interfaces import discovery
from app.metrics.store import record as record_samples
from app.models import AuditEvent, Interface, InterfaceFeed, User, utcnow
from e2e.stand_ins import Answer, ntopng
from tests.helpers import OTHER_ORIGIN, new_event, new_sample
from tests.ntopng import TOKEN, connect
from tests.stubs import Serve

BASE = "/api/interfaces"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def add_feed(session: Session, name: str = "igc0", **changes: Any) -> InterfaceFeed:
    fields: dict[str, Any] = {
        "integration": "opnsense",
        "connection": "api",
        "native_name": name,
    } | changes
    made = InterfaceFeed(**fields)
    session.add(made)
    session.commit()
    return made


def make(client: TestClient, token: str, **body: Any) -> Any:
    return client.post(
        BASE, json={"name": "Internet", "role": "internet"} | body, headers=headers(token)
    )


def audited(session: Session, action: Action) -> list[AuditEvent]:
    session.expire_all()
    return list(
        session.scalars(
            select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.id)
        )
    )


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    answers = [
        client.get(BASE),
        client.post(BASE, json={"name": "x", "role": "home"}),
        client.patch(f"{BASE}/1", json={"name": "x"}),
        client.delete(f"{BASE}/1"),
        client.put(f"{BASE}/feeds/1", json={}),
        client.post(f"{BASE}/discover"),
        client.get(f"{BASE}/resolve", params={"integration": "a", "connection": "b"}),
    ]

    assert [answer.status_code for answer in answers] == [401] * 7


def test_a_change_needs_the_security_token_and_the_apps_own_address(
    client: TestClient, csrf_token: str
) -> None:
    bad_origin = client.post(
        BASE,
        json={"name": "x", "role": "home"},
        headers=headers(csrf_token) | {"Origin": OTHER_ORIGIN},
    )
    no_token = client.post(BASE, json={"name": "x", "role": "home"})

    assert bad_origin.status_code == 403
    assert no_token.status_code in (401, 403)


class TestTheList:
    def test_an_install_with_nothing_is_empty(self, client: TestClient, csrf_token: str) -> None:
        response = client.get(BASE)

        assert response.status_code == 200
        assert response.json() == {
            "interfaces": [],
            "unplaced": [],
            "ignored": [],
            "suggestions": [],
            "max_interfaces": 24,
        }

    def test_it_shows_each_interface_with_its_feeds_and_what_isnt_placed(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        wan = add_feed(session, "igc0", label="WAN", detail="fibre")
        add_feed(session, "igc1")
        aside = add_feed(session, "lo0", ignored=True)
        add_feed(session, "", integration="crowdsec", connection="lapi")
        made = make(client, csrf_token, feeds=[wan.id], networks=["192.168.1.9/24"], notes="out")
        assert made.status_code == 201

        body = client.get(BASE).json()

        [internet] = body["interfaces"]
        assert internet | {"id": 0} == {
            "id": 0,
            "name": "Internet",
            "role": "internet",
            "notes": "out",
            "networks": ["192.168.1.0/24"],
            "position": 0,
            "feeds": [internet["feeds"][0]],
        }
        [feed] = internet["feeds"]
        assert feed | {"last_seen_at": ""} == {
            "id": wan.id,
            "integration": "opnsense",
            "integration_name": "OPNsense",
            "connection": "api",
            "connection_label": "OPNsense API",
            "native_name": "igc0",
            "label": "WAN",
            "detail": "fibre",
            "interface_id": internet["id"],
            "ignored": False,
            "last_seen_at": "",
        }
        assert [(f["integration_name"], f["native_name"]) for f in body["unplaced"]] == [
            ("CrowdSec", ""),
            ("OPNsense", "igc1"),
        ]
        assert [f["id"] for f in body["ignored"]] == [aside.id]

    def test_a_program_this_version_does_not_know_is_shown_by_its_key(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        add_feed(session, "x0", integration="newfangled", connection="thing")

        [feed] = client.get(BASE).json()["unplaced"]

        assert (feed["integration_name"], feed["connection_label"]) == ("newfangled", "thing")

    def test_it_suggests_where_feeds_could_go_and_places_none(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        wan = add_feed(session, "wan")

        body = client.get(BASE).json()

        assert body["suggestions"] == [
            {
                "name": "Internet",
                "role": "internet",
                "feed_ids": [wan.id],
                "reason": "“wan” says what it is for: wan in OPNsense.",
                "interface_id": None,
            }
        ]
        assert [f["id"] for f in body["unplaced"]] == [wan.id]


class TestMakingOne:
    def test_it_is_made_and_a_record_is_kept(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        port = add_feed(session)

        response = make(client, csrf_token, name="  Internet ", feeds=[port.id], notes=" out ")

        assert response.status_code == 201
        body = response.json()
        assert (body["name"], body["notes"], body["position"]) == ("Internet", "out", 0)
        assert [feed["id"] for feed in body["feeds"]] == [port.id]
        [event] = audited(session, Action.INTERFACE_CREATED)
        assert event.detail == {
            "interface_id": body["id"],
            "name": "Internet",
            "role": "internet",
            "feeds": 1,
        }

    def test_the_next_goes_after_it(self, client: TestClient, csrf_token: str) -> None:
        make(client, csrf_token)

        second = make(client, csrf_token, name="Home", role="home")

        assert second.json()["position"] == 1

    def test_a_name_that_is_taken_is_a_conflict(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        make(client, csrf_token)

        response = make(client, csrf_token, name="internet")

        assert response.status_code == 409
        assert response.json()["detail"] == "There is already an interface called internet."
        assert len(audited(session, Action.INTERFACE_CREATED)) == 1

    def test_a_feed_that_is_not_there_is_not_found_and_nothing_is_made(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        response = make(client, csrf_token, feeds=[999_999])

        assert response.status_code == 404
        assert response.json()["detail"] == "There is no such feed."
        assert session.scalars(select(Interface)).all() == []

    def test_what_is_not_a_network_is_unprocessable(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = make(client, csrf_token, networks=["my house"])

        assert response.status_code == 422
        assert "isn't a network" in response.json()["detail"]

    @pytest.mark.parametrize(
        "body",
        [
            {"name": ""},
            {"name": " "},
            {"name": "x" * 41},
            {"role": "spaceship"},
            {"notes": "x" * 301},
            {"networks": ["10.0.0.0/8"] * 17},
            {"networks": [""]},
            {"feeds": [0]},
            {"feeds": list(range(1, 202))},
            {"surprise": 1},
        ],
    )
    def test_what_is_malformed_is_refused(
        self, client: TestClient, csrf_token: str, body: dict[str, Any]
    ) -> None:
        assert make(client, csrf_token, **body).status_code == 422

    def test_there_is_a_limit_on_how_many(
        self, client: TestClient, csrf_token: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.interfaces import service

        monkeypatch.setattr(service, "MAX_INTERFACES", 1)
        make(client, csrf_token)

        response = make(client, csrf_token, name="Home", role="home")

        assert response.status_code == 409
        assert "You can have 1 interfaces" in response.json()["detail"]


class TestChangingOne:
    def test_what_is_given_changes_and_a_record_says_what(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        made = make(client, csrf_token, notes="out").json()

        response = client.patch(
            f"{BASE}/{made['id']}",
            json={"name": "WAN", "networks": ["10.0.0.0/8"], "position": 3},
            headers=headers(csrf_token),
        )

        assert response.status_code == 200
        body = response.json()
        assert (body["name"], body["role"], body["notes"]) == ("WAN", "internet", "out")
        assert (body["networks"], body["position"]) == (["10.0.0.0/8"], 3)
        [event] = audited(session, Action.INTERFACE_CHANGED)
        assert event.detail == {
            "interface_id": made["id"],
            "name": "WAN",
            "role": "internet",
            "changed": "name, networks, position",
        }

    def test_notes_can_be_emptied_and_the_role_changed(
        self, client: TestClient, csrf_token: str
    ) -> None:
        made = make(client, csrf_token, notes="out").json()

        response = client.patch(
            f"{BASE}/{made['id']}", json={"notes": "", "role": "dmz"}, headers=headers(csrf_token)
        )

        assert (response.json()["notes"], response.json()["role"]) == ("", "dmz")

    def test_saying_what_is_already_so_changes_nothing_and_keeps_no_record(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        made = make(client, csrf_token).json()

        response = client.patch(
            f"{BASE}/{made['id']}", json={"name": "Internet"}, headers=headers(csrf_token)
        )

        assert response.status_code == 200
        assert audited(session, Action.INTERFACE_CHANGED) == []

    def test_the_name_of_another_is_a_conflict(self, client: TestClient, csrf_token: str) -> None:
        make(client, csrf_token)
        home = make(client, csrf_token, name="Home", role="home").json()

        response = client.patch(
            f"{BASE}/{home['id']}", json={"name": "Internet"}, headers=headers(csrf_token)
        )

        assert response.status_code == 409

    def test_one_that_is_not_there_is_not_found(self, client: TestClient, csrf_token: str) -> None:
        response = client.patch(f"{BASE}/999", json={"name": "x"}, headers=headers(csrf_token))

        assert response.status_code == 404
        assert response.json()["detail"] == "There is no such interface."

    def test_a_network_that_is_not_one_is_unprocessable(
        self, client: TestClient, csrf_token: str
    ) -> None:
        made = make(client, csrf_token).json()

        response = client.patch(
            f"{BASE}/{made['id']}", json={"networks": ["no"]}, headers=headers(csrf_token)
        )

        assert response.status_code == 422

    @pytest.mark.parametrize("body", [{"position": -1}, {"position": 1001}, {"name": ""}, {"x": 1}])
    def test_what_is_malformed_is_refused(
        self, client: TestClient, csrf_token: str, body: dict[str, Any]
    ) -> None:
        made = make(client, csrf_token).json()

        response = client.patch(f"{BASE}/{made['id']}", json=body, headers=headers(csrf_token))

        assert response.status_code == 422

    @pytest.mark.parametrize("path", ["0", "abc", str(2**63)])
    def test_an_id_that_cannot_be_one_is_refused(
        self, client: TestClient, csrf_token: str, path: str
    ) -> None:
        response = client.patch(f"{BASE}/{path}", json={"name": "x"}, headers=headers(csrf_token))

        assert response.status_code == 422


class TestRemovingOne:
    def test_its_feeds_are_kept_and_not_placed(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        port = add_feed(session)
        made = make(client, csrf_token, feeds=[port.id]).json()

        response = client.delete(f"{BASE}/{made['id']}", headers=headers(csrf_token))

        assert response.status_code == 204
        body = client.get(BASE).json()
        assert body["interfaces"] == []
        assert [feed["id"] for feed in body["unplaced"]] == [port.id]
        [event] = audited(session, Action.INTERFACE_REMOVED)
        assert event.detail == {"interface_id": made["id"], "name": "Internet", "role": "internet"}

    def test_one_that_is_not_there_is_not_found(self, client: TestClient, csrf_token: str) -> None:
        response = client.delete(f"{BASE}/999", headers=headers(csrf_token))

        assert response.status_code == 404


class TestPlacingAFeed:
    def test_it_goes_on_an_interface_and_a_record_says_where(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        port = add_feed(session)
        made = make(client, csrf_token).json()

        response = client.put(
            f"{BASE}/feeds/{port.id}",
            json={"interface_id": made["id"]},
            headers=headers(csrf_token),
        )

        assert response.status_code == 200
        assert response.json()["interface_id"] == made["id"]
        [event] = audited(session, Action.INTERFACE_FEED_PLACED)
        assert event.detail == {
            "feed_id": port.id,
            "integration": "opnsense",
            "connection": "api",
            "native_name": "igc0",
            "ignored": False,
            "interface_id": made["id"],
        }

    def test_it_can_be_set_aside_and_put_back(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        port = add_feed(session)

        aside = client.put(
            f"{BASE}/feeds/{port.id}", json={"ignored": True}, headers=headers(csrf_token)
        )
        back = client.put(f"{BASE}/feeds/{port.id}", json={}, headers=headers(csrf_token))

        assert (aside.json()["ignored"], aside.json()["interface_id"]) == (True, None)
        assert (back.json()["ignored"], back.json()["interface_id"]) == (False, None)
        placed = audited(session, Action.INTERFACE_FEED_PLACED)
        assert [(event.detail or {}).get("ignored") for event in placed] == [True, False]

    def test_placed_and_set_aside_at_once_is_refused(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        port = add_feed(session)
        made = make(client, csrf_token).json()

        response = client.put(
            f"{BASE}/feeds/{port.id}",
            json={"interface_id": made["id"], "ignored": True},
            headers=headers(csrf_token),
        )

        assert response.status_code == 422
        assert "not both" in json.dumps(response.json())

    def test_a_feed_that_is_not_there_is_not_found(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.put(f"{BASE}/feeds/999", json={}, headers=headers(csrf_token))

        assert response.status_code == 404
        assert response.json()["detail"] == "There is no such feed."

    def test_an_interface_that_is_not_there_is_not_found(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        port = add_feed(session)

        response = client.put(
            f"{BASE}/feeds/{port.id}", json={"interface_id": 999}, headers=headers(csrf_token)
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "There is no such interface."


class TestResolving:
    def resolve(self, client: TestClient, **query: str) -> Any:
        return client.get(
            f"{BASE}/resolve", params={"integration": "opnsense", "connection": "api"} | query
        )

    def test_data_from_a_placed_port_says_which_interface(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        port = add_feed(session)
        made = make(client, csrf_token, feeds=[port.id]).json()

        response = self.resolve(client, name="igc0")

        assert response.status_code == 200
        assert response.json() == {
            "interface_id": made["id"],
            "name": "Internet",
            "role": "internet",
            "ignored": False,
        }

    def test_data_from_a_port_set_aside_says_so(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        add_feed(session, ignored=True)

        assert self.resolve(client, name="igc0").json() == {
            "interface_id": None,
            "name": None,
            "role": None,
            "ignored": True,
        }

    def test_data_nobody_placed_belongs_nowhere(self, client: TestClient, csrf_token: str) -> None:
        assert self.resolve(client).json() == {
            "interface_id": None,
            "name": None,
            "role": None,
            "ignored": False,
        }

    @pytest.mark.parametrize("query", [{"integration": ""}, {"connection": ""}, {"name": "x" * 65}])
    def test_what_is_malformed_is_refused(self, client: TestClient, csrf_token: str, query: Any):
        assert self.resolve(client, **query).status_code == 422


class TestDiscovering:
    def discover(self, client: TestClient, token: str) -> Any:
        return client.post(f"{BASE}/discover", headers=headers(token))

    def feeds(self, session: Session) -> dict[tuple[str, str, str], InterfaceFeed]:
        session.expire_all()
        return {
            (feed.integration, feed.connection, feed.native_name): feed
            for feed in session.scalars(select(InterfaceFeed))
        }

    def test_nothing_stored_finds_nothing(self, client: TestClient, csrf_token: str) -> None:
        response = self.discover(client, csrf_token)

        assert response.status_code == 200
        assert response.json() == {"new": 0, "complete": True, "notes": []}

    def test_the_ports_of_events_and_metrics_and_the_connections_are_found_and_placed_nowhere(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        now = utcnow()
        record_events(
            session, settings, [new_event(source="opnsense", connection="api", iface="igc0")], now
        )
        record_samples(
            session,
            settings,
            [new_sample(name="interface.bytes_in", labels={"interface": "igc1"})],
            now,
        )
        session.commit()
        add_feed(session, "igc0")

        response = self.discover(client, csrf_token)

        assert response.json() == {"new": 1, "complete": True, "notes": []}
        feeds = self.feeds(session)
        assert set(feeds) == {("opnsense", "api", "igc0"), ("opnsense", "api", "igc1")}
        assert all(feed.interface_id is None and not feed.ignored for feed in feeds.values())

    def test_looking_again_finds_nothing_new(self, client: TestClient, csrf_token: str) -> None:
        self.discover(client, csrf_token)

        assert self.discover(client, csrf_token).json()["new"] == 0

    def test_ntopng_is_asked_for_its_interfaces(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        serve: Serve,
    ) -> None:
        connect(session, settings, serve(ntopng(TOKEN)).url)

        response = self.discover(client, csrf_token)

        assert response.json() == {"new": 2, "complete": True, "notes": []}
        feeds = self.feeds(session)
        eth0, eth1 = feeds["ntopng", "api", "eth0"], feeds["ntopng", "api", "eth1"]
        assert (eth0.label, eth0.detail) == ("", "live packet capture")
        assert (eth1.label, eth1.detail) == ("LAN", "live packet capture")

    def test_an_interface_that_has_no_system_name_is_known_by_its_number(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        serve: Serve,
    ) -> None:
        listing = {"rc": 0, "rsp": [{"ifid": 3, "ifname": "", "name": "Lab"}]}
        connect(session, settings, serve(lambda seen: Answer(body=json.dumps(listing))).url)

        self.discover(client, csrf_token)

        assert ("ntopng", "api", "3") in self.feeds(session)

    def test_a_login_ntopng_refuses_is_a_note_and_the_rest_is_still_found(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        serve: Serve,
    ) -> None:
        connect(session, settings, serve(ntopng("another-token")).url)
        add_feed(session, "igc0")

        response = self.discover(client, csrf_token)

        assert response.status_code == 200
        assert response.json() == {
            "new": 0,
            "complete": True,
            "notes": [f"ntopng couldn't list its interfaces. {probes.NTOPNG_LOGIN_REFUSED}"],
        }

    def test_a_ntopng_that_cannot_be_reached_is_a_note(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        serve: Serve,
    ) -> None:
        server = serve(ntopng(TOKEN))
        connect(session, settings, server.url)
        server.stop()

        [note] = self.discover(client, csrf_token).json()["notes"]

        assert note.startswith("ntopng couldn't list its interfaces. ")

    def test_a_secret_that_cannot_be_opened_is_a_note(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        serve: Serve,
    ) -> None:
        connect(session, settings, serve(ntopng(TOKEN)).url)
        other = settings.model_copy(
            update={"secret_key": SecretStr("a different key altogether, 32+ bytes")}
        )
        client.app.dependency_overrides[get_settings] = lambda: other  # type: ignore[attr-defined]

        [note] = self.discover(client, csrf_token).json()["notes"]

        assert note.startswith("ntopng: ")
        assert "can't be opened" in note

    def test_a_search_of_the_events_that_takes_too_long_is_said_and_the_rest_is_kept(
        self, client: TestClient, csrf_token: str, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def too_slow(db: Session, now: datetime) -> tuple[list[discovery.Found], bool]:
            return [discovery.Found("a", "b", "c")], False

        monkeypatch.setattr(discovery, "from_events", too_slow)

        response = self.discover(client, csrf_token)

        assert response.json() == {"new": 1, "complete": False, "notes": []}
        assert ("a", "b", "c") in self.feeds(session)

    def test_the_whole_connections_are_found(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        from app.models import IntegrationConnection

        session.add(
            IntegrationConnection(
                integration="crowdsec", connection="lapi", base_url="https://192.0.2.1:8080"
            )
        )
        session.commit()

        self.discover(client, csrf_token)

        assert ("crowdsec", "lapi", "") in self.feeds(session)


def test_the_roles_of_the_api_are_the_roles_of_the_database() -> None:
    from typing import get_args

    from app.api.interfaces import Role
    from app.models import INTERFACE_ROLES

    assert get_args(Role) == INTERFACE_ROLES
