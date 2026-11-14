"""The chat with the assistant: conversations, asking, and asking again after a failure. For
someone signed in. The assistant only reads (app/ai/tools.py): nothing here changes the network
or AresGate's settings, only the conversations themselves. What it suggests the owner do comes back
as ``actions``, which the owner approves by pressing a button that makes the same request the
page for it would."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, select

from app.ai import chat
from app.api.ai import AiContext
from app.api.deps import Db, signed_in
from app.models import AiConversation, AiMessage, utcnow

router = APIRouter(prefix="/ai/conversations", tags=["ai"], dependencies=[Depends(signed_in)])

ConversationId = Annotated[int, Path(ge=1, le=2**63 - 1)]
MAX_LISTED = 50
Question = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=chat.MAX_QUESTION)
]


class PageIn(BaseModel):
    """Where the owner is when they ask, so that "this incident" means the one on screen: the page
    and what it is about. Nothing here is trusted: it only says what to look up and what to
    tell the assistant."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["incident", "device", "logs", "incidents", "other"]
    id: int | None = Field(default=None, ge=1, le=2**63 - 1)
    # A device's page is by its address.
    address: Annotated[str, StringConstraints(max_length=45)] | None = None
    # The search on screen, on the logs and the list of incidents.
    query: Annotated[str, StringConstraints(max_length=chat.MAX_SEARCH)] | None = None
    title: Annotated[str, StringConstraints(max_length=chat.MAX_TITLE)] | None = None

    def known(self) -> chat.Page:
        return chat.Page(self.kind, self.id, self.address, self.query, self.title)


class QuestionIn(BaseModel):
    text: Question
    # The page it was asked from, when it is asked from the panel on any page.
    page: PageIn | None = None


class LookupOut(BaseModel):
    """What an answer looked at: the tool, and what it found in a few words."""

    tool: str
    summary: str


class CiteOut(BaseModel):
    """What an answer cites: an ``incident`` or an ``integration``, its id and what to call it."""

    kind: str
    key: str
    label: str


class ActionOut(BaseModel):
    """Something the assistant suggests the owner do: the owner presses its button, and the page
    makes the same request the page for it would (the assistant changes nothing itself). ``kind``
    is ``open`` (go to a page), ``status`` (``value`` is the new status of an incident) or
    ``verdict`` (``value`` is the verdict, ``note`` why)."""

    kind: Literal["open", "status", "verdict"]
    # What it is about: an ``incident``, ``device`` or ``integration`` with its ``key``, or
    # ``logs`` (and then ``value`` is the search).
    target_kind: str
    target_key: str
    value: str | None
    note: str | None
    label: str


class MessageOut(BaseModel):
    id: int
    role: str
    text: str
    # False for an answer that could not be made, whose text says why.
    ok: bool
    created_at: AwareDatetime
    lookups: list[LookupOut]
    cites: list[CiteOut]
    actions: list[ActionOut]
    # The requests to the provider that made it, to open on the AI usage page.
    call_ids: list[int]


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
    messages: list[MessageOut]


class SummaryOut(BaseModel):
    id: int
    title: str
    updated_at: AwareDatetime
    messages: int


def _message(message: AiMessage) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        text=message.text,
        ok=message.ok,
        created_at=message.created_at,
        lookups=[LookupOut(**item) for item in message.lookups],
        cites=[CiteOut(**item) for item in message.cites],
        actions=[ActionOut.model_validate(item) for item in message.actions],
        call_ids=message.call_ids,
    )


def _out(db: Db, conversation: AiConversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[_message(message) for message in chat.messages(db, conversation)],
    )


def _found(db: Db, conversation_id: int) -> AiConversation:
    conversation = db.get(AiConversation, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such conversation.")
    return conversation


@router.get("")
def list_conversations(db: Db) -> list[SummaryOut]:
    """The conversations, the one with the latest word first."""
    count = func.count(AiMessage.id)
    rows = db.execute(
        select(AiConversation, count)
        .outerjoin(AiMessage, AiMessage.conversation_id == AiConversation.id)
        .group_by(AiConversation.id)
        .order_by(AiConversation.updated_at.desc(), AiConversation.id.desc())
        .limit(MAX_LISTED)
    ).all()
    return [
        SummaryOut(id=item.id, title=item.title, updated_at=item.updated_at, messages=total)
        for item, total in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def start(body: QuestionIn, db: Db, context: AiContext) -> ConversationOut:
    """Begins a conversation with a question and answers it. This can take a minute or two: the
    assistant may look things up and ask the provider more than once."""
    now = utcnow()
    conversation = AiConversation(title=chat.title_of(body.text), created_at=now, updated_at=now)
    db.add(conversation)
    db.flush()
    chat.say(db, context, conversation, body.text, now, body.page.known() if body.page else None)
    out = _out(db, conversation)
    db.commit()
    return out


@router.get("/{conversation_id}")
def get_conversation(conversation_id: ConversationId, db: Db) -> ConversationOut:
    return _out(db, _found(db, conversation_id))


@router.post("/{conversation_id}/messages")
def ask(
    conversation_id: ConversationId, body: QuestionIn, db: Db, context: AiContext
) -> ConversationOut:
    """Asks another question in a conversation and answers it."""
    conversation = _found(db, conversation_id)
    if len(chat.messages(db, conversation)) >= chat.MAX_MESSAGES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This conversation has got long. Begin a new one to keep the answers sharp.",
        )
    chat.say(
        db, context, conversation, body.text, utcnow(), body.page.known() if body.page else None
    )
    out = _out(db, conversation)
    db.commit()
    return out


@router.post("/{conversation_id}/retry")
def retry(conversation_id: ConversationId, db: Db, context: AiContext) -> ConversationOut:
    """Asks the last question again after an answer that could not be made, in place of that
    answer. Anything else is left alone."""
    conversation = _found(db, conversation_id)
    history = chat.messages(db, conversation)
    if len(history) < 2 or history[-1].role != "assistant" or history[-1].ok:
        raise HTTPException(status.HTTP_409_CONFLICT, "There is no failed answer to ask again.")
    failed, question = history[-1], history[-2]
    db.delete(failed)
    db.delete(question)
    db.flush()
    chat.say(db, context, conversation, question.text, utcnow())
    out = _out(db, conversation)
    db.commit()
    return out


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(conversation_id: ConversationId, db: Db) -> Response:
    """Deletes a conversation and everything said in it. What was sent to the provider stays in
    the usage record until it is cleared by its own retention."""
    db.delete(_found(db, conversation_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
