"""The assistant's answer as it is written, for a page that shows it coming.

Asking works as it does in app/ai/chat.py (the same rounds, the same lookups, the same gateway and
the same checks of what the model suggests), but each round's request is streamed
(app/ai/gateway.py ``stream``) and what happens is told as it happens: a lookup that has run, with
what it found, and then the text of the answer as the model writes it, with the real values put
back in the stand-ins it was given (``RevealStream``, which holds back a stand-in that has not yet
come whole). Nothing is stored until the answer has ended; then it is stored as it is when it
isn't streamed, and that is what the page shows in the end.

It is made to run in one task of the event loop, which is where the streamed request is, so the
database is used in a thread at a time (``anyio.to_thread``) and never in the loop.
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime
from functools import partial

import anyio.to_thread
from sqlalchemy.orm import Session

from app import audit
from app.ai import chat, gateway
from app.ai.answer_reader import AnswerReader
from app.ai.chat import Page, Reply
from app.ai.gateway import Context, Sent, Unavailable
from app.ai.redaction import RevealStream
from app.models import AiConversation, AiMessage


@dataclass(frozen=True)
class Looked:
    """A lookup that has run, and what it found in a few words."""

    tool: str
    summary: str


@dataclass(frozen=True)
class Wrote:
    """The next of the answer, as the owner is to read it."""

    text: str


@dataclass(frozen=True)
class Dropped:
    """What was written so far was not the answer: the model asked to look something up after all,
    or the request failed."""


Event = Looked | Wrote | Dropped | AiMessage


async def _in_thread[T](work: Callable[[], T]) -> T:
    return await anyio.to_thread.run_sync(work)


async def _written(prepared: gateway.Prepared, context: Context) -> AsyncGenerator[Wrote | Sent]:
    """The answer of one round as it is written, and last how the request ended."""
    reader = AnswerReader()
    reveal = RevealStream(prepared.redactor)
    room = chat.MAX_ANSWER

    def fit(text: str) -> str:
        """What the model writes past the longest answer is not given, as ``chat.parse`` leaves it
        out of the one that is stored."""
        nonlocal room
        # It reads the same as the one that is stored, which has no line breaks in it.
        text = audit.plain(text)[:room]
        room -= len(text)
        return text

    async with aclosing(gateway.stream(prepared, context)) as pieces:
        async for piece in pieces:
            if isinstance(piece, Sent):
                # The last word, which was held in case it was the start of a stand-in, is not.
                if text := fit(await _in_thread(reveal.flush)):
                    yield Wrote(text)
                yield piece
                return  # pragma: no cover - the reader has what it needs and closes this
            if written := reader.feed(piece):
                shown = await _in_thread(partial(reveal.feed, written, reader.answered))
                if text := fit(shown):
                    yield Wrote(text)
    raise AssertionError("The gateway ended a stream without saying how.")  # pragma: no cover


async def _asked(
    db: Session,
    context: Context,
    question: gateway.Question,
    ran: list[tuple[chat.Lookup, chat.Found]],
    told: int,
    now: datetime,
) -> AsyncGenerator[Looked | Wrote | gateway.Answer | Unavailable]:
    """One request to the model: the lookups it needed, which are run when the question is made
    (``ran`` is filled, and the ones after the first ``told`` are told), the answer as it is
    written, and last what is recorded of it, or why nothing was asked."""
    prepared = await _in_thread(partial(gateway.prepare, db, context, question, now))
    # What the lookups found is known once the prompt is made. Each is told once, though the ones
    # asked for before are run again for every round.
    for lookup, found in ran[told:]:
        yield Looked(lookup.tool.name, found.summary)
    if isinstance(prepared, Unavailable):
        yield prepared
        return
    async for item in _written(prepared, context):
        if isinstance(item, Sent):
            yield await _in_thread(partial(gateway.record, db, prepared, item, now))
            return
        yield item
    raise AssertionError("The gateway ended a stream without saying how.")  # pragma: no cover


def _answers(settled: Reply | list[chat.Lookup]) -> bool:
    """Whether a round ended with the answer, and not with more to look up or a failure."""
    return isinstance(settled, Reply) and settled.ok


async def reply_stream(
    db: Session,
    context: Context,
    conversation: AiConversation,
    earlier: list[AiMessage],
    text: str,
    now: datetime,
    page: Page | None = None,
) -> AsyncGenerator[Looked | Wrote | Dropped | Reply]:
    """Answers a question as ``chat.reply_to`` does, telling what happens as it happens, and ends
    with the ``Reply``. The caller commits."""
    asked = await _in_thread(partial(chat.page_lookups, db, page))
    call_ids: list[int] = []
    told = 0
    for number in range(1, chat.MAX_ROUNDS + 1):
        ran: list[tuple[chat.Lookup, chat.Found]] = []
        last = number == chat.MAX_ROUNDS
        question = chat.build_question(
            db, conversation, earlier, text, asked, ran, now, last=last, page=page
        )
        settled: Reply | list[chat.Lookup] | None = None
        wrote = False
        async for item in _asked(db, context, question, ran, told, now):
            if isinstance(item, Looked | Wrote):
                wrote = wrote or isinstance(item, Wrote)
                yield item
            else:
                settled = chat.settle(item, ran, call_ids, last=last)
        told = len(ran)
        if settled is None:  # pragma: no cover - ``_asked`` ends with what is settled
            raise AssertionError("A round ended without an outcome.")
        # What was written was not the answer when more is to be looked up, or when there is none.
        if wrote and not _answers(settled):
            yield Dropped()
        if isinstance(settled, Reply):
            yield settled
            return
        asked += [lookup for lookup in settled if lookup not in asked]
    raise AssertionError("unreachable")  # pragma: no cover - the last round returns above


async def say_stream(
    db: Session,
    context: Context,
    conversation: AiConversation,
    text: str,
    now: datetime,
    page: Page | None = None,
) -> AsyncGenerator[Looked | Wrote | Dropped | AiMessage]:
    """What ``chat.say`` does, as it happens: the owner's question is added, what the assistant
    looks up and writes is told, and last comes its message, stored. The caller commits."""
    earlier = await _in_thread(partial(chat.put_question, db, conversation, text, now))
    async with aclosing(
        reply_stream(db, context, conversation, earlier, text, now, page)
    ) as events:
        async for event in events:
            if isinstance(event, Reply):
                yield await _in_thread(partial(chat.store, db, conversation, event, now))
            else:
                yield event
