"""Testing a connection: one harmless read for each, taken from the product's own API
documentation, that shows the address is right, the certificate is accepted and the credentials
work.

A probe reports in words for whoever is setting the integration up. What an integration answers
is its own text and can't be trusted, so a probe says only what it checked, plus a few short
facts (a version, an interface name) with control characters removed.
"""

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from app import audit
from app.integrations.client import ApiClient, CallFailed, Reply, Target, clean_path
from app.integrations.registry import (
    MAX_CHOSEN,
    OPNSENSE_MODULES,
    Entry,
    ModuleState,
    chosen_numbers,
)

# What a system is asked about, small enough to say nothing about the person's network: CrowdSec
# is asked whether this address (from the range reserved for documentation) is banned.
DOCUMENTATION_ADDRESS = "192.0.2.1"


@dataclass(frozen=True)
class Verdict:
    ok: bool
    message: str
    # What was found of the connection's modules, if it has any and they were looked at.
    modules: Mapping[str, ModuleState] | None = None
    # Whether a limit held the connection, so it wasn't tested now. What it was last found to be
    # stands, and this is not counted as a success.
    held: bool = False


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


def problem(
    reply: Reply, product: str, *, refused: str | None = None, forbidden: str | None = None
) -> Verdict | None:
    """Why a reply isn't a good one, or None if it is. A product that tells a sign-in it refuses
    (401) from a user it won't allow (403) can say each in its own words."""
    status = reply.status
    if reply.ok:
        return None
    if status == 401 and refused is not None:
        return Verdict(False, refused)
    if status == 403 and forbidden is not None:
        return Verdict(False, forbidden)
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


# Which of 401 and 403 a product uses for a sign-in it refuses, and which for a user it won't
# allow, differs from one to the next, so each says what its own answer means. Read from each
# product's source, which says where the documentation doesn't; the pages are listed in
# DOCS/integrations.md ("What a refusal means").
OPNSENSE_REFUSED = (
    "OPNsense didn't accept the API key and secret (HTTP 401, Authentication Failed). Check both: "
    "the secret is shown only once, when the key is made, so make a new key for the user if it "
    "is lost."
)
CROWDSEC_REFUSED = (
    "CrowdSec's local API answered access forbidden (HTTP 403), which is how it refuses an API "
    "key it doesn't know: it was mistyped, or the bouncer was deleted. Check the key, or make a "
    "new one with `cscli bouncers add`."
)
NTOPNG_NOT_GRANTED = (
    "ntopng accepted the sign-in, but the user isn't allowed to read this (HTTP 401, "
    "NOT_GRANTED). A login it refuses is redirected to its login page instead. Check the user's "
    "role under Manage Users: alerts need the capability to see them, and a packet capture "
    "the permission to download PCAP files."
)
NTOPNG_NO_INTERFACE = (
    "ntopng refused the user (HTTP 403), which it does for a user whose allowed interface is "
    "one it doesn't have. Check the user's Allowed Interface under Manage Users."
)


def opnsense_problem(reply: Reply, path: str) -> Verdict | None:
    """Why OPNsense's answer isn't a good one. It answers 401 to a key and secret it doesn't
    know, and 403 to a user that is signed in but whose privileges don't include the page."""
    forbidden = None
    if reply.status == 403:
        forbidden = (
            "OPNsense accepted the key and secret, but the user isn't allowed to read "
            f"{clean_path(path)} (HTTP 403, Forbidden). Give the user the privilege for that "
            "page under System, Access, Users."
        )
    return problem(reply, "OPNsense", refused=OPNSENSE_REFUSED, forbidden=forbidden)


def crowdsec_problem(reply: Reply) -> Verdict | None:
    """Why CrowdSec's answer isn't a good one: a bouncer key it doesn't know is a 403."""
    return problem(reply, "CrowdSec", forbidden=CROWDSEC_REFUSED)


def ntopng_problem(reply: Reply) -> Verdict | None:
    """Why ntopng's answer isn't a good one: 401 is what it says to a user who is signed in
    and lacks the permission (NOT_GRANTED), and 403 to one allowed only an interface it
    doesn't have."""
    return problem(reply, "ntopng", refused=NTOPNG_NOT_GRANTED, forbidden=NTOPNG_NO_INTERFACE)


# What a service on the internet answers when it is busy or down: the same request often works a
# moment later, so a probe of one asks once more after ``RETRY_PAUSE`` seconds before it says so.
UNAVAILABLE = (502, 503, 504)
RETRY_PAUSE = 3.0


async def ask_twice(
    client: ApiClient,
    method: str,
    path: str,
    *,
    query: Mapping[str, str] | None = None,
    json_body: object = None,
    headers: Mapping[str, str] | None = None,
) -> Reply:
    """A request to a service on the internet, asked again once if it says it is unavailable."""
    reply = await client.request(method, path, query=query, json_body=json_body, headers=headers)
    if reply.status not in UNAVAILABLE:
        return reply
    await asyncio.sleep(RETRY_PAUSE)
    return await client.request(method, path, query=query, json_body=json_body, headers=headers)


def unavailable(reply: Reply, product: str) -> Verdict | None:
    """What a busy or down service on the internet says of the test, or None if it isn't one. It
    is the service's own trouble and not the key's, so it says so."""
    if reply.status not in UNAVAILABLE:
        return None
    return Verdict(
        False,
        f"{product} is unavailable right now (HTTP {reply.status}). That is on {product}'s side: "
        "it is busy or down, and not a problem with the key or with AresGate. AresGate asks "
        "again on its own, or press Test again in a few minutes.",
    )


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


SYSTEM_INFORMATION = "/api/diagnostics/system/system_information"


async def opnsense(client: ApiClient, target: Target) -> Verdict:
    """OPNsense's system information, read with the key and secret as HTTP basic authentication,
    and then which of the services that run on it are installed, each from its status request."""
    credentials = (target.secrets["api_key"], target.secrets["api_secret"])
    reply = await client.request("GET", SYSTEM_INFORMATION, auth=credentials)
    if bad := opnsense_problem(reply, SYSTEM_INFORMATION):
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
    client: ApiClient,
    target: Target,
    path: str,
    query: Mapping[str, str] | None = None,
    *,
    keep_bytes: int | None = None,
) -> Reply:
    """A GET of ntopng's REST API, signed in the way the connection says: with an authentication
    token, or with HTTP basic authentication. ``keep_bytes`` is for an answer that is data, not
    text, such as a packet capture."""
    if target.options.get("auth") == "basic":
        credentials = (str(target.options["username"]), target.secrets["password"])
        return await client.request(
            "GET", path, query=query, auth=credentials, keep_bytes=keep_bytes
        )
    return await client.request(
        "GET",
        path,
        query=query,
        headers={"Authorization": f"Token {target.secrets['token']}"},
        keep_bytes=keep_bytes,
    )


NTOPNG_INTERFACES = "/lua/rest/v2/get/ntopng/interfaces.lua"
NTOPNG_INTERFACE = "/lua/rest/v2/get/interface/data.lua"
# A list of interfaces is asked about one by one for what each holds; a system with more than this
# has the rest listed by name only.
MAX_DETAILED = 20


# What systems call an interface that only carries a machine's traffic to itself: ``lo`` on Linux,
# ``lo0`` on the BSDs (OPNsense among them).
_LOOPBACK = re.compile(r"lo\d*")


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

    @property
    def loopback(self) -> bool:
        """The interface only carries the machine's traffic to itself, so it has nothing of the
        network in it. ntopng gives no flag for it, only the system's name for the interface."""
        return _LOOPBACK.fullmatch(self.ifname) is not None


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
    if bad := ntopng_problem(reply):
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


def default_interfaces(listed: Sequence[NtopngInterface]) -> list[NtopngInterface]:
    """The interfaces that are read when none is chosen: every one ntopng lists but the loopback,
    which has nothing of the network in it (at most as many as can be chosen). Where a loopback is
    all there is, it is read, since there would be nothing else to."""
    real = [item for item in listed if not item.loopback]
    return (real or list(listed))[:MAX_CHOSEN]


def interface_names(found: Sequence[NtopngInterface]) -> str:
    """The interfaces as a sentence needs them: ``ID 0: wan, ID 1: LAN (eth1), ID 3: lo0
    (loopback)``."""
    return (
        ", ".join(
            f"ID {item.ifid}: {item.label}{' (loopback)' if item.loopback else ''}"
            for item in found
        )
        or "none"
    )


def _numbers(ifids: Sequence[int]) -> str:
    """Interface IDs as a sentence needs them: ``ID 1``, ``IDs 1 and 2``, ``IDs 1, 2 and 6``."""
    numbers = [str(ifid) for ifid in ifids]
    if len(numbers) == 1:
        return f"ID {numbers[0]}"
    return f"IDs {', '.join(numbers[:-1])} and {numbers[-1]}"


def _loopback_note(found: Sequence[NtopngInterface]) -> str:
    """Why a loopback isn't worth reading, for any among them, or nothing."""
    names = [item.ifname for item in found if item.loopback]
    if not names:
        return ""
    if len(names) == 1:
        return f"{names[0]} is the loopback, which normally has nothing worth reading."
    which = f"{', '.join(names[:-1])} and {names[-1]}"
    return f"{which} are loopbacks, which normally have nothing worth reading."


def _suggestion(listed: Sequence[NtopngInterface]) -> str:
    """What to choose from a list of interfaces, for someone whose choice isn't on it."""
    usual = default_interfaces(listed)
    text = (
        f"Choose the ones to read under Interfaces. Suggested: "
        f"{_numbers([item.ifid for item in usual])}."
    )
    note = _loopback_note([item for item in listed if item not in usual])
    return f"{text} {note}" if note else text


def _by_default(listed: Sequence[NtopngInterface], chosen: Sequence[NtopngInterface]) -> str:
    """Says what is read when no interface is chosen."""
    lead = "No interface is chosen, so AresGate reads"
    left = [item for item in listed if item not in chosen]
    if not left:
        return f"{lead} every one ntopng lists."
    if any(not item.loopback for item in left):
        return f"{lead} the first {len(chosen)} of the {len(listed)} ntopng lists."
    return f"{lead} every one ntopng lists but the loopback."


async def ntopng(client: ApiClient, target: Target) -> Verdict:
    """The interfaces ntopng monitors, which also shows the interfaces chosen exist, and whether
    each has seen anything. With none chosen, it says which are read instead."""
    listed = await ntopng_interfaces(client, target)
    if isinstance(listed, Verdict):
        return listed
    if not listed:
        return Verdict(
            False, "ntopng answered, but lists no interfaces, so there is nothing to read."
        )
    wanted = chosen_numbers(target.options["interface_id"])
    known = {item.ifid: item for item in listed}
    if missing := [ifid for ifid in wanted if ifid not in known]:
        return _no_such_interfaces(missing, listed)
    chosen = [known[ifid] for ifid in wanted] or default_interfaces(listed)
    seen = [(item, await ntopng_traffic(client, target, item.ifid)) for item in chosen]
    if wanted and len(seen) == 1:
        return _one_interface(*seen[0])
    sentences = [_interface_sentence(port, traffic) for port, traffic in seen]
    lead = "" if wanted else f" {_by_default(listed, chosen)}"
    message = f"ntopng answered.{lead} {' '.join(sentences)}"
    if any(traffic is not None and traffic.quiet for _, traffic in seen):
        message += " Nothing comes in from an interface until it has seen traffic."
    if note := _loopback_note(chosen):
        message += f" {note}"
    return Verdict(True, message)


def _interface_sentence(port: NtopngInterface, traffic: Traffic | None) -> str:
    """What one interface is, and what it has seen, as a sentence."""
    sentence = f"Interface {port.ifid} is {port.label}"
    if traffic is None:
        return f"{sentence}."
    if traffic.quiet:
        return f"{sentence} and hasn't seen any traffic yet."
    return f"{sentence}: {traffic.describe()}."


def _no_such_interfaces(missing: Sequence[int], listed: Sequence[NtopngInterface]) -> Verdict:
    """The interfaces that were chosen and ntopng doesn't have, with the ones it does have and
    which to choose."""
    which = (
        f"interface with ID {missing[0]}"
        if len(missing) == 1
        else f"interfaces with IDs {', '.join(str(ifid) for ifid in missing)}"
    )
    return Verdict(
        False,
        f"ntopng answered, but has no {which}. It has: {interface_names(listed)}. "
        f"{_suggestion(listed)}",
    )


def _one_interface(chosen: NtopngInterface, traffic: Traffic | None) -> Verdict:
    """The verdict for a connection that reads one interface."""
    message = f"ntopng answered. Interface {chosen.ifid} is {chosen.label}"
    note = f" {_loopback_note([chosen])}" if chosen.loopback else ""
    if traffic is None:
        return Verdict(True, f"{message}.{note}")
    if traffic.quiet:
        return Verdict(
            True,
            f"{message}, but it hasn't seen any traffic yet, so there is nothing to read from it "
            f"until it does. If it isn't the interface you mean, choose another.{note}",
        )
    return Verdict(True, f"{message}: {traffic.describe()}.{note}")


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
            part
            for part in (
                "loopback, normally not useful" if item.loopback else "",
                item.source,
                traffic.describe() if traffic else "",
            )
            if part
        )
        entries.append(
            Entry(
                value=str(item.ifid),
                label=item.label,
                detail=detail,
                quiet=traffic is not None and traffic.quiet,
                loopback=item.loopback,
            )
        )
    return Lookup(True, f"ntopng lists {_count_of(len(entries), 'interface')}.", tuple(entries))


WAZUH_MANAGER = "The Wazuh manager"
# The same, as a sentence puts it ("doesn't look like the Wazuh manager's").
THE_MANAGER = "the Wazuh manager"
WAZUH_AGENTS = "/agents"


async def wazuh_sign_in(client: ApiClient, target: Target) -> str | Verdict:
    """Signs in to the manager's API for a token (valid for a few minutes), as Wazuh's API
    documentation describes, and keeps it out of every message. The token, or why not."""
    signed_in = await client.request(
        "POST",
        "/security/user/authenticate",
        query={"raw": "true"},
        auth=(str(target.options["username"]), target.secrets["password"]),
    )
    if bad := problem(signed_in, WAZUH_MANAGER):
        return bad
    token = signed_in.text.strip()
    if not token or len(token) > 4096 or any(character.isspace() for character in token):
        return unexpected(THE_MANAGER)
    client.hide(token)
    return token


def wazuh_agent_rows(reply: Reply) -> list[object] | None:
    """The agents in the answer to ``GET /agents``, or None if it isn't a list of them."""
    answer = as_object(reply.json())
    data = as_object(answer.get("data")) if answer else None
    return as_array(data.get("affected_items")) if data else None


NO_AGENTS_LISTED = (
    "The Wazuh manager accepted the sign-in, but lists no agents to this user, not even the "
    "manager itself (agent 000). That is what a user whose role doesn't allow reading agents "
    "sees. Link the agents_readonly role to the user."
)


async def wazuh_manager(client: ApiClient, target: Target) -> Verdict:
    """Signs in, then asks the API about itself with the token, and for one agent. The manager
    lists itself as agent 000 to a user whose role may read agents, and nothing at all to one
    whose role may not (the API answers that with an empty list, not with a refusal), so an empty
    list is what a user without the right role looks like."""
    token = await wazuh_sign_in(client, target)
    if isinstance(token, Verdict):
        return token
    bearer = {"Authorization": f"Bearer {token}"}
    reply = await client.request("GET", "/", headers=bearer)
    if bad := problem(reply, WAZUH_MANAGER):
        return bad
    data = as_object(reply.json())
    info = as_object(data.get("data")) if data else None
    if info is None or "api_version" not in info:
        return unexpected(THE_MANAGER)
    listed = await client.request(
        "GET", WAZUH_AGENTS, query={"limit": "1", "select": "id"}, headers=bearer
    )
    if bad := problem(listed, WAZUH_MANAGER):
        return bad
    agents = wazuh_agent_rows(listed)
    if agents is None:
        return unexpected(THE_MANAGER)
    if not agents:
        return Verdict(False, NO_AGENTS_LISTED)
    return Verdict(
        True,
        f"The Wazuh manager answered: API version {fact(info['api_version'])}, "
        "and the user can list its agents.",
    )


WAZUH_INDEXER = "The Wazuh indexer"
THE_INDEXER = "the Wazuh indexer"
WAZUH_ALERTS = "/wazuh-alerts-*/_search"
# The index patterns a user has to be allowed to read, for what each is about.
ALERT_INDICES = "wazuh-alerts-*"
STATE_INDICES = "wazuh-states-*"
INDEXER_REFUSED = (
    f"{WAZUH_INDEXER} didn't accept the credentials (HTTP 401). It has its own users, apart "
    "from the manager API's: Indexer management, Security, Internal users."
)
# What the indexer's security plugin says of a user who may not do what was asked, for example
# ``no permissions for [indices:data/read/search] and User [name=aresgate, backend_roles=[]]``.
MISSING_PERMISSION = re.compile(r"no permissions for \[([A-Za-z0-9_:/*.-]{1,80})\]")


def missing_permission(reply: Reply) -> str | None:
    """The permission the indexer says the user lacks, if it says one in the way its security
    plugin does. Only an action's name is taken from what it said, so nothing else gets through."""
    answer = as_object(reply.json())
    error = as_object(answer.get("error")) if answer else None
    reason = error.get("reason") if error else None
    found = MISSING_PERMISSION.search(reason) if isinstance(reason, str) else None
    return found.group(1) if found else None


def indexer_forbidden(reply: Reply, indices: str = ALERT_INDICES) -> str:
    """Why the indexer won't let the user read the alerts (or, for ``wazuh-states-*``, what the
    agents report), and what to change. It answers 403 to a user who signed in properly but whose
    roles don't allow the request, and 401 to one who didn't, so this is never a wrong
    password."""
    what = "the alerts" if indices == ALERT_INDICES else "what the agents report"
    message = (
        f"{WAZUH_INDEXER} accepted the sign-in, but the user isn't allowed to read {what} "
        "(HTTP 403)."
    )
    permission = missing_permission(reply)
    if permission:
        message += f" It says the user has no permission for {fact(permission, 80)}."
    if permission and permission.startswith("cluster:"):
        return f"{message} Add it under the user's role, in Cluster permissions."
    return (
        f"{message} Give the user's role the index permission read on {indices}, and map "
        "the user to the role (Mapped users)."
    )


def indexer_problem(reply: Reply, indices: str = ALERT_INDICES) -> Verdict | None:
    """Why the indexer's answer to the search isn't a good one, or None if it is."""
    forbidden = indexer_forbidden(reply, indices) if reply.status == 403 else None
    return problem(reply, WAZUH_INDEXER, refused=INDEXER_REFUSED, forbidden=forbidden)


async def wazuh_search(
    client: ApiClient, target: Target, path: str, body: Mapping[str, object]
) -> Reply:
    """A search of one of the indexer's index patterns (``path`` is its ``/…/_search``), with
    basic authentication."""
    return await client.request(
        "POST",
        path,
        json_body=body,
        auth=(str(target.options["username"]), target.secrets["password"]),
    )


async def wazuh_alerts_search(
    client: ApiClient, target: Target, body: Mapping[str, object]
) -> Reply:
    """A search of the indexer's ``wazuh-alerts-*`` indices. The test and the collector that
    reads the alerts both ask this way, so a test that passes means the collector is allowed to
    do what it does."""
    return await wazuh_search(client, target, WAZUH_ALERTS, body)


def _stored(total: object) -> str:
    """How many alerts the indexer says it holds, as a sentence, or nothing if it doesn't say
    in a way that is understood. Its count stops at 10,000 unless it is asked for more."""
    count, exact = None, True
    if isinstance(total, int) and not isinstance(total, bool):
        count = total
    elif (counted := as_object(total)) is not None:
        value = counted.get("value")
        count = value if isinstance(value, int) and not isinstance(value, bool) else None
        exact = counted.get("relation") != "gte"
    if count is None or count < 0:
        return ""
    if count == 0:
        return " It holds none yet."
    if not exact:
        return f" It holds {count:,} or more."
    return f" It holds {count:,} {'alert' if count == 1 else 'alerts'}."


async def wazuh_indexer(client: ApiClient, target: Target) -> Verdict:
    """Searches the alerts the way the collector does, but asks for none of them. That is the
    one thing AresGate needs the user to be allowed: the root page, which names the version, is
    forbidden to a user that has read access to the alerts and no cluster permission, such as
    one with Wazuh's own read-only example role."""
    reply = await wazuh_alerts_search(client, target, {"size": 0})
    if bad := indexer_problem(reply):
        return bad
    answer = as_object(reply.json())
    found = as_object(answer.get("hits")) if answer else None
    if found is None or as_array(found.get("hits")) is None:
        return unexpected(THE_INDEXER)
    return Verdict(
        True,
        f"{WAZUH_INDEXER} answered, and the user can search the alerts."
        f"{_stored(found.get('total'))}",
    )


async def crowdsec(client: ApiClient, target: Target) -> Verdict:
    """Asks the local API whether one address is banned. That takes a bouncer's key, which can
    only read decisions, and answers with a list or null whether or not there are any."""
    reply = await client.request(
        "GET",
        "/v1/decisions",
        query={"ip": DOCUMENTATION_ADDRESS},
        headers={"X-Api-Key": target.secrets["api_key"]},
    )
    if bad := crowdsec_problem(reply):
        return bad
    if reply.text.strip() != "null" and not isinstance(reply.json(), list):
        return unexpected("CrowdSec")
    return Verdict(True, "CrowdSec's local API accepted the key.")


async def alienvault_otx(client: ApiClient, target: Target) -> Verdict:
    """Asks OTX who the key belongs to. That is a request about the key's own account, so it
    sends no address to OTX and counts as no lookup."""
    reply = await ask_twice(
        client, "GET", "/api/v1/users/me", headers={"X-OTX-API-KEY": target.secrets["api_key"]}
    )
    refused = "OTX didn't accept the key. Copy it again from your OTX account's settings."
    if gone := unavailable(reply, "OTX"):
        return gone
    if bad := problem(reply, "OTX", refused=refused, forbidden=refused):
        return bad
    account = as_object(reply.json())
    if account is None or not isinstance(account.get("username"), str):
        return unexpected("OTX")
    return Verdict(True, "OTX accepted the key.")


async def greynoise_ping(client: ApiClient, target: Target) -> Verdict:
    """Asks GreyNoise whether the key works and which plan it belongs to. The ping is about the
    key alone, so it sends no address and counts as no lookup. Only a subscription's key is
    tested this way: the Community API's keys are tested with a lookup, which it counts."""
    reply = await ask_twice(client, "GET", "/ping", headers={"key": target.secrets["api_key"]})
    refused = "GreyNoise didn't accept the key. Copy it again from your GreyNoise account."
    if gone := unavailable(reply, "GreyNoise"):
        return gone
    if bad := problem(reply, "GreyNoise", refused=refused, forbidden=refused):
        return bad
    answer = as_object(reply.json())
    if answer is None or answer.get("message") != "pong":
        return unexpected("GreyNoise")
    plan = answer.get("plan")
    named = f" It belongs to the {plan[:40]} plan." if isinstance(plan, str) and plan else ""
    return Verdict(True, f"GreyNoise accepted the key.{named}")


async def nvd(client: ApiClient, target: Target) -> Verdict:
    """Asks NVD for one well-known CVE, with the key if the settings send one, and checks that the
    answer is a list of CVEs. NVD answers an unknown key with an error that says so in its
    ``message`` header, which is passed on. The request counts as one of the requests NVD allows in
    30 seconds, which the loop that asks about CVEs leaves room for."""
    use_key = target.options.get("access") != "none"
    key = target.secrets.get("api_key") if use_key else None
    reply = await ask_twice(
        client,
        "GET",
        "/rest/json/cves/2.0",
        query={"cveIds": NVD_TEST_CVE, "resultsPerPage": "1"},
        headers={"apiKey": key} if key else None,
    )
    if gone := unavailable(reply, "NVD"):
        return gone
    if not reply.ok:
        said = audit.clean(reply.headers.get("message"), 120)
        if reply.status == 404 and said and "apikey" in said.lower():
            return Verdict(False, "NVD didn't accept the key. Request a new one from NVD.")
        if reply.status in (403, 429):
            return Verdict(
                False,
                "NVD turned the request away (HTTP "
                f"{reply.status}), which it does when the key is wrong or its limit is reached. "
                "Check the key, or try again in a minute.",
            )
        if bad := problem(reply, "NVD"):
            return bad
    answer = as_object(reply.json())
    if answer is None or as_array(answer.get("vulnerabilities")) is None:
        return unexpected("NVD")
    return Verdict(
        True,
        "NVD answered with the key."
        if key
        else "NVD answered. Without a key it allows 5 requests in 30 seconds.",
    )


# A CVE that NVD has recorded, the Log4Shell one, which it will keep.
NVD_TEST_CVE = "CVE-2021-44228"


# A hardware address that belongs to no device: the example RFC 7042 gives for documentation.
DOCUMENTATION_MAC = "00:00:5e:00:53:00"


async def fingerbank(client: ApiClient, target: Target) -> Verdict:
    """Asks Fingerbank about a hardware address that belongs to no device, with the key. Fingerbank
    answers 200 with a device, or 404 when it has none for the address: either way it accepted the
    key. A 429 means it asked for fewer requests, which says nothing against the key either. The
    request sends no real device, and costs one of the requests the key allows an hour."""
    reply = await ask_twice(
        client,
        "GET",
        "/api/v2/combinations/interrogate",
        json_body={"mac": DOCUMENTATION_MAC},
        headers={"Authorization": f"Bearer {target.secrets['api_key']}"},
    )
    if gone := unavailable(reply, "Fingerbank"):
        return gone
    if reply.status == 429:
        return Verdict(
            True, "Fingerbank accepted the key, but asked for fewer requests for a moment."
        )
    if reply.status != 404:
        refused = "Fingerbank didn't accept the key. Copy it again from your Fingerbank account."
        blocked = "Fingerbank has blocked this key. Its fair usage policy allows one key for each."
        if bad := problem(reply, "Fingerbank", refused=refused, forbidden=blocked):
            return bad
        if as_object(reply.json()) is None:
            return unexpected("Fingerbank")
    return Verdict(True, "Fingerbank accepted the key.")


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
    ("otx", "api"): alienvault_otx,
    ("nvd", "api"): nvd,
    ("fingerbank", "api"): fingerbank,
}

# The connections whose test spends one of the lookups their key allows. They are tested by hand,
# through the budget of the threat intelligence code (app/intel/connection.py), never on a timer.
METERED: frozenset[tuple[str, str]] = frozenset({("virustotal", "api"), ("greynoise", "api")})


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
