from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import Action, Outcome
from app.config import Settings
from app.models import AuditEvent, StoredCredential
from app.security import credential_store
from app.security.credential_store import Kind

BASE = "/api/credentials"
API_KEY = "a-firewall-api-key-for-tests"
FIREWALL = f"{BASE}/integration/opnsense/api_key"


def put(client: TestClient, token: str, value: object = API_KEY, path: str = FIREWALL):
    return client.put(path, json={"value": value}, headers={"X-CSRF-Token": token})


def test_a_secret_can_be_kept_and_its_value_is_never_sent_back(
    client: TestClient, csrf_token: str, session: Session, settings: Settings
) -> None:
    response = put(client, csrf_token)

    assert response.status_code == 200
    assert response.json()["kind"] == "integration"
    assert (response.json()["name"], response.json()["field"]) == ("opnsense", "api_key")
    assert API_KEY not in response.text
    session.expire_all()
    revealed = credential_store.reveal(session, settings, Kind.INTEGRATION, "opnsense", "api_key")
    assert revealed == API_KEY


def test_the_list_says_which_secrets_are_set_and_nothing_more(
    client: TestClient, csrf_token: str
) -> None:
    put(client, csrf_token)
    put(client, csrf_token, "another-secret-for-tests", f"{BASE}/ai_provider/anthropic/api_key")

    response = client.get(BASE)

    assert response.status_code == 200
    listed = response.json()
    assert [(item["kind"], item["name"], item["field"]) for item in listed] == [
        ("ai_provider", "anthropic", "api_key"),
        ("integration", "opnsense", "api_key"),
    ]
    assert all(
        set(item) == {"kind", "name", "field", "created_at", "updated_at"} for item in listed
    )
    assert API_KEY not in response.text
    assert "another-secret-for-tests" not in response.text


def test_nothing_returns_a_secret_after_it_is_set(client: TestClient, csrf_token: str) -> None:
    put(client, csrf_token)

    for path in (BASE, FIREWALL, f"{BASE}/integration/opnsense", f"{BASE}/integration"):
        response = client.get(path)
        assert API_KEY not in response.text, path


def test_setting_a_secret_again_replaces_it(
    client: TestClient, csrf_token: str, session: Session, settings: Settings
) -> None:
    first = put(client, csrf_token, "the first").json()
    second = put(client, csrf_token, "the second").json()

    assert second["created_at"] == first["created_at"]
    assert second["updated_at"] >= first["updated_at"]
    session.expire_all()
    revealed = credential_store.reveal(session, settings, Kind.INTEGRATION, "opnsense", "api_key")
    assert revealed == "the second"
    assert len(client.get(BASE).json()) == 1


def test_a_secret_can_be_deleted(client: TestClient, csrf_token: str, session: Session) -> None:
    put(client, csrf_token)

    response = client.delete(FIREWALL, headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 204
    assert client.get(BASE).json() == []
    session.expire_all()
    assert session.scalars(select(StoredCredential)).all() == []


def test_deleting_a_secret_that_is_not_kept_says_so(client: TestClient, csrf_token: str) -> None:
    response = client.delete(FIREWALL, headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 404


def test_each_change_is_in_the_audit_log_without_the_secret(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    put(client, csrf_token)
    client.delete(FIREWALL, headers={"X-CSRF-Token": csrf_token})

    session.expire_all()
    events = list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action.in_((Action.CREDENTIAL_STORED, Action.CREDENTIAL_DELETED)))
            .order_by(AuditEvent.id)
        )
    )
    assert [event.action for event in events] == ["credential.stored", "credential.deleted"]
    for event in events:
        assert event.outcome == Outcome.SUCCESS.value
        assert event.username == "brian"
        assert event.detail == {"kind": "integration", "name": "opnsense", "field": "api_key"}
        assert API_KEY not in str(event.detail)


def test_the_failed_requests_do_not_change_the_audit_log(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    client.delete(FIREWALL, headers={"X-CSRF-Token": csrf_token})
    put(client, csrf_token, "")

    session.expire_all()
    credential_events = session.scalars(
        select(AuditEvent).where(AuditEvent.action.like("credential.%"))
    ).all()
    assert credential_events == []


def test_a_value_that_is_missing_empty_blank_or_too_long_is_refused(
    client: TestClient, csrf_token: str
) -> None:
    for value in ("", "   \n\t", "x" * 4097, None, 12):
        assert put(client, csrf_token, value).status_code == 422, value
    no_body = client.put(FIREWALL, json={}, headers={"X-CSRF-Token": csrf_token})
    assert no_body.status_code == 422
    assert client.get(BASE).json() == []


def test_a_refused_value_is_not_quoted_back(client: TestClient, csrf_token: str) -> None:
    too_long = "hunter2-" * 600

    response = put(client, csrf_token, too_long)

    assert response.status_code == 422
    assert "hunter2" not in response.text
    [problem] = response.json()["detail"]
    assert problem["loc"] == ["body", "value"]
    assert "input" not in problem


def test_the_longest_value_is_accepted(client: TestClient, csrf_token: str) -> None:
    assert put(client, csrf_token, "x" * 4096).status_code == 200


def test_names_must_be_short_lowercase_words(client: TestClient, csrf_token: str) -> None:
    for path in (
        f"{BASE}/integration/Opnsense/api_key",
        f"{BASE}/integration/opnsense/api key",
        f"{BASE}/integration/{'x' * 64}/api_key",
        f"{BASE}/integration/-opnsense/api_key",
        f"{BASE}/nonsense/opnsense/api_key",
    ):
        assert put(client, csrf_token, path=path).status_code == 422, path
    assert client.get(BASE).json() == []


def test_signing_in_is_required(client: TestClient, account: object) -> None:
    listed = client.get(BASE)
    replaced = client.put(FIREWALL, json={"value": API_KEY})
    deleted = client.delete(FIREWALL)

    assert (listed.status_code, replaced.status_code, deleted.status_code) == (401, 401, 401)


def test_a_change_needs_the_security_token_of_the_sign_in(
    client: TestClient, csrf_token: str
) -> None:
    replaced = client.put(FIREWALL, json={"value": API_KEY})
    deleted = client.delete(FIREWALL)

    assert (replaced.status_code, deleted.status_code) == (403, 403)
    assert client.get(BASE).json() == []


def test_a_change_must_come_from_aresgate_itself(client: TestClient, csrf_token: str) -> None:
    response = client.put(
        FIREWALL,
        json={"value": API_KEY},
        headers={"X-CSRF-Token": csrf_token, "Origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert client.get(BASE).json() == []
