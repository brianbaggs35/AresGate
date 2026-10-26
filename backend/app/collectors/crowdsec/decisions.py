"""The addresses CrowdSec has banned, from what it detected on this network, kept as events.

``GET /v1/decisions`` answers with the decisions in force, as a list, or ``null`` when there are
none. Each is an object with its ``id``, the ``origin`` that made it, a ``type`` (``ban``), the
``scope`` and ``value`` it applies to (``Ip`` and an address), how long is left (``duration``,
such as ``3h59m12s``), the ``scenario`` and whether it is only a ``simulated`` one. A bouncer's
key, which is what AresGate holds, may read nothing else.

Only the origins that are about this network are asked for, with the ``origins`` parameter of
that endpoint: ``crowdsec`` (a scenario that fired on its own logs), ``cscli`` (a ban typed in by
hand), ``cscli-import`` (bans imported from a file) and ``console`` (named in CrowdSec's source;
what the Console puts under it isn't described in its documentation). ``CAPI``, the community
blocklist, and ``lists:*``, the lists subscribed to, are tens of thousands of addresses that
attacked other people, which would drown the ones that attacked this network;
``remediation_sync`` is left out because nothing says it is about this network. The answer
carries no time for when a decision was made, so an event is dated by the run that first saw it,
and a decision seen before is skipped, however long ago that was.

Read from CrowdSec's documentation: the answer in the local API's bouncers guide, the
``origins`` parameter and which calls a bouncer's key may make in its OpenAPI specification
(``pkg/models/localapi_swagger.yaml``), and the origins in ``pkg/types/constants.go`` and the
"decisions management" user guide."""

from collections.abc import Mapping
from datetime import datetime, timedelta

from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.events.event import NewEvent, Severity
from app.integrations import probes
from app.metrics.sample import NewSample

PATH = "/v1/decisions"
PRODUCT = "CrowdSec"
SOURCE = "crowdsec"
CONNECTION = "lapi"
# The origins of the decisions that are about this network.
ORIGINS = "crowdsec,cscli,cscli-import,console"
# The most decisions one run keeps. A home network gets a handful.
LIMIT = 1000
ACTIVE = "decisions.active"


class Decisions(Collector):
    key = "crowdsec-decisions"
    title = "Bans"
    summary = (
        "Reads the addresses CrowdSec has banned for attacking this network every minute and "
        "keeps each as an event: the address, the scenario and for how long, with how many are "
        "banned now as a metric."
    )
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = SOURCE
    connection = CONNECTION

    async def collect(self, context: Context) -> Outcome:
        rows = await _rows(context)
        events = parse(rows, context.now)
        if rows and not events:
            raise CollectorFailed("It answered, but the bans aren't in a form AresGate reads.")
        added = await context.record_unseen(events)
        sample = NewSample(SOURCE, CONNECTION, ACTIVE, float(len(events)), context.now)
        await context.record_samples([sample])
        return Outcome(items=added)


async def _rows(context: Context) -> list[object]:
    reply = await context.client.request(
        "GET",
        PATH,
        query={"origins": ORIGINS},
        headers={"X-Api-Key": context.target.secrets["api_key"]},
    )
    if bad := probes.problem(reply, PRODUCT):
        raise CollectorFailed(bad.message)
    if reply.text.strip() == "null":
        return []
    rows = probes.as_array(reply.json())
    if rows is None:
        raise CollectorFailed(probes.unexpected(PRODUCT).message)
    return rows[:LIMIT]


def parse(rows: list[object], seen_at: datetime) -> list[NewEvent]:
    """The decisions that can be read as events, in the order given, dated ``seen_at``. One that
    isn't an object, or has no number or no value to apply to, is left out."""
    events: list[NewEvent] = []
    for row in rows:
        decision = probes.as_object(row)
        if decision is not None and (event := _event(decision, seen_at)) is not None:
            events.append(event)
    return events


def _text(decision: Mapping[str, object], key: str) -> str:
    """A member as text: what CrowdSec gives as a string or a number, or nothing."""
    value = decision.get(key)
    return str(value) if isinstance(value, str | int) and not isinstance(value, bool) else ""


def _event(decision: Mapping[str, object], seen_at: datetime) -> NewEvent | None:
    number, value = _text(decision, "id"), _text(decision, "value")
    if not number or not value:
        return None
    scope, scenario = _text(decision, "scope"), _text(decision, "scenario")
    kind = _text(decision, "type").lower() or "ban"
    simulated = decision.get("simulated") is True
    return NewEvent(
        source=SOURCE,
        connection=CONNECTION,
        kind="decision",
        severity=_severity(kind, simulated),
        occurred_at=seen_at,
        # A number CrowdSec starts again from if its database is lost isn't enough on its own.
        identity=(number, scope.lower(), value, scenario),
        summary=_summary(kind, value, _text(decision, "duration"), scenario, simulated),
        signature=scenario or None,
        # What was banned is the source of the attack, when it is an address.
        src_address=value if scope.lower() == "ip" else None,
        raw=dict(decision),
    )


def _severity(kind: str, simulated: bool) -> Severity:
    """CrowdSec gives a decision no severity of its own. A ban is a worry, because something
    attacked and was stopped; any other remedy is a lesser one, and a ban that was only
    simulated is a note."""
    if simulated:
        return Severity.INFO
    return Severity.MEDIUM if kind == "ban" else Severity.LOW


def _summary(kind: str, value: str, duration: str, scenario: str, simulated: bool) -> str:
    """One line for a list: ``Ban 203.0.113.9 for 3h59m12s: crowdsecurity/ssh-bf``."""
    head = f"{kind.capitalize()} {value}"
    if duration:
        head = f"{head} for {duration}"
    if simulated:
        head = f"{head} (simulated)"
    return f"{head}: {scenario}" if scenario else head
