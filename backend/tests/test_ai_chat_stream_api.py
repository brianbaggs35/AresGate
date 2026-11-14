"""Asking the assistant from the web app and having the answer as it is written: the same
conversations as ``/api/ai/conversations``, with the lookups and the answer told as server-sent
events."""

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai import chat
from app.config import Settings
from app.models import AiConversation, AiMessage, User, utcnow
from tests.stubs import Serve
from tests.test_ai_chat import look, reply
from tests.test_ai_chat_stream import Streamed
from tests.test_ai_service import KEY
from tests.test_ai_triage import incident, ready

BASE = "/api/ai/conversations"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def events_of(text: str) -> list[tuple[str, Any]]:
    """The server-sent events in a response: each one's name and what its data says."""
    found: list[tuple[str, Any]] = []
    for block in text.strip().split("\n\n"):
        name, data = block.split("\n")
        assert name.startswith("event: ")
        assert data.startswith("data: ")
        found.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return found


def ask_streamed(
    client: TestClient,
    token: str,
    path: str = f"{BASE}/stream",
    text: str = "Anything?",
    **more: Any,
) -> Any:
    return client.post(path, headers=headers(token), json={"text": text, **more})


def provider(app: FastAPI, serve: Serve, streamed: Streamed) -> None:
    app.state.ai_origins["anthropic"] = serve(streamed).url


@pytest.mark.parametrize("path", [f"{BASE}/stream", f"{BASE}/1/stream"])
def test_it_is_only_for_someone_signed_in(client: TestClient, account: User, path: str) -> None:
    assert client.post(path, json={"text": "Hi"}).status_code == 401


@pytest.mark.parametrize("path", [f"{BASE}/stream", f"{BASE}/1/stream"])
def test_it_needs_the_token_that_says_the_page_asked(
    client: TestClient, csrf_token: str, path: str
) -> None:
    assert client.post(path, json={"text": "Hi"}).status_code == 403


@pytest.mark.parametrize("text", ["", "   ", "x" * (chat.MAX_QUESTION + 1)])
def test_a_question_has_to_say_something_and_not_too_much(
    client: TestClient, csrf_token: str, text: str
) -> None:
    assert ask_streamed(client, csrf_token, text=text).status_code == 422
    assert client.get(BASE).json() == []


def test_a_conversation_begins_with_a_question_and_the_answer_is_told_as_it_is_written(
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
        Streamed(
            reply(lookups=[look("open_incidents")], answer=""),
            reply(answer=f"See [incident {found.id}].", cites=[f"incident {found.id}"]),
            size=6,
        ),
    )

    response = ask_streamed(client, csrf_token, text="What needs me?")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-accel-buffering"] == "no"
    events = events_of(response.text)
    names = [name for name, _ in events]
    assert names[0] == "conversation"
    assert names[1] == "looked"
    assert names[-1] == "done"
    assert set(names[2:-1]) == {"wrote"}
    assert events[1][1] == {"tool": "open_incidents", "summary": "1 open incident"}
    assert "".join(data["text"] for name, data in events if name == "wrote") == (
        f"See [incident {found.id}]."
    )
    done = events[-1][1]
    assert events[0][1] == {"id": done["id"]}
    assert done["title"] == "What needs me?"
    user, assistant = done["messages"]
    assert (user["role"], assistant["role"], assistant["ok"]) == ("user", "assistant", True)
    assert assistant["text"] == f"See [incident {found.id}]."
    assert assistant["lookups"] == [{"tool": "open_incidents", "summary": "1 open incident"}]
    assert len(assistant["call_ids"]) == 2
    assert KEY not in response.text
    # It is kept, like any other conversation.
    assert client.get(f"{BASE}/{done['id']}").json() == done


def test_the_page_it_is_asked_from_is_looked_up_first(
    client: TestClient,
    csrf_token: str,
    app: FastAPI,
    serve: Serve,
    session: Session,
    settings: Settings,
) -> None:
    ready(session, settings)
    found = incident(session)
    session.commit()
    provider(app, serve, Streamed(reply(answer="This one.")))

    response = ask_streamed(
        client, csrf_token, page={"kind": "incident", "id": found.id}, text="What is this?"
    )

    names = [name for name, _ in events_of(response.text)]
    assert names[:2] == ["conversation", "looked"]


def test_a_question_in_a_conversation_is_answered_the_same_way(
    client: TestClient,
    csrf_token: str,
    app: FastAPI,
    serve: Serve,
    session: Session,
    settings: Settings,
) -> None:
    ready(session, settings)
    provider(app, serve, Streamed(reply(answer="Fine."), reply(answer="Still fine.")))
    first = ask_streamed(client, csrf_token).text
    started = events_of(first)[-1][1]

    response = ask_streamed(client, csrf_token, f"{BASE}/{started['id']}/stream", "And now?")

    done = events_of(response.text)[-1][1]
    assert done["id"] == started["id"]
    assert [(message["role"], message["text"]) for message in done["messages"]] == [
        ("user", "Anything?"),
        ("assistant", "Fine."),
        ("user", "And now?"),
        ("assistant", "Still fine."),
    ]


def test_a_conversation_that_is_not_there_is_not_asked_in(
    client: TestClient, csrf_token: str
) -> None:
    response = ask_streamed(client, csrf_token, f"{BASE}/999/stream")

    assert response.status_code == 404


def test_a_conversation_that_has_got_long_is_not_asked_in(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    row = AiConversation(title="Long", created_at=utcnow(), updated_at=utcnow())
    session.add(row)
    session.flush()
    session.add_all(
        AiMessage(conversation_id=row.id, role="user", text="x", created_at=utcnow())
        for _ in range(chat.MAX_MESSAGES)
    )
    session.commit()

    response = ask_streamed(client, csrf_token, f"{BASE}/{row.id}/stream")

    assert response.status_code == 409


def test_with_ai_off_the_answer_says_how_to_turn_it_on(client: TestClient, csrf_token: str) -> None:
    events = events_of(ask_streamed(client, csrf_token).text)

    assert [name for name, _ in events] == ["conversation", "done"]
    assistant = events[-1][1]["messages"][1]
    assert (assistant["ok"], assistant["text"].startswith("AI is turned off.")) == (False, True)


def test_what_was_written_before_the_answer_failed_is_taken_back(
    client: TestClient,
    csrf_token: str,
    app: FastAPI,
    serve: Serve,
    session: Session,
    settings: Settings,
) -> None:
    ready(session, settings)
    provider(app, serve, Streamed(reply(answer="Half of an ans"), tail="error"))

    events = events_of(ask_streamed(client, csrf_token).text)

    names = [name for name, _ in events]
    assert names[-2:] == ["dropped", "done"]
    assert events[-1][1]["messages"][1]["ok"] is False
