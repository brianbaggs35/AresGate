"""Testing a connection: one harmless read for each, taken from the product's own API
documentation, that shows the address is right, the certificate is accepted and the credentials
work.

A probe reports in words for whoever is setting the integration up. What an integration answers
is its own text and can't be trusted, so a probe says only what it checked, plus a few short
facts (a version, an interface name) with control characters removed.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import cast

from app import audit
from app.integrations.client import ApiClient, CallFailed, Reply, Target
from app.integrations.registry import OPNSENSE_MODULES, Entry, ModuleState

# What a system is asked about, small enough to say nothing about the person's network: CrowdSec
# is asked whether this address (from the range reserved for documentation) is banned.
DOCUMENTATION_ADDRESS = "192.0.2.1"


@dataclass(frozen=True)
class Verdict:
    ok: bool
    message: str
    # What was found of the connection's modules, if it has any and they were looked at.
    modules: Mapping[str, ModuleState] | None = None


Probe = Callable[[ApiClient, Target], Awaitable[Verdict]]


@dataclass(frozen=True)
class Lookup:
    """What a system listed when it was asked, such as ntopng's interfaces, or why it didn't."""

    ok: bool
    message: str
    entries: tuple[Entry, ...] = ()


Lookuper = Callable[[ApiClient, Target], Awaitable[Lookup]]


def fact(value: object, limit: int = 60) -> str:
    """Something an integration said, as a short piece of plain text."""
    return audit.clean(str(value), limit) or "unknown"


def as_object(value: object) -> dict[str, object] | None:
    """The members of a JSON object, or None if the value isn't one."""
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def as_array(value: object) -> list[object] | None:
    return cast("list[object]", value) if isinstance(value, list) else None


def problem(reply: Reply, product: str) -> Verdict | None:
    """Why a reply isn't a good one, or None if it is."""
    status = reply.status
    if reply.ok:
        return None
    if 300 <= status < 400:
        return Verdict(
            False,
            f"{product} redirected the request, which AresGate doesn't follow. Check the "
            "address: whether it is http or https, and the port.",
        )
    if status in (401, 403):
        return Verdict(
            False,
            f"{product} didn't accept the credentials, or the user isn't allowed to read this "
            f"(HTTP {status}).",
        )
    if status == 404:
        return Verdict(
            False,
            f"{product} answered 404, so this may not be {product}, or it is a version that "
            "doesn't have this part of the API.",
        )
    return Verdict(False, f"{product} answered HTTP {status}.")


def unexpected(product: str) -> Verdict:
    return Verdict(False, f"It answered, but the answer doesn't look like {product}'s.")


def service_state(reply: Reply) -> ModuleState:
    """Whether a service is there and running, from the answer to a request for its status. The
    plugins differ in what they say, so this only looks for the words OPNsense's services use."""
    if reply.status == 404:
        return ModuleState.NOT_INSTALLED
    if reply.status in (401, 403):
        return ModuleState.NO_ACCESS
    if not reply.ok:
        return ModuleState.UNKNOWN
    data = as_object(reply.json())
    words = [value.lower() for value in data.values() if isinstance(value, str)] if data else []
    if any("running" in word for word in words):
        return ModuleState.RUNNING
    if any("stop" in word or "disabled" in word for word in words):
        return ModuleState.STOPPED
    return ModuleState.INSTALLED


async def opnsense(client: ApiClient, target: Target) -> Verdict:
    """OPNsense's system information, read with the key and secret as HTTP basic authentication,
    and then which of the services that run on it are installed, each from its status request."""
    credentials = (target.secrets["api_key"], target.secrets["api_secret"])
    reply = await client.request(
        "GET", "/api/diagnostics/system/system_information", auth=credentials
    )
    if bad := problem(reply, "OPNsense"):
        return bad
    data = as_object(reply.json())
    if data is None:
        return unexpected("OPNsense")
    versions = as_array(data.get("versions"))
    message = f"OPNsense answered: {fact(versions[0])}." if versions else "OPNsense answered."
    states: dict[str, ModuleState] = {}
    for module in OPNSENSE_MODULES:
        if not module.path:
            states[module.key] = ModuleState.RUNNING
            continue
        try:
            states[module.key] = service_state(
                await client.request("GET", module.path, auth=credentials)
            )
        except CallFailed:
            states[module.key] = ModuleState.UNKNOWN
    found = [
        f"{module.label} ({states[module.key].value})"
        for module in OPNSENSE_MODULES
        if module.path and states[module.key].present
    ]
    message += f" Services found: {', '.join(found)}." if found else " No other services found."
    return Verdict(True, message, states)


async def zenarmor(client: ApiClient, target: Target) -> Verdict:
    """Asks Zenarmor's own API for its policies. Zenarmor's documentation has the API key as the
    user name of HTTP basic authentication, with no password, and every request naming a user."""
    reply = await client.request(
        "GET",
        "/policies",
        query={"user": str(target.options["user"])},
        auth=(target.secrets["api_key"], ""),
    )
    if bad := problem(reply, "Zenarmor"):
        return bad
    if reply.json() is None:
        return unexpected("Zenarmor")
    return Verdict(True, "Zenarmor's API accepted the key.")


# What a login ntopng refuses looks like, since it redirects to its login page instead of saying no.
NTOPNG_LOGIN_REFUSED = (
    "ntopng redirected to its login page, which it does when the login is refused. "
    "Check the token, or the username and password."
)


async def ntopng_get(
    client: ApiClient, target: Target, path: str, query: Mapping[str, str] | None = None
) -> Reply:
    """A GET of ntopng's REST API, signed in the way the connection says: with an authentication
    token, or with HTTP basic authentication."""
    if target.options.get("auth") == "basic":
        credentials = (str(target.options["username"]), target.secrets["password"])
        return await client.request("GET", path, query=query, auth=credentials)
    return await client.request(
        "GET", path, query=query, headers={"Authorization": f"Token {target.secrets['token']}"}
    )


NTOPNG_INTERFACES = "/lua/rest/v2/get/ntopng/interfaces.lua"
NTOPNG_INTERFACE = "/lua/rest/v2/get/interface/data.lua"
# A list of interfaces is asked about one by one for what each holds; a system with more than this
# has the rest listed by name only.
MAX_DETAILED = 20


@dataclass(frozen=True)
class NtopngInterface:
    """One interface of ntopng's list: its ``ifid``, its name in the system, the name ntopng shows
    for it (the same unless someone renamed it) and what it takes its traffic from."""

    ifid: int
    ifname: str
    name: str
    source: str

    @property
    def label(self) -> str:
        if self.name and self.ifname and self.name != self.ifname:
            return f"{self.name} ({self.ifname})"
        return self.ifname or self.name or f"Interface {self.ifid}"


@dataclass(frozen=True)
class Traffic:
    """What an interface of ntopng has seen since ntopng started."""

    hosts: int
    local_hosts: int | None
    flows: int
    seen: int

    @property
    def quiet(self) -> bool:
        return not (self.hosts or self.flows or self.seen)

    def describe(self) -> str:
        if self.quiet:
            return "no traffic seen yet"
        hosts = _count_of(self.hosts, "host")
        if self.local_hosts is not None:
            hosts += f" ({self.local_hosts} local)"
        return f"{hosts}, {_count_of(self.flows, 'flow')}, {_size(self.seen)} seen"


def _count_of(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _size(number: int) -> str:
    amount = float(number)
    for unit in ("B", "kB", "MB", "GB"):
        if amount < 1000:
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1000
    return f"{amount:.1f} TB"


def _whole(value: object) -> int | None:
    """A count that ntopng gave, or None if it isn't one."""
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        return None
    return int(value) if float(value).is_integer() else None


def _traffic_of(data: Mapping[str, object]) -> Traffic | None:
    hosts, flows = _whole(data.get("num_hosts")), _whole(data.get("num_flows"))
    seen = _whole(data.get("bytes"))
    if seen is None:
        down, up = _whole(data.get("bytes_download")), _whole(data.get("bytes_upload"))
        seen = down + up if down is not None and up is not None else None
    if hosts is None or flows is None or seen is None:
        return None
    return Traffic(hosts, _whole(data.get("num_local_hosts")), flows, seen)


def _text_of(value: object) -> str:
    return audit.clean(str(value), 60) or "" if value is not None else ""


def _source_of(item: Mapping[str, object]) -> str:
    """What ntopng says the interface takes its traffic from."""
    if item.get("is_pcap_interface") is True:
        return "from a capture file"
    if item.get("is_zmq_interface") is True:
        return "flows from an exporter"
    if item.get("is_packet_interface") is True:
        return "live packet capture"
    return ""


async def ntopng_interfaces(client: ApiClient, target: Target) -> list[NtopngInterface] | Verdict:
    """The interfaces ntopng monitors, as ``get/ntopng/interfaces.lua`` lists them, or why it
    couldn't be read. ntopng answers a login it refuses with a redirect to its login page."""
    reply = await ntopng_get(client, target, NTOPNG_INTERFACES)
    if 300 <= reply.status < 400:
        return Verdict(False, NTOPNG_LOGIN_REFUSED)
    if bad := problem(reply, "ntopng"):
        return bad
    data = as_object(reply.json())
    listed = as_array(data.get("rsp")) if data else None
    if listed is None:
        return unexpected("ntopng")
    found: list[NtopngInterface] = []
    for entry in listed:
        item = as_object(entry)
        if item is None or not isinstance(item.get("ifid"), int):
            continue
        found.append(
            NtopngInterface(
                ifid=cast("int", item["ifid"]),
                ifname=_text_of(item.get("ifname")),
                name=_text_of(item.get("name")),
                source=_source_of(item),
            )
        )
    return sorted(found, key=lambda item: item.ifid)


async def ntopng_traffic(client: ApiClient, target: Target, ifid: int) -> Traffic | None:
    """What an interface has seen, or None if ntopng wouldn't say: the list is the answer that
    matters, so this never fails a test or a lookup."""
    try:
        reply = await ntopng_get(client, target, NTOPNG_INTERFACE, {"ifid": str(ifid)})
    except CallFailed:
        return None
    answer = as_object(reply.json()) if reply.ok else None
    data = as_object(answer.get("rsp")) if answer else None
    return _traffic_of(data) if data else None


def interface_names(found: list[NtopngInterface]) -> str:
    """The interfaces as a sentence needs them: ``ID 0: wan, ID 1: LAN (eth1)``."""
    return ", ".join(f"ID {item.ifid}: {item.label}" for item in found) or "none"


async def ntopng(client: ApiClient, target: Target) -> Verdict:
    """The interfaces ntopng monitors, which also shows the chosen interface exists, and whether
    it has seen anything."""
    listed = await ntopng_interfaces(client, target)
    if isinstance(listed, Verdict):
        return listed
    wanted = int(target.options["interface_id"])
    chosen = next((item for item in listed if item.ifid == wanted), None)
    if chosen is None:
        return Verdict(
            False,
            f"ntopng answered, but has no interface with ID {wanted}. "
            f"It has: {interface_names(listed)}.",
        )
    message = f"ntopng answered. Interface {wanted} is {chosen.label}"
    traffic = await ntopng_traffic(client, target, wanted)
    if traffic is None:
        return Verdict(True, f"{message}.")
    if traffic.quiet:
        return Verdict(
            True,
            f"{message}, but it hasn't seen any traffic yet, so there is nothing to read from it "
            "until it does. If it isn't the interface you mean, choose another.",
        )
    return Verdict(True, f"{message}: {traffic.describe()}.")


async def ntopng_interface_lookup(client: ApiClient, target: Target) -> Lookup:
    """The interfaces ntopng lists, each with what it takes its traffic from and what it has
    seen, so that the one to read can be told from the others."""
    listed = await ntopng_interfaces(client, target)
    if isinstance(listed, Verdict):
        return Lookup(False, listed.message)
    if not listed:
        return Lookup(False, "ntopng answered, but lists no interfaces.")
    entries: list[Entry] = []
    for position, item in enumerate(listed):
        traffic = (
            await ntopng_traffic(client, target, item.ifid) if position < MAX_DETAILED else None
        )
        detail = " · ".join(
            part for part in (item.source, traffic.describe() if traffic else "") if part
        )
        entries.append(
            Entry(
                value=str(item.ifid),
                label=item.label,
                detail=detail,
                quiet=traffic is not None and traffic.quiet,
            )
        )
    return Lookup(True, f"ntopng lists {_count_of(len(entries), 'interface')}.", tuple(entries))


async def wazuh_sign_in(client: ApiClient, target: Target) -> str | Verdict:
    """Signs in to the manager's API for a token (valid for a few minutes), as Wazuh's API
    documentation describes, and keeps it out of every message. The token, or why not."""
    signed_in = await client.request(
        "POST",
        "/security/user/authenticate",
        query={"raw": "true"},
        auth=(str(target.options["username"]), target.secrets["password"]),
    )
    if bad := problem(signed_in, "The Wazuh manager"):
        return bad
    token = signed_in.text.strip()
    if not token or len(token) > 4096 or any(character.isspace() for character in token):
        return unexpected("the Wazuh manager")
    client.hide(token)
    return token


async def wazuh_manager(client: ApiClient, target: Target) -> Verdict:
    """Signs in, then asks the API about itself with the token."""
    token = await wazuh_sign_in(client, target)
    if isinstance(token, Verdict):
        return token
    reply = await client.request("GET", "/", headers={"Authorization": f"Bearer {token}"})
    if bad := problem(reply, "The Wazuh manager"):
        return bad
    data = as_object(reply.json())
    info = as_object(data.get("data")) if data else None
    if info is None or "api_version" not in info:
        return unexpected("the Wazuh manager")
    return Verdict(True, f"The Wazuh manager answered: API version {fact(info['api_version'])}.")


async def wazuh_indexer(client: ApiClient, target: Target) -> Verdict:
    """The indexer's root, which names the cluster and its version, with basic authentication."""
    reply = await client.request(
        "GET",
        "/",
        auth=(str(target.options["username"]), target.secrets["password"]),
    )
    if bad := problem(reply, "The Wazuh indexer"):
        return bad
    data = as_object(reply.json())
    version = as_object(data.get("version")) if data else None
    if version is None or "number" not in version:
        return unexpected("the Wazuh indexer")
    return Verdict(True, f"The Wazuh indexer answered: version {fact(version['number'])}.")


async def crowdsec(client: ApiClient, target: Target) -> Verdict:
    """Asks the local API whether one address is banned. That takes a bouncer's key, which can
    only read decisions, and answers with a list or null whether or not there are any."""
    reply = await client.request(
        "GET",
        "/v1/decisions",
        query={"ip": DOCUMENTATION_ADDRESS},
        headers={"X-Api-Key": target.secrets["api_key"]},
    )
    if bad := problem(reply, "CrowdSec"):
        return bad
    if reply.text.strip() != "null" and not isinstance(reply.json(), list):
        return unexpected("CrowdSec")
    return Verdict(True, "CrowdSec's local API accepted the key.")


LOOKUPS: Mapping[tuple[str, str, str], Lookuper] = {
    ("ntopng", "api", "interface_id"): ntopng_interface_lookup,
}

PROBES: Mapping[tuple[str, str], Probe] = {
    ("opnsense", "api"): opnsense,
    ("opnsense", "zenarmor"): zenarmor,
    ("ntopng", "api"): ntopng,
    ("wazuh", "manager"): wazuh_manager,
    ("wazuh", "indexer"): wazuh_indexer,
    ("crowdsec", "lapi"): crowdsec,
}


async def run(probe: Probe, client: ApiClient, target: Target) -> Verdict:
    """A probe's verdict, with a request that got no answer put as a failed verdict too."""
    try:
        return await probe(client, target)
    except CallFailed as failure:
        return Verdict(False, str(failure))


async def look_up(lookup: Lookuper, client: ApiClient, target: Target) -> Lookup:
    """What a system lists, with a request that got no answer put as a failed lookup too."""
    try:
        return await lookup(client, target)
    except CallFailed as failure:
        return Lookup(False, str(failure))
