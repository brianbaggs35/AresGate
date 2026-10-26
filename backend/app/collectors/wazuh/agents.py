"""The Wazuh agents' health, read from the manager's API: how many are in each state as a
metric, and an event for each that has gone quiet.

The API wants a token first (``POST /security/user/authenticate?raw=true``, which answers with it
as plain text) and then ``GET /agents`` with it as a bearer. The answer is an object whose
``data.affected_items`` are the agents: the ``id`` (the manager itself is ``000``), ``name``,
``ip``, ``status`` (``active``, ``disconnected``, ``pending`` or ``never_connected``) and when it
last reported in (``lastKeepAlive``, such as ``2026-10-26T10:12:03+00:00``). A host that was
monitored and has stopped reporting is worth knowing about, since stopping the agent is the first
thing an intruder with the run of a host may do, so the time an agent was last heard from is
the time of its event. A host that reports again and goes quiet again is a new one.

Read from Wazuh's documentation: the manager API's OpenAPI specification (``POST
/security/user/authenticate``, ``GET /agents`` with its ``limit``, ``select`` and ``status``
parameters, and the ``Agent`` schema with ``lastKeepAlive``). Not tried against a live Wazuh:
whether ``lastKeepAlive`` carries a zone on every version, so one that doesn't is left out."""

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from app.collectors import traffic
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.events.event import NewEvent, Severity
from app.integrations import probes
from app.metrics.sample import NewSample

PATH = "/agents"
PRODUCT = "The Wazuh manager"
SOURCE = "wazuh"
CONNECTION = "manager"
FIELDS = "id,name,ip,status,lastKeepAlive"
# The most agents one run reads. A home network has a handful.
LIMIT = 500
COUNT = "agents.count"
MANAGER = "000"
# Every state is counted on every run, so a state with none in it is a zero and not a gap.
STATES = ("active", "disconnected", "pending", "never_connected")


class Agents(Collector):
    key = "wazuh-agents"
    title = "Agents"
    summary = (
        "Checks every minute which of Wazuh's agents are reporting and which have gone quiet, "
        "with how many are in each state as a metric and an event for each one that stopped."
    )
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = SOURCE
    connection = CONNECTION

    async def collect(self, context: Context) -> Outcome:
        rows = await _rows(context)
        found = [entry for row in rows if (entry := probes.as_object(row)) is not None]
        if rows and not found:
            raise CollectorFailed("It answered, but the agents aren't in a form AresGate reads.")
        # The manager lists itself as an agent, which it isn't one to watch.
        agents = [entry for entry in found if traffic.text(entry, "id") not in ("", MANAGER)]
        await context.record_samples(samples(agents, context.now))
        return Outcome(items=await context.record(silent(agents)))


async def _rows(context: Context) -> list[object]:
    token = await probes.wazuh_sign_in(context.client, context.target)
    if isinstance(token, probes.Verdict):
        raise CollectorFailed(token.message)
    reply = await context.client.request(
        "GET",
        PATH,
        query={"limit": str(LIMIT), "select": FIELDS},
        headers={"Authorization": f"Bearer {token}"},
    )
    if bad := probes.problem(reply, PRODUCT):
        raise CollectorFailed(bad.message)
    answer = probes.as_object(reply.json())
    data = probes.as_object(answer.get("data")) if answer else None
    rows = probes.as_array(data.get("affected_items")) if data else None
    if rows is None:
        raise CollectorFailed(probes.unexpected(PRODUCT).message)
    return rows


def samples(agents: Sequence[Mapping[str, object]], sampled_at: datetime) -> list[NewSample]:
    """How many agents are in each state. A state the manager has no word for here is counted
    under its own name."""
    counted = Counter(traffic.text(agent, "status").lower() or "unknown" for agent in agents)
    states = (*STATES, *sorted(set(counted) - set(STATES)))
    return [
        NewSample(SOURCE, CONNECTION, COUNT, float(counted[state]), sampled_at, {"status": state})
        for state in states
    ]


def silent(agents: Sequence[Mapping[str, object]]) -> list[NewEvent]:
    """An event for each agent that is disconnected and last reported in at a time that says its
    zone, dated by when it was last heard from."""
    events: list[NewEvent] = []
    for agent in agents:
        last_heard = _moment(traffic.text(agent, "lastKeepAlive"))
        if traffic.text(agent, "status").lower() == "disconnected" and last_heard is not None:
            events.append(_event(agent, last_heard))
    return events


def _moment(stamp: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _event(agent: Mapping[str, object], last_heard: datetime) -> NewEvent:
    number, name, address = (traffic.text(agent, key) for key in ("id", "name", "ip"))
    where = f"{name} ({address})" if name and address else name or address or f"agent {number}"
    return NewEvent(
        source=SOURCE,
        connection=CONNECTION,
        kind="agent",
        severity=Severity.INFO,
        occurred_at=last_heard,
        identity=(number, last_heard.isoformat()),
        summary=f"{where} stopped reporting to Wazuh",
        signature="agent disconnected",
        # The host that went quiet is where it happened.
        dst_address=address or None,
        raw=dict(agent),
    )
