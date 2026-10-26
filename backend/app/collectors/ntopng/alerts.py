"""ntopng's alerts, for the flows and for the hosts, kept as events.

``GET /lua/rest/v2/get/flow/alert/list.lua`` and ``.../host/alert/list.lua`` take the interface
(``ifid``), the ``status`` of the alerts (``any`` is the engaged ones and the ones in its database,
acknowledged or not), the time they are about (``epoch_begin`` and ``epoch_end``, both in seconds
since 1970), a limit (``length``) and the column to ``sort`` by and its ``order``. The answer is an
object whose ``rsp.records`` is an array with an object for each alert: its ``row_id``, when it
began (``tstamp.value``), its type (``alert_id``, with a ``label``), ``score.value`` and
``severity.value`` (0 none, 1 debug, 2 info, 3 notice, 4 warning, 5 error, 6 critical, 8
emergency), and ``msg`` with its plain ``name`` and a ``description`` that holds HTML. A flow
alert has the client (``cli_ip.value``) and server (``srv_ip.value``) with their ports
(``cli_port.value``, ``srv_port.value``) and the protocol (``proto.label``). A host alert has the
host (``ip.value``) and, if it is one, its ``role.value`` (``attacker`` or ``victim``).

Each run asks for the alerts of the last half hour. That overlaps the runs before it, which is
harmless: an alert is stored once, by what it says and when it began. An alert is dated by when it
began, so one that is still engaged is the same event every run.

Read from ntopng's source, since its documentation has the endpoints and an example of the answer
but not their parameters (``scripts/lua/rest/v2/get/flow/alert/list.lua``, ``host/alert/list.lua``
and ``scripts/lua/modules/alert_store/``), and from the REST API v2 examples (section 2.4.2) for
the answer. Not tried against a live ntopng. The user must be allowed to see alerts. ntopng keeps
other alerts too (for interfaces, networks, devices and its own system), which are not read."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from app.collectors import traffic
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.ntopng.api import PRODUCT, interface, read
from app.events.event import NewEvent, Severity
from app.integrations import probes

FLOWS = "/lua/rest/v2/get/flow/alert/list.lua"
HOSTS = "/lua/rest/v2/get/host/alert/list.lua"
SOURCE = "ntopng"
CONNECTION = "api"
# How far back each read looks, and how many of the newest alerts of each kind it keeps.
WINDOW = timedelta(minutes=30)
LIMIT = 500


class Alerts(Collector):
    key = "ntopng-alerts"
    title = "Alerts"
    summary = (
        "Reads the alerts ntopng has raised for flows and for hosts every minute and keeps each "
        "as an event: what it found, how serious ntopng rates it and the hosts it is about."
    )
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = SOURCE
    connection = CONNECTION

    async def collect(self, context: Context) -> Outcome:
        flows = await _records(context, FLOWS)
        hosts = await _records(context, HOSTS)
        events = parse("flow", flows) + parse("host", hosts)
        if (flows or hosts) and not events:
            raise CollectorFailed("It answered, but the alerts aren't in a form AresGate reads.")
        return Outcome(items=await context.record(events))


async def _records(context: Context, path: str) -> list[object]:
    begin = int((context.now - WINDOW).timestamp())
    query = {
        "ifid": interface(context),
        "status": "any",
        "epoch_begin": str(begin),
        "epoch_end": str(int(context.now.timestamp())),
        "length": str(LIMIT),
        "sort": "tstamp",
        "order": "desc",
    }
    answer = probes.as_object(await read(context, path, query))
    records = probes.as_array(answer.get("records")) if answer else None
    if records is None:
        raise CollectorFailed(probes.unexpected(PRODUCT).message)
    return records


def parse(family: str, records: list[object]) -> list[NewEvent]:
    """The alerts of one family (``flow`` or ``host``) that can be read as events, in the order
    given. A record that isn't an object, or has no time, is left out."""
    seen = traffic.Occurrences()
    events: list[NewEvent] = []
    for record in records:
        alert = probes.as_object(record)
        if alert is not None and (event := _event(family, alert, seen)) is not None:
            events.append(event)
    return events


def _part(alert: Mapping[str, object], key: str) -> Mapping[str, object]:
    """A member such as ``tstamp`` or ``cli_ip``, which ntopng gives as an object with a ``label``
    for the page and a ``value`` for a program."""
    return probes.as_object(alert.get(key)) or {}


def _value(alert: Mapping[str, object], key: str) -> str:
    return traffic.text(_part(alert, key), "value")


def _whole(alert: Mapping[str, object], key: str) -> int | None:
    return traffic.number(_part(alert, key), "value")


def _event(family: str, alert: Mapping[str, object], seen: traffic.Occurrences) -> NewEvent | None:
    began = _whole(alert, "tstamp")
    if began is None:
        return None
    flow = family == "flow"
    client, server, host = _value(alert, "cli_ip"), _value(alert, "srv_ip"), _value(alert, "ip")
    cli_port, srv_port = _whole(alert, "cli_port"), _whole(alert, "srv_port")
    name = traffic.text(_part(alert, "msg"), "name") or traffic.text(alert, "alert_name")
    facts = (
        traffic.text(alert, "row_id"),
        _value(alert, "alert_id"),
        str(began),
        client or host,
        server,
        str(cli_port),
        str(srv_port),
    )
    # A flow alert goes from its client to its server. A host alert is about one host: the
    # source if ntopng calls it the attacker, otherwise the destination.
    if flow:
        source, destination = client, server
    elif _value(alert, "role") == "attacker":
        source, destination = host, ""
    else:
        source, destination = "", host
    return NewEvent(
        source=SOURCE,
        connection=CONNECTION,
        kind="alert",
        severity=_severity(_whole(alert, "severity")),
        occurred_at=datetime.fromtimestamp(began, UTC),
        identity=(family, *seen.identity(facts)),
        summary=_summary(
            flow, name, host, traffic.endpoint(client, cli_port), traffic.endpoint(server, srv_port)
        ),
        signature=name or None,
        src_address=source or None,
        src_port=cli_port if flow else None,
        dst_address=destination or None,
        dst_port=srv_port if flow else None,
        protocol=traffic.text(_part(alert, "proto"), "label").lower() or None,
        raw=dict(alert),
    )


def _severity(level: int | None) -> Severity:
    """How serious AresGate treats ntopng's severity, which it works out from an alert's score:
    none, debug and info are information, a notice is low, a warning medium, an error high and
    critical and emergency critical. The grouping is AresGate's."""
    if level is None or level < 3:
        return Severity.INFO
    if level == 3:
        return Severity.LOW
    if level == 4:
        return Severity.MEDIUM
    return Severity.HIGH if level == 5 else Severity.CRITICAL


def _summary(flow: bool, name: str, host: str, client: str, server: str) -> str:
    """One line for a list: ``Blacklisted flow: 192.168.1.40:51514 to 203.0.113.9:443`` for a flow
    and ``Scan attacker on 192.168.1.40`` for a host."""
    head = name or "Alert"
    if flow:
        where = traffic.route(client, server)
        return f"{head}: {where}" if where else head
    return f"{head} on {host}" if host else head
