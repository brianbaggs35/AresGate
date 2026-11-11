"""Running an agent: the graph from the first look to the report, what the model is shown and what
it says, and what is kept of each step. The provider is a server on this machine that says what it
is told to, one reply for each request."""

import asyncio
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from ipaddress import ip_address

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents import catalog, graph, probe, run, service
from app.agents import settings as agent_settings
from app.agents.run import Probing
from app.ai import tools
from app.config import Settings
from app.incidents import cleanup
from app.integrations import netguard
from app.models import (
    Agent,
    AgentProposal,
    AgentRun,
    AgentStep,
    AiCall,
    Device,
    DeviceAddress,
    Incident,
)
from app.models.base import utcnow
from tests.stubs import Answer as Reply
from tests.stubs import Seen, Serve
from tests.test_ai_gateway import Log, anthropic_says, context
from tests.test_ai_service import NOW
from tests.test_ai_triage import ATTACKER, DEVICE, incident, prompt_of, ready, signals


def new_session_for(session: Session) -> Callable[[], Session]:
    return sessionmaker(bind=session.get_bind(), expire_on_commit=False)


def said(**changes: object) -> str:
    """What a model says: by default a report with nothing found and nothing more to look at."""
    body: dict[str, object] = {"summary": "All quiet.", "findings": [], "lookups": []}
    body.update(changes)
    return json.dumps(body)


def look(tool: str, **args: object) -> dict[str, object]:
    return {"tool": tool, "id": None, "name": None, "hours": None, "limit": None, **args}


def finding(**changes: object) -> dict[str, object]:
    return {
        "severity": "high",
        "title": "A scan got further than usual",
        "detail": "Check the firewall rule for port 22.",
        "cites": [],
        **changes,
    }


class Scripted:
    """A provider that gives these replies one after another, and keeps what it was asked."""

    def __init__(self, *replies: str | Callable[[str], str]) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.bodies: list[dict[str, object]] = []

    def __call__(self, seen: Seen) -> Reply:
        prompt = prompt_of(seen)
        self.prompts.append(prompt)
        self.bodies.append(json.loads(seen.body))
        step = self.replies.pop(0)
        return anthropic_says(step if isinstance(step, str) else step(prompt))(seen)


def made(session: Session, template: str = "threat_hunter", **changes: object) -> Agent:
    fields: dict[str, object] = {
        "name": "Hunter",
        "template": template,
        "goal": "",
        "enabled": True,
        "allow_active": False,
        "created_at": NOW,
        "updated_at": NOW,
    }
    fields.update(changes)
    found = Agent(**fields)
    session.add(found)
    session.flush()
    return found


def asked(session: Session, found: Agent, trigger: str = "manual") -> int:
    waiting = service.queue(session, found, trigger, utcnow())
    session.commit()
    return waiting.id


def finished(session: Session, run_id: int) -> AgentRun:
    session.expire_all()
    return session.get_one(AgentRun, run_id)


def steps_of(session: Session, run_id: int) -> list[AgentStep]:
    session.expire_all()
    return list(
        session.scalars(select(AgentStep).where(AgentStep.run_id == run_id).order_by(AgentStep.seq))
    )


def execute(
    session: Session,
    settings: Settings,
    run_id: int,
    url: str | None = None,
    probing: Probing | None = None,
) -> None:
    asyncio.run(
        run.execute(new_session_for(session), context(settings, Log(), url), run_id, probing)
    )


def with_incident(session: Session) -> Incident:
    found = incident(session)
    signals(session, found)
    session.commit()
    return found


def test_a_run_without_ai_collects_what_the_template_looks_at_and_says_why_the_ai_took_no_part(
    session: Session, settings: Settings
) -> None:
    with_incident(session)
    run_id = asked(session, made(session))

    execute(session, settings, run_id)

    done = finished(session, run_id)
    assert done.status == "succeeded"
    assert done.error is None
    assert done.node is None
    assert done.started_at is not None
    assert done.finished_at is not None
    assert done.summary.startswith("Collected open incidents limit 5: ")
    assert "The AI took no part: AI is turned off." in done.summary
    assert done.ai == "AI is turned off. Turn it on under Settings > AI to use it."
    assert done.findings == []
    assert done.rounds == 1
    titles = [(step.node, step.title) for step in steps_of(session, run_id)]
    assert titles == [
        (
            "plan",
            "Planned what to look at first: open incidents limit 5, alerts hours 24 limit 10, "
            "blocked sources hours 24 limit 5",
        ),
        ("act", "Looked at open incidents limit 5"),
        ("act", "Looked at alerts hours 24 limit 10"),
        ("act", "Looked at blocked sources hours 24 limit 5"),
        ("think", "Didn't ask the AI"),
        ("report", "Wrote the report"),
    ]
    first_look = steps_of(session, run_id)[1]
    assert first_look.detail["tool"] == "open_incidents"
    assert f"Scan from {ATTACKER}" in str(first_look.detail["lines"])
    assert [step.seq for step in steps_of(session, run_id)] == [1, 2, 3, 4, 5, 6]


def test_a_run_shows_the_model_only_what_the_level_allows_and_keeps_its_report(
    session: Session, settings: Settings, serve: Serve
) -> None:
    seen = with_incident(session)
    provider = Scripted(
        said(
            summary="One scan reached the firewall and went no further.",
            findings=[
                finding(cites=[f"incident {seen.id}", "incident 99", f"[Incident {seen.id}]"])
            ],
        )
    )
    server = serve(provider)
    ready(session, settings, level="strict")
    found = made(session, goal=f"Watch {DEVICE} especially.")
    run_id = asked(session, found)

    execute(session, settings, run_id, server.url)

    [prompt] = provider.prompts
    assert ATTACKER not in prompt
    assert DEVICE not in prompt
    assert re.search(r"Watch HOST_\d+ especially", prompt)
    assert re.search(r"Scan from [A-Z]+_\d+", prompt)
    assert '<data label="open incidents limit 5">' in prompt
    done = finished(session, run_id)
    assert (done.status, done.ai, done.rounds) == ("succeeded", "", 1)
    assert done.summary == "One scan reached the firewall and went no further."
    [kept] = done.findings
    assert kept["severity"] == "high"
    assert kept["cites"] == [
        {"kind": "incident", "key": str(seen.id), "label": f"Incident {seen.id}"}
    ]
    [call] = session.scalars(select(AiCall)).all()
    assert call.purpose == "agent"
    assert call.about == f"agent {found.id} run {run_id}"
    assert done.call_ids == [call.id]
    asked_step = steps_of(session, run_id)[-2]
    assert asked_step.title.startswith("Asked Anthropic, ")
    assert asked_step.detail["call_id"] == call.id


def known_device(session: Session, address: str, name: str | None = None) -> None:
    now = utcnow()
    found = Device(mac="aa:bb:cc:00:00:01", hostname=name, first_seen_at=now, last_seen_at=now)
    session.add(found)
    session.flush()
    session.add(
        DeviceAddress(
            device_id=found.id, address=ip_address(address), first_seen_at=now, last_seen_at=now
        )
    )
    session.commit()


def test_a_model_that_asks_to_look_at_more_is_given_it_and_asked_again(
    session: Session, settings: Settings, serve: Serve
) -> None:
    seen = with_incident(session)
    provider = Scripted(
        said(
            lookups=[
                look("incident", id=seen.id),
                look("open_incidents", limit=5),
                look("scan_exposure"),
                look("nothing"),
                "not a lookup",
            ]
        ),
        said(summary="Nothing got in.", findings=[finding(title="  ")]),
    )
    server = serve(provider)
    ready(session, settings)
    found = made(session)
    run_id = asked(session, found)

    execute(session, settings, run_id, server.url)

    done = finished(session, run_id)
    assert (done.status, done.rounds, done.ai) == ("succeeded", 2, "")
    assert done.summary == "Nothing got in."
    assert done.findings == []
    assert len(done.call_ids) == 2
    first, second = provider.prompts
    assert f'<data label="incident id {seen.id}">' not in first
    assert f'<data label="incident id {seen.id}">' in second
    assert second.count('<data label="open incidents limit 5">') == 1
    assert "scan exposure" not in second
    assert "You cannot look at anything else now" not in second
    titles = [step.title for step in steps_of(session, run_id)]
    assert f"Looked at incident id {seen.id}" in titles
    asked_for = [
        step.detail["asked_for"] for step in steps_of(session, run_id) if "asked_for" in step.detail
    ]
    assert asked_for == [[f"incident id {seen.id}"], []]


def test_the_model_has_to_report_the_third_time_it_is_asked(
    session: Session, settings: Settings, serve: Serve
) -> None:
    provider = Scripted(
        said(lookups=[look("blocked_sources", hours=1, limit=3)]),
        said(lookups=[look("open_incidents", limit=2)]),
        said(summary="That is all.", lookups=[look("blocked_sources", hours=5, limit=1)]),
    )
    server = serve(provider)
    ready(session, settings)
    found = made(session, "intelligence_analyst")
    run_id = asked(session, found)

    execute(session, settings, run_id, server.url)

    done = finished(session, run_id)
    assert (done.status, done.rounds, done.summary) == ("succeeded", 3, "That is all.")
    assert len(provider.prompts) == 3
    assert [graph.NO_MORE in prompt for prompt in provider.prompts] == [False, False, True]
    assert "blocked sources hours 1 limit 3" in provider.prompts[1]
    assert "open incidents limit 2" in provider.prompts[2]
    assert "blocked sources hours 5 limit 1" not in "".join(provider.prompts)


def test_the_model_is_told_which_tools_the_template_allows(
    session: Session, settings: Settings, serve: Serve
) -> None:
    provider = Scripted(said())
    server = serve(provider)
    ready(session, settings)
    run_id = asked(session, made(session, "health_watch"))

    execute(session, settings, run_id, server.url)

    body = provider.bodies[0]
    system = str(body["system"])
    assert "- integrations:" in system
    assert "- open_incidents:" not in system
    assert "You can only read." in system
    assert "enum" in json.dumps(body)


def test_a_provider_that_fails_leaves_a_run_that_reports_what_it_collected(
    session: Session, settings: Settings, serve: Serve
) -> None:
    server = serve(lambda seen: Reply(status=500, body="{}"))
    ready(session, settings)
    run_id = asked(session, made(session, "health_watch"))

    execute(session, settings, run_id, server.url)

    done = finished(session, run_id)
    assert done.status == "succeeded"
    assert done.ai.startswith("The AI didn't answer:")
    assert len(done.call_ids) == 1
    assert done.summary.startswith("Collected integrations: ")
    assert "The AI took no part: The AI didn't answer" in done.summary
    [asking] = [step for step in steps_of(session, run_id) if step.node == "think"]
    assert asking.title.startswith("Asked Anthropic, ")


@pytest.mark.parametrize("text", ["I am a teapot.", "[1, 2]", "{broken}", "{broken"])
def test_an_answer_that_is_not_a_report_is_not_used(
    session: Session, settings: Settings, serve: Serve, text: str
) -> None:
    server = serve(Scripted(text))
    ready(session, settings)
    run_id = asked(session, made(session, "health_watch"))

    execute(session, settings, run_id, server.url)

    done = finished(session, run_id)
    assert done.status == "succeeded"
    assert done.ai == "The AI's answer couldn't be used."
    assert len(done.call_ids) == 1


def test_a_run_that_tests_the_network_without_being_allowed_sends_nothing(
    session: Session, settings: Settings
) -> None:
    known_device(session, "127.0.0.1", "camera")
    found = made(session, "exposure_scanner", allow_active=False)
    waiting = AgentRun(agent_id=found.id, trigger="manual", status="queued", requested_at=utcnow())
    session.add(waiting)
    session.commit()
    sent: list[str] = []

    def connect(address: str, port: int, timeout: float) -> bool:
        sent.append(address)
        return True

    execute(
        session,
        settings,
        waiting.id,
        probing=Probing(netguard.HOME_NETWORK_AND_LOOPBACK, {23: probe.PORTS[23]}, connect),
    )

    done = finished(session, waiting.id)
    assert sent == []
    assert done.status == "succeeded"
    assert done.findings == []
    assert "not run: the agent isn't allowed to test the network" in done.summary


def test_a_run_of_an_agent_allowed_to_test_the_network_reports_what_answered(
    session: Session, settings: Settings
) -> None:
    known_device(session, "127.0.0.1", "camera")
    run_id = asked(session, made(session, "exposure_scanner", allow_active=True))

    execute(
        session,
        settings,
        run_id,
        probing=Probing(
            netguard.HOME_NETWORK_AND_LOOPBACK,
            {23: probe.PORTS[23], 80: probe.PORTS[80]},
            lambda address, port, timeout: True,
        ),
    )

    done = finished(session, run_id)
    assert done.status == "succeeded"
    assert [(item["severity"], item["title"]) for item in done.findings] == [
        ("critical", "Telnet is open on camera (127.0.0.1)"),
        ("info", "HTTP is open on camera (127.0.0.1)"),
    ]
    assert done.summary.startswith("Collected scan exposure: tested 1 device, 2 open ports.")
    looked = [step for step in steps_of(session, run_id) if step.title == "Looked at scan exposure"]
    assert "Telnet" in str(looked[0].detail["lines"])


def test_a_test_of_the_network_that_finds_nothing_says_so(
    session: Session, settings: Settings
) -> None:
    known_device(session, "127.0.0.1")
    run_id = asked(session, made(session, "exposure_scanner", allow_active=True))

    execute(
        session,
        settings,
        run_id,
        probing=Probing(
            netguard.HOME_NETWORK_AND_LOOPBACK, {23: probe.PORTS[23]}, lambda a, p, t: False
        ),
    )

    done = finished(session, run_id)
    assert done.findings == []
    looked = [step for step in steps_of(session, run_id) if step.title == "Looked at scan exposure"]
    assert looked[0].detail["lines"] == ["Nothing risky answered on 1 devices."]


def test_a_run_that_was_stopped_before_it_began_is_not_run(
    session: Session, settings: Settings
) -> None:
    waiting = asked(session, made(session))
    row = session.get_one(AgentRun, waiting)
    service.cancel(row, utcnow())
    session.commit()

    execute(session, settings, waiting)

    done = finished(session, waiting)
    assert (done.status, done.started_at) == ("cancelled", None)
    assert steps_of(session, waiting) == []


def test_a_run_whose_template_is_gone_fails_and_says_so(
    session: Session, settings: Settings
) -> None:
    run_id = asked(session, made(session, "retired"))

    execute(session, settings, run_id)

    done = finished(session, run_id)
    assert (done.status, done.error) == ("failed", "The agent, or what it was made from, is gone.")


def test_a_run_the_owner_stopped_ends_before_its_next_step(
    session: Session, settings: Settings
) -> None:
    run_id = asked(session, made(session))
    session.get_one(AgentRun, run_id).cancel_requested = True
    session.commit()

    execute(session, settings, run_id)

    done = finished(session, run_id)
    assert (done.status, done.node, done.summary) == ("cancelled", None, "")
    assert [step.title for step in steps_of(session, run_id)] == ["Stopped by you"]


def test_a_run_that_breaks_fails_with_the_reason_and_keeps_the_steps_before(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object) -> list[graph.Entry]:
        raise RuntimeError("the firewall is on fire")

    monkeypatch.setattr(graph, "_look", broken)
    run_id = asked(session, made(session))

    execute(session, settings, run_id)

    done = finished(session, run_id)
    assert (done.status, done.node) == ("failed", None)
    assert done.error == "It stopped unexpectedly: the firewall is on fire"
    assert [step.node for step in steps_of(session, run_id)] == ["plan", "report"]
    assert steps_of(session, run_id)[-1].title == "Stopped"


def test_a_run_that_takes_too_long_is_ended(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def slow(*args: object) -> list[graph.Entry]:
        time.sleep(0.5)
        return []

    monkeypatch.setattr(graph, "_look", slow)
    monkeypatch.setattr(run, "DEADLINE", 0.05)
    run_id = asked(session, made(session))

    execute(session, settings, run_id)

    done = finished(session, run_id)
    assert (done.status, done.error) == ("failed", "It took longer than the agent may.")


def test_a_look_at_a_tool_that_does_not_exist_is_skipped(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    odd = replace(catalog.HEALTH_WATCH, first=(catalog.Lookup("nothing"),))

    def only(key: str) -> catalog.Template:
        del key
        return odd

    monkeypatch.setattr(catalog, "template", only)
    run_id = asked(session, made(session, "health_watch"))

    execute(session, settings, run_id)

    done = finished(session, run_id)
    assert done.status == "succeeded"
    assert done.summary.startswith("Collected nothing.")


def test_the_worker_starts_what_is_due_and_runs_everything_that_waits_in_order(
    session: Session, settings: Settings
) -> None:
    scheduled = made(
        session,
        "health_watch",
        name="Watcher",
        interval_minutes=30,
        next_run_at=utcnow() - timedelta(minutes=1),
    )
    by_hand = made(session)
    first = asked(session, by_hand)

    count = asyncio.run(run.run_once(new_session_for(session), context(settings, Log())))

    assert count == 2
    runs = list(session.scalars(select(AgentRun).order_by(AgentRun.id)))
    assert [(item.agent_id, item.trigger, item.status) for item in runs] == [
        (by_hand.id, "manual", "succeeded"),
        (scheduled.id, "schedule", "succeeded"),
    ]
    assert runs[0].id == first


def test_the_worker_ends_what_was_interrupted_forgets_the_old_and_keeps_going_after_a_failure(
    session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    found = made(session)
    stuck = AgentRun(agent_id=found.id, trigger="manual", status="running", requested_at=utcnow())
    old = AgentRun(
        agent_id=found.id,
        trigger="manual",
        status="succeeded",
        requested_at=utcnow() - service.RETENTION * 2,
        finished_at=utcnow() - service.RETENTION * 2,
    )
    session.add_all([stuck, old])
    session.commit()
    stuck_id, old_id = stuck.id, old.id
    monkeypatch.setattr(run, "PRUNE_EVERY", 0.0)
    calls: list[int] = []

    async def breaking(*args: object) -> int:
        calls.append(1)
        raise RuntimeError("no luck")

    monkeypatch.setattr(run, "run_once", breaking)

    working = asyncio.wait_for(
        run.run(
            new_session_for(session),
            context(settings, Log()),
            interval=timedelta(milliseconds=5),
        ),
        0.2,
    )

    with pytest.raises(TimeoutError):
        asyncio.run(working)

    assert len(calls) > 1
    assert "Couldn't run the agents" in caplog.text
    session.expire_all()
    assert session.get_one(AgentRun, stuck_id).status == "failed"
    assert old_id not in set(session.scalars(select(AgentRun.id)))


@pytest.mark.parametrize(("enabled", "prune_every"), [(True, 0.0), (True, 3600.0), (False, 0.0)])
def test_the_worker_runs_what_waits_again_and_again_and_does_nothing_where_collecting_is_off(
    session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    prune_every: float,
) -> None:
    ran: list[int] = []

    async def counting(*args: object) -> int:
        ran.append(1)
        return 0

    monkeypatch.setattr(run, "run_once", counting)
    monkeypatch.setattr(run, "PRUNE_EVERY", prune_every)

    working = asyncio.wait_for(
        run.run(
            new_session_for(session),
            context(settings, Log()),
            enabled=enabled,
            interval=timedelta(milliseconds=5),
        ),
        0.1,
    )

    with pytest.raises(TimeoutError):
        asyncio.run(working)

    assert bool(ran) is enabled


def test_a_run_whose_graph_cannot_be_made_fails_with_nothing_to_report(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(work: graph.Work) -> object:
        raise RuntimeError("no graph")

    monkeypatch.setattr(graph, "build", broken)
    run_id = asked(session, made(session))

    execute(session, settings, run_id)

    done = finished(session, run_id)
    assert (done.status, done.summary, done.rounds) == ("failed", "", 0)
    assert done.error == "It stopped unexpectedly: no graph"


def test_a_reply_is_read_wherever_the_model_put_its_json() -> None:
    template = catalog.THREAT_HUNTER
    fenced = '```json\n{"summary": "Fine.", "findings": [], "lookups": []}\n```'
    sentence = 'Here you go: {"summary": "Fine.", "findings": [], "lookups": []} Thanks.'

    assert graph.parse(fenced, template) == graph.Reading("Fine.", [], [])
    assert graph.parse(sentence, template) == graph.Reading("Fine.", [], [])
    assert graph.parse("no braces at all", template) is None
    assert graph.parse("[]", template) is None
    assert graph.parse("{nope}", template) is None
    assert run.steps_of(None) == []
    assert run.steps_of({"steps": None}) == []


def test_what_a_model_says_is_cut_down_to_what_is_allowed() -> None:
    template = catalog.THREAT_HUNTER
    said_text = json.dumps(
        {
            "summary": 7,
            "findings": [
                finding(severity="catastrophic", title="x" * 500, detail=None, cites="nothing"),
                "not a finding",
                *[finding(title=f"Finding {n}") for n in range(30)],
            ],
            "lookups": [
                look("device", name="nas" + "\x00", id=True, hours=2.7, limit=None),
                *[look("alerts") for _ in range(10)],
                look("reputation"),
                {"tool": 5},
            ],
        }
    )

    reading = graph.parse(said_text, template)

    assert reading is not None
    assert reading.summary == ""
    assert len(reading.findings) == graph.MAX_FINDINGS
    assert reading.findings[0] == ("info", "x" * graph.MAX_TITLE, "", [])
    assert len(reading.lookups) == graph.MAX_LOOKUPS
    assert reading.lookups[0] == catalog.Lookup(
        "device", tools.Args(id=None, name="nas", hours=2, limit=None)
    )
    assert all(item.tool in template.asks for item in reading.lookups)


def test_a_reply_that_names_no_lists_is_a_report_with_nothing_in_it() -> None:
    reading = graph.parse(
        '{"summary": "Quiet.", "findings": "none", "lookups": null}', catalog.HEALTH_WATCH
    )

    assert reading == graph.Reading("Quiet.", [], [])


def test_a_finding_cites_only_what_the_agent_was_given() -> None:
    entries = [
        graph.Entry(
            tool="open_incidents",
            label="open incidents",
            summary="1 incident",
            lines=[],
            refs=[{"kind": "incident", "key": "3", "label": "Incident 3"}],
            hits=[],
        )
    ]

    assert graph.cited(["[incident 3]", "Incident 3", "incident 4", "integration x"], entries) == [
        {"kind": "incident", "key": "3", "label": "Incident 3"}
    ]


def test_the_graph_is_the_one_langgraph_describes() -> None:
    assert {(edge.source, edge.target, edge.conditional) for edge in graph.structure()} == {
        ("plan", "act", False),
        ("act", "think", False),
        ("think", "act", True),
        ("think", "report", True),
    }


def test_what_langgraph_would_trace_is_switched_off() -> None:
    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"


def test_every_template_names_only_tools_that_exist_and_lookups_the_model_may_ask_for() -> None:
    for item in catalog.TEMPLATES:
        assert all(tools.by_name(name) is not None for name in item.asks)
        assert {lookup.tool for lookup in item.first} <= {*item.asks, *tools.names(), graph.SCAN}
        assert graph.system_for(item).startswith("You are an agent of AresGate")
        assert graph.schema(item)["required"] == [
            "summary",
            "findings",
            "lookups",
            *(["rejects"] if item.proposes else []),
        ]


def kept_run(session: Session, found: Agent, status: str = "succeeded", **changes: object) -> None:
    fields: dict[str, object] = {
        "agent_id": found.id,
        "trigger": "manual",
        "status": status,
        "requested_at": NOW,
        "finished_at": utcnow() - timedelta(hours=5, minutes=30),
        "summary": "Two scans, nothing else.",
        "findings": [
            {"severity": "high", "title": "Port 22 is being hammered", "detail": "", "cites": []},
            {"severity": "low", "title": "A new camera appeared", "detail": "", "cites": []},
        ],
        **changes,
    }
    session.add(AgentRun(**fields))
    session.commit()


def test_a_run_is_told_what_the_last_one_reported_and_says_which_findings_are_ongoing(
    session: Session, settings: Settings, serve: Serve
) -> None:
    provider = Scripted(
        said(
            summary="Port 22 is still being hammered.",
            findings=[
                finding(title="port 22 is being HAMMERED!"),
                finding(title="A new printer appeared", severity="low"),
            ],
        )
    )
    server = serve(provider)
    ready(session, settings)
    found = made(session)
    kept_run(session, found)
    kept_run(session, found, status="failed", summary="Never used.", findings=[])
    run_id = asked(session, found)

    execute(session, settings, run_id, server.url)

    [prompt] = provider.prompts
    assert "Your last run was 5 hours ago and reported: Two scans, nothing else." in prompt
    assert "- high: Port 22 is being hammered" in prompt
    assert "- low: A new camera appeared" in prompt
    assert "Never used." not in prompt
    assert "Say what has changed since." in prompt
    done = finished(session, run_id)
    assert [(item["title"], item["status"]) for item in done.findings] == [
        ("port 22 is being HAMMERED!", "ongoing"),
        ("A new printer appeared", "new"),
    ]


def test_a_first_run_is_not_told_of_one_before_it_and_its_findings_are_new(
    session: Session, settings: Settings, serve: Serve
) -> None:
    provider = Scripted(said(findings=[finding()]))
    server = serve(provider)
    ready(session, settings)
    found = made(session)
    run_id = asked(session, found)

    execute(session, settings, run_id, server.url)

    assert "Your last run" not in provider.prompts[0]
    assert [item["status"] for item in finished(session, run_id).findings] == ["new"]


def test_a_last_run_that_found_nothing_is_reported_as_nothing(
    session: Session, settings: Settings, serve: Serve
) -> None:
    provider = Scripted(said())
    server = serve(provider)
    ready(session, settings)
    found = made(session)
    kept_run(session, found, summary="", findings=[])
    run_id = asked(session, found)

    execute(session, settings, run_id, server.url)

    assert "reported: nothing" in provider.prompts[0]
    assert "It raised:" not in provider.prompts[0]


def test_what_the_last_run_said_is_made_safe_for_a_provider_that_may_not_see_addresses(
    session: Session, settings: Settings, serve: Serve
) -> None:
    provider = Scripted(said())
    server = serve(provider)
    ready(session, settings, level="strict")
    found = made(session)
    kept_run(session, found, summary=f"{ATTACKER} scanned {DEVICE}.", findings=[])
    run_id = asked(session, found)

    execute(session, settings, run_id, server.url)

    assert ATTACKER not in provider.prompts[0]
    assert DEVICE not in provider.prompts[0]


class TestTheCleanupAgent:
    """The agent that tidies: it works without an AI, the model may only leave candidates alone,
    and the surest are done by the agent itself only where the agents have been set to."""

    def stage(self, session: Session) -> tuple[Agent, list[str]]:
        # The worker judges what is old by the clock, so what is staged is dated by it too.
        now = utcnow()
        for number in (1, 2):
            incident(
                session,
                subject=f"198.51.100.{number}",
                title="Scan of ssh",
                severity=number,
                last_seen_at=now - timedelta(minutes=5),
            )
        incident(
            session, subject="198.51.100.40", title="Old", last_seen_at=now - timedelta(days=9)
        )
        session.commit()
        found = made(session, "noise_cleaner", name="Tidy")
        return found, [item.key for item in cleanup.find(session, now)]

    def test_without_an_ai_it_still_suggests_what_it_found_and_says_so(
        self, session: Session, settings: Settings
    ) -> None:
        found, keys = self.stage(session)
        run_id = asked(session, found)

        execute(session, settings, run_id)

        done = finished(session, run_id)
        assert done.status == "succeeded"
        assert done.ai
        rows = session.scalars(select(AgentProposal).order_by(AgentProposal.id)).all()
        assert sorted(row.key for row in rows) == sorted(keys)
        assert {row.status for row in rows} == {"pending"}
        assert {row.run_id for row in rows} == {run_id}
        assert steps_of(session, run_id)[-1].title == "Suggested 2 clean-ups"

    def test_the_model_is_told_the_candidates_and_may_name_ones_to_leave_alone(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        found, keys = self.stage(session)
        provider = Scripted(said(rejects=[keys[0], "not-a-key"]))
        server = serve(provider)
        ready(session, settings)
        run_id = asked(session, found)

        execute(session, settings, run_id, server.url)

        [prompt] = provider.prompts
        assert all(f"[candidate {key}]" in prompt for key in keys)
        assert "Candidates for tidying appear as [candidate KEY]" in str(provider.bodies[0])
        kept_keys = session.scalars(select(AgentProposal.key)).all()
        assert kept_keys == keys[1:]
        assert steps_of(session, run_id)[-1].title == "Suggested 1 clean-up"

    def test_other_kinds_are_not_told_about_candidates_or_asked_to_reject(self) -> None:
        assert "rejects" not in graph.schema(catalog.THREAT_HUNTER)["properties"]  # type: ignore[operator]
        assert "[candidate" not in graph.system_for(catalog.THREAT_HUNTER)
        assert "rejects" in graph.schema(catalog.NOISE_CLEANER)["properties"]  # type: ignore[operator]

    def test_where_the_agents_may_it_does_the_surest_itself_and_says_so(
        self, session: Session, settings: Settings
    ) -> None:
        found, _ = self.stage(session)
        agent_settings.get(session, utcnow()).cleanup_mode = "auto"
        session.commit()
        run_id = asked(session, found)

        execute(session, settings, run_id)

        by_kind = {row.kind: row for row in session.scalars(select(AgentProposal))}
        assert by_kind["stale"].status == "applied"
        assert by_kind["stale"].decided_by == "agent"
        assert by_kind["duplicates"].status == "pending"
        last = steps_of(session, run_id)[-1]
        assert last.title == "Suggested 1 clean-up, and tidied 1 thing itself"
        assert last.detail["applied"] == 1

    def test_a_run_with_nothing_to_tidy_says_so(self, session: Session, settings: Settings) -> None:
        found = made(session, "noise_cleaner")
        session.commit()
        run_id = asked(session, found)

        execute(session, settings, run_id)

        assert steps_of(session, run_id)[-1].title == "Nothing new to tidy"
