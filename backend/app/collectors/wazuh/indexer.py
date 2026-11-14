"""What the Wazuh collectors that read the indexer's ``wazuh-states-*`` indices have in common.

Those indices hold what the agents report about their machines as it is now (the vulnerabilities
found, and the inventories of the system, its network interfaces, ports and software), one
document for each fact, unlike ``wazuh-alerts-*``, which is a log. A search answers with the
documents as ``hits.hits``, each with its ``_source``. The field names are those of the index
templates in Wazuh's source (``src/wazuh_modules/inventory_harvester/indexer/template`` and
``vulnerability_scanner/indexer/template``, release 4.14.1): ``agent.id`` and ``agent.name`` say
which agent, and the rest is ECS. A pre-release of 5.0 nests the agent under ``wazuh.agent``
instead, so both are read."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors import traffic
from app.collectors.base import CollectorFailed, Context
from app.integrations import probes
from app.models import HostListing

PRODUCT = probes.WAZUH_INDEXER
# The most documents one search of an index asks for: OpenSearch refuses a window of more than
# 10,000 without paging, which a home network does not need.
WINDOW = 10_000


@dataclass(frozen=True)
class Page:
    """What a search found: the documents' ``_source``, and whether the index holds more."""

    sources: Sequence[Mapping[str, object]]
    more: bool


async def search(context: Context, index: str, body: Mapping[str, object]) -> Page:
    """Searches the index pattern (``wazuh-states-inventory-ports*``) and returns the documents
    found, as many as the query's ``size`` allows. Raises ``CollectorFailed`` with what to change
    when the indexer refuses, or answers in a way that isn't a search."""
    reply = await probes.wazuh_search(
        context.client, context.target, f"/{index}/_search", {"track_total_hits": True, **body}
    )
    if bad := probes.indexer_problem(reply, probes.STATE_INDICES):
        raise CollectorFailed(bad.message)
    answer = probes.as_object(reply.json())
    found = probes.as_object(answer.get("hits")) if answer else None
    hits = probes.as_array(found.get("hits")) if found else None
    if found is None or hits is None:
        raise CollectorFailed(probes.unexpected(PRODUCT).message)
    sources = [
        source
        for hit in hits
        if (document := probes.as_object(hit)) is not None
        and (source := probes.as_object(document.get("_source"))) is not None
    ]
    if hits and not sources:
        raise CollectorFailed(
            "It answered, but what the agents report isn't in a form AresGate reads."
        )
    return Page(sources, how_many(found.get("total")) > len(hits))


def how_many(total: object) -> int:
    """How many documents matched, as the indexer says: a number, or an object with the number
    as its ``value``. Nothing it says that way is no more than were returned."""
    counted = probes.as_object(total)
    value = counted.get("value") if counted is not None else total
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def member(entry: Mapping[str, object], key: str) -> Mapping[str, object]:
    """A member that is an object, or an empty one."""
    return probes.as_object(entry.get(key)) or {}


def agent_of(source: Mapping[str, object]) -> tuple[str, str]:
    """The id and the name of the agent a document is about, empty when it says neither."""
    agent = member(source, "agent")
    if not traffic.text(agent, "id"):
        agent = member(member(source, "wazuh"), "agent")
    return traffic.text(agent, "id"), traffic.text(agent, "name")


@dataclass(frozen=True)
class Listed:
    """An agent as the manager listed it: its address, and when it was last heard from."""

    address: str | None
    last_seen: datetime


def listed(db: Session) -> dict[str, Listed]:
    """The agents the manager has listed, by their number. The states indices say what an agent
    reports but not whether it is in touch, nor, for the vulnerabilities, where it is."""
    return {
        key: Listed(None if address is None else str(address), last_seen)
        for key, address, last_seen in db.execute(
            select(HostListing.key, HostListing.address, HostListing.last_seen_at).where(
                HostListing.source == "wazuh", HostListing.connection == "manager"
            )
        )
    }
