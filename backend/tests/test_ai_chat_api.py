"""The chat from the web app: starting a conversation, asking in it, asking again after an answer
that could not be made, and deleting it."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import chat
from app.config import Settings
from app.models import AiConversation, AiMessage, User, utcnow
from tests.stubs import Serve
from tests.test_ai_chat import Scripted, look, reply
from tests.test_ai_service import KEY
from tests.test_ai_triage import incident, ready

BASE = "/api/ai/conversations"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def begin(client: TestClient, token: str, text: str = "Anything?") -> Any:
    return client.post(BASE, headers=headers(token), json={"text": text})


def provider(app: FastAPI, serve: Serve, scripted: Scripted) -> None:
    app.state.ai_origins["anthropic"] = serve(scripted).url


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", BASE),
        ("post", BASE),
        ("get", f"{BASE}/1"),
        ("post", f"{BASE}/1/messages"),
        ("post", f"{BASE}/1/retry"),
        ("delete", f"{BASE}/1"),
    ],
)
def test_it_is_only_for_someone_signed_in(
    client: TestClient, account: User, method: str, path: str
) -> None:
    assert client.request(method, path).status_code == 401


def test_there_are_no_conversations_to_begin_with(client: TestClient, csrf_token: str) -> None:
    assert client.get(BASE).json() == []


def test_a_conversation_begins_with_a_question_and_the_answer_comes_with_it(
    client: TestClient,
    csrf_token: str,
    app: FastAPI,
    serve: Serve,
    session: Session,
    settings: Settings,
) -> None:
    ready(session, settings)
    found = incident(session, severity=3)
    session.commit()
    provider(
        app,
        serve,
        Scripted(
            reply(lookups=[look("open_incidents")], answer=""),
            reply(answer=f"See [incident {found.id}].", cites=[f"incident {found.id}"]),
        ),
    )

    response = begin(client, csrf_token, "What needs me?")

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "What needs me?"
    user, assistant = body["messages"]
    assert (user["role"], user["text"], user["ok"]) == ("user", "What needs me?", True)
    assert (assistant["role"], assistant["ok"]) == ("assistant", True)
    assert assistant["text"] == f"See [incident {found.id}]."
    assert assistant["lookups"] == [{"tool": "open_incidents", "summary": "1 open incident"}]
    assert assistant["cites"] == [
        {"kind": "incident", "key": str(found.id), "label": f"Incident {found.id}"}
    ]
    assert assistant["actions"] == []
    assert len(assistant["call_ids"]) == 2
    assert KEY not in response.text
    assert client.get(f"{BASE}/{body['id']}").json() == body


def test_with_ai_off_the_answer_says_how_to_turn_it_on(client: TestClient, csrf_token: str) -> None:
    body = begin(client, csrf_token).json()

    assistant = body["messages"][1]
    assert assistant["ok"] is False
    assert assistant["text"].startswith("AI is turned off.")
    assert assistant["call_ids"] == []


@pytest.mark.parametrize("text", ["", "   ", "x" * (chat.MAX_QUESTION + 1)])
def test_a_question_has_to_say_something_and_not_too_much(
    client: TestClient, csrf_token: str, text: str
) -> None:
    assert begin(client, csrf_token, text).status_code == 422
    assert client.get(BASE).json() == []


def test_a_question_is_kept_without_the_spaces_around_it(
    client: TestClient, csrf_token: str
) -> None:
    body = begin(client, csrf_token, "  Hello?  ").json()

    assert body["messages"][0]["text"] == "Hello?"


def test_it_needs_the_token_that_says_the_page_asked(client: TestClient, csrf_token: str) -> None:
    assert client.post(BASE, json={"text": "Hi"}).status_code == 403


def test_the_conversations_are_listed_with_the_latest_word_first(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    first = begin(client, csrf_token, "First").json()
    second = begin(client, csrf_token, "Second").json()
    client.post(
        f"{BASE}/{first['id']}/messages", headers=headers(csrf_token), json={"text": "More"}
    )

    listed = client.get(BASE).json()

    assert [(item["id"], item["title"], item["messages"]) for item in listed] == [
        (first["id"], "First", 4),
        (second["id"], "Second", 2),
    ]


def test_a_conversation_that_is_not_there_is_not_found(client: TestClient, csrf_token: str) -> None:
    for method, path in [
        ("get", f"{BASE}/4040"),
        ("post", f"{BASE}/4040/messages"),
        ("post", f"{BASE}/4040/retry"),
        ("delete", f"{BASE}/4040"),
    ]:
        response = client.request(method, path, headers=headers(csrf_token), json={"text": "x"})

        assert response.status_code == 404, path
        assert response.json() == {"detail": "There is no such conversation."}


def test_another_question_goes_on_in_the_same_conversation(
    client: TestClient,
    csrf_token: str,
    app: FastAPI,
    serve: Serve,
    session: Session,
    settings: Settings,
) -> None:
    ready(session, settings)
    scripted = Scripted(reply(answer="One."), reply(answer="Two."))
    provider(app, serve, scripted)
    started = begin(client, csrf_token, "One?").json()

    response = client.post(
        f"{BASE}/{started['id']}/messages", headers=headers(csrf_token), json={"text": "Two?"}
    )

    assert response.status_code == 200
    assert [message["text"] for message in response.json()["messages"]] == [
        "One?",
        "One.",
        "Two?",
        "Two.",
    ]
    assert "Owner: One?" in scripted.prompts[1]


def test_a_question_asked_from_a_page_is_answered_about_what_is_on_it_and_may_suggest_what_to_do(
    client: TestClient,
    csrf_token: str,
    app: FastAPI,
    serve: Serve,
    session: Session,
    settings: Settings,
) -> None:
    ready(session, settings)
    found = incident(session, severity=3, title="Guessing at ssh")
    session.commit()
    scripted = Scripted(
        reply(
            answer="It is a scan.",
            actions=[
                {
                    "kind": "status",
                    "target": f"incident {found.id}",
                    "value": "resolved",
                    "note": None,
                }
            ],
        ),
        reply(answer="Fine."),
    )
    provider(app, serve, scripted)

    started = client.post(
        BASE,
        headers=headers(csrf_token),
        json={"text": "What is this?", "page": {"kind": "incident", "id": found.id}},
    ).json()
    asked_again = client.post(
        f"{BASE}/{started['id']}/messages",
        headers=headers(csrf_token),
        json={"text": "And here?", "page": {"kind": "logs", "query": "source:wazuh"}},
    )

    assert f"The owner has the page of incident {found.id} open." in scripted.prompts[0]
    assert "Guessing at ssh" in scripted.prompts[0]
    assert started["messages"][1]["actions"] == [
        {
            "kind": "status",
            "target_kind": "incident",
            "target_key": str(found.id),
            "value": "resolved",
            "note": None,
            "label": f"Mark Incident {found.id} as resolved",
        }
    ]
    assert asked_again.status_code == 200
    assert "searching for: source:wazuh" in scripted.prompts[1]
    assert client.get(f"{BASE}/{started['id']}").json()["messages"][1]["actions"] != []


@pytest.mark.parametrize(
    "page",
    [
        {"kind": "mystery"},
        {"kind": "incident", "id": 0},
        {"kind": "incident", "id": "x"},
        {"kind": "logs", "query": "x" * (chat.MAX_SEARCH + 1)},
        {"kind": "other", "title": "x" * (chat.MAX_TITLE + 1)},
        {"kind": "device", "address": "x" * 46},
        {"kind": "logs", "surprise": True},
    ],
)
def test_a_page_that_makes_no_sense_is_refused(
    client: TestClient, csrf_token: str, page: dict[str, Any]
) -> None:
    response = client.post(
        BASE, headers=headers(csrf_token), json={"text": "What is this?", "page": page}
    )

    assert response.status_code == 422


def test_a_conversation_that_has_got_long_is_asked_to_begin_again(
    client: TestClient, csrf_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(chat, "MAX_MESSAGES", 2)
    started = begin(client, csrf_token).json()

    response = client.post(
        f"{BASE}/{started['id']}/messages", headers=headers(csrf_token), json={"text": "More"}
    )

    assert response.status_code == 409
    assert "Begin a new one" in response.json()["detail"]
    assert len(client.get(f"{BASE}/{started['id']}").json()["messages"]) == 2


def test_after_an_answer_that_failed_the_question_can_be_asked_again(
    client: TestClient,
    csrf_token: str,
    app: FastAPI,
    serve: Serve,
    session: Session,
    settings: Settings,
) -> None:
    started = begin(client, csrf_token, "Anything?").json()
    assert started["messages"][1]["ok"] is False
    ready(session, settings)
    provider(app, serve, Scripted(reply(answer="Now it works.")))

    response = client.post(f"{BASE}/{started['id']}/retry", headers=headers(csrf_token))

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert [(m["role"], m["text"], m["ok"]) for m in messages] == [
        ("user", "Anything?", True),
        ("assistant", "Now it works.", True),
    ]
    assert len(session.scalars(select(AiMessage)).all()) == 2


def test_there_is_nothing_to_ask_again_unless_the_last_answer_failed(
    client: TestClient,
    csrf_token: str,
    app: FastAPI,
    serve: Serve,
    session: Session,
    settings: Settings,
) -> None:
    ready(session, settings)
    provider(app, serve, Scripted(reply()))
    started = begin(client, csrf_token).json()
    empty = AiConversation(title="empty", created_at=utcnow(), updated_at=utcnow())
    session.add(empty)
    session.commit()

    for conversation_id in (started["id"], empty.id):
        response = client.post(f"{BASE}/{conversation_id}/retry", headers=headers(csrf_token))

        assert response.status_code == 409
        assert response.json() == {"detail": "There is no failed answer to ask again."}


def test_a_conversation_is_deleted_with_everything_said_in_it(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    started = begin(client, csrf_token).json()
    other = begin(client, csrf_token, "Other").json()

    response = client.delete(f"{BASE}/{started['id']}", headers=headers(csrf_token))

    assert response.status_code == 204
    assert client.get(f"{BASE}/{started['id']}").status_code == 404
    assert [item["id"] for item in client.get(BASE).json()] == [other["id"]]
    session.expire_all()
    assert {m.conversation_id for m in session.scalars(select(AiMessage))} == {other["id"]}
