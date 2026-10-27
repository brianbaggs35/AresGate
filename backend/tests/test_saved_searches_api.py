from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.searches import LIMIT
from app.models import SavedSearch, User
from tests.helpers import OTHER_ORIGIN

BASE = "/api/searches"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def save(client: TestClient, token: str, **body: Any) -> Any:
    return client.post(
        BASE,
        json={"scope": "logs", "name": "Scans", "query": "kind:alert since:6h", **body},
        headers=headers(token),
    )


def named(client: TestClient, scope: str) -> list[str]:
    return [item["name"] for item in client.get(BASE, params={"scope": scope}).json()["items"]]


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    answers = [
        client.get(BASE, params={"scope": "logs"}),
        client.post(BASE, json={"scope": "logs", "name": "a", "query": "b"}),
        client.delete(f"{BASE}/1"),
    ]

    assert [answer.status_code for answer in answers] == [401, 401, 401]


class TestKeepingASearch:
    def test_an_install_with_none_has_an_empty_list(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert client.get(BASE, params={"scope": "logs"}).json() == {"items": []}

    def test_it_is_kept_under_its_name_for_its_page(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = save(client, csrf_token)

        assert response.status_code == 201
        body = response.json()
        assert body | {"id": 0, "created_at": "", "updated_at": ""} == {
            "id": 0,
            "scope": "logs",
            "name": "Scans",
            "query": "kind:alert since:6h",
            "created_at": "",
            "updated_at": "",
        }
        assert client.get(BASE, params={"scope": "logs"}).json() == {"items": [body]}

    def test_the_other_page_does_not_have_it(self, client: TestClient, csrf_token: str) -> None:
        save(client, csrf_token)

        assert named(client, "incidents") == []

    def test_a_page_keeps_a_name_apart_from_the_other(
        self, client: TestClient, csrf_token: str
    ) -> None:
        save(client, csrf_token, scope="logs", query="kind:alert")
        response = save(client, csrf_token, scope="incidents", query="severity>=high")

        assert response.status_code == 201
        assert named(client, "logs") == ["Scans"]
        assert named(client, "incidents") == ["Scans"]

    def test_the_words_are_trimmed(self, client: TestClient, csrf_token: str) -> None:
        body = save(client, csrf_token, name="  Scans  ", query="  kind:alert  ").json()

        assert (body["name"], body["query"]) == ("Scans", "kind:alert")

    def test_they_are_listed_by_name_whatever_the_case(
        self, client: TestClient, csrf_token: str
    ) -> None:
        for name in ("beta", "Gamma", "alpha"):
            save(client, csrf_token, name=name)

        assert named(client, "logs") == ["alpha", "beta", "Gamma"]

    def test_saving_under_a_name_again_changes_the_search(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        first = save(client, csrf_token).json()

        again = save(client, csrf_token, query="severity>=high")

        assert again.status_code == 200
        assert again.json()["id"] == first["id"]
        assert again.json()["query"] == "severity>=high"
        assert again.json()["created_at"] == first["created_at"]
        assert session.scalar(select(func.count()).select_from(SavedSearch)) == 1

    def test_a_search_is_read_in_the_words_of_its_page(
        self, client: TestClient, csrf_token: str
    ) -> None:
        # kind: is a way to search the logs, not the incidents.
        assert save(client, csrf_token, scope="logs", query="kind:alert").status_code == 201

        response = save(client, csrf_token, scope="incidents", query="kind:alert")

        assert response.status_code == 422
        assert response.json()["detail"] == (
            'There\'s no search field called "kind". To look for the text itself, put it in quotes.'
        )
        assert named(client, "incidents") == []

    def test_the_words_that_stand_for_a_time_are_not_worked_out_when_it_is_kept(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert save(client, csrf_token, query="since:today").json()["query"] == "since:today"

    def test_it_has_to_say_something(self, client: TestClient, csrf_token: str) -> None:
        assert save(client, csrf_token, query="   ").status_code == 422
        assert save(client, csrf_token, name="   ").status_code == 422

    def test_a_name_and_a_search_are_only_so_long(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert save(client, csrf_token, name="n" * 61).status_code == 422
        assert save(client, csrf_token, name="n" * 60).status_code == 201
        assert save(client, csrf_token, name="x", query="a" * 501).status_code == 422

    def test_it_is_for_the_incidents_or_the_logs(self, client: TestClient, csrf_token: str) -> None:
        assert save(client, csrf_token, scope="devices").status_code == 422
        assert client.get(BASE, params={"scope": "devices"}).status_code == 422
        assert client.get(BASE).status_code == 422

    def test_nothing_else_is_taken(self, client: TestClient, csrf_token: str) -> None:
        assert save(client, csrf_token, owner="me").status_code == 422

    def test_a_page_keeps_only_so_many(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        session.add_all(
            SavedSearch(scope="logs", name=f"search {n}", query="kind:alert") for n in range(LIMIT)
        )
        session.commit()

        full = save(client, csrf_token, name="one too many")

        assert full.status_code == 409
        assert full.json()["detail"] == (
            f"You can keep {LIMIT} searches for this page. Delete one to save another."
        )
        # One that is there can still be changed, and the other page has room.
        assert save(client, csrf_token, name="search 3", query="since:1h").status_code == 200
        assert save(client, csrf_token, scope="incidents", query="since:1h").status_code == 201

    def test_another_website_cannot_keep_one(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        response = client.post(
            BASE,
            json={"scope": "logs", "name": "Scans", "query": "kind:alert"},
            headers={**headers(csrf_token), "Origin": OTHER_ORIGIN},
        )

        assert response.status_code == 403
        assert session.scalars(select(SavedSearch)).all() == []


class TestForgettingASearch:
    def test_it_is_gone(self, client: TestClient, csrf_token: str, session: Session) -> None:
        kept = save(client, csrf_token).json()
        save(client, csrf_token, name="Others")

        response = client.delete(f"{BASE}/{kept['id']}", headers=headers(csrf_token))

        assert response.status_code == 204
        assert named(client, "logs") == ["Others"]

    def test_there_is_no_such_one(self, client: TestClient, csrf_token: str) -> None:
        response = client.delete(f"{BASE}/12345", headers=headers(csrf_token))

        assert response.status_code == 404
        assert response.json()["detail"] == "There's no such saved search."

    def test_an_id_is_a_whole_number_above_nothing(
        self, client: TestClient, csrf_token: str
    ) -> None:
        answers = [
            client.delete(f"{BASE}/{part}", headers=headers(csrf_token)) for part in ("0", "abc")
        ]

        assert [answer.status_code for answer in answers] == [422, 422]
