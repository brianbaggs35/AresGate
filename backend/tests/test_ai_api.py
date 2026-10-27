import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import String, literal_column, select, text
from sqlalchemy import table as sa_table
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.ai import catalog
from app.audit import Action, Outcome
from app.config import Settings
from app.models import ApiCall, AuditEvent, StoredCredential, User
from app.security import credential_store
from app.security.credential_store import Kind
from e2e import stand_ins
from tests.helpers import OTHER_ORIGIN
from tests.stubs import Serve

BASE = "/api/ai"
KEY = "sk-an-api-key-for-tests-0123456789"
HOME_URL = "http://192.168.1.50:11434"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def put(client: TestClient, token: str, key: str, body: object):
    return client.put(f"{BASE}/providers/{key}", json=body, headers=headers(token))


def post(client: TestClient, token: str, path: str):
    return client.post(f"{BASE}{path}", headers=headers(token))


def use(client: TestClient, token: str, **body: object):
    return client.put(f"{BASE}/use", json=body, headers=headers(token))


def audited(session: Session, action: Action) -> list[AuditEvent]:
    session.expire_all()
    return list(
        session.scalars(
            select(AuditEvent).where(AuditEvent.action == action.value).order_by(AuditEvent.id)
        )
    )


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    for method, path in (
        ("get", BASE),
        ("put", f"{BASE}/providers/openai"),
        ("delete", f"{BASE}/providers/openai"),
        ("post", f"{BASE}/providers/openai/test"),
        ("post", f"{BASE}/providers/ollama/models"),
        ("put", f"{BASE}/use"),
    ):
        assert client.request(method, path).status_code == 401, (method, path)


def test_a_change_needs_the_security_token_and_an_origin_from_the_app(
    client: TestClient, csrf_token: str
) -> None:
    for method, path in (
        ("put", f"{BASE}/providers/openai"),
        ("delete", f"{BASE}/providers/openai"),
        ("post", f"{BASE}/providers/openai/test"),
        ("post", f"{BASE}/providers/ollama/models"),
        ("put", f"{BASE}/use"),
    ):
        assert client.request(method, path, json={}).status_code == 403, (method, path)
        foreign = client.request(
            method, path, json={}, headers={**headers(csrf_token), "Origin": OTHER_ORIGIN}
        )
        assert foreign.status_code == 403, (method, path)


def test_every_provider_is_listed_with_its_models_and_prices(
    client: TestClient, csrf_token: str
) -> None:
    response = client.get(BASE)

    assert response.status_code == 200
    body = response.json()
    assert (body["enabled"], body["provider"], body["priced_as_of"]) == (False, None, "2026-10-27")
    assert [item["key"] for item in body["providers"]] == [
        "anthropic",
        "openai",
        "ollama",
        "ollama_cloud",
    ]
    anthropic, openai, ollama, cloud = body["providers"]
    assert anthropic["models"][0]["id"] == "claude-haiku-5-5"
    assert anthropic["default_model"] == "claude-haiku-5-5"
    assert openai["default_model"] == "gpt-6-luna"
    assert anthropic["models"][0]["price"] == {
        "input": 0.1,
        "output": 0.5,
        "cached_input": 0.01,
        "long_over": 100000,
        "long_input": 0.5,
        "long_output": 2.5,
    }
    assert openai["models"][0]["price"]["long_over"] is None
    assert (ollama["kind"], ollama["takes_url"], ollama["needs_key"], ollama["models"]) == (
        "local",
        True,
        False,
        [],
    )
    assert (cloud["kind"], cloud["takes_url"], cloud["needs_key"]) == ("cloud", False, True)
    assert all(
        (item["configured"], item["key_saved"], item["status"]) == (False, False, "not_connected")
        for item in body["providers"]
    )
    assert anthropic["key_url"].startswith("https://")


def test_a_provider_can_be_set_up_and_its_key_is_never_sent_back(
    client: TestClient, csrf_token: str, session: Session, settings: Settings, account: User
) -> None:
    response = put(client, csrf_token, "anthropic", {"model": "claude-haiku-5-5", "api_key": KEY})

    assert response.status_code == 200
    body = response.json()
    assert (body["configured"], body["key_saved"], body["status"]) == (True, True, "untested")
    assert (body["model"], body["base_url"]) == ("claude-haiku-5-5", None)
    assert KEY not in response.text
    assert KEY not in client.get(BASE).text
    session.expire_all()
    assert (
        credential_store.reveal(session, settings, Kind.AI_PROVIDER, "anthropic", "api_key") == KEY
    )
    [event] = audited(session, Action.AI_PROVIDER_SAVED)
    assert (event.outcome, event.detail) == (Outcome.SUCCESS.value, {"provider": "anthropic"})
    assert KEY not in json.dumps(event.detail)


def test_the_key_is_encrypted_in_the_database_and_nowhere_else(
    client: TestClient, csrf_token: str, session: Session, engine: Engine
) -> None:
    put(client, csrf_token, "openai", {"model": "gpt-6-luna", "api_key": KEY})
    client.get(BASE)

    session.expire_all()
    [sealed] = session.scalars(select(StoredCredential))
    assert KEY not in sealed.value_sealed
    assert sealed.value_sealed.startswith("v1.")
    # Not in any column of any table, whatever its name.
    with engine.connect() as connection:
        for [table] in connection.execute(
            text("select tablename from pg_tables where schemaname = current_schema()")
        ):
            rows = connection.execute(
                select(literal_column("t::text", String)).select_from(sa_table(table).alias("t"))
            ).scalars()
            assert not any(KEY in row for row in rows), table


def test_a_provider_that_is_not_filled_in_properly_is_refused_and_nothing_is_kept(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    refused = put(client, csrf_token, "anthropic", {"model": "claude-nothing"})

    assert refused.status_code == 422
    assert [(item["loc"], item["type"]) for item in refused.json()["detail"]] == [
        (["body", "model"], "value_error"),
        (["body", "api_key"], "value_error"),
    ]
    assert client.get(BASE).json()["providers"][0]["configured"] is False
    assert audited(session, Action.AI_PROVIDER_SAVED) == []


def test_extra_fields_and_a_provider_that_does_not_exist_are_refused(
    client: TestClient, csrf_token: str
) -> None:
    extra = put(client, csrf_token, "openai", {"model": "gpt-6-luna", "api_key": KEY, "x": 1})
    nothing = put(client, csrf_token, "nothing", {"model": "m"})

    assert extra.status_code == 422
    assert nothing.status_code == 404
    assert nothing.json() == {"detail": "There is no such AI provider."}
    for method, path in (
        ("delete", f"{BASE}/providers/nothing"),
        ("post", f"{BASE}/providers/nothing/test"),
        ("post", f"{BASE}/providers/nothing/models"),
    ):
        assert client.request(method, path, headers=headers(csrf_token)).status_code == 404
    assert (
        client.put(f"{BASE}/providers/Not A Name", json={}, headers=headers(csrf_token)).status_code
        == 422
    )


def test_a_provider_is_set_up_again_without_typing_the_key_again(
    client: TestClient, csrf_token: str
) -> None:
    put(client, csrf_token, "anthropic", {"model": "claude-haiku-5-5", "api_key": KEY})

    again = put(client, csrf_token, "anthropic", {"model": "claude-sonnet-5-5"})

    assert again.status_code == 200
    assert again.json()["model"] == "claude-sonnet-5-5"
    assert again.json()["key_saved"] is True


def test_a_provider_is_tested_and_how_it_went_is_kept(
    client: TestClient, csrf_token: str, app: FastAPI, serve: Serve, session: Session
) -> None:
    server = serve(stand_ins.anthropic(KEY, {"claude-haiku-5-5"}))
    app.state.ai_origins["anthropic"] = server.url
    put(client, csrf_token, "anthropic", {"model": "claude-haiku-5-5", "api_key": KEY})

    response = post(client, csrf_token, "/providers/anthropic/test")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["message"] == "claude-haiku-5-5 answered. It counted 14 tokens in and 1 out."
    assert body["provider"]["status"] == "connected"
    assert body["provider"]["last_success_at"] is not None
    assert KEY not in response.text
    [event] = audited(session, Action.AI_PROVIDER_TESTED)
    assert event.outcome == Outcome.SUCCESS.value
    [call] = session.scalars(select(ApiCall))
    assert (call.integration, call.connection, call.path) == ("ai", "anthropic", "/v1/messages")


def test_a_key_that_is_refused_is_reported_without_quoting_anything(
    client: TestClient, csrf_token: str, app: FastAPI, serve: Serve, session: Session
) -> None:
    server = serve(stand_ins.openai("a-different-key", {"gpt-6-luna"}))
    app.state.ai_origins["openai"] = server.url
    put(client, csrf_token, "openai", {"model": "gpt-6-luna", "api_key": KEY})

    response = post(client, csrf_token, "/providers/openai/test")

    body = response.json()
    assert body["ok"] is False
    assert body["message"].startswith("OpenAI didn't accept the API key")
    assert (body["provider"]["status"], body["provider"]["last_error"]) == (
        "problem",
        body["message"],
    )
    assert KEY not in response.text
    [event] = audited(session, Action.AI_PROVIDER_TESTED)
    assert event.outcome == Outcome.FAILURE.value


def test_a_provider_that_is_not_set_up_cannot_be_tested_or_asked_for_models(
    client: TestClient, csrf_token: str
) -> None:
    for path in ("/providers/openai/test", "/providers/ollama/models"):
        response = post(client, csrf_token, path)
        assert response.status_code == 409, path
        assert response.json() == {"detail": "Set it up first."}


def test_a_key_that_has_gone_missing_is_said_so_when_testing(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    put(client, csrf_token, "openai", {"model": "gpt-6-luna", "api_key": KEY})
    credential_store.remove(session, Kind.AI_PROVIDER, "openai", "api_key")
    session.commit()

    for path in ("/providers/openai/test", "/providers/openai/models"):
        body = post(client, csrf_token, path).json() if "test" in path else None
        if body is not None:
            assert body["ok"] is False
            assert "missing or can't be opened" in body["message"]


def test_the_models_an_ollama_has_are_fetched_and_kept(
    client: TestClient, csrf_token: str, serve: Serve, session: Session
) -> None:
    server = serve(stand_ins.ollama("", {"qwen3:8b", "llama3.2:3b"}))
    put(client, csrf_token, "ollama", {"model": "", "base_url": server.url})

    response = post(client, csrf_token, "/providers/ollama/models")

    body = response.json()
    assert (body["ok"], body["message"]) == (True, "It has 2 models.")
    assert [item["name"] for item in body["provider"]["found"]] == ["llama3.2:3b", "qwen3:8b"]
    assert body["provider"]["found_at"] is not None
    assert body["provider"]["status"] == "connected"
    assert [item["name"] for item in client.get(BASE).json()["providers"][2]["found"]] == [
        "llama3.2:3b",
        "qwen3:8b",
    ]
    [event] = audited(session, Action.AI_MODELS_FETCHED)
    assert event.outcome == Outcome.SUCCESS.value


def test_one_model_is_not_two(client: TestClient, csrf_token: str, serve: Serve) -> None:
    server = serve(stand_ins.ollama("", {"qwen3:8b"}))
    put(client, csrf_token, "ollama", {"model": "", "base_url": server.url})

    assert (
        post(client, csrf_token, "/providers/ollama/models").json()["message"] == "It has 1 model."
    )


def test_ollamas_cloud_fetches_its_models_once_it_has_a_key(
    client: TestClient, csrf_token: str, app: FastAPI, serve: Serve
) -> None:
    server = serve(stand_ins.ollama(KEY, {"gemma4:31b"}))
    app.state.ai_origins["ollama_cloud"] = server.url
    put(client, csrf_token, "ollama_cloud", {"model": "", "api_key": KEY})

    response = post(client, csrf_token, "/providers/ollama_cloud/models")

    assert response.json()["ok"] is True
    assert response.json()["provider"]["found"][0]["name"] == "gemma4:31b"
    assert KEY not in response.text


def test_models_that_could_not_be_fetched_say_why(
    client: TestClient, csrf_token: str, app: FastAPI, serve: Serve, session: Session
) -> None:
    server = serve(stand_ins.ollama("another-key", {"gemma4:31b"}))
    app.state.ai_origins["ollama_cloud"] = server.url
    put(client, csrf_token, "ollama_cloud", {"model": "", "api_key": KEY})

    body = post(client, csrf_token, "/providers/ollama_cloud/models").json()

    assert body["ok"] is False
    assert body["message"].startswith("Ollama Cloud didn't accept the API key")
    assert body["provider"]["status"] == "problem"
    assert body["provider"]["found"] == []
    [event] = audited(session, Action.AI_MODELS_FETCHED)
    assert event.outcome == Outcome.FAILURE.value


def test_models_cannot_be_fetched_for_a_provider_with_a_list_of_its_own(
    client: TestClient, csrf_token: str
) -> None:
    put(client, csrf_token, "openai", {"model": "gpt-6-luna", "api_key": KEY})

    response = post(client, csrf_token, "/providers/openai/models")

    assert response.status_code == 409


def test_a_missing_key_is_said_so_when_fetching_models(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    put(client, csrf_token, "ollama_cloud", {"model": "", "api_key": KEY})
    credential_store.remove(session, Kind.AI_PROVIDER, "ollama_cloud", "api_key")
    session.commit()

    body = post(client, csrf_token, "/providers/ollama_cloud/models").json()

    assert body["ok"] is False
    assert "missing or can't be opened" in body["message"]


def test_an_ollama_must_be_at_home(client: TestClient, csrf_token: str) -> None:
    refused = put(client, csrf_token, "ollama", {"model": "", "base_url": "http://8.8.8.8:11434"})

    assert refused.status_code == 422
    assert refused.json()["detail"][0]["loc"] == ["body", "base_url"]


def test_ai_is_turned_on_and_off_for_a_provider_that_is_ready(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    put(client, csrf_token, "anthropic", {"model": "claude-haiku-5-5", "api_key": KEY})

    on = use(client, csrf_token, enabled=True, provider="anthropic")
    off = use(client, csrf_token, enabled=False, provider=None)

    assert (on.status_code, on.json()["enabled"], on.json()["provider"]) == (200, True, "anthropic")
    assert (off.json()["enabled"], off.json()["provider"]) == (False, None)
    events = audited(session, Action.AI_CHOSEN)
    assert sorted(str((event.detail or {}).get("provider")) for event in events) == [
        "anthropic",
        "none",
    ]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"enabled": True, "provider": "openai"}, "provider"),
        ({"enabled": True}, "provider"),
    ],
)
def test_ai_is_not_turned_on_for_a_provider_that_is_not_ready(
    client: TestClient, csrf_token: str, body: dict[str, object], field: str, session: Session
) -> None:
    response = use(client, csrf_token, **body)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]
    assert audited(session, Action.AI_CHOSEN) == []
    assert client.get(BASE).json()["enabled"] is False


def test_removing_a_provider_forgets_its_key_and_stops_using_ai_if_it_was_asked(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    put(client, csrf_token, "anthropic", {"model": "claude-haiku-5-5", "api_key": KEY})
    use(client, csrf_token, enabled=True, provider="anthropic")

    response = client.delete(f"{BASE}/providers/anthropic", headers=headers(csrf_token))

    assert response.status_code == 204
    listed = client.get(BASE).json()
    assert (listed["enabled"], listed["provider"]) == (False, None)
    assert listed["providers"][0]["configured"] is False
    assert listed["providers"][0]["key_saved"] is False
    assert session.scalars(select(StoredCredential)).first() is None
    [event] = audited(session, Action.AI_PROVIDER_REMOVED)
    assert event.detail == {"provider": "anthropic"}


def test_removing_what_is_not_set_up_is_not_found(client: TestClient, csrf_token: str) -> None:
    response = client.delete(f"{BASE}/providers/openai", headers=headers(csrf_token))

    assert response.status_code == 404
    assert response.json() == {"detail": "It isn't set up."}


def test_the_catalog_and_the_listing_agree(client: TestClient, csrf_token: str) -> None:
    listed = client.get(BASE).json()["providers"]

    for out, definition in zip(listed, catalog.PROVIDERS, strict=True):
        assert [model["id"] for model in out["models"]] == [m.id for m in definition.models]
        assert out["pricing_url"] == definition.pricing_url
        assert out["models_url"] == definition.models_url
