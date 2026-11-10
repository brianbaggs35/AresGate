"""What is done to agents and their runs: asking for a run, starting the ones that are due,
stopping one, and forgetting the old."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import catalog, service
from app.models import Agent, AgentRun, AgentStep

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def agent(session: Session, template: str = "threat_hunter", **changes: object) -> Agent:
    fields: dict[str, object] = {
        "name": "Hunter",
        "template": template,
        "goal": "",
        "enabled": True,
        "interval_minutes": None,
        "allow_active": False,
        "next_run_at": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    fields.update(changes)
    made = Agent(**fields)
    session.add(made)
    session.flush()
    return made


def test_a_run_is_asked_for_and_waits_for_the_worker(session: Session) -> None:
    made = agent(session)

    run = service.queue(session, made, "manual", NOW)

    assert (run.status, run.trigger, run.requested_at) == ("queued", "manual", NOW)
    assert service.waiting(session) == [run.id]
    assert service.active_run(session, made.id) == run


def test_an_agent_with_a_run_waiting_or_going_cannot_be_asked_for_another(session: Session) -> None:
    made = agent(session)
    run = service.queue(session, made, "manual", NOW)

    with pytest.raises(service.Busy):
        service.queue(session, made, "manual", NOW)

    run.status = "running"
    with pytest.raises(service.Busy):
        service.queue(session, made, "schedule", NOW)

    run.status = "succeeded"
    assert service.queue(session, made, "manual", NOW).id != run.id


def test_an_agent_that_tests_the_network_runs_only_when_allowed_and_only_by_hand(
    session: Session,
) -> None:
    made = agent(session, "exposure_scanner")

    with pytest.raises(service.NotAllowed, match="Allow this agent"):
        service.queue(session, made, "manual", NOW)

    made.allow_active = True
    with pytest.raises(service.NotAllowed, match="only runs when you start it"):
        service.queue(session, made, "schedule", NOW)

    assert service.queue(session, made, "manual", NOW).status == "queued"


def test_an_agent_whose_template_is_gone_can_still_be_asked_for_a_run(session: Session) -> None:
    made = agent(session, "gone")

    assert service.queue(session, made, "manual", NOW).status == "queued"


def test_the_next_run_is_one_interval_away_if_there_is_a_schedule() -> None:
    assert service.next_run_at(True, 60, NOW) == NOW + timedelta(hours=1)
    assert service.next_run_at(False, 60, NOW) is None
    assert service.next_run_at(True, None, NOW) is None


def test_agents_whose_time_has_come_are_asked_for_and_their_next_time_is_set(
    session: Session,
) -> None:
    due = agent(
        session, "health_watch", interval_minutes=30, next_run_at=NOW - timedelta(minutes=1)
    )
    later = agent(session, interval_minutes=30, next_run_at=NOW + timedelta(minutes=1))
    paused = agent(session, interval_minutes=30, enabled=False, next_run_at=NOW - timedelta(days=1))
    by_hand = agent(session, next_run_at=None)

    assert service.schedule(session, NOW) == 1

    [run] = session.scalars(select(AgentRun)).all()
    assert (run.agent_id, run.trigger) == (due.id, "schedule")
    assert due.next_run_at == NOW + timedelta(minutes=30)
    assert later.next_run_at == NOW + timedelta(minutes=1)
    assert paused.next_run_at == NOW - timedelta(days=1)
    assert by_hand.next_run_at is None


def test_an_agent_still_running_its_last_run_is_left_alone_but_its_time_moves_on(
    session: Session,
) -> None:
    busy = agent(session, interval_minutes=30, next_run_at=NOW - timedelta(minutes=1))
    service.queue(session, busy, "manual", NOW)

    assert service.schedule(session, NOW) == 0

    assert busy.next_run_at == NOW + timedelta(minutes=30)
    assert len(session.scalars(select(AgentRun)).all()) == 1


def test_an_agent_that_tests_the_network_is_never_started_by_its_schedule(session: Session) -> None:
    agent(session, "exposure_scanner", allow_active=True, interval_minutes=30, next_run_at=NOW)

    assert service.schedule(session, NOW) == 0
    assert session.scalars(select(AgentRun)).all() == []


def test_a_run_that_waits_is_stopped_at_once_and_one_that_goes_stops_before_its_next_step(
    session: Session,
) -> None:
    made = agent(session)
    waiting = service.queue(session, made, "manual", NOW)

    service.cancel(waiting, NOW)

    assert (waiting.status, waiting.finished_at) == ("cancelled", NOW)
    running = service.queue(session, made, "manual", NOW)
    running.status = "running"
    service.cancel(running, NOW)
    assert (running.status, running.cancel_requested) == ("running", True)
    over = AgentRun(agent_id=made.id, trigger="manual", status="succeeded", requested_at=NOW)
    service.cancel(over, NOW)
    assert over.status == "succeeded"
    assert not over.cancel_requested


def test_runs_that_were_going_when_the_worker_stopped_are_ended(session: Session) -> None:
    made = agent(session)
    run = service.queue(session, made, "manual", NOW)
    run.status = "running"
    run.node = "act"

    assert service.interrupted(session, NOW) == 1

    assert (run.status, run.node, run.finished_at) == ("failed", None, NOW)
    assert run.error == "It was interrupted when AresGate stopped."


def test_old_runs_are_forgotten_with_their_steps_and_recent_and_waiting_ones_are_kept(
    session: Session,
) -> None:
    made = agent(session)
    old = AgentRun(
        agent_id=made.id,
        trigger="manual",
        status="succeeded",
        requested_at=NOW - service.RETENTION - timedelta(days=1),
        finished_at=NOW - service.RETENTION - timedelta(days=1),
    )
    recent = AgentRun(
        agent_id=made.id,
        trigger="manual",
        status="succeeded",
        requested_at=NOW - timedelta(days=1),
        finished_at=NOW - timedelta(days=1),
    )
    waiting = AgentRun(
        agent_id=made.id,
        trigger="manual",
        status="queued",
        requested_at=NOW - service.RETENTION - timedelta(days=5),
    )
    session.add_all([old, recent, waiting])
    session.flush()
    session.add(AgentStep(run_id=old.id, seq=1, at=NOW, node="plan", title="x", detail={}))
    session.flush()

    service.prune(session, NOW)
    session.expire_all()

    assert {run.id for run in session.scalars(select(AgentRun))} == {recent.id, waiting.id}
    assert session.scalars(select(AgentStep)).all() == []


def test_every_template_is_found_by_its_key_and_no_other_is() -> None:
    assert [catalog.template(item.key) for item in catalog.TEMPLATES] == list(catalog.TEMPLATES)
    assert catalog.template("nothing") is None
    assert {item.key for item in catalog.TEMPLATES if item.active} == {"exposure_scanner"}
    assert all(item.interval_minutes is None for item in catalog.TEMPLATES if item.active)
