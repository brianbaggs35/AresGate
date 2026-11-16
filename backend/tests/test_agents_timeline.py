"""How a conclusion was reached: the moments of a run, and of an incident across the agents that
looked at it, in order."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.agents import timeline
from app.models import AgentHandoff, AgentPlanStep, AgentProposal, AgentStep
from tests.test_agents_api import ran, stored
from tests.test_ai_service import NOW

MINUTE = timedelta(minutes=1)


def cites(incident: int) -> list[dict[str, str]]:
    return [{"kind": "incident", "key": str(incident), "label": f"Incident {incident}"}]


def kinds(moments: list[timeline.Moment]) -> list[str]:
    return [item.kind for item in moments]


def test_a_run_shows_its_steps_who_asked_it_whom_it_asked_and_what_it_concluded(
    session: Session,
) -> None:
    boss = stored(session, "security_orchestrator", name="Orchestrator")
    worker = stored(session, "incident_investigator", name="Investigator")
    first = ran(session, boss, finished_at=NOW + 10 * MINUTE, summary="Two things need a look.")
    second = ran(
        session,
        worker,
        trigger="handoff",
        finished_at=NOW + 20 * MINUTE,
        summary="One scan.",
        findings=[{"severity": "low", "title": "A scan", "cites": cites(4)}],
    )
    for seq, (node, title) in enumerate(
        [
            ("plan", "Planned"),
            ("act", "Looked at incident 4"),
            ("think", "Asked Anthropic"),
            ("report", "Wrote"),
        ],
        start=1,
    ):
        session.add(
            AgentStep(
                run_id=first.id,
                seq=seq,
                at=NOW + seq * MINUTE,
                node=node,
                title=title,
                detail={"summary": "One incident."} if node == "act" else {},
            )
        )
    session.add(
        AgentHandoff(
            run_id=first.id,
            from_agent_id=boss.id,
            to_kind="incident_investigator",
            to_agent_id=worker.id,
            to_run_id=second.id,
            subject="Incident 4",
            incident_id=4,
            reason="It scanned three devices.",
            status="queued",
            depth=1,
            created_at=NOW + 6 * MINUTE,
        )
    )
    session.add(
        AgentPlanStep(
            agent_id=boss.id,
            run_id=first.id,
            key="k",
            title="Isolate it",
            risk="Cuts it off.",
            status="approved",
            created_at=NOW + 7 * MINUTE,
            decided_at=NOW + 8 * MINUTE,
        )
    )
    session.commit()

    moments = timeline.for_run(session, first)

    assert kinds(moments) == [
        "began",
        "looked",
        "thought",
        "reported",
        "handoff",
        "planned",
        "decided",
        "concluded",
    ]
    assert moments[1].detail == "One incident."
    assert moments[4].title == "Asked Investigator to look into Incident 4"
    assert moments[5].detail == "Risk: Cuts it off."
    assert (moments[6].agent, moments[6].title) == ("You", "Approved the step: Isolate it")
    assert (moments[-1].title, moments[-1].detail) == ("Two things need a look.", "0 findings")

    asked = timeline.for_run(session, second)

    assert kinds(asked) == ["asked_by", "concluded"]
    assert asked[0].title == "Was asked by Orchestrator to look into Incident 4"
    assert asked[0].agent == "Investigator"


def test_a_run_that_is_not_over_has_no_conclusion_and_an_agent_that_is_gone_is_named(
    session: Session,
) -> None:
    agent = stored(session, "threat_hunter")
    running = ran(session, agent, "running")
    session.add(
        AgentHandoff(
            run_id=running.id,
            from_agent_id=agent.id,
            to_kind="network_analyst",
            subject="Incident 1",
            reason="Why.",
            status="refused",
            refusal="No agent.",
            depth=1,
            created_at=NOW,
        )
    )
    session.commit()

    [moment] = timeline.for_run(session, running)

    assert moment.kind == "handoff"
    assert moment.title == "Asked Network threat analyst to look into Incident 1"
    assert moment.detail == "Why. Refused: No agent."


def test_an_incident_shows_each_agents_part_in_it_and_nothing_about_other_incidents(
    session: Session,
) -> None:
    boss = stored(session, "security_orchestrator", name="Orchestrator")
    worker = stored(session, "incident_investigator", name="Investigator")
    other = stored(session, "threat_hunter", name="Hunter")
    looked = ran(
        session,
        worker,
        finished_at=NOW + 10 * MINUTE,
        findings=[
            {
                "severity": "high",
                "title": "Brute force",
                "detail": "Many tries.",
                "cites": cites(4),
            },
            {"severity": "low", "title": "Unrelated", "cites": cites(5)},
        ],
    )
    for seq in range(1, 10):
        session.add(
            AgentStep(
                run_id=looked.id, seq=seq, at=NOW + seq * MINUTE, node="act", title=f"Look {seq}"
            )
        )
    elsewhere = ran(
        session,
        other,
        finished_at=NOW,
        findings=[{"severity": "low", "title": "Elsewhere", "cites": cites(5)}],
    )
    session.add(
        AgentHandoff(
            run_id=elsewhere.id,
            from_agent_id=boss.id,
            to_kind="incident_investigator",
            to_agent_id=worker.id,
            to_run_id=looked.id,
            subject="Incident 4",
            incident_id=4,
            reason="Look.",
            status="queued",
            depth=1,
            created_at=NOW - MINUTE,
        )
    )
    session.add(
        AgentPlanStep(
            agent_id=boss.id,
            key="k",
            title="Block it",
            status="pending",
            created_at=NOW + 15 * MINUTE,
            incident_id=4,
        )
    )
    session.add(
        AgentProposal(
            agent_id=other.id,
            kind="duplicates",
            key="d",
            title="Two the same",
            action="dismiss",
            incident_ids=[4, 6],
            confidence=90,
            status="applied",
            created_at=NOW + 16 * MINUTE,
        )
    )
    session.commit()

    moments = timeline.for_incident(session, 4)

    assert kinds(moments) == [
        "handoff",
        "asked_by",
        "looked",
        "looked",
        "looked",
        "looked",
        "looked",
        "looked",
        "concluded",
        "planned",
        "tidy",
    ]
    conclusion = moments[8]
    assert (conclusion.agent, conclusion.title) == ("Investigator", "high: Brute force")
    assert conclusion.detail == "Many tries."
    assert moments[-1].detail == "applied"
    assert timeline.for_incident(session, 77) == []


def test_a_timeline_holds_the_newest_moments_up_to_the_limit(session: Session) -> None:
    agent = stored(session)
    run = ran(session, agent, finished_at=NOW + timeline.LIMIT * 2 * MINUTE)
    for seq in range(timeline.LIMIT + 20):
        session.add(
            AgentStep(run_id=run.id, seq=seq, at=NOW + seq * MINUTE, node="act", title=str(seq))
        )
    session.commit()

    moments = timeline.for_run(session, run)

    assert len(moments) == timeline.LIMIT
    assert moments[-1].kind == "concluded"
    assert moments[0].title == "21"
