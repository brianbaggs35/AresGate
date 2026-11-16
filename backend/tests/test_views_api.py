"""Saved views: the filters and order of a list, kept under a name for one account."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.views import LIMIT
from app.models import SavedView, User
from e2e import factories
from tests.helpers import OTHER_ORIGIN

BASE = "/api/views"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def save(client: TestClient, token: str, **body: Any) -> Any:
    return client.post(
        BASE,
        json={
            "page": "incidents",
            "name": "Needs a look",
            "query": {"status": ["open", "investigating"], "order": "priority"},
            **body,
        },
        headers=headers(token),
    )


def named(client: TestClient, page: str | None = None) -> list[str]:
    params = {"page": page} if page else {}
    return [item["name"] for item in client.get(BASE, params=params).json()["items"]]


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    answers = [
        client.get(BASE),
        client.post(BASE, json={"page": "assets", "name": "a", "query": {}}),
        client.patch(f"{BASE}/1", json={"name": "b"}),
        client.delete(f"{BASE}/1"),
    ]

    assert [answer.status_code for answer in answers] == [401] * 4


def test_a_change_without_the_security_token_is_refused(
    client: TestClient, csrf_token: str
) -> None:
    answers = [
        client.post(BASE, json={"page": "assets", "name": "a", "query": {}}),
        client.post(
            BASE,
            json={"page": "assets", "name": "a", "query": {}},
            headers={**headers(csrf_token), "Origin": OTHER_ORIGIN},
        ),
    ]

    assert [answer.status_code for answer in answers] == [403, 403]


class TestKeepingAView:
    def test_an_install_with_none_has_an_empty_list(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert client.get(BASE).json() == {"items": []}

    def test_it_is_kept_under_its_name_for_its_page(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = save(client, csrf_token)

        assert response.status_code == 201
        kept = response.json()
        assert kept["page"] == "incidents"
        assert kept["name"] == "Needs a look"
        assert kept["query"] == {"status": ["open", "investigating"], "order": "priority"}
        assert kept["is_default"] is False
        assert named(client, "incidents") == ["Needs a look"]
        assert named(client, "assets") == []

    def test_the_views_of_every_page_are_listed_by_page_and_then_name(
        self, client: TestClient, csrf_token: str
    ) -> None:
        save(client, csrf_token, name="b")
        save(client, csrf_token, name="A")
        save(client, csrf_token, page="assets", name="Z", query={})
        save(client, csrf_token, page="alerts", name="Y", query={})

        assert named(client) == ["Y", "Z", "A", "b"]

    def test_saving_under_a_name_again_changes_that_view(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        first = save(client, csrf_token).json()

        again = save(client, csrf_token, query={"order": "recent"})

        assert again.status_code == 200
        assert again.json()["id"] == first["id"]
        assert again.json()["query"] == {"order": "recent"}
        assert session.scalar(select(func.count()).select_from(SavedView)) == 1

    def test_a_page_keeps_only_so_many(self, client: TestClient, csrf_token: str) -> None:
        for number in range(LIMIT):
            assert save(client, csrf_token, name=f"View {number}").status_code == 201

        refused = save(client, csrf_token, name="One too many")

        assert refused.status_code == 409
        assert str(LIMIT) in refused.json()["detail"]
        assert save(client, csrf_token, page="assets", name="Elsewhere").status_code == 201
        assert save(client, csrf_token, name="View 3", query={}).status_code == 200

    def test_it_can_be_made_the_one_a_page_opens_on(
        self, client: TestClient, csrf_token: str
    ) -> None:
        first = save(client, csrf_token, name="First", default=True).json()
        second = save(client, csrf_token, name="Second", default=True).json()

        found = {item["name"]: item["is_default"] for item in client.get(BASE).json()["items"]}

        assert first["is_default"] is True
        assert second["is_default"] is True
        assert found == {"First": False, "Second": True}

    def test_a_query_must_be_a_few_short_filters(self, client: TestClient, csrf_token: str) -> None:
        bad = [
            {"not a name": "x"},
            {"": "x"},
            {"a": "x" * 501},
            {"a": ["x"] * 21},
            {f"k{n}": "x" for n in range(21)},
            {"a": 3},
        ]

        answers = [save(client, csrf_token, query=query).status_code for query in bad]

        assert answers == [422] * len(bad)

    def test_the_name_and_the_page_must_be_something(
        self, client: TestClient, csrf_token: str
    ) -> None:
        answers = [
            save(client, csrf_token, name="  ").status_code,
            save(client, csrf_token, name="x" * 61).status_code,
            save(client, csrf_token, page="logs").status_code,
            save(client, csrf_token, extra=1).status_code,
        ]

        assert answers == [422] * 4


class TestChangingAView:
    def test_it_can_be_renamed(self, client: TestClient, csrf_token: str) -> None:
        view = save(client, csrf_token).json()

        response = client.patch(
            f"{BASE}/{view['id']}", json={"name": " Look at these "}, headers=headers(csrf_token)
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Look at these"
        assert response.json()["query"] == view["query"]

    def test_a_name_that_is_taken_is_refused(self, client: TestClient, csrf_token: str) -> None:
        save(client, csrf_token, name="Taken")
        view = save(client, csrf_token, name="Mine").json()

        response = client.patch(
            f"{BASE}/{view['id']}", json={"name": "Taken"}, headers=headers(csrf_token)
        )

        assert response.status_code == 409
        assert named(client) == ["Mine", "Taken"]

    def test_its_own_name_again_changes_nothing(self, client: TestClient, csrf_token: str) -> None:
        view = save(client, csrf_token).json()

        response = client.patch(
            f"{BASE}/{view['id']}", json={"name": view["name"]}, headers=headers(csrf_token)
        )

        assert response.status_code == 200

    def test_it_can_be_made_the_default_and_stop_being_it(
        self, client: TestClient, csrf_token: str
    ) -> None:
        one = save(client, csrf_token, name="One", default=True).json()
        two = save(client, csrf_token, name="Two").json()

        made = client.patch(
            f"{BASE}/{two['id']}", json={"default": True}, headers=headers(csrf_token)
        )
        stopped = client.patch(
            f"{BASE}/{two['id']}", json={"default": False}, headers=headers(csrf_token)
        )

        assert made.json()["is_default"] is True
        assert [item["is_default"] for item in client.get(BASE).json()["items"]] == [False, False]
        assert one["id"] != two["id"]
        assert stopped.json()["is_default"] is False

    def test_a_change_of_nothing_is_allowed(self, client: TestClient, csrf_token: str) -> None:
        view = save(client, csrf_token).json()

        response = client.patch(f"{BASE}/{view['id']}", json={}, headers=headers(csrf_token))

        assert response.status_code == 200
        assert response.json()["name"] == view["name"]


class TestForgettingAView:
    def test_it_is_forgotten(self, client: TestClient, csrf_token: str) -> None:
        view = save(client, csrf_token).json()

        response = client.delete(f"{BASE}/{view['id']}", headers=headers(csrf_token))
        left = named(client)

        assert response.status_code == 204
        assert left == []

    def test_one_that_is_not_there_is_not_found(self, client: TestClient, csrf_token: str) -> None:
        deleted = client.delete(f"{BASE}/99", headers=headers(csrf_token))
        renamed = client.patch(f"{BASE}/99", json={"name": "x"}, headers=headers(csrf_token))

        assert [deleted.status_code, renamed.status_code] == [404, 404]


class TestWhoseTheyAre:
    def other(self, session: Session) -> SavedView:
        someone = factories.account(session, username="someone-else")
        theirs = SavedView(
            user_id=someone.id, page="incidents", name="Theirs", query={"order": "recent"}
        )
        session.add(theirs)
        session.commit()
        return theirs

    def test_another_accounts_views_are_not_listed(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        self.other(session)
        save(client, csrf_token, name="Mine")

        assert named(client) == ["Mine"]

    def test_another_accounts_view_cannot_be_changed_or_forgotten(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        theirs = self.other(session)

        answers = [
            client.patch(
                f"{BASE}/{theirs.id}", json={"name": "Mine now"}, headers=headers(csrf_token)
            ).status_code,
            client.delete(f"{BASE}/{theirs.id}", headers=headers(csrf_token)).status_code,
        ]

        assert answers == [404, 404]
        assert session.get(SavedView, theirs.id) is not None

    def test_the_same_name_can_be_kept_by_each_account(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        self.other(session)

        assert save(client, csrf_token, name="Theirs").status_code == 201

    def test_each_account_has_its_own_default(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        theirs = self.other(session)
        theirs.is_default = True
        session.commit()

        save(client, csrf_token, name="Mine", default=True)

        assert session.get(SavedView, theirs.id) is not None
        session.refresh(theirs)
        assert theirs.is_default is True
