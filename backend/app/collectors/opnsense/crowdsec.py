"""The alerts and decisions of the CrowdSec plugin on OPNsense, kept as events.

The plugin has its own API, read through the OPNsense connection that exists, so CrowdSec needs no
second set of credentials when it runs on the firewall. ``/api/crowdsec/alerts/search`` and
``/api/crowdsec/decisions/search`` run ``cscli alerts list -l 0 -o json`` and ``cscli decisions
list -l 0 -o json`` on the firewall and answer in OPNsense's search form: ``rows`` with ``total``,
``rowCount`` and ``current``. A search reads how many rows are wanted from the body of a POST
(``rowCount``, 9999 if it isn't said), which is how the plugin's own table asks.

A row of alerts has the alert's ``id``, ``value`` (its scope and the address, ``Ip:198.51.100.7``),
``reason`` (the scenario), ``country``, ``as`` (the name of the network), ``decisions`` (what was
decided, counted by kind: ``ban:1``) and ``created`` (when). A row of decisions has its ``id``,
``source`` (the origin), ``scope_value`` (``Ip:198.51.100.7``), ``reason`` (the scenario),
``action`` (``ban``), ``country``, ``as``, ``events_count``, ``expiration`` (how long is left, such
as ``3h59m12s``) and ``alert_id``. The plugin leaves out a decision that has run out (an
``expiration`` that starts with a minus sign), and so does this. Where ``cscli`` prints nothing or
``null``, which it does for an empty list and also when CrowdSec isn't running, the plugin answers
``{"message": "unable to retrieve data"}`` instead of a table, and that is read as none.

A decision is the same event as the one the standalone CrowdSec collector keeps (``Decisions`` in
``app.collectors.crowdsec``), with the same identity, so one ban read through both is one event.
Only the origins that are about this network are kept, as there. An alert has a time of its own,
so it is dated by it.

Read from the OPNsense API reference for the plugin (``development/api/plugins/crowdsec``), which
lists the controllers but not the rows, and from the plugin's source in the ``opnsense/plugins``
repository (``security/crowdsec``): ``AlertsController.php`` and ``DecisionsController.php`` for
the rows, ``actions_crowdsec.conf`` for the commands behind them, ``ACL.xml`` for the privilege
(``CrowdSec``, which covers ``api/crowdsec/*``, the calls that change things as well) and core's
``ApiControllerBase::searchRecordsetBase`` for how a search is asked. Not verified on a live
firewall: that ``created`` is RFC 3339 as ``cscli`` writes its dates, and that the list leaves out
the community blocklist, as it does when ``cscli`` is run by hand (the origins kept make it no
matter)."""

from collections.abc import Mapping
from datetime import datetime, timedelta

from app.collectors import traffic
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.crowdsec.decisions import ACTIVE, LOCAL_ORIGINS, SOURCE, decision_event
from app.collectors.opnsense.api import PRODUCT, read
from app.events.event import NewEvent, Severity
from app.integrations import probes
from app.metrics.sample import NewSample

ALERTS_PATH = "/api/crowdsec/alerts/search"
DECISIONS_PATH = "/api/crowdsec/decisions/search"
# The events this reports are CrowdSec's, read through the OPNsense connection.
CONNECTION = "opnsense"
# The most rows one run keeps. A home network gets a handful of bans and some alerts a day.
LIMIT = 1000
# What the plugin answers with, in place of a table, when ``cscli`` printed nothing or ``null``.
# It prints ``null`` when there is nothing to list, so this is a quiet network, and it is also
# what a CrowdSec that isn't running gives: the plugin doesn't tell them apart.
NOTHING = "unable to retrieve data"


async def _rows(context: Context, path: str) -> list[object]:
    answer = await read(context, path, body={"rowCount": LIMIT, "current": 1})
    data = probes.as_object(answer)
    if data is not None and data.get("message") == NOTHING:
        return []
    rows = probes.as_array(data.get("rows")) if data else None
    if rows is None:
        raise CollectorFailed(probes.unexpected(PRODUCT).message)
    return rows[:LIMIT]


def _split(scope_value: str) -> tuple[str, str]:
    """``Ip:2001:db8::7`` as its scope and its value: the address has colons of its own."""
    scope, _, value = scope_value.partition(":")
    return scope, value


class PluginDecisions(Collector):
    key = "opnsense-crowdsec-decisions"
    title = "CrowdSec bans (plugin)"
    summary = (
        "Reads the bans of the CrowdSec plugin on the firewall every minute and keeps each as "
        "an event: the address, the scenario and for how long, with how many are banned now "
        "as a metric."
    )
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = "opnsense"
    connection = "api"
    module = "crowdsec"

    async def collect(self, context: Context) -> Outcome:
        rows = await _rows(context, DECISIONS_PATH)
        events = parse_decisions(rows, context.now)
        if rows and not events:
            raise CollectorFailed("It answered, but the bans aren't in a form AresGate reads.")
        added = await context.record_unseen(events)
        sample = NewSample(SOURCE, CONNECTION, ACTIVE, float(len(events)), context.now)
        await context.record_samples([sample])
        return Outcome(items=added)


class PluginAlerts(Collector):
    key = "opnsense-crowdsec-alerts"
    title = "CrowdSec alerts (plugin)"
    summary = (
        "Reads the alerts of the CrowdSec plugin on the firewall every minute and keeps each as "
        "an event: the scenario, the address and where it is."
    )
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = "opnsense"
    connection = "api"
    module = "crowdsec"

    async def collect(self, context: Context) -> Outcome:
        rows = await _rows(context, ALERTS_PATH)
        events = parse_alerts(rows)
        if rows and not events:
            raise CollectorFailed("It answered, but the alerts aren't in a form AresGate reads.")
        return Outcome(items=await context.record(events))


def parse_decisions(rows: list[object], seen_at: datetime) -> list[NewEvent]:
    """The decisions that can be read as events, in the order given, dated ``seen_at``. One that
    isn't an object, has no number or no value, has run out or is not about this network is left
    out."""
    events: list[NewEvent] = []
    for row in rows:
        decision = probes.as_object(row)
        if decision is not None and (event := _decision(decision, seen_at)) is not None:
            events.append(event)
    return events


def _decision(row: Mapping[str, object], seen_at: datetime) -> NewEvent | None:
    number = traffic.text(row, "id")
    scope, value = _split(traffic.text(row, "scope_value"))
    origin, left = traffic.text(row, "source"), traffic.text(row, "expiration")
    if not number or not value or origin not in LOCAL_ORIGINS or left.startswith("-"):
        return None
    scenario = traffic.text(row, "reason")
    kind = traffic.text(row, "action").lower() or "ban"
    return decision_event(
        number=number,
        scope=scope,
        value=value,
        kind=kind,
        scenario=scenario,
        duration=left,
        simulated=False,
        seen_at=seen_at,
        connection=CONNECTION,
        raw={
            "id": row.get("id"),
            "origin": origin,
            "type": kind,
            "scope": scope,
            "value": value,
            "scenario": scenario,
            "duration": left,
            **_where(row),
            "alert_id": row.get("alert_id"),
            "events_count": row.get("events_count"),
        },
    )


def _where(row: Mapping[str, object]) -> dict[str, object]:
    """Where the address is: its country (a code) and the name of its network, if they are known."""
    found = {"country": traffic.text(row, "country"), "as_name": traffic.text(row, "as")}
    return {key: value for key, value in found.items() if value}


def parse_alerts(rows: list[object]) -> list[NewEvent]:
    """The alerts that can be read as events, in the order given. One that isn't an object, has no
    number, no value or no time is left out."""
    events: list[NewEvent] = []
    for row in rows:
        alert = probes.as_object(row)
        if alert is not None and (event := _alert(alert)) is not None:
            events.append(event)
    return events


def _moment(stamp: str) -> datetime | None:
    """When an alert was made, such as ``2026-10-26T14:31:02Z``. One with no zone is no use, as
    nothing says which it is in."""
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _alert(row: Mapping[str, object]) -> NewEvent | None:
    number = traffic.text(row, "id")
    scope, value = _split(traffic.text(row, "value"))
    created = _moment(traffic.text(row, "created"))
    if not number or not value or created is None:
        return None
    scenario = traffic.text(row, "reason")
    decided = traffic.text(row, "decisions")
    return NewEvent(
        source=SOURCE,
        connection=CONNECTION,
        kind="alert",
        # A scenario that fired is an attack, whatever was done: less so when nothing was.
        severity=Severity.MEDIUM if decided else Severity.LOW,
        occurred_at=created,
        identity=("alert", number, scope.lower(), value, scenario),
        summary=_summary(scenario, value, decided),
        signature=scenario or None,
        src_address=value if scope.lower() == "ip" else None,
        raw={
            "id": row.get("id"),
            "scope": scope,
            "value": value,
            "scenario": scenario,
            "decisions": decided,
            "created_at": traffic.text(row, "created"),
            **_where(row),
        },
    )


def _summary(scenario: str, value: str, decided: str) -> str:
    """One line for a list: ``crowdsecurity/ssh-bf from 198.51.100.7 (ban:1)``."""
    line = f"{scenario} from {value}" if scenario else f"Alert from {value}"
    return f"{line} ({decided})" if decided else line
