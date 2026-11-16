"""The steps the response planner proposes: kept once, decided once, and forgotten when old."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import plans, service
from app.agents.plans import Planned
from app.models import AgentPlanStep
from tests.test_agents_api import ran, stored
from tests.test_ai_service import NOW

DAY = timedelta(days=1)


def planned(title: str = "Isolate the camera", incident: int | None = 3) -> Planned:
    return Planned(title, "Move it to the guest network.", "It is off the network.", incident)


def test_a_step_is_kept_once_however_it_is_worded_and_only_so_many_at_a_time(
    session: Session,
) -> None:
    agent = stored(session, "response_planner")
    run = ran(session, agent)

    first = plans.record(
        session, agent.id, run.id, [planned(), planned("ISOLATE the camera.")], NOW
    )
    again = plans.record(session, agent.id, run.id, [planned()], NOW)
    many = plans.record(
        session, agent.id, run.id, [planned(f"Step {number}", None) for number in range(20)], NOW
    )

    assert [item.status for item in first] == ["pending"]
    assert again == []
    assert len(many) == plans.MAX_STEPS


def test_a_step_is_decided_once(session: Session) -> None:
    agent = stored(session, "response_planner")
    [step] = plans.record(session, agent.id, ran(session, agent).id, [planned()], NOW)

    plans.decide(step, True, NOW)

    assert (step.status, step.decided_at) == ("approved", NOW)
    with pytest.raises(plans.Settled, match="already been approved"):
        plans.decide(step, False, NOW)


def test_a_step_that_was_dismissed_is_not_proposed_again(session: Session) -> None:
    agent = stored(session, "response_planner")
    run = ran(session, agent)
    [step] = plans.record(session, agent.id, run.id, [planned()], NOW)
    plans.decide(step, False, NOW)

    assert plans.record(session, agent.id, run.id, [planned()], NOW) == []
    assert step.status == "dismissed"


def test_old_steps_are_forgotten_decided_after_ninety_days_and_waiting_after_thirty(
    session: Session,
) -> None:
    agent = stored(session, "response_planner")
    run = ran(session, agent)
    for title, status, created, decided in (
        ("decided long ago", "approved", NOW - 100 * DAY, NOW - 91 * DAY),
        ("decided lately", "approved", NOW - 100 * DAY, NOW - 5 * DAY),
        ("waiting too long", "pending", NOW - 31 * DAY, None),
        ("waiting", "pending", NOW - 3 * DAY, None),
    ):
        session.add(
            AgentPlanStep(
                agent_id=agent.id,
                run_id=run.id,
                key=title,
                title=title,
                status=status,
                created_at=created,
                decided_at=decided,
            )
        )
    session.commit()

    service.prune(session, NOW)
    session.commit()

    kept = session.scalars(select(AgentPlanStep.title).order_by(AgentPlanStep.id)).all()
    assert list(kept) == ["decided lately", "waiting"]
