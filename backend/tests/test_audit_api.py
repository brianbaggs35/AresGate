from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import audit
from app.audit import Action, Outcome
from app.models import User

# Later than the sign-in the tests start with, which is recorded at the real time, so a filter
# that starts at NOW leaves that event out however long the tests run.
NOW = datetime(2099, 1, 1, 12, 0, tzinfo=UTC)


def add(
    db: Session,
    action: Action = Action.LOGOUT,
    outcome: Outcome = Outcome.SUCCESS,
    *,
    at: datetime = NOW,
    username: str | None = None,
) -> int:
    event = audit.record(db, action, outcome, username=username, now=at)
    db.commit()
    return event.id


def events(client: TestClient, **query: object) -> list[dict[str, object]]:
    response = client.get("/api/audit/events", params=query)  # type: ignore[arg-type]
    assert response.status_code == 200
    return response.json()["events"]  # type: ignore[no-any-return]


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    response = client.get("/api/audit/events")

    assert response.status_code == 401
    assert response.json() == {"detail": "You're not signed in."}


def test_lists_events_newest_first_with_what_was_kept(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    older = add(session, Action.LOGIN_FAILED, Outcome.FAILURE, at=NOW - timedelta(days=1))
    newer = add(session, Action.LOGOUT, at=NOW)
    # Signing in, which these tests did to be allowed to look, is in the log too.
    only = {"action": ["auth.login_failed", "auth.logout"]}

    body = client.get("/api/audit/events", params={**only, "since": NOW.isoformat()}).json()
    assert [event["id"] for event in body["events"]] == [newer]
    assert body["next_before"] is None

    listed = events(client, **only)
    assert [event["id"] for event in listed] == [newer, older]
    assert listed[0] == {
        "id": newer,
        "occurred_at": "2099-01-01T12:00:00Z",
        "action": "auth.logout",
        "outcome": "success",
        "user_id": None,
        "username": None,
        "client_address": None,
        "user_agent": None,
        "detail": None,
    }


def test_filters_by_action_outcome_and_username(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    failed = add(session, Action.LOGIN_FAILED, Outcome.FAILURE, username="brian")
    add(session, Action.LOGIN_FAILED, Outcome.FAILURE, username="someone")
    logout = add(session, Action.LOGOUT, username="brian")

    def ids(**query: object) -> list[object]:
        return [event["id"] for event in events(client, **query, since="2099-01-01T00:00:00Z")]

    assert ids(action="auth.login_failed", username="brian") == [failed]
    assert ids(action=["auth.logout", "auth.login_failed"], username="brian") == [logout, failed]
    assert ids(outcome="failure", username="brian") == [failed]


def test_filters_by_time(client: TestClient, csrf_token: str, session: Session) -> None:
    add(session, at=NOW - timedelta(days=3))
    inside = add(session, at=NOW - timedelta(days=2))
    add(session, at=NOW)

    listed = events(
        client,
        since=(NOW - timedelta(days=2, hours=1)).isoformat(),
        until=(NOW - timedelta(days=1)).isoformat(),
    )

    assert [event["id"] for event in listed] == [inside]


def test_pages_through_the_events(client: TestClient, csrf_token: str, session: Session) -> None:
    ids = [add(session, at=NOW + timedelta(minutes=minute)) for minute in range(4)]
    since = NOW.isoformat()

    first = client.get("/api/audit/events", params={"limit": 3, "since": since}).json()
    second = client.get(
        "/api/audit/events",
        params={"limit": 3, "since": since, "before": first["next_before"]},
    ).json()

    assert [event["id"] for event in first["events"]] == ids[:0:-1]
    assert first["next_before"] == ids[1]
    assert [event["id"] for event in second["events"]] == [ids[0]]
    assert second["next_before"] is None


def test_refuses_what_makes_no_sense(client: TestClient, csrf_token: str) -> None:
    for query in (
        {"limit": 0},
        {"limit": audit.MAX_PAGE + 1},
        {"before": 0},
        {"outcome": "maybe"},
        {"since": "2099-01-01T12:00:00"},  # no time zone, so it could mean any of 24 times
        {"until": "yesterday"},
        {"username": "x" * 65},
        {"action": "x" * 65},
    ):
        assert client.get("/api/audit/events", params=query).status_code == 422, query


def test_it_is_read_only(client: TestClient, csrf_token: str) -> None:
    for method in (client.post, client.put, client.patch, client.delete):
        response = method("/api/audit/events", headers={"X-CSRF-Token": csrf_token})
        assert response.status_code == 405
