"""What ntopng has learned of each host by watching it: its operating system, the autonomous system
and country of its address, and the fingerprints of how it opens connections (TLS, SSH and TCP). A
device that suddenly looks like another operating system, or talks with a fingerprint no program of
its own makes, is worth the analyst's attention, and this is what it has to compare.

``GET /lua/rest/v2/get/host/data.lua`` takes the interface (``ifid``) and the address (``host``)
and answers with an object in ``rsp``, which is what ntopng's own host page is built from: the
``name``, ``os`` (a number: 0 unknown, 1 Windows, 2 Apple, 3 Android, 4 Linux, 5 FreeBSD) and
``os_detail`` (text, mostly empty), ``asn`` and ``asname``, ``country`` and, for a host in the
local network, ``ja4_fingerprint`` and ``hassh_fingerprint``, objects that have the fingerprint for
a member and an object for its value (``app_name``, ``num_uses``, ``is_malicious``), and
``tcp_fingerprint``, text. The documentation shows only the first members; the rest are read from
ntopng's source (``src/Host.cpp`` and ``src/LocalHost.cpp``). ntopng 5 and 6 gave a JA3
fingerprint where it now gives JA4; neither is asked for here, since a version that has no JA4
simply gives none.

Each run reads the busiest 40 hosts of the local networks, as ``protocols.py`` does, every half
hour: a host's system and country change rarely. A host that has gone between the list and the
question is skipped, unless every one is. Not tried against a live ntopng."""

from collections.abc import Mapping
from datetime import timedelta
from ipaddress import ip_address
from typing import Any

from app.collectors import traffic
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.ntopng.api import PRODUCT, interfaces, read
from app.collectors.ntopng.hosts import name_of, on_interface
from app.collectors.ntopng.protocols import busiest
from app.collectors.readings import number
from app.hostinfo.traits import NewTrait
from app.integrations import probes

PATH = "/lua/rest/v2/get/host/data.lua"
# nDPI's numbers for an operating system, as ntopng gives them in ``os``.
SYSTEMS = {1: "Windows", 2: "macOS/iOS/iPadOS", 3: "Android", 4: "Linux", 5: "FreeBSD"}
# How many fingerprints of each kind are kept for a host.
FINGERPRINTS = 10


class HostDetails(Collector):
    key = "ntopng-host-details"
    title = "Host details"
    summary = (
        "Reads what ntopng has learned of each busy host every half hour: its operating system, "
        "the network and country of its address, and the fingerprints of how it connects."
    )
    interval = timedelta(minutes=30)
    timeout = timedelta(minutes=2)
    integration = "ntopng"
    connection = "api"

    async def collect(self, context: Context) -> Outcome:
        found: list[NewTrait] = []
        refused: list[CollectorFailed] = []
        asked = 0
        for ifid in await interfaces(context):
            for address in busiest(await on_interface(context, ifid)):
                asked += 1
                try:
                    data = probes.as_object(
                        await read(context, PATH, {"ifid": str(ifid), "host": address})
                    )
                except CollectorFailed as failure:
                    refused.append(failure)
                    continue
                if data is None:
                    raise CollectorFailed(probes.unexpected(PRODUCT).message)
                if (trait := parse(address, data)) is not None:
                    found.append(trait)
        if asked and len(refused) == asked:
            raise refused[0]
        return Outcome(items=await context.record_traits(found))


def parse(address: str, data: Mapping[str, object]) -> NewTrait | None:
    """What ``data`` says of the host at ``address``, or None for an address that isn't one."""
    try:
        where = ip_address(address)
    except ValueError:
        return None
    asn = traffic.number(data, "asn")
    fingerprints: dict[str, Any] = {}
    for key, member in (("ja4", "ja4_fingerprint"), ("hassh", "hassh_fingerprint")):
        if listed := _fingerprints(data.get(member)):
            fingerprints[key] = listed
    if tcp := traffic.text(data, "tcp_fingerprint"):
        fingerprints["tcp"] = tcp
    return NewTrait(
        address=where,
        hostname=name_of({**data, "ip": address}),
        os_name=traffic.text(data, "os_detail") or SYSTEMS.get(int(number(data.get("os")) or 0)),
        asn=asn or None,
        as_name=traffic.text(data, "asname") or None,
        country=traffic.text(data, "country") or None,
        fingerprints=fingerprints,
    )


def _fingerprints(value: object) -> list[dict[str, object]]:
    """The fingerprints of one kind, the most used first: ``{value, app, uses, malicious}``."""
    found = probes.as_object(value) or {}
    listed: list[tuple[float, dict[str, object]]] = []
    for fingerprint, entry in found.items():
        said = probes.as_object(entry) or {}
        uses = number(said.get("num_uses")) or 0.0
        listed.append(
            (
                uses,
                {
                    "value": fingerprint,
                    "app": traffic.text(said, "app_name"),
                    "uses": int(uses),
                    "malicious": said.get("is_malicious") is True,
                },
            )
        )
    return [item for _, item in sorted(listed, key=lambda pair: -pair[0])[:FINGERPRINTS]]
