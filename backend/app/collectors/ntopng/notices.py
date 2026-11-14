"""The alerts ntopng keeps that are not about a flow or a host, kept as events: those of an
interface (it dropped packets, it has too many flows), of a network (a flood), of a device (a MAC
address that connected, or came back with another IP address) and of ntopng itself (a process
restarted, the disk is filling).

They are the same request as the alerts of ``alerts.py``, to ``interface/alert/list.lua``,
``network/alert/list.lua``, ``mac/alert/list.lua`` and ``system/alert/list.lua`` under
``/lua/rest/v2/get/``: they take the interface (``ifid``), the ``status``, the time (``epoch_begin``
and ``epoch_end``, in seconds), a limit (``length``) and the ``sort`` and ``order``, and answer with
``rsp.records``, each with ``tstamp.value``, ``severity.value``, ``row_id``, ``alert_id.value`` and
``msg`` (its plain ``name``). An interface alert also has its ``subtype`` (``value`` and ``name`` of
the interface), a network alert the network's ``name`` and ``alias``, and a device alert its
``address`` (``value``, the MAC address) and ``name``. A system alert belongs to ntopng, not to
an interface, so it is read once, however many interfaces there are.

The events are of the kind ``notice``, not ``alert``: they say what ntopng did or saw about its own
work and about the network's housekeeping, and the incident engine looks only at alerts, so none of
them can become an incident. They are on the events page, and are read on their own so that an
account that may not see one family doesn't cost the flow and host alerts: a family it is refused
is left out, and the run fails only when it is refused them all.

Read from ntopng's source (``scripts/lua/rest/v2/get/*/alert/list.lua`` and
``scripts/lua/modules/alert_store/*_alert_store.lua``), which the documentation doesn't cover. There
are no alert lists for active monitoring or SNMP devices in ntopng's REST API, so they are not
read. Not tried against a live ntopng."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from app.collectors import traffic
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.ntopng.alerts import severity_of
from app.collectors.ntopng.api import PRODUCT, interfaces, names, read
from app.events.event import NewEvent
from app.integrations import probes

SOURCE = "ntopng"
CONNECTION = "api"
WINDOW = timedelta(minutes=30)
LIMIT = 200
# The families, with where each is listed. A system alert isn't an interface's.
FAMILIES = {
    "interface": "/lua/rest/v2/get/interface/alert/list.lua",
    "network": "/lua/rest/v2/get/network/alert/list.lua",
    "device": "/lua/rest/v2/get/mac/alert/list.lua",
    "system": "/lua/rest/v2/get/system/alert/list.lua",
}
PER_INTERFACE = ("interface", "network", "device")


class Notices(Collector):
    key = "ntopng-notices"
    title = "Interface, network, device and system alerts"
    summary = (
        "Reads the alerts ntopng keeps for its interfaces, networks, devices and itself every "
        "minute and keeps each as a notice: what happened and when."
    )
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = SOURCE
    connection = CONNECTION

    async def collect(self, context: Context) -> Outcome:
        ports = await names(context)
        ifids = await interfaces(context)
        events: list[NewEvent] = []
        refused: list[CollectorFailed] = []
        asked = 0
        for family, path in FAMILIES.items():
            # A system alert is one list for ntopng, which has an interface to ask about whichever
            # it is.
            for ifid in ifids if family in PER_INTERFACE else ifids[:1]:
                asked += 1
                port = ports.get(ifid) if family in PER_INTERFACE else None
                try:
                    events.extend(await _family(context, family, path, ifid, port))
                except _Refused as failure:
                    refused.append(failure.failure)
        if len(refused) == asked:
            raise refused[0]
        return Outcome(items=await context.record(events))


class _Refused(Exception):
    """A list ntopng wouldn't give, kept apart from the failures that stop the run."""

    def __init__(self, failure: CollectorFailed) -> None:
        super().__init__(str(failure))
        self.failure = failure


async def _family(
    context: Context, family: str, path: str, ifid: int, port: str | None
) -> list[NewEvent]:
    try:
        records = await _records(context, path, ifid)
    except CollectorFailed as failure:
        raise _Refused(failure) from failure
    found = parse(family, records, port)
    if records and not found:
        raise CollectorFailed("It answered, but the alerts aren't in a form AresGate reads.")
    return found


async def _records(context: Context, path: str, ifid: int) -> list[object]:
    begin = int((context.now - WINDOW).timestamp())
    query = {
        "ifid": str(ifid),
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


def parse(family: str, records: list[object], port: str | None = None) -> list[NewEvent]:
    """The alerts of one family that can be read as notices, in the order given. A record that
    isn't an object, or has no time, is left out."""
    seen = traffic.Occurrences()
    events: list[NewEvent] = []
    for record in records:
        alert = probes.as_object(record)
        if alert is not None and (event := _event(family, alert, seen, port)) is not None:
            events.append(event)
    return events


def _part(alert: Mapping[str, object], key: str) -> Mapping[str, object]:
    return probes.as_object(alert.get(key)) or {}


def _subject(family: str, alert: Mapping[str, object]) -> str:
    """What the alert is about, in words: the interface, the network or the device."""
    if family == "interface":
        subtype = _part(alert, "subtype")
        return traffic.text(subtype, "name") or traffic.text(subtype, "value")
    if family == "network":
        return traffic.text(alert, "alias") or traffic.text(alert, "name")
    if family == "device":
        address = traffic.text(_part(alert, "address"), "value")
        name = traffic.text(alert, "name")
        return f"{name} ({address})" if name and address else address or name
    return ""


def _event(
    family: str, alert: Mapping[str, object], seen: traffic.Occurrences, port: str | None
) -> NewEvent | None:
    began = traffic.number(_part(alert, "tstamp"), "value")
    if began is None:
        return None
    name = traffic.text(_part(alert, "msg"), "name") or traffic.text(alert, "alert_name")
    subject = _subject(family, alert)
    facts = (
        traffic.text(alert, "row_id"),
        traffic.text(_part(alert, "alert_id"), "value"),
        str(began),
        subject,
    )
    head = name or "Alert"
    return NewEvent(
        source=SOURCE,
        connection=CONNECTION,
        kind="notice",
        severity=severity_of(traffic.number(_part(alert, "severity"), "value")),
        occurred_at=datetime.fromtimestamp(began, UTC),
        identity=(family, *seen.identity(facts)),
        summary=f"{head}: {subject}" if subject else head,
        signature=name or None,
        iface=port,
        raw={**alert, "family": family},
    )
