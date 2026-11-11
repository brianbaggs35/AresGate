"""What one run of an agent does, as a LangGraph graph.

    plan -> act -> think -> report
              ^______|        (while the model asks to look at more, up to three rounds)

``plan`` decides what to look at first (from the template). ``act`` looks, with the tools of
app/ai/tools.py, which only read, and, for an agent allowed to, tests the devices on the network
(app/agents/probe.py). ``think`` shows what was found to the AI provider through the gateway
(app/ai/gateway.py), so a provider only sees what the redaction level allows and every request is
recorded, and gets back a report and perhaps more to look at, which sends the run round again.
``report`` settles the summary and the findings. Where the AI is off, not set up or not answering,
the run is still a run: it reports what it collected and says why the AI took no part.

Each node says what it did in ``steps``, which the runner (app/agents/run.py) keeps as the run
goes, so that the web app can show an agent at work.
"""

import asyncio
import json
import operator
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Final, NamedTuple, TypedDict, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.agents import catalog, fingerprint, flow, probe, proposals
from app.agents import settings as agent_settings
from app.agents.catalog import Lookup, Template
from app.ai import gateway, tools
from app.ai.gateway import Context, Question, Unavailable
from app.ai.redaction import Level, Redactor
from app.ai.tools import Args
from app.incidents import cleanup
from app.integrations import netguard
from app.integrations.netguard import AddressPolicy
from app.models import Device
from app.models.base import utcnow

PURPOSE: Final = "agent"
SCAN: Final = "scan_exposure"
READ: Final = "read_services"
ACTIVE: Final = (SCAN, READ)
# The model is asked up to this many times: it may ask to look at more twice, and the last time
# has to answer with what it has.
MAX_ROUNDS: Final = 3
MAX_LOOKUPS: Final = 4
MAX_LINES: Final = 40
MAX_FINDINGS: Final = 12
MAX_SUMMARY: Final = 1500
MAX_TITLE: Final = 160
MAX_DETAIL: Final = 800
MAX_ACTION: Final = 400
CONFIDENCE: Final = ("low", "medium", "high")
MAX_GOAL: Final = 2000
MAX_TOKENS: Final = 1800
MAX_NAMES: Final = 500
NO_MORE: Final = "You cannot look at anything else now: report with what you have."


class Step(TypedDict):
    """One thing a node did, for the owner to follow."""

    title: str
    detail: dict[str, object]


class Entry(TypedDict):
    """What one look found. ``lines`` are as the owner reads them; what a provider is shown is made
    from them again, through its redactor. ``hits`` are the open ports of a test."""

    tool: str
    label: str
    summary: str
    lines: list[str]
    refs: list[dict[str, str]]
    hits: list[dict[str, object]]


class Finding(TypedDict):
    severity: str
    title: str
    detail: str
    cites: list[dict[str, str]]
    # What the owner should do about it, and how sure the agent is: low, medium or high.
    action: str
    confidence: str
    # Whether the agent's last run reported the same thing: ``new`` or ``ongoing``.
    status: str


class State(TypedDict):
    round: int
    pending: list[Lookup]
    ran: Annotated[list[Entry], operator.add]
    findings: list[Finding]
    summary: str
    # Why the AI took no part, or empty when it did.
    ai: str
    call_ids: Annotated[list[int], operator.add]
    steps: list[Step]
    # The keys of the candidates for tidying that the model said to leave alone.
    rejects: list[str]


def initial() -> State:
    return State(
        round=0,
        pending=[],
        ran=[],
        findings=[],
        summary="",
        ai="",
        call_ids=[],
        steps=[],
        rejects=[],
    )


@dataclass(frozen=True)
class Previous:
    """What an agent's last run that finished reported, so that the next one can say what has
    changed instead of saying it all again."""

    at: datetime
    summary: str
    findings: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Snapshot:
    """What a run needs to know of its agent, read before it starts."""

    agent_id: int
    run_id: int
    name: str
    goal: str
    allow_active: bool
    template: Template
    previous: Previous | None = None


@dataclass(frozen=True)
class Work:
    """What the nodes of a run work with: where to get a session, how to ask a provider, and who
    the agent is. ``policy``, ``ports`` and ``connect`` are how devices are tested, which only a
    test of the agents changes."""

    snapshot: Snapshot
    new_session: Callable[[], Session]
    context: Context
    policy: AddressPolicy = netguard.HOME_NETWORK
    ports: Mapping[int, probe.Service] = field(default_factory=lambda: probe.PORTS)
    connect: Callable[[str, int, float], bool] = probe.connects
    read: fingerprint.Reader = fingerprint.look
    read_ports: Sequence[int] = fingerprint.PORTS


def label(lookup: Lookup) -> str:
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
    return " ".join([lookup.tool.replace("_", " "), *given])


# -- what the model is told


def _tool_list(template: Template) -> str:
    described = [(name, tools.by_name(name)) for name in template.asks]
    return "\n".join(f"- {tool.name}: {tool.description}" for _, tool in described if tool)


def system_for(template: Template) -> str:
    asked = (
        'To look at more, name a tool in "lookups" (up to four) and leave "findings" for '
        "when you have looked. You are asked again with what was found, and may look at more once. "
        'Fill "id", "name", "hours" and "limit" only as the tool uses them and leave the '
        f"rest null. The tools:\n{_tool_list(template)}"
        if template.asks
        else ""
    )
    tidy = (
        "Candidates for tidying appear as [candidate KEY]. Every one is suggested to the owner "
        'unless you name its key in "rejects", which you should do for any that hides something '
        "real, saying why in a finding. Only name keys you were given.\n\n"
        if template.proposes
        else ""
    )
    return f"""\
You are an agent of AresGate, a security monitor for one home network. {template.brief}

You can only read. You cannot change anything in AresGate or on the network, and you must never \
say that you did or that you will. Answer only from the facts you are given. If they do not say \
it, say that you do not know. Never invent incidents, addresses, devices, numbers or products. \
Most traffic from the internet to a home network is automated scanning that never succeeds and is \
not worth waking anyone for; say so when that is what you see, and be honest when something is \
worth the owner's attention.

{asked}

"summary" is your report in a few short sentences, the most important thing first. "findings" \
are the things worth the owner's attention, each with a severity (info, low, medium, high or \
critical), a short title, "detail" (what you saw and why it matters), "action" (the one thing to \
do about it, or an empty string when there is nothing to do) and "confidence" (low, medium or \
high: how sure you are, given only what you were shown); leave "findings" empty when there is \
nothing. Write an incident as [incident 3]. In a finding's "cites" list what it is based on, as \
"incident 3" or "integration opnsense", only things that appeared in what you were given.

{tidy}Answer only with the JSON you are asked for.\
"""


def schema(template: Template) -> Mapping[str, object]:
    lookup: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "tool": {"type": "string", "enum": list(template.asks) or ["none"]},
            "id": {"type": ["integer", "null"]},
            "name": {"type": ["string", "null"]},
            "hours": {"type": ["integer", "null"]},
            "limit": {"type": ["integer", "null"]},
        },
        "required": ["tool", "id", "name", "hours", "limit"],
    }
    finding: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "severity": {"type": "string", "enum": list(probe.SEVERITIES)},
            "title": {"type": "string"},
            "detail": {"type": "string"},
            "cites": {"type": "array", "items": {"type": "string"}},
            "action": {"type": "string"},
            "confidence": {"type": "string", "enum": list(CONFIDENCE)},
        },
        "required": ["severity", "title", "detail", "cites", "action", "confidence"],
    }
    properties: dict[str, object] = {
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": finding},
        "lookups": {"type": "array", "items": lookup},
    }
    required = ["summary", "findings", "lookups"]
    if template.proposes:
        properties["rejects"] = {"type": "array", "items": {"type": "string"}}
        required.append("rejects")
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _evidence(redactor: Redactor, ran: Sequence[Entry]) -> list[str]:
    return [redactor.evidence(entry["label"], entry["lines"]) for entry in ran]


def _memory(redactor: Redactor, previous: Previous, now: datetime) -> str:
    """What the last run said, for this one to build on. Its words are written by a model, so they
    go through the redactor like everything else that is shown to a provider."""
    hours = max(0, int((now - previous.at).total_seconds() // 3600))
    lines = [
        f"Your last run was {hours} hours ago and reported: "
        f"{redactor.text(previous.summary, MAX_SUMMARY) or 'nothing'}"
    ]
    if previous.findings:
        lines.append("It raised:")
        lines += [
            f"- {severity}: {redactor.text(title, MAX_TITLE)}"
            for severity, title in previous.findings
        ]
    lines.append(
        "Say what has changed since. Report something again only if it is still true and still "
        "matters, and say that it is ongoing; do not repeat what is settled."
    )
    return "\n".join(lines)


def question_for(
    snapshot: Snapshot, ran: Sequence[Entry], names: Sequence[str], now: datetime, *, last: bool
) -> Question:
    def build(redactor: Redactor) -> str:
        parts = [f"It is {now:%Y-%m-%d %H:%M} UTC."]
        if snapshot.goal.strip():
            parts.append(
                f"The owner's instructions to you: {redactor.text(snapshot.goal, MAX_GOAL)}"
            )
        if snapshot.previous is not None:
            parts.append(_memory(redactor, snapshot.previous, now))
        parts += _evidence(redactor, ran)
        if last:
            parts.append(NO_MORE)
        return "\n\n".join(parts)

    return Question(
        purpose=PURPOSE,
        system=system_for(snapshot.template),
        build=build,
        about=f"agent {snapshot.agent_id} run {snapshot.run_id}",
        schema=schema(snapshot.template),
        max_tokens=MAX_TOKENS,
        names=names,
    )


# -- what the model said


class Raised(NamedTuple):
    """One finding as the model wrote it, before what it cites is checked."""

    severity: str
    title: str
    detail: str
    cites: list[str]
    action: str
    confidence: str


@dataclass(frozen=True)
class Reading:
    summary: str
    findings: list[Raised]
    lookups: list[Lookup]
    rejects: list[str] = field(default_factory=list[str])


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
    """The fields of a JSON object the model wrote, or None if it is not one."""
    return cast("dict[str, object]", item) if isinstance(item, dict) else None


def _items(item: object) -> list[object]:
    """The items of a JSON list the model wrote, or none if it is not a list."""
    return cast("list[object]", item) if isinstance(item, list) else []


def _lookup(item: object, template: Template) -> Lookup | None:
    fields = _fields(item)
    if fields is None:
        return None
    name = fields.get("tool")
    # What the template does not allow is ignored, so a model can't ask for anything else, a test
    # of the network least of all.
    if not isinstance(name, str) or name not in template.asks:
        return None
    given = fields.get("name")
    return Lookup(
        name,
        Args(
            id=_number(fields.get("id")),
            name=audit.clean(given, 120) if isinstance(given, str) else None,
            hours=_number(fields.get("hours")),
            limit=_number(fields.get("limit")),
        ),
    )


def _finding(item: object) -> Raised | None:
    fields = _fields(item)
    if fields is None:
        return None
    title = fields.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    severity = fields.get("severity")
    detail = fields.get("detail")
    cites = fields.get("cites")
    action = fields.get("action")
    confidence = fields.get("confidence")
    return Raised(
        severity if isinstance(severity, str) and severity in probe.SEVERITIES else "info",
        audit.clean(title, MAX_TITLE) or "",
        (audit.clean(detail, MAX_DETAIL) or "") if isinstance(detail, str) else "",
        [cite for cite in _items(cites) if isinstance(cite, str)],
        (audit.clean(action, MAX_ACTION) or "") if isinstance(action, str) else "",
        confidence if isinstance(confidence, str) and confidence in CONFIDENCE else "medium",
    )


def parse(text: str, template: Template) -> Reading | None:
    """What a reply says, or None if it is not a report."""
    try:
        loaded = _loads(text)
    except ValueError:
        return None
    fields = _fields(loaded)
    if fields is None:
        return None
    summary = fields.get("summary")
    found = fields.get("findings")
    asked = fields.get("lookups")
    findings = [kept for item in _items(found) if (kept := _finding(item)) is not None]
    lookups = [kept for item in _items(asked) if (kept := _lookup(item, template)) is not None]
    rejects = [item for item in _items(fields.get("rejects")) if isinstance(item, str)]
    return Reading(
        summary=(audit.clean(summary, MAX_SUMMARY) or "") if isinstance(summary, str) else "",
        findings=findings[:MAX_FINDINGS],
        lookups=lookups[:MAX_LOOKUPS],
        rejects=[audit.clean(item, 60) or "" for item in rejects[: MAX_FINDINGS * 3]],
    )


def same(title: str) -> str:
    """What makes two findings the same: their words, not their capitals or punctuation."""
    return " ".join(re.findall(r"[a-z0-9]+", title.lower()))


def status_of(title: str, previous: Previous | None) -> str:
    """Whether the agent's last run reported this already."""
    if previous is not None and any(same(title) == same(old) for _, old in previous.findings):
        return "ongoing"
    return "new"


def cited(names: list[str], ran: Sequence[Entry]) -> list[dict[str, str]]:
    """What a finding cites that was really in what the agent was given."""
    known = {f"{ref['kind']} {ref['key']}".lower(): ref for entry in ran for ref in entry["refs"]}
    kept: dict[str, dict[str, str]] = {}
    for name in names:
        ref = known.get(name.strip(" []").lower())
        if ref is not None:
            kept.setdefault(f"{ref['kind']} {ref['key']}", ref)
    return list(kept.values())


# -- the nodes


def _look(work: Work, lookups: Sequence[Lookup], now: datetime) -> list[Entry]:
    """Looks at each thing asked for, and gives back what was found."""
    entries: list[Entry] = []
    with work.new_session() as db:
        # The owner reads what is found as it is: it is only made safe for a provider later.
        redactor = Redactor(db, Level.LOCAL, now)
        for lookup in lookups:
            if lookup.tool in ACTIVE:
                entries.append(_test(work, db, lookup, now))
                continue
            tool = tools.by_name(lookup.tool)
            if tool is None:
                continue
            found = tool.run(db, redactor, lookup.args, now)
            entries.append(
                Entry(
                    tool=lookup.tool,
                    label=label(lookup),
                    summary=found.summary,
                    lines=found.lines,
                    refs=[
                        {"kind": ref.kind, "key": ref.key, "label": ref.label} for ref in found.refs
                    ],
                    hits=[],
                )
            )
    return entries


def _test(work: Work, db: Session, lookup: Lookup, now: datetime) -> Entry:
    """Tests the devices on the network, if the agent has been allowed to."""
    if not work.snapshot.allow_active:
        return Entry(
            tool=lookup.tool,
            label=label(lookup),
            summary="not run: the agent isn't allowed to test the network",
            lines=["The agent hasn't been allowed to test the network, so nothing was sent."],
            refs=[],
            hits=[],
        )
    if lookup.tool == READ:
        found = fingerprint.scan(db, now, policy=work.policy, ports=work.read_ports, read=work.read)
        summary = fingerprint.summary(found)
        nothing = f"Nothing worth saying in what the services of {found.tested} devices announce."
    else:
        found = probe.scan(db, now, policy=work.policy, ports=work.ports, connect=work.connect)
        summary = probe.summary(found)
        nothing = f"Nothing risky answered on {found.tested} devices."
    return Entry(
        tool=lookup.tool,
        label=label(lookup),
        summary=summary,
        lines=[probe.line(hit) for hit in found.hits] or [nothing],
        refs=[],
        hits=[
            {
                "device": hit.target.label,
                "title": hit.headline,
                "port": hit.port,
                "service": hit.service.name,
                "severity": hit.service.severity,
                "why": hit.service.why,
            }
            for hit in found.hits
        ],
    )


def _names(db: Session) -> list[str]:
    return [
        name
        for name in db.scalars(
            select(Device.hostname).where(Device.hostname.is_not(None)).limit(MAX_NAMES)
        )
        if name
    ]


def _step_of(entry: Entry) -> Step:
    return Step(
        title=f"Looked at {entry['label']}",
        detail={
            "tool": entry["tool"],
            "summary": entry["summary"],
            "lines": entry["lines"][:MAX_LINES],
            "more": max(0, len(entry["lines"]) - MAX_LINES),
            "refs": entry["refs"][:MAX_LINES],
        },
    )


def build(work: Work) -> object:
    """The graph of one run."""
    template = work.snapshot.template

    def plan(state: State) -> dict[str, object]:
        del state
        first = list(template.first)
        return {
            "round": 1,
            "pending": first,
            "steps": [
                Step(
                    title=f"Planned what to look at first: {', '.join(label(i) for i in first)}",
                    detail={"template": template.key},
                )
            ],
        }

    async def act(state: State) -> dict[str, object]:
        entries = await asyncio.to_thread(_look, work, state["pending"], utcnow())
        return {"ran": entries, "pending": [], "steps": [_step_of(entry) for entry in entries]}

    async def think(state: State) -> dict[str, object]:
        last = state["round"] >= MAX_ROUNDS
        now = utcnow()

        def prepare() -> gateway.Prepared | Unavailable:
            with work.new_session() as db:
                prepared = gateway.prepare(
                    db,
                    work.context,
                    question_for(work.snapshot, state["ran"], _names(db), now, last=last),
                    now,
                )
                db.commit()
                return prepared

        prepared = await asyncio.to_thread(prepare)
        if isinstance(prepared, Unavailable):
            return _without_ai(prepared.reason, "Didn't ask the AI")
        sent = await gateway.send(prepared, work.context)

        def record() -> gateway.Answer:
            with work.new_session() as db:
                answer = gateway.record(db, prepared, sent, now)
                db.commit()
                return answer

        answer = await asyncio.to_thread(record)
        who = f"{prepared.definition.label}, {prepared.model}"
        if not answer.ok:
            return {
                **_without_ai(f"The AI didn't answer: {answer.reason}", f"Asked {who}"),
                "call_ids": [answer.call_id],
            }
        reading = parse(answer.text, template)
        if reading is None:
            return {
                **_without_ai("The AI's answer couldn't be used.", f"Asked {who}"),
                "call_ids": [answer.call_id],
            }
        done = {entry["tool"] + entry["label"] for entry in state["ran"]}
        more = (
            []
            if last
            else [item for item in reading.lookups if item.tool + label(item) not in done]
        )
        findings = _findings_of(reading, state["ran"], work.snapshot.previous)
        return {
            "ai": "",
            "summary": reading.summary,
            "findings": findings,
            "pending": more,
            "rejects": reading.rejects,
            "round": state["round"] + 1 if more else state["round"],
            "call_ids": [answer.call_id],
            "steps": [
                Step(
                    title=f"Asked {who}",
                    detail={
                        "call_id": answer.call_id,
                        "summary": reading.summary,
                        "findings": len(findings),
                        "asked_for": [label(item) for item in more],
                    },
                )
            ],
        }

    async def report(state: State) -> dict[str, object]:
        return await _report(work, state)

    def route(state: State) -> str:
        return "act" if state["pending"] else "report"

    return flow.compile_graph(
        State, {"plan": plan, "act": act, "think": think, "report": report}, route
    )


def _findings_of(
    reading: Reading, ran: Sequence[Entry], previous: Previous | None
) -> list[Finding]:
    """What the model made of what was looked at, each finding marked new or ongoing."""
    return [
        Finding(
            severity=raised.severity,
            title=raised.title,
            detail=raised.detail,
            cites=cited(raised.cites, ran),
            action=raised.action,
            confidence=raised.confidence,
            status=status_of(raised.title, previous),
        )
        for raised in reading.findings
    ]


async def _report(work: Work, state: State) -> dict[str, object]:
    """Settles the report: what the model said, or what was collected when it said nothing, and,
    for an agent that suggests tidying, the suggestions."""
    findings = state["findings"] or _found_by_testing(state["ran"])
    summary = state["summary"] or _collected(state)
    steps = [Step(title="Wrote the report", detail={"findings": len(findings)})]
    if work.snapshot.template.proposes:
        steps.append(await asyncio.to_thread(_suggest, work, state["rejects"]))
    return {"summary": summary, "findings": findings, "steps": steps}


def _suggest(work: Work, rejects: Sequence[str]) -> Step:
    """Keeps what could be tidied as suggestions for the owner, and does the surest of it where the
    agents have been set to. The model only chooses what to leave alone."""
    now = utcnow()
    with work.new_session() as db:
        found = cleanup.find(db, now)
        auto = agent_settings.get(db, now).cleanup_mode == "auto"
        made, done = proposals.record(
            db, work.snapshot.agent_id, work.snapshot.run_id, found, set(rejects), now, auto=auto
        )
        db.commit()
        pending = len(made) - len(done)
        title = f"Suggested {_plural(pending, 'clean-up')}" if pending else "Nothing new to tidy"
        if done:
            title += f", and tidied {_plural(len(done), 'thing')} itself"
        return Step(
            title=title,
            detail={
                "lines": [f"{item.title} ({item.status})" for item in made],
                "suggested": pending,
                "applied": len(done),
            },
        )


def _plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else many or one + 's'}"


def _without_ai(reason: str, title: str) -> dict[str, object]:
    return {
        "ai": reason,
        "pending": [],
        "steps": [Step(title=title, detail={"reason": reason})],
    }


def _found_by_testing(ran: Sequence[Entry]) -> list[Finding]:
    """What a test of the network found, as findings, for a run the AI took no part in."""
    return [
        Finding(
            severity=str(hit["severity"]),
            title=str(hit["title"]),
            detail=str(hit["why"]),
            cites=[],
            action="",
            # A port that answered did answer, whatever the AI says of it.
            confidence="high",
            status="new",
        )
        for entry in ran
        for hit in entry["hits"]
    ]


def _collected(state: State) -> str:
    """The report of a run the AI took no part in: what was collected, and why it didn't."""
    found = "; ".join(f"{entry['label']}: {entry['summary']}" for entry in state["ran"])
    reason = f" The AI took no part: {state['ai']}" if state["ai"] else ""
    return f"Collected {found or 'nothing'}.{reason}"


def structure() -> list[flow.Edge]:
    """The graph of a run, as LangGraph describes it, for the page that draws it."""

    def unused() -> Session:  # pragma: no cover - the nodes are never run
        raise NotImplementedError

    snapshot = Snapshot(0, 0, "", "", False, catalog.THREAT_HUNTER)
    return flow.edges_of(build(Work(snapshot, unused, cast("Context", None))))
