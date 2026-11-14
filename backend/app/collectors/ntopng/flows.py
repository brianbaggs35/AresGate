"""The flows ntopng finds most suspicious right now, kept as events, so that an alert can be
matched with the flow behind it: who talked to whom, over what protocol, how much and how long.

``GET /lua/rest/v2/get/flow/active.lua`` takes the interface (``ifid``), the page (``perPage``,
``currentPage``) and the column to sort by (``sortColumn``, here ``column_score``) and its
``sortOrder``. The answer is an object whose ``rsp.data`` is an array with an object for each flow:
its ``key`` (a number that is the flow's for as long as it lasts), ``first_seen`` and ``last_seen``
(seconds since 1970), its ``client`` and ``server`` (``ip``, ``port``, ``name``, ``country``),
``protocol`` (``l4``, ``l7``), ``bytes``, ``duration``, ``thpt`` and ``score``, the flow score
ntopng gives, which is text when it is formatted for a page (``1.2 K``).

A home network has thousands of flows at a time and nearly all of them are as they should be, so
each run keeps only the 100 with the highest score, and none that ntopng scored 0. A flow is kept
as it was the first time it was seen: its bytes keep rising, but the event is the flow. They are
events of the kind ``flow``, not ``alert``: the incident engine looks only at alerts, so a flow
can never become an incident by itself, and the page that lists an incident's events shows them
next to it.

Read from ntopng's source, since its documentation has the endpoint and an example of the answer
but not its parameters (``scripts/lua/rest/v2/get/flow/active.lua`` and
``scripts/lua/modules/live_flows_filter.lua``), and from the REST API v2 examples (section 2.3.3).
The sort column is read from ``NetworkInterface.cpp``. Not tried against a live ntopng."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from app.collectors import traffic
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.ntopng.api import PRODUCT, interfaces, names, read
from app.collectors.readings import number
from app.events.event import NewEvent, Severity
from app.integrations import probes

PATH = "/lua/rest/v2/get/flow/active.lua"
SOURCE = "ntopng"
CONNECTION = "api"
LIMIT = 100


class Flows(Collector):
    key = "ntopng-flows"
    title = "Suspicious flows"
    summary = (
        "Reads the hundred flows ntopng gives the highest score every minute and keeps each as an "
        "event: who talked to whom, over what protocol, and how much."
    )
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = SOURCE
    connection = CONNECTION

    async def collect(self, context: Context) -> Outcome:
        ports = await names(context)
        events: list[NewEvent] = []
        for ifid in await interfaces(context):
            query = {
                "ifid": str(ifid),
                "sortColumn": "column_score",
                "sortOrder": "desc",
                "perPage": str(LIMIT),
                "currentPage": "1",
            }
            answer = probes.as_object(await read(context, PATH, query))
            rows = probes.as_array(answer.get("data")) if answer else None
            if rows is None:
                raise CollectorFailed(probes.unexpected(PRODUCT).message)
            found = parse(rows, ports.get(ifid))
            if rows and not found and not any(_scored_zero(row) for row in rows):
                raise CollectorFailed("It answered, but the flows aren't in a form AresGate reads.")
            events.extend(found)
        return Outcome(items=await context.record(events))


def _scored_zero(row: object) -> bool:
    flow = probes.as_object(row)
    return flow is not None and number(flow.get("score")) == 0


def parse(rows: list[object], port: str | None = None) -> list[NewEvent]:
    """The flows that can be read as events, in the order given. A flow that isn't an object, has
    no key or no time, or that ntopng gave the score 0, is left out."""
    events: list[NewEvent] = []
    for row in rows:
        flow = probes.as_object(row)
        if flow is not None and (event := _event(flow, port)) is not None:
            events.append(event)
    return events


def _end(flow: Mapping[str, object], key: str) -> Mapping[str, object]:
    return probes.as_object(flow.get(key)) or {}


def _event(flow: Mapping[str, object], port: str | None) -> NewEvent | None:
    key = traffic.text(flow, "key")
    began = traffic.number(flow, "first_seen")
    # A score ntopng formats (``1.2 K``) is not a number here, and is above 0.
    if not key or began is None or number(flow.get("score")) == 0:
        return None
    client, server = _end(flow, "client"), _end(flow, "server")
    cli_address, srv_address = traffic.text(client, "ip"), traffic.text(server, "ip")
    cli_port, srv_port = traffic.number(client, "port"), traffic.number(server, "port")
    protocol = _end(flow, "protocol")
    l7 = traffic.text(protocol, "l7")
    where = traffic.route(
        traffic.endpoint(cli_address, cli_port), traffic.endpoint(srv_address, srv_port)
    )
    return NewEvent(
        source=SOURCE,
        connection=CONNECTION,
        kind="flow",
        severity=Severity.INFO,
        occurred_at=datetime.fromtimestamp(began, UTC),
        # The key is the flow's for as long as it lasts, and its start tells it from a later flow
        # that gets the same key.
        identity=(port or "", key, began),
        summary=f"{l7 or 'Flow'}: {where}" if where else l7 or "Flow",
        signature=l7 or None,
        src_address=cli_address or None,
        src_port=cli_port,
        dst_address=srv_address or None,
        dst_port=srv_port,
        protocol=traffic.text(protocol, "l4").lower() or None,
        iface=port,
        raw=dict(flow),
    )
