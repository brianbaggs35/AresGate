"""Wazuh's alerts, read from the indexer and kept as events.

The manager writes every alert it raises to the indexer, one document in a daily
``wazuh-alerts-*`` index. ``POST /wazuh-alerts-*/_search`` with a query in its body answers with
``hits.hits``, each a document: its ``_id`` and the alert as ``_source``. The alert has the
``timestamp`` it was raised at (``2026-10-26T10:12:03.482+0000``), the ``rule`` that fired (its
``id``, a ``level`` from 0 to 16 and a ``description``), the ``agent`` it is about, and in
``data`` what the decoders found in the log line, such as the source address and port. The
manager's own API doesn't give alerts, so this is the only place to read them.

Read from Wazuh's documentation: the ``wazuh-alerts-*`` indices and their fields (Indexer
indices and the alerts index template, in the Wazuh repository's ``extensions/elasticsearch``),
the level table (Ruleset > Rules classification) and the search API (OpenSearch's ``_search`` with
a ``range`` query and ``sort``). Not tried against a live Wazuh: the exact shape of ``data``
differs by decoder, so only the address, port and protocol fields common to them are read.

Each run asks for the newest alerts of the last half hour. That overlaps the runs before it,
which is harmless: an alert is stored once, by its document's id and time, and one that reached
the indexer late is still found."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from app.collectors import traffic
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.events.event import NewEvent, Severity
from app.integrations import probes

PATH = "/wazuh-alerts-*/_search"
PRODUCT = "The Wazuh indexer"
SOURCE = "wazuh"
CONNECTION = "indexer"
# How far back each read looks, and how many of the newest alerts it keeps. A home network
# raises a few an hour.
WINDOW = timedelta(minutes=30)
LIMIT = 500


class Alerts(Collector):
    key = "wazuh-alerts"
    title = "Alerts"
    summary = (
        "Reads the alerts Wazuh has raised every minute and keeps each as an event: the rule, "
        "how serious Wazuh rates it, the host it is about and the address it came from."
    )
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = SOURCE
    connection = CONNECTION

    async def collect(self, context: Context) -> Outcome:
        hits = await _hits(context)
        events = parse(hits)
        if hits and not events:
            raise CollectorFailed("It answered, but the alerts aren't in a form AresGate reads.")
        return Outcome(items=await context.record(events))


def _query(now: datetime) -> dict[str, object]:
    since = (now - WINDOW).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {
        "size": LIMIT,
        "sort": [{"timestamp": {"order": "desc"}}],
        "query": {"range": {"timestamp": {"gte": since}}},
    }


async def _hits(context: Context) -> list[object]:
    reply = await context.client.request(
        "POST",
        PATH,
        json_body=_query(context.now),
        auth=(str(context.target.options["username"]), context.target.secrets["password"]),
    )
    if bad := probes.problem(reply, PRODUCT):
        raise CollectorFailed(bad.message)
    answer = probes.as_object(reply.json())
    found = probes.as_object(answer.get("hits")) if answer else None
    hits = probes.as_array(found.get("hits")) if found else None
    if hits is None:
        raise CollectorFailed(probes.unexpected(PRODUCT).message)
    return hits


def parse(hits: list[object]) -> list[NewEvent]:
    """The alerts that can be read as events, in the order given. A hit that isn't an object, or
    has no id, or no alert with a time that says its zone, is left out."""
    events: list[NewEvent] = []
    for hit in hits:
        document = probes.as_object(hit)
        if document is not None and (event := _event(document)) is not None:
            events.append(event)
    return events


def _moment(stamp: str) -> datetime | None:
    """Wazuh's time, such as ``2026-10-26T10:12:03.482+0000``. One that doesn't say its zone is
    no use, because the manager's own isn't known here."""
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _object(entry: Mapping[str, object], key: str) -> Mapping[str, object]:
    return probes.as_object(entry.get(key)) or {}


def _event(document: Mapping[str, object]) -> NewEvent | None:
    identity = traffic.text(document, "_id")
    alert = probes.as_object(document.get("_source"))
    occurred_at = _moment(traffic.text(alert, "timestamp")) if alert else None
    if not identity or alert is None or occurred_at is None:
        return None
    rule, agent, data = _object(alert, "rule"), _object(alert, "agent"), _object(alert, "data")
    level = traffic.number(rule, "level")
    description = traffic.text(rule, "description")
    return NewEvent(
        source=SOURCE,
        connection=CONNECTION,
        kind="alert",
        severity=_severity(level),
        occurred_at=occurred_at,
        identity=(identity,),
        summary=_summary(description, traffic.text(agent, "name"), traffic.text(rule, "id"), level),
        signature=description or None,
        src_address=traffic.text(data, "srcip") or None,
        src_port=traffic.number(data, "srcport"),
        # An alert that names no destination is about the host that raised it.
        dst_address=traffic.text(data, "dstip") or traffic.text(agent, "ip") or None,
        dst_port=traffic.number(data, "dstport"),
        protocol=traffic.text(data, "protocol").lower() or None,
        raw=dict(alert),
    )


def _severity(level: int | None) -> Severity:
    """How serious AresGate treats a rule level, from Wazuh's table of them (Ruleset > Rules
    classification), which runs from 0 to 16. Up to 3 is information: ignored, low relevance, a
    low priority notification or a successful login. 4 to 6 are low priority and user errors and
    low relevance attacks. 7 to 10 are worth a look: a "bad word", a first time seen, an error
    from an invalid source, repeated user errors. 11 to 13 are an integrity warning and the
    events Wazuh calls high importance. 14 and up are its high importance security events,
    severe attacks and the maximum, which no rule of its own uses. The grouping is AresGate's:
    the table names the levels and doesn't say where one kind of response begins."""
    if level is None or level < 4:
        return Severity.INFO
    if level < 7:
        return Severity.LOW
    if level < 11:
        return Severity.MEDIUM
    return Severity.HIGH if level < 14 else Severity.CRITICAL


def _summary(description: str, agent: str, rule: str, level: int | None) -> str:
    """One line for a list: ``sshd: authentication failed on web1 (rule 5760, level 5)``."""
    head = description or "Alert"
    if agent:
        head = f"{head} on {agent}"
    facts = ", ".join(
        fact
        for fact in (f"rule {rule}" if rule else "", f"level {level}" if level is not None else "")
        if fact
    )
    return f"{head} ({facts})" if facts else head
