"""The assistant: an AI provider answers the owner's questions about the network, in a chat.

A question is answered from facts AresGate looks up, never from what the model remembers. Each
time the owner asks, the model is shown an overview of the network right now, the conversation so
far and the question, and either answers or asks to look something up, from the short list in
app/ai/tools.py (open incidents, one incident, recent alerts, who was blocked, a device, how the
integrations are doing). It may look things up twice, and then has to answer with what it has.
The lookups are only reads: the assistant can't change anything, and an answer says what it was
based on, so that the owner can check it.

Everything goes through the gateway (app/ai/gateway.py), so a provider only sees what the
redaction level allows, every request is recorded in ``ai_calls`` where the owner can read exactly
what was sent, and nothing is asked when AI is off or the spending limit is reached.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from ipaddress import ip_address
from typing import Final, cast

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import audit
from app.ai import gateway, tools
from app.ai.gateway import Context, Question, Unavailable
from app.ai.redaction import Redactor
from app.ai.tools import Args, Found, Ref
from app.events.event import Severity
from app.incidents.verdicts import MUTING
from app.models import (
    AiConversation,
    AiMessage,
    Device,
    DeviceAddress,
    Incident,
    IntegrationConnection,
)
from app.models.verdicts import VERDICTS

PURPOSE: Final = "chat"
# How many times the model is asked about one question: it may look things up twice, and the
# third time has to answer.
MAX_ROUNDS: Final = 3
MAX_LOOKUPS: Final = 4
# How much of the conversation is shown to the model, and how long a question may be.
HISTORY: Final = 6
MAX_REMEMBERED: Final = 1500
MAX_QUESTION: Final = 2000
MAX_ANSWER: Final = 6000
MAX_TITLE: Final = 80
# A conversation this long is better begun again: the model is shown only the end of it.
MAX_MESSAGES: Final = 100
MAX_TOKENS: Final = 1500
MAX_NAMES: Final = 500
# What the assistant may suggest the owner do with one answer, and how long a search it suggests
# may be.
MAX_ACTIONS: Final = 3
MAX_SEARCH: Final = 200
# The statuses an incident can be put in, and the pages an action can open.
STATUSES: Final = ("open", "investigating", "resolved", "dismissed")

_TOOL_LIST: Final = "\n".join(f"- {tool.name}: {tool.description}" for tool in tools.TOOLS)
SYSTEM: Final = f"""\
You are the analyst of AresGate, a security monitor for one home network. You are answering the \
owner's questions in a chat. The owner is technical but busy: answer in plain words, short, the \
most important thing first, and say what to do when there is something to do.

You can only read. You cannot change anything in AresGate or on the network, and you must never \
say that you did or that you will. You may suggest what the owner could do, in \
"actions": the owner sees each as a button and decides, so write it as a suggestion and never as \
done.

Answer only from the facts you are given: the overview, what you looked up and the conversation. \
If they do not say it, say that you do not know, or look it up. Never invent incidents, \
addresses, devices, numbers or products. Most traffic from the internet to a home network is \
automated scanning and password guessing that never succeeds and is not worth waking anyone for; \
say so when that is what you see, and be honest when something is worth the owner's attention.

To look something up, name a tool in "lookups" (up to four) and leave "answer" empty. You are \
asked again with what was found, and may look up more once. Fill "id", "name", "hours" and \
"limit" only as the tool uses them and leave the rest null. The tools:
{_TOOL_LIST}

When you have what you need, put the answer in "answer" and leave "lookups" empty. Write an \
incident as [incident 3] and a device as [device 12]. In "cites" list what you based the answer \
on, as "incident 3", "device 12" or "integration opnsense", only things that appeared in what you \
were given.

"actions" is empty unless a suggestion helps, and holds at most three. Each has a "kind" and a \
"target": "open" takes the owner to a page (target "incident 3", "device 12", "integration \
opnsense", or "logs" with the search to run in "value"); "status" sets the status of an incident \
(target "incident 3", "value" one of {", ".join(STATUSES)}); "verdict" says what the owner thinks \
of an incident (target "incident 3", "value" one of {", ".join(VERDICTS)}, and why in "note"). \
Only suggest it about incidents and devices that appeared in what you were given, and suggest \
"dismissed" or a verdict that quiets an incident only when you are sure it is nothing.

Answer only with the JSON you are asked for.\
"""

LOOKUP: Final[Mapping[str, object]] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "tool": {"type": "string", "enum": list(tools.names())},
        "id": {"type": ["integer", "null"]},
        "name": {"type": ["string", "null"]},
        "hours": {"type": ["integer", "null"]},
        "limit": {"type": ["integer", "null"]},
    },
    "required": ["tool", "id", "name", "hours", "limit"],
}
ACTION: Final[Mapping[str, object]] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "kind": {"type": "string", "enum": ["open", "status", "verdict"]},
        "target": {"type": "string"},
        "value": {"type": ["string", "null"]},
        "note": {"type": ["string", "null"]},
    },
    "required": ["kind", "target", "value", "note"],
}
SCHEMA: Final[Mapping[str, object]] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "lookups": {"type": "array", "items": LOOKUP},
        "answer": {"type": "string"},
        "cites": {"type": "array", "items": {"type": "string"}},
        "actions": {"type": "array", "items": ACTION},
    },
    "required": ["lookups", "answer", "cites", "actions"],
}


def about(conversation_id: int) -> str:
    """What a request is about, as the usage page lists it."""
    return f"chat {conversation_id}"


# -- what the model said


@dataclass(frozen=True)
class Lookup:
    tool: tools.Tool
    args: Args


@dataclass(frozen=True)
class Suggestion:
    """What the model suggests the owner do, as it said it, before it is checked against what was
    found (``_proposed``)."""

    kind: str
    target: str
    value: str | None
    note: str | None


@dataclass(frozen=True)
class Step:
    """One reply of the model: what it wants looked up, or its answer, what it cites and what it
    suggests the owner do."""

    lookups: list[Lookup]
    answer: str | None
    cites: list[str]
    actions: list[Suggestion] = field(default_factory=lambda: [])


def _loads(text: str) -> object:
    """The JSON object in an answer, which some models put inside a code fence or a sentence."""
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except ValueError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        return json.loads(match.group(0)) if match else None


def _number(value: object) -> int | None:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _fields(item: object) -> dict[str, object] | None:
    return cast("dict[str, object]", item) if isinstance(item, dict) else None


def _items(value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []


def _lookup(item: object) -> Lookup | None:
    fields = _fields(item)
    if fields is None:
        return None
    name = fields.get("tool")
    tool = tools.by_name(name) if isinstance(name, str) else None
    if tool is None:
        return None
    given = fields.get("name")
    args = Args(
        id=_number(fields.get("id")),
        name=audit.clean(given, 120) if isinstance(given, str) else None,
        hours=_number(fields.get("hours")),
        limit=_number(fields.get("limit")),
    )
    return Lookup(tool, args)


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _suggestion(item: object) -> Suggestion | None:
    fields = _fields(item)
    if fields is None:
        return None
    kind, target = _text_or_none(fields.get("kind")), _text_or_none(fields.get("target"))
    if kind is None or target is None:
        return None
    return Suggestion(
        kind, target, _text_or_none(fields.get("value")), _text_or_none(fields.get("note"))
    )


def parse(text: str) -> Step | None:
    """What a reply says, or None if it isn't one. A tool that isn't on the list is ignored, so
    the model can't ask for anything else."""
    try:
        loaded = _loads(text)
    except ValueError:
        return None
    fields = _fields(loaded)
    if fields is None:
        return None
    lookups = [found for item in _items(fields.get("lookups")) if (found := _lookup(item))]
    suggestions = [found for item in _items(fields.get("actions")) if (found := _suggestion(item))]
    answer = fields.get("answer")
    return Step(
        lookups=lookups[:MAX_LOOKUPS],
        answer=audit.clean(answer, MAX_ANSWER) if isinstance(answer, str) else None,
        cites=[item for item in _items(fields.get("cites")) if isinstance(item, str)],
        actions=suggestions,
    )


# -- what the model is shown


def _overview(db: Session, now: datetime) -> str:
    """Where things stand, in a few lines, so that most questions need nothing looked up."""
    by_severity = dict(
        db.execute(
            select(Incident.severity, func.count())
            .where(
                Incident.status.in_(tools.ACTIVE),
                or_(Incident.verdict.is_(None), Incident.verdict.not_in(MUTING)),
            )
            .group_by(Incident.severity)
        ).all()
    )
    total = sum(by_severity.values())
    spread = ", ".join(
        f"{by_severity[level]} {Severity(level).name.lower()}"
        for level in sorted(by_severity, reverse=True)
    )
    connections = db.scalar(select(func.count()).select_from(IntegrationConnection)) or 0
    failing = (
        db.scalar(
            select(func.count())
            .select_from(IntegrationConnection)
            .where(IntegrationConnection.last_error.is_not(None))
        )
        or 0
    )
    incidents = (
        f"{total} incidents need someone ({spread})" if total else "no incident needs anyone"
    )
    return (
        f"It is {now:%Y-%m-%d %H:%M} UTC. Right now {incidents}. "
        f"{connections} integrations are connected, {failing} of them failing."
    )


def _remembered(redactor: Redactor, earlier: list[AiMessage]) -> str:
    lines = [
        f"{'Owner' if message.role == 'user' else 'You'}: "
        f"{redactor.text(message.text, MAX_REMEMBERED)}"
        for message in earlier
    ]
    return redactor.evidence("earlier in this conversation", lines, per_line=MAX_REMEMBERED + 20)


def _label(lookup: Lookup) -> str:
    given = [
        f"{name} {value}"
        for name, value in (
            ("id", lookup.args.id),
            ("name", lookup.args.name),
            ("hours", lookup.args.hours),
            ("limit", lookup.args.limit),
        )
        if value is not None
    ]
    return " ".join([lookup.tool.name.replace("_", " "), *given])


def _run(
    db: Session, redactor: Redactor, lookups: list[Lookup], now: datetime
) -> list[tuple[Lookup, Found]]:
    """What each lookup finds, written through the redactor of the request it is for."""
    found: list[tuple[Lookup, Found]] = []
    for lookup in lookups:
        found.append((lookup, lookup.tool.run(db, redactor, lookup.args, now)))
    return found


NO_MORE: Final = "You cannot look anything else up now: answer with what you have."


@dataclass(frozen=True)
class Page:
    """Where the owner is while they ask: the page, and what it is about. ``kind`` is
    ``incident`` or ``device`` (with its ``id``, or for a device its ``address``), ``logs`` or
    ``incidents`` (with the ``query`` on screen) or ``other`` (with its ``title``)."""

    kind: str
    id: int | None = None
    address: str | None = None
    query: str | None = None
    title: str | None = None


PAGE_KINDS: Final = ("incident", "device", "logs", "incidents", "other")
_TOOLS: Final = {tool.name: tool for tool in tools.TOOLS}


def _page_lookups(db: Session, page: Page | None) -> list[Lookup]:
    """What the page the owner is on is about, looked up before the model is asked anything, so
    that "this incident" and "this device" mean what they are looking at."""
    if page is None:
        return []
    if page.kind == "incident" and page.id is not None:
        return [Lookup(_TOOLS["incident"], Args(id=page.id))]
    if page.kind != "device":
        return []
    device_id = page.id
    if device_id is None and page.address is not None:
        try:
            address = ip_address(page.address)
        except ValueError:
            return []
        device_id = db.scalars(
            select(DeviceAddress.device_id)
            .where(DeviceAddress.address == address)
            .order_by(DeviceAddress.last_seen_at.desc())
            .limit(1)
        ).first()
    return [Lookup(_TOOLS["device"], Args(id=device_id))] if device_id is not None else []


def _looking_at(redactor: Redactor, page: Page | None) -> str | None:
    """A line telling the model which page the owner has open, or None."""
    if page is None or page.kind not in PAGE_KINDS:
        return None
    if page.kind == "incident":
        return f"The owner has the page of incident {page.id} open." if page.id else None
    if page.kind == "device":
        return "The owner has the page of a device open (it is looked up below)."
    if page.kind in ("logs", "incidents"):
        where = "the Logs page" if page.kind == "logs" else "the list of incidents"
        shown = redactor.text(page.query, MAX_SEARCH) if page.query else ""
        return f"The owner is on {where}" + (f", searching for: {shown}." if shown else ".")
    title = audit.clean(page.title, MAX_TITLE) if page.title else ""
    return f"The owner is on the {title} page." if title else None


def _question(
    db: Session,
    conversation: AiConversation,
    earlier: list[AiMessage],
    text: str,
    lookups: list[Lookup],
    ran: list[tuple[Lookup, Found]],
    now: datetime,
    *,
    last: bool,
    page: Page | None = None,
) -> Question:
    """The question for one round. ``ran`` is filled with what the lookups found when the prompt
    is built, which is what an answer may cite."""

    def build(redactor: Redactor) -> str:
        ran[:] = _run(db, redactor, lookups, now)
        parts = [_overview(db, now)]
        if (looking := _looking_at(redactor, page)) is not None:
            parts.append(looking)
        if earlier:
            parts.append(_remembered(redactor, earlier))
        parts += [redactor.evidence(_label(lookup), found.lines) for lookup, found in ran]
        parts.append(f"The owner asks: {redactor.text(text, MAX_QUESTION)}")
        if last:
            parts.append(NO_MORE)
        return "\n\n".join(parts)

    names = [
        name
        for name in db.scalars(
            select(Device.hostname).where(Device.hostname.is_not(None)).limit(MAX_NAMES)
        )
        if name
    ]
    return Question(
        purpose=PURPOSE,
        system=SYSTEM,
        build=build,
        about=about(conversation.id),
        schema=SCHEMA,
        max_tokens=MAX_TOKENS,
        names=names,
    )


# -- the answer


@dataclass(frozen=True)
class Reply:
    """What came of a question: an answer, or why there was none."""

    ok: bool
    text: str
    lookups: list[dict[str, str]]
    cites: list[dict[str, str]]
    call_ids: list[int]
    # What it suggests the owner do, each kept only if it is about something it was shown.
    actions: list[dict[str, str | None]] = field(default_factory=lambda: [])


def _failed(reason: str, call_ids: list[int]) -> Reply:
    return Reply(ok=False, text=reason, lookups=[], cites=[], call_ids=call_ids)


def _known(ran: list[tuple[Lookup, Found]]) -> dict[str, Ref]:
    """What the lookups found that an answer may cite or suggest something about, by how the model
    names it: ``incident 3``."""
    return {f"{ref.kind} {ref.key}".lower(): ref for _, found in ran for ref in found.refs}


_STATUS_LABELS: Final = {
    "open": "Reopen {}",
    "investigating": "Start investigating {}",
    "resolved": "Mark {} as resolved",
    "dismissed": "Dismiss {}",
}
_VERDICT_LABELS: Final = {
    "not_suspicious": "Call {} not suspicious",
    "low_priority": "Call {} low priority",
    "threat": "Call {} a real threat",
}


def _action(
    kind: str, target: Ref | str, value: str | None, note: str | None, label: str
) -> dict[str, str | None]:
    where = target if isinstance(target, Ref) else None
    return {
        "kind": kind,
        "target_kind": where.kind if where else str(target),
        "target_key": where.key if where else "",
        "value": value,
        "note": note,
        "label": label,
    }


def _search_of_logs(item: Suggestion) -> dict[str, str | None] | None:
    """The search of the logs a suggestion opens, or None if it names no text to look for."""
    search = audit.clean(item.value, MAX_SEARCH) if item.value else ""
    if not search:
        return None
    return _action("open", "logs", search, None, f'Search the logs for "{search}"')


def _made(item: Suggestion, ref: Ref | None) -> dict[str, str | None] | None:
    """The one thing a suggestion means, or None if it is not something the owner can do."""
    value = item.value.strip().lower() if item.value else None
    note = audit.clean(item.note, 200) if item.note else None
    if item.kind == "open" and item.target.strip().lower() == "logs":
        return _search_of_logs(item)
    if item.kind == "open" and ref is not None:
        return _action("open", ref, None, None, f"Open {ref.label}")
    if ref is None or ref.kind != "incident" or value is None:
        return None
    if item.kind == "status" and value in _STATUS_LABELS:
        return _action("status", ref, value, None, _STATUS_LABELS[value].format(ref.label))
    if item.kind == "verdict" and value in _VERDICT_LABELS:
        return _action("verdict", ref, value, note, _VERDICT_LABELS[value].format(ref.label))
    return None


def _proposed(
    suggestions: list[Suggestion], ran: list[tuple[Lookup, Found]]
) -> list[dict[str, str | None]]:
    """What the model suggests that is something the owner can really do: about an incident, a
    device or an integration it was shown (or a search of the logs), with a value that is one of
    the allowed ones. Anything else is dropped, so a suggestion can't name what the lookups did
    not return, and it is the owner who presses the button."""
    known = _known(ran)
    kept: dict[tuple[str, str, str | None], dict[str, str | None]] = {}
    for item in suggestions:
        made = _made(item, known.get(item.target.strip(" []").lower()))
        if made is not None:
            kept.setdefault((item.kind, item.target.lower(), made["value"]), made)
    return list(kept.values())[:MAX_ACTIONS]


def _cited(names: list[str], ran: list[tuple[Lookup, Found]]) -> list[dict[str, str]]:
    """What the answer cites that was really in what it was given, in the order it cited it."""
    known = _known(ran)
    kept: dict[str, Ref] = {}
    for name in names:
        ref = known.get(name.strip(" []").lower())
        if ref is not None:
            kept.setdefault(f"{ref.kind} {ref.key}", ref)
    return [{"kind": ref.kind, "key": ref.key, "label": ref.label} for ref in kept.values()]


def _looked_at(ran: list[tuple[Lookup, Found]]) -> list[dict[str, str]]:
    return [{"tool": lookup.tool.name, "summary": found.summary} for lookup, found in ran]


def reply_to(
    db: Session,
    context: Context,
    conversation: AiConversation,
    earlier: list[AiMessage],
    text: str,
    now: datetime,
    page: Page | None = None,
) -> Reply:
    """Answers a question, asking the model up to ``MAX_ROUNDS`` times: each time it may ask for
    more to be looked up, and the last time it has to answer. For one of the API's own threads.
    The page the owner is on, if they said, is looked up first. The caller commits."""
    asked: list[Lookup] = _page_lookups(db, page)
    call_ids: list[int] = []
    for number in range(1, MAX_ROUNDS + 1):
        ran: list[tuple[Lookup, Found]] = []
        question = _question(
            db, conversation, earlier, text, asked, ran, now, last=number == MAX_ROUNDS, page=page
        )
        outcome = gateway.ask(db, context, question, now)
        if isinstance(outcome, Unavailable):
            return _failed(outcome.reason, call_ids)
        call_ids.append(outcome.call_id)
        if not outcome.ok:
            return _failed(outcome.reason or "The AI did not answer.", call_ids)
        step = parse(outcome.text)
        if step is None:
            return _failed("The AI's answer could not be read. Ask again.", call_ids)
        if step.lookups and number < MAX_ROUNDS:
            asked += [lookup for lookup in step.lookups if lookup not in asked]
            continue
        if step.answer:
            return Reply(
                True,
                step.answer,
                _looked_at(ran),
                _cited(step.cites, ran),
                call_ids,
                _proposed(step.actions, ran),
            )
        return _failed("The AI did not give an answer. Ask again.", call_ids)
    raise AssertionError("unreachable")  # pragma: no cover - the last round returns above


# -- the conversation


def title_of(text: str) -> str:
    """What a conversation is called: its first question, cut short."""
    first = (text.strip().splitlines() or [""])[0]
    return audit.clean(first, MAX_TITLE) or "Conversation"


def messages(db: Session, conversation: AiConversation) -> list[AiMessage]:
    """What was said, oldest first."""
    return list(
        db.scalars(
            select(AiMessage)
            .where(AiMessage.conversation_id == conversation.id)
            .order_by(AiMessage.id)
        )
    )


def _remember(history: list[AiMessage]) -> list[AiMessage]:
    """The end of the conversation that the model is shown: the answers it made, not the ones it
    failed to."""
    return [message for message in history if message.ok][-HISTORY:]


def say(
    db: Session,
    context: Context,
    conversation: AiConversation,
    text: str,
    now: datetime,
    page: Page | None = None,
) -> None:
    """Adds the owner's question to a conversation and the assistant's answer to it (or why there
    is none). ``page`` is where the owner is when they ask. The caller commits."""
    earlier = _remember(messages(db, conversation))
    db.add(AiMessage(conversation_id=conversation.id, role="user", text=text, created_at=now))
    db.flush()
    answer = reply_to(db, context, conversation, earlier, text, now, page)
    db.add(
        AiMessage(
            conversation_id=conversation.id,
            role="assistant",
            text=answer.text,
            ok=answer.ok,
            lookups=answer.lookups,
            cites=answer.cites,
            actions=answer.actions,
            call_ids=answer.call_ids,
            created_at=now,
        )
    )
    conversation.updated_at = now
    db.flush()
