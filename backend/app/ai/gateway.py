"""The one place AresGate asks an AI provider anything.

Everything that wants an answer from a model (triage, the chat, a briefing) describes its question
here, and this module is the only code, besides the connection test in ``service``, that calls
``wire.complete`` (a test makes sure of it). That is what makes three promises hold for all of
them at once:

- **A provider only sees what the redaction level allows.** The question is built through a
  ``Redactor`` (app/ai/redaction.py), the whole prompt is gone over once more, and the answer is
  turned back into real values only here, for whoever asked.
- **Every request is recorded** in ``ai_calls`` with the prompt as the provider saw it, what it
  answered, what it counted and what that cost, so the usage page, the limits and an audit of
  what left the house all read the same record.
- **Nothing is asked when AI is off or not set up**, and the answer says why in words, so a page
  can tell whoever clicked what to do rather than doing nothing.

A request has three parts so that the database and the network are never held together: ``prepare``
(the database), ``send`` (the network, asynchronous) and ``record`` (the database). ``ask`` does
all three for the API's own threads.
"""

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

import anyio.from_thread
from sqlalchemy.orm import Session

from app import audit
from app.agents import settings as agent_settings
from app.ai import limits, redaction, service, wire
from app.ai.catalog import Kind, ProviderDef
from app.ai.catalog import provider as provider_def
from app.ai.redaction import Level, Redactor
from app.config import Settings
from app.integrations import netguard
from app.integrations.client import ApiClient, CallFailed, Recorder, Target
from app.integrations.netguard import AddressPolicy
from app.integrations.probes import Verdict
from app.models import AiCall, AiProvider
from app.models.base import utcnow

# A model that is thinking takes longer than a connection test, which asks for one token.
DEADLINE = 120.0
READ_TIMEOUT = 100.0
MAX_ABOUT = 120
MICROS = Decimal(1_000_000)


@dataclass(frozen=True)
class Context:
    """What asking needs from outside the database: where providers may be, and where requests
    are logged. ``origins`` points a hosted provider somewhere else, which only the test server
    does."""

    settings: Settings
    recorder: Recorder
    hosted: AddressPolicy = netguard.PUBLIC_INTERNET
    local: AddressPolicy = netguard.OLLAMA_ON_THIS_COMPUTER
    origins: Mapping[str, str] = field(default_factory=dict[str, str])

    def policy_for(self, definition: ProviderDef) -> AddressPolicy:
        return self.local if definition.kind is Kind.LOCAL else self.hosted


def context_for_worker(settings: Settings, recorder: Recorder) -> Context:
    """The context of the worker, which has no app to read it from."""
    local = (
        netguard.OLLAMA_IN_CONTAINER if settings.in_container else netguard.OLLAMA_ON_THIS_COMPUTER
    )
    return Context(settings=settings, recorder=recorder, local=local)


@dataclass(frozen=True)
class Question:
    """What to ask. ``system`` is the start of the prompt that is the same every time (a provider
    that caches keeps it); ``build`` makes the rest from the redactor it is given, so every
    address, name and line of evidence in it passes through the redactor."""

    purpose: str
    system: str
    build: Callable[[Redactor], str]
    about: str | None = None
    schema: Mapping[str, object] | None = None
    max_tokens: int = 1024
    # What is the same for every question about a threat (app/ai/brief.py), made with the redactor
    # and put first in the prompt, ahead of ``system``, so that a provider that caches keeps it.
    start: Callable[[Redactor], str] | None = None
    # The addresses (or networks) of the home on the internet, shown as WAN_n.
    own: Sequence[str] = ()
    names: Sequence[str] = ()
    users: Sequence[str] = ()


@dataclass(frozen=True)
class Unavailable:
    """Nothing was asked, and why, for whoever wanted the answer."""

    reason: str


@dataclass(frozen=True)
class Prepared:
    """A question ready to send: who gets it, and exactly what they will read."""

    question: Question
    definition: ProviderDef
    model: str
    target: Target
    level: Level
    system: str
    prompt: str
    redactor: Redactor


@dataclass(frozen=True)
class Sent:
    """What came of sending it: an answer, or why there was none."""

    completion: wire.Completion | None
    failure: str | None
    milliseconds: int


@dataclass(frozen=True)
class Answer:
    """What was asked, answered. ``text`` has the real values back in it. A request that failed
    has no text and says why."""

    ok: bool
    text: str
    reason: str | None
    call_id: int
    truncated: bool = False
    # Who answered, as it is in the record.
    provider: str = ""
    model: str = ""


def effective_level(definition: ProviderDef, chosen: str) -> Level:
    """The level a provider is actually given: ``local`` is for a provider on the owner's own
    network, so any other is given ``balanced`` instead, whatever was chosen."""
    level = Level(chosen)
    if level is Level.LOCAL and definition.kind is not Kind.LOCAL:
        return Level.BALANCED
    return level


def system_for(level: Level, system: str, start: str = "") -> str:
    """The start of every prompt: the notice about evidence, what the stand-ins are (where there
    are any), what is the same for all questions of its kind if there is any, and then what this
    question needs."""
    parts = [redaction.DATA_NOTICE]
    if level is not Level.LOCAL:
        parts.append(redaction.GLOSSARY)
    if start:
        parts.append(start)
    return "\n\n".join([*parts, system])


@dataclass(frozen=True)
class _Choice:
    """Which provider is to be asked, and for what: ``model`` is None for the one it was set up
    with and ``where`` is the page to send the owner to. With no ``provider``, ``reason`` is why."""

    provider: str | None
    model: str | None = None
    where: str = ""
    reason: str | None = None


def _choose(db: Session, now: datetime, agents: bool) -> _Choice:
    """What the owner chose to ask: for the agents, what they chose under Settings > Agents, for
    everything else what they chose under Settings > AI."""
    if agents:
        picked = agent_settings.pick(db, now)
        if picked.reason is not None or picked.provider is None:
            return _Choice(None, reason=picked.reason)
        return _Choice(picked.provider, picked.model, "Settings > Agents")
    shared = service.usage(db, now)
    if not shared.enabled:
        return _Choice(None, reason="AI is turned off. Turn it on under Settings > AI to use it.")
    if shared.provider is None:
        return _Choice(None, reason="No AI provider is chosen. Choose one under Settings > AI.")
    return _Choice(shared.provider, None, "Settings > AI")


def _unavailable(
    db: Session, now: datetime, purpose: str = ""
) -> tuple[AiProvider | None, str | None, str | None]:
    """The provider to ask and the model to ask it for (None for the one it was set up with), or
    the reason there is no provider. The agents have a choice of their own."""
    agents = purpose == agent_settings.PURPOSE
    choice = _choose(db, now, agents)
    if choice.provider is None:
        return None, choice.reason, None
    row = db.get(AiProvider, choice.provider)
    definition = provider_def(choice.provider)
    if row is None or definition is None:
        return (
            None,
            f"The AI provider that was chosen is gone. Choose one under {choice.where}.",
            None,
        )
    if not (choice.model or row.model):
        return None, f"The AI provider has no model yet. Choose one under {choice.where}.", None
    # A provider on the owner's own computer, or Ollama's cloud, costs nothing by the token.
    if definition.kind is Kind.HOSTED:
        stopped = limits.reached(db, now) or (agent_settings.reached(db, now) if agents else None)
        if stopped is not None:
            return None, stopped, None
    return row, None, choice.model


def availability(db: Session, now: datetime, purpose: str = "") -> str | None:
    """Why nothing would be asked now, in words for whoever is waiting for an answer, or None when
    a provider would be asked."""
    return _unavailable(db, now, purpose)[1]


def prepare(
    db: Session, context: Context, question: Question, now: datetime
) -> Prepared | Unavailable:
    """Everything needed to send a question: the provider, with its key opened, and the prompt as
    that provider may read it. Changes the database only to make stand-ins."""
    row, reason, model = _unavailable(db, now, question.purpose)
    if row is None:
        return Unavailable(reason or "")
    definition = provider_def(row.provider)
    if definition is None:  # pragma: no cover - _unavailable has seen it
        return Unavailable("The AI provider is unknown.")
    try:
        target = service.load_target(db, context.settings, definition, row, context.origins)
    except service.Incomplete as incomplete:
        return Unavailable(str(incomplete))
    level = effective_level(definition, service.usage(db, now).redaction)
    key = target.secrets.get(service.API_KEY)
    redactor = Redactor(
        db,
        level,
        now,
        own=question.own,
        names=question.names,
        users=question.users,
        secrets=[key] if key else [],
    )
    prompt = redactor.finish(question.build(redactor))
    start = redactor.finish(question.start(redactor)) if question.start else ""
    return Prepared(
        question=question,
        definition=definition,
        model=model or row.model,
        target=target,
        level=level,
        system=system_for(level, question.system, start),
        prompt=prompt,
        redactor=redactor,
    )


async def send(prepared: Prepared, context: Context) -> Sent:
    """Sends a prepared question and waits for the answer. Needs no database."""
    started = time.monotonic()
    question = prepared.question
    try:
        async with ApiClient(
            prepared.target,
            context.recorder,
            context.policy_for(prepared.definition),
            deadline=DEADLINE,
            read_timeout=READ_TIMEOUT,
        ) as client:
            completion = await wire.complete(
                client,
                prepared.definition,
                prepared.model,
                prepared.target.secrets.get(service.API_KEY),
                system=prepared.system,
                prompt=prepared.prompt,
                schema=question.schema,
                max_tokens=question.max_tokens,
                cache_key=question.purpose,
            )
    except (CallFailed, wire.AiFailed) as failure:
        return Sent(None, str(failure), _milliseconds(started))
    return Sent(completion, None, _milliseconds(started))


def _milliseconds(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def cost_micros(definition: ProviderDef, model: str, completion: wire.Completion) -> int | None:
    """What an answer cost, in millionths of a dollar: nothing on the owner's own computer, the
    catalog's price for a model it knows, and unknown for the others."""
    if definition.kind is Kind.LOCAL:
        return 0
    known = definition.model(model)
    if known is None:
        return None
    dollars = known.price.cost(
        completion.input_tokens,
        completion.output_tokens,
        completion.cached_tokens,
        completion.cache_write_tokens,
    )
    return int((dollars * MICROS).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def record(db: Session, prepared: Prepared, sent: Sent, now: datetime | None = None) -> Answer:
    """Keeps what happened in ``ai_calls`` and in how the provider is doing, and gives back the
    answer with the real values in it. The caller commits."""
    now = now or utcnow()
    completion = sent.completion
    question = prepared.question
    call = AiCall(
        occurred_at=now,
        purpose=question.purpose,
        about=audit.clean(question.about, MAX_ABOUT),
        provider=prepared.definition.key,
        model=prepared.model,
        level=prepared.level.value,
        ok=completion is not None,
        duration_ms=sent.milliseconds,
        prompt=prepared.prompt,
        error=audit.clean(sent.failure, 500),
    )
    if completion is not None:
        call.input_tokens = completion.input_tokens
        call.output_tokens = completion.output_tokens
        call.cached_tokens = completion.cached_tokens
        call.cache_write_tokens = completion.cache_write_tokens
        call.reasoning_tokens = completion.reasoning_tokens
        call.truncated = completion.truncated
        call.cost_micros = cost_micros(prepared.definition, prepared.model, completion)
        call.answer = completion.text
    db.add(call)
    row = db.get(AiProvider, prepared.definition.key)
    if row is not None:
        service.record_attempt(row, Verdict(completion is not None, sent.failure or ""), now)
    db.flush()
    if completion is None:
        return Answer(ok=False, text="", reason=sent.failure, call_id=call.id)
    return Answer(
        ok=True,
        text=prepared.redactor.reveal(completion.text),
        reason=None,
        call_id=call.id,
        truncated=completion.truncated,
        provider=call.provider,
        model=call.model,
    )


def ask(
    db: Session, context: Context, question: Question, now: datetime | None = None
) -> Answer | Unavailable:
    """Prepares, sends and records a question, for code that runs in one of the API's own threads.
    The caller commits."""
    now = now or utcnow()
    prepared = prepare(db, context, question, now)
    if isinstance(prepared, Unavailable):
        return prepared
    sent = anyio.from_thread.run(send, prepared, context)
    return record(db, prepared, sent, now)
