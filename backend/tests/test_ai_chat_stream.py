"""The assistant's answer as it is written: what is told while it is asked, with a provider that
streams each answer a few characters at a time, so that every word, stand-in and escape is cut
somewhere."""

import json
import re
from collections.abc import Callable

import anyio
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import chat, chat_stream
from app.ai.chat_stream import Dropped, Looked, Wrote
from app.ai.gateway import Context
from app.config import Settings
from app.models import AiCall, AiConversation, AiMessage
from tests.stubs import Answer as Reply
from tests.stubs import Seen, Serve
from tests.test_ai_chat import conversation, look, reply
from tests.test_ai_gateway import Log, context
from tests.test_ai_service import NOW
from tests.test_ai_triage import DEVICE, incident, prompt_of, ready, signals


def stream_of(text: str, size: int = 5, stop: str = "end_turn", tail: str = "stop") -> str:
    """What Anthropic answers a request for a stream with: the text in pieces of ``size``, or, for
    a ``tail`` of ``error``, an error where the end should be."""

    def event(kind: str, **data: object) -> str:
        return f"event: {kind}\ndata: {json.dumps({'type': kind, **data})}\n\n"

    pieces = [text[at : at + size] for at in range(0, len(text), size)]
    body = event("message_start", message={"usage": {"input_tokens": 1000, "output_tokens": 1}})
    body += event("ping")
    for piece in pieces:
        body += event("content_block_delta", index=0, delta={"type": "text_delta", "text": piece})
    if tail == "error":
        return body + event("error", error={"type": "overloaded_error", "message": "Overloaded"})
    body += event("message_delta", delta={"stop_reason": stop}, usage={"output_tokens": 200})
    return body + event("message_stop")


class Streamed:
    """A provider that streams these replies one after another, and keeps what it was asked."""

    def __init__(
        self, *replies: str | Callable[[str], str], size: int = 5, tail: str = "stop"
    ) -> None:
        self.replies = list(replies)
        self.size = size
        self.tail = tail
        self.prompts: list[str] = []
        self.asked: list[dict[str, object]] = []

    def __call__(self, seen: Seen) -> Reply:
        self.prompts.append(prompt_of(seen))
        self.asked.append(json.loads(seen.body))
        step = self.replies.pop(0)
        text = step if isinstance(step, str) else step(self.prompts[-1])
        return Reply(
            body=stream_of(text, self.size, tail=self.tail),
            headers={"Content-Type": "text/event-stream"},
        )


def told(
    session: Session,
    where: Context,
    row: AiConversation,
    text: str = "Anything?",
    page: chat.Page | None = None,
) -> list[chat_stream.Looked | Wrote | Dropped | AiMessage]:
    async def go() -> list[chat_stream.Looked | Wrote | Dropped | AiMessage]:
        return [
            event async for event in chat_stream.say_stream(session, where, row, text, NOW, page)
        ]

    return anyio.run(go)


def written(events: list[chat_stream.Looked | Wrote | Dropped | AiMessage]) -> str:
    return "".join(event.text for event in events if isinstance(event, Wrote))


def asking(
    session: Session,
    settings: Settings,
    serve: Serve,
    provider: Streamed,
    text: str = "Anything?",
    page: chat.Page | None = None,
) -> list[chat_stream.Looked | Wrote | Dropped | AiMessage]:
    server = serve(provider)
    ready(session, settings)
    return told(session, context(settings, Log(), server.url), conversation(session), text, page)


@pytest.mark.parametrize("size", [1, 2, 3, 5, 9, 1000])
def test_the_answer_comes_as_it_is_written_and_is_stored_as_it_is_when_it_is_not_streamed(
    session: Session, settings: Settings, serve: Serve, size: int
) -> None:
    said = 'Start with [incident 3]: "scanned"\nthen é 😀 done.'
    provider = Streamed(reply(answer=said, cites=["incident 3"]), size=size)

    events = asking(session, settings, serve, provider)

    *progress, message = events
    # Without the line break, as it is stored.
    plain = said.replace("\n", " ")
    assert written(progress) == plain
    assert all(isinstance(event, Wrote) for event in progress)
    assert isinstance(message, AiMessage)
    assert (message.role, message.ok, message.text) == ("assistant", True, plain)
    assert provider.asked[0]["stream"] is True
    [call] = session.scalars(select(AiCall)).all()
    assert (call.ok, call.purpose, call.output_tokens) == (True, "chat", 200)
    assert call.answer == reply(answer=said, cites=["incident 3"])


def test_a_lookup_is_told_when_it_has_run_and_the_answer_is_not_written_before_it(
    session: Session, settings: Settings, serve: Serve
) -> None:
    found = incident(session, severity=3)
    session.commit()
    provider = Streamed(
        reply(lookups=[look("open_incidents")], answer="Let me look."),
        reply(answer=f"See [incident {found.id}]."),
    )

    events = asking(session, settings, serve, provider)

    assert events[0] == Looked("open_incidents", "1 open incident")
    assert written(events) == f"See [incident {found.id}]."
    assert Dropped() not in events
    assert isinstance(events[-1], AiMessage)
    assert events[-1].lookups == [{"tool": "open_incidents", "summary": "1 open incident"}]


def test_each_lookup_is_told_once_though_it_is_run_again_for_every_round(
    session: Session, settings: Settings, serve: Serve
) -> None:
    found = incident(session, severity=3)
    session.commit()
    provider = Streamed(
        reply(lookups=[look("open_incidents")], answer=""),
        reply(lookups=[look("open_incidents"), look("incident", id=found.id)], answer=""),
        reply(answer="Done."),
    )

    events = asking(session, settings, serve, provider)

    assert [event.tool for event in events if isinstance(event, Looked)] == [
        "open_incidents",
        "incident",
    ]
    assert written(events) == "Done."


def test_the_page_the_owner_is_on_is_looked_up_and_told_first(
    session: Session, settings: Settings, serve: Serve
) -> None:
    found = incident(session)
    session.commit()

    events = asking(
        session,
        settings,
        serve,
        Streamed(reply(answer="This one.")),
        page=chat.Page("incident", id=found.id),
    )

    assert isinstance(events[0], Looked)
    assert events[0].tool == "incident"


def test_a_stand_in_is_given_back_as_the_real_address_however_the_pieces_cut_it(
    session: Session, settings: Settings, serve: Serve
) -> None:
    found = incident(session, severity=3)
    signals(session, found)
    session.commit()

    def says(prompt: str) -> str:
        stand_in = re.search(r"\bHOST_\d+\b", prompt)
        assert stand_in is not None
        return reply(answer=f"Block {stand_in.group(0)} now, then check {stand_in.group(0)}.")

    provider = Streamed(reply(lookups=[look("incident", id=found.id)], answer=""), says, size=3)

    events = asking(session, settings, serve, provider)

    assert written(events) == f"Block {DEVICE} now, then check {DEVICE}."
    assert "HOST_" not in written(events)


def test_what_is_written_as_an_answer_before_lookups_is_taken_back(
    session: Session, settings: Settings, serve: Serve
) -> None:
    found = incident(session, severity=3)
    session.commit()
    answer_first = json.dumps(
        {"answer": "Hmm, I think", "lookups": [look("open_incidents")], "cites": [], "actions": []}
    )
    provider = Streamed(answer_first, reply(answer=f"See [incident {found.id}]."))

    events = asking(session, settings, serve, provider)

    assert events.index(Dropped()) < events.index(Looked("open_incidents", "1 open incident"))
    assert written(events) == f"Hmm, I thinkSee [incident {found.id}]."
    assert isinstance(events[-1], AiMessage)
    assert events[-1].text == f"See [incident {found.id}]."


def test_an_answer_that_stops_part_of_the_way_is_taken_back_and_said_to_have_failed(
    session: Session, settings: Settings, serve: Serve
) -> None:
    provider = Streamed(reply(answer="This is half of an ans"), tail="error")

    events = asking(session, settings, serve, provider)

    *progress, message = events
    assert progress[-1] == Dropped()
    assert written(progress) != ""
    assert isinstance(message, AiMessage)
    assert (message.ok, message.text) == (
        False,
        "The model stopped answering part of the way through.",
    )
    [call] = session.scalars(select(AiCall)).all()
    assert (call.ok, call.error) == (False, message.text)


def test_a_provider_that_says_no_has_nothing_to_take_back(
    session: Session, settings: Settings, serve: Serve
) -> None:
    server = serve(lambda seen: Reply(status=401, body="{}"))
    ready(session, settings)

    events = told(session, context(settings, Log(), server.url), conversation(session))

    [message] = events
    assert isinstance(message, AiMessage)
    assert (message.ok, "didn't accept the API key" in message.text) == (False, True)


def test_with_ai_off_nothing_is_asked_and_the_answer_says_how_to_turn_it_on(
    session: Session, settings: Settings
) -> None:
    [message] = told(session, context(settings, Log()), conversation(session))

    assert isinstance(message, AiMessage)
    assert (message.ok, message.text.startswith("AI is turned off.")) == (False, True)
    assert session.scalars(select(AiCall)).all() == []


def test_a_reply_that_cannot_be_read_is_said_to_be_so(
    session: Session, settings: Settings, serve: Serve
) -> None:
    events = asking(session, settings, serve, Streamed("this is not JSON"))

    *progress, message = events
    assert progress == []
    assert isinstance(message, AiMessage)
    assert message.text == "The AI's answer could not be read. Ask again."


def test_what_is_written_past_the_longest_answer_is_not_given(
    session: Session, settings: Settings, serve: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(chat, "MAX_ANSWER", 12)
    provider = Streamed(reply(answer="x" * 40), size=4)

    events = asking(session, settings, serve, provider)

    assert written(events) == "x" * 12
    assert isinstance(events[-1], AiMessage)
    assert len(events[-1].text) <= 12


def test_the_question_and_the_answer_are_both_in_the_conversation(
    session: Session, settings: Settings, serve: Serve
) -> None:
    server = serve(Streamed(reply(answer="Fine.")))
    ready(session, settings)
    row = conversation(session)

    told(session, context(settings, Log(), server.url), row, "Is it fine?")

    kept = session.scalars(select(AiMessage).where(AiMessage.conversation_id == row.id)).all()
    assert [(message.role, message.text) for message in kept] == [
        ("user", "Is it fine?"),
        ("assistant", "Fine."),
    ]


def test_the_last_word_is_given_when_the_answer_ends_in_one_that_could_have_been_a_stand_in(
    session: Session, settings: Settings, serve: Serve
) -> None:
    events = asking(session, settings, serve, Streamed(reply(answer="All HOST"), size=1))

    assert written(events) == "All HOST"
