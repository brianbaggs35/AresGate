"""The vulnerabilities Wazuh found on the monitored machines, kept as events.

The manager's vulnerability scanner matches what each agent says is installed against the CVE
feeds and writes one document for each match to the indexer's ``wazuh-states-vulnerabilities-*``
indices: the ``vulnerability`` (its ``id``, the CVE, a ``severity`` of Low, Medium, High or
Critical, a CVSS ``score.base`` and its ``description``), the ``package`` it is in (``name`` and
``version``), the ``agent`` it is on and the operating system (``host.os``). A document is there for
as long as the machine has the flaw, so a fixed one disappears. See ``indexer.py`` for where the
field names come from.

An event is kept the first time a flaw is seen on a machine, dated by that run, since a flaw that
was detected a month ago is not news of this month and has no time of the kind an alert has. It is
told by the agent, the CVE and the package with its version, so a package that is updated and is
still affected is a new event, and the same flaw on two machines is two. The events say which
agent and, when the manager has listed the agent, its address, so the page of an asset can find
them. They are not alerts: they are never part of an incident, since a flaw is not an attack.

What could only be inferred: that ``vulnerability.severity`` is capitalised as the Wazuh
documentation writes the levels (it is compared without regard to case, so a lowercase one works
too), and that ``score.base`` is the highest of the CVSS scores. The newest documents are not asked
for, because the template has no time of when a flaw was last seen: the highest scores are, so a
network with more flaws than a run reads keeps the worst of them."""

from collections.abc import Mapping
from datetime import timedelta

from app.collectors import traffic
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.wazuh import indexer
from app.events.event import NewEvent, Severity

SOURCE = "wazuh"
CONNECTION = "indexer"
INDEX = "wazuh-states-vulnerabilities-*"
# How many it keeps of a run: a home network has some hundreds at most.
LIMIT = 1000
_SEVERITY = {
    "critical": Severity.CRITICAL,
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "low": Severity.LOW,
}


class Vulnerabilities(Collector):
    key = "wazuh-vulnerabilities"
    title = "Vulnerabilities"
    summary = (
        "Reads the vulnerabilities Wazuh has found in the software on its agents' machines and "
        "keeps each as an event: the CVE, how serious it is, the package and the machine."
    )
    interval = timedelta(minutes=15)
    timeout = timedelta(minutes=2)
    integration = SOURCE
    connection = CONNECTION

    async def collect(self, context: Context) -> Outcome:
        page = await indexer.search(
            context,
            INDEX,
            {
                "size": min(LIMIT, indexer.WINDOW),
                "sort": [{"vulnerability.score.base": {"order": "desc"}}],
                "query": {"match_all": {}},
            },
        )
        listed = await context.save(indexer.listed)
        events = [event for source in page.sources if (event := _event(source, context, listed))]
        if page.sources and not events:
            raise CollectorFailed(
                "It answered, but the vulnerabilities aren't in a form AresGate reads."
            )
        return Outcome(items=await context.record_unseen(events))


def _event(
    document: Mapping[str, object], context: Context, listed: Mapping[str, indexer.Listed]
) -> NewEvent | None:
    """The event for one document, or None when it names no agent, no CVE or no package."""
    agent, name = indexer.agent_of(document)
    flaw = indexer.member(document, "vulnerability")
    package = indexer.member(document, "package")
    cve, thing = traffic.text(flaw, "id"), traffic.text(package, "name")
    if not agent or not cve or not thing:
        return None
    version = traffic.text(package, "version")
    level = traffic.text(flaw, "severity")
    score = indexer.member(flaw, "score").get("base")
    rated = (
        f", CVSS {score}" if isinstance(score, int | float) and not isinstance(score, bool) else ""
    )
    where = name or f"agent {agent}"
    what = f"{thing} {version}" if version else thing
    known = listed.get(agent)
    return NewEvent(
        source=SOURCE,
        connection=CONNECTION,
        kind="vulnerability",
        severity=_SEVERITY.get(level.lower(), Severity.INFO),
        occurred_at=context.now,
        identity=(agent, cve, thing, version),
        summary=f"{cve} in {what} on {where} ({level or 'not rated'}{rated})",
        signature=cve,
        dst_address=known.address if known else None,
        raw=dict(document),
    )
