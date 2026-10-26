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
from app.integrations.registry import OPNSENSE_MODULES, ModuleState

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


async def ntopng(client: ApiClient, target: Target) -> Verdict:
    """The interfaces ntopng monitors, which also shows the chosen interface exists. ntopng
    answers a login it refuses with a redirect to its login page, not with a 401."""
    if target.options.get("auth") == "basic":
        credentials = (str(target.options["username"]), target.secrets["password"])
        reply = await client.request(
            "GET", "/lua/rest/v2/get/ntopng/interfaces.lua", auth=credentials
        )
    else:
        reply = await client.request(
            "GET",
            "/lua/rest/v2/get/ntopng/interfaces.lua",
            headers={"Authorization": f"Token {target.secrets['token']}"},
        )
    if 300 <= reply.status < 400:
        return Verdict(
            False,
            "ntopng redirected to its login page, which it does when the login is refused. "
            "Check the token, or the username and password.",
        )
    if bad := problem(reply, "ntopng"):
        return bad
    data = as_object(reply.json())
    interfaces = as_array(data.get("rsp")) if data else None
    if interfaces is None:
        return unexpected("ntopng")
    found: dict[int, str] = {}
    for entry in interfaces:
        item = as_object(entry)
        if item and isinstance(item.get("ifid"), int):
            found[cast("int", item["ifid"])] = fact(item.get("ifname", item.get("name", "")))
    wanted = int(target.options["interface_id"])
    if wanted not in found:
        listed = ", ".join(f"{name} ({ifid})" for ifid, name in sorted(found.items()))
        return Verdict(
            False,
            f"ntopng answered, but has no interface with ID {wanted}. It has: {listed or 'none'}.",
        )
    return Verdict(True, f"ntopng answered. Interface {wanted} is {found[wanted]}.")


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
