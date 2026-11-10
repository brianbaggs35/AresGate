"""Running agents: the worker takes the runs that were asked for, one after the other, runs the
graph of each (app/agents/graph.py) and keeps every step as it happens, so that the web app can
show an agent at work, and what came of it when it is done.

A run is asked for by the owner or by an agent's schedule and waits in ``agent_runs`` until the
worker starts it, so nothing is lost if the worker is not running at the time. A run that is going
when the worker stops is ended as interrupted the next time it starts.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Final, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.agents import catalog, flow, graph, probe, service
from app.agents.graph import State, Work
from app.ai.gateway import Context
from app.integrations import netguard
from app.integrations.netguard import AddressPolicy
from app.models import Agent, AgentRun, AgentStep
from app.models.base import utcnow

logger = logging.getLogger(__name__)

INTERVAL: Final = timedelta(seconds=5)
PRUNE_EVERY: Final = 3600.0
# The longest a run may take: a model that is thinking, and a slow network, but not for ever.
DEADLINE: Final = 900.0


@dataclass(frozen=True)
class Probing:
    """How devices are tested. Only the tests of the agents change it."""

    policy: AddressPolicy = netguard.HOME_NETWORK
    ports: Mapping[int, probe.Service] = field(default_factory=lambda: probe.PORTS)
    connect: Callable[[str, int, float], bool] = probe.connects


def _begin(new_session: Callable[[], Session], run_id: int) -> graph.Snapshot | None:
    """Takes a run that is waiting, and says what it needs to know of its agent. A run that was
    stopped, or whose agent or template is gone, is not run."""
    with new_session() as db:
        taken = db.scalar(
            select(AgentRun.id).where(AgentRun.id == run_id, AgentRun.status == "queued")
        )
        run = db.get(AgentRun, taken) if taken is not None else None
        if run is None:
            return None
        agent = db.get(Agent, run.agent_id)
        template = catalog.template(agent.template) if agent else None
        now = utcnow()
        if agent is None or template is None:
            run.status = "failed"
            run.finished_at = now
            run.error = "The agent, or what it was made from, is gone."
            db.commit()
            return None
        run.status = "running"
        run.started_at = now
        db.commit()
        return graph.Snapshot(
            agent_id=agent.id,
            run_id=run.id,
            name=agent.name,
            goal=agent.goal,
            allow_active=agent.allow_active,
            template=template,
        )


def _enter(new_session: Callable[[], Session], run_id: int, node: str) -> bool:
    """Notes which step a run is in, and whether the owner has asked for it to stop."""
    with new_session() as db:
        run = db.get(AgentRun, run_id)
        if run is None:  # pragma: no cover - the agent was deleted while it ran
            return True
        run.node = node
        db.commit()
        return run.cancel_requested and node != "report"


def _keep(
    new_session: Callable[[], Session], run_id: int, node: str, steps: list[graph.Step]
) -> None:
    """Keeps what a node did, in order after what came before."""
    if not steps:
        return
    with new_session() as db:
        seq = db.scalar(
            select(func.coalesce(func.max(AgentStep.seq), 0)).where(AgentStep.run_id == run_id)
        )
        for number, step in enumerate(steps, start=(seq or 0) + 1):
            db.add(
                AgentStep(
                    run_id=run_id,
                    seq=number,
                    at=utcnow(),
                    node=node,
                    title=audit.clean(step["title"], 200) or "",
                    detail=step["detail"],
                )
            )
        db.commit()


def _finish(
    new_session: Callable[[], Session],
    run_id: int,
    state: State | None,
    status: str,
    error: str | None,
) -> None:
    """Ends a run, keeping what it came to."""
    with new_session() as db:
        run = db.get(AgentRun, run_id)
        if run is None:  # pragma: no cover - the agent was deleted while it ran
            return
        if state is not None:
            run.summary = state["summary"]
            run.findings = cast("list[dict[str, object]]", state["findings"])
            run.rounds = state["round"]
            run.ai = audit.clean(state["ai"], 500) or ""
            run.call_ids = state["call_ids"]
        run.status = status
        run.error = audit.clean(error, 500)
        run.finished_at = utcnow()
        run.node = None
        db.commit()
    if status != "succeeded":
        _keep(
            new_session,
            run_id,
            "report",
            [graph.Step(title="Stopped by you" if status == "cancelled" else "Stopped", detail={})],
        )


def steps_of(result: object) -> list[graph.Step]:
    """What a node that has finished said it did."""
    if not isinstance(result, dict):
        return []
    return cast("list[graph.Step]", cast("dict[str, object]", result).get("steps") or [])


async def execute(
    new_session: Callable[[], Session],
    context: Context,
    run_id: int,
    probing: Probing | None = None,
) -> None:
    """Runs one run that is waiting, to the end. However it ends, it is over and says how."""
    snapshot = await asyncio.to_thread(_begin, new_session, run_id)
    if snapshot is None:
        return
    chosen = probing or Probing()
    work = Work(
        snapshot,
        new_session,
        context,
        policy=chosen.policy,
        ports=chosen.ports,
        connect=chosen.connect,
    )
    state: State | None = None
    node = ""
    status, error = "succeeded", None
    try:
        async with (
            asyncio.timeout(DEADLINE),
            contextlib.aclosing(flow.stream(graph.build(work), graph.initial())) as events,
        ):
            async for mode, payload in events:
                if mode == "values":
                    state = cast("State", payload)
                    continue
                started = cast("dict[str, object]", payload)
                if "result" not in started:
                    node = cast("str", started["name"])
                    if await asyncio.to_thread(_enter, new_session, run_id, node):
                        status = "cancelled"
                        break
                else:
                    steps = steps_of(started["result"])
                    await asyncio.to_thread(_keep, new_session, run_id, node, steps)
    except TimeoutError:
        status, error = "failed", "It took longer than the agent may."
    except Exception as failure:
        logger.exception("Agent run %d failed", run_id)
        status, error = "failed", f"It stopped unexpectedly: {failure}"
    await asyncio.to_thread(_finish, new_session, run_id, state, status, error)


def _claim(new_session: Callable[[], Session]) -> list[int]:
    with new_session() as db:
        service.schedule(db, utcnow())
        ids = service.waiting(db)
        db.commit()
    return ids


async def run_once(
    new_session: Callable[[], Session], context: Context, probing: Probing | None = None
) -> int:
    """Starts the runs that are due, and runs everything that waits, the oldest first. Gives back
    how many it ran."""
    ids = await asyncio.to_thread(_claim, new_session)
    for run_id in ids:
        await execute(new_session, context, run_id, probing)
    return len(ids)


def _forget(new_session: Callable[[], Session]) -> None:
    with new_session() as db:
        service.interrupted(db, utcnow())
        service.prune(db, utcnow())
        db.commit()


def _prune(new_session: Callable[[], Session]) -> None:
    with new_session() as db:
        service.prune(db, utcnow())
        db.commit()


async def run(
    new_session: Callable[[], Session],
    context: Context,
    *,
    enabled: bool = True,
    interval: timedelta = INTERVAL,
) -> None:
    """Runs what waits, and looks again, until cancelled. A failure is logged and tried again,
    because it must never stop the worker."""
    if enabled:
        await asyncio.to_thread(_forget, new_session)
    pruned = time.monotonic()
    while True:
        if enabled:
            try:
                await run_once(new_session, context)
                if time.monotonic() - pruned >= PRUNE_EVERY:
                    await asyncio.to_thread(_prune, new_session)
                    pruned = time.monotonic()
            except Exception:
                logger.exception("Couldn't run the agents")
        await asyncio.sleep(interval.total_seconds())
