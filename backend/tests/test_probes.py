import asyncio
import base64
import json
from collections.abc import Callable

import pytest

from app.integrations import netguard, probes
from app.integrations.client import ApiClient, Call, Reply, Target
from app.integrations.netguard import HOME_NETWORK_AND_LOOPBACK
from app.integrations.probes import Verdict
from app.integrations.registry import OPNSENSE_MODULES, ModuleState
from tests.stubs import Answer, Seen, Serve, StubServer

Router = Callable[[Seen], Answer]


class Log:
    def __init__(self) -> None:
        self.calls: list[Call] = []

    async def __call__(self, call: Call) -> None:
        self.calls.append(call)


def verdict(
    serve: Serve,
    integration: str,
    connection: str,
    handler: Router,
    *,
    options: dict[str, str | int] | None = None,
    secrets: dict[str, str] | None = None,
) -> tuple[Verdict, StubServer, Log]:
    server = serve(handler)
    where = Target(
        integration=integration,
        connection=connection,
        origin=netguard.parse_origin(server.url, allow_http=True),
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options=options or {},
        secrets=secrets or {},
    )
    log = Log()

    async def go() -> Verdict:
        async with ApiClient(where, log, HOME_NETWORK_AND_LOOPBACK) as client:
            return await probes.run(probes.PROBES[(integration, connection)], client, where)

    return asyncio.run(go()), server, log


def lookup(
    serve: Serve,
    key: tuple[str, str, str],
    handler: Router,
    *,
    options: dict[str, str | int] | None = None,
    secrets: dict[str, str] | None = None,
) -> tuple[probes.Lookup, StubServer, Log]:
    server = serve(handler)
    where = Target(
        integration=key[0],
        connection=key[1],
        origin=netguard.parse_origin(server.url, allow_http=True),
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options=options or {},
        secrets=secrets or {},
    )
    log = Log()

    async def go() -> probes.Lookup:
        async with ApiClient(where, log, HOME_NETWORK_AND_LOOPBACK) as client:
            return await probes.look_up(probes.LOOKUPS[key], client, where)

    return asyncio.run(go()), server, log


def basic(seen: Seen) -> tuple[str, str]:
    encoded = seen.headers["authorization"].removeprefix("Basic ")
    user, _, password = base64.b64decode(encoded).decode().partition(":")
    return user, password


def json_answer(data: object, status: int = 200) -> Answer:
    return Answer(status=status, body=json.dumps(data))


OPNSENSE_SECRETS = {"api_key": "the-key", "api_secret": "the-secret"}


def opnsense_router(**services: Answer) -> Router:
    """OPNsense with its system information, and the status answers given by service path."""

    def route(seen: Seen) -> Answer:
        if seen.path == "/api/diagnostics/system/system_information":
            return json_answer(
                {"name": "fw", "versions": ["OPNsense 25.7.2-amd64", "FreeBSD 14.3"]}
            )
        return services.get(seen.path, Answer(status=404, body='{"errorMessage": "not found"}'))

    return route


def test_opnsense_answers_with_its_version_and_the_services_it_runs(serve: Serve) -> None:
    router = opnsense_router(
        **{
            "/api/ids/service/status": json_answer({"status": "running"}),
            "/api/crowdsec/service/status": json_answer(
                {"crowdsec-status": "running", "crowdsec-firewall-status": "stopped"}
            ),
            "/api/openvpn/service/search_sessions": json_answer({"rows": []}),
            "/api/wireguard/service/status": Answer(status=403),
            "/api/ipsec/service/status": Answer(status=500),
            "/api/unbound/service/status": json_answer({"status": "stopped"}),
            "/api/dnsmasq/service/status": json_answer({"status": "disabled"}),
            "/api/kea/service/status": Answer(status=404),
            "/api/ntopng/service/status": Answer(drop=True),
        }
    )

    result, server, log = verdict(serve, "opnsense", "api", router, secrets=OPNSENSE_SECRETS)

    assert result.ok
    assert result.modules == {
        "firewall": ModuleState.RUNNING,
        "suricata": ModuleState.RUNNING,
        "crowdsec": ModuleState.RUNNING,
        "openvpn": ModuleState.INSTALLED,
        "wireguard": ModuleState.NO_ACCESS,
        "ipsec": ModuleState.UNKNOWN,
        "unbound": ModuleState.STOPPED,
        "dnsmasq": ModuleState.STOPPED,
        "kea": ModuleState.NOT_INSTALLED,
        "ntopng": ModuleState.UNKNOWN,
        "wazuhagent": ModuleState.NOT_INSTALLED,
    }
    assert result.message == (
        "OPNsense answered: OPNsense 25.7.2-amd64. Services found: Suricata (running), "
        "CrowdSec (running), OpenVPN (installed), Unbound DNS (stopped), Dnsmasq (stopped)."
    )
    assert {seen.method for seen in server.seen} == {"GET"}
    assert {basic(seen) for seen in server.seen} == {("the-key", "the-secret")}
    assert log.calls[0].path == "/api/diagnostics/system/system_information"
    assert len(log.calls) == len(OPNSENSE_MODULES)


def test_opnsense_without_any_services_says_so(serve: Serve) -> None:
    result, _, _ = verdict(serve, "opnsense", "api", opnsense_router(), secrets=OPNSENSE_SECRETS)

    assert result.ok
    assert result.message == "OPNsense answered: OPNsense 25.7.2-amd64. No other services found."


def test_opnsense_without_a_version_still_answers(serve: Serve) -> None:
    result, _, _ = verdict(
        serve,
        "opnsense",
        "api",
        lambda seen: (
            json_answer({"name": "fw"}) if "system_information" in seen.path else Answer(404)
        ),
        secrets=OPNSENSE_SECRETS,
    )

    assert result.ok
    assert result.message.startswith("OPNsense answered. ")


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (Answer(status=401), "OPNsense didn't accept the credentials, or the user isn't allowed"),
        (Answer(status=403), "(HTTP 403)"),
        (Answer(status=404), "OPNsense answered 404"),
        (Answer(status=502), "OPNsense answered HTTP 502."),
        (Answer(status=302, headers={"Location": "/ui"}), "redirected the request"),
        (Answer(body="<html>"), "doesn't look like OPNsense's"),
        (Answer(body="[1, 2]"), "doesn't look like OPNsense's"),
    ],
)
def test_opnsense_that_does_not_answer_properly_is_explained(
    serve: Serve, answer: Answer, message: str
) -> None:
    result, server, _ = verdict(
        serve, "opnsense", "api", lambda seen: answer, secrets=OPNSENSE_SECRETS
    )

    assert not result.ok
    assert message in result.message
    assert result.modules is None
    assert len(server.seen) == 1


def test_a_request_that_gets_no_answer_is_a_failed_verdict(serve: Serve) -> None:
    result, _, _ = verdict(
        serve, "opnsense", "api", lambda seen: Answer(drop=True), secrets=OPNSENSE_SECRETS
    )

    assert not result.ok
    assert "broke, or it isn't a web server" in result.message


def test_zenarmor_is_asked_for_its_policies_with_the_key_as_the_user_name(serve: Serve) -> None:
    result, server, log = verdict(
        serve,
        "opnsense",
        "zenarmor",
        lambda seen: json_answer([{"policy_id": 0}]),
        options={"user": "aresgate"},
        secrets={"api_key": "zen-key"},
    )

    assert result == Verdict(True, "Zenarmor's API accepted the key.")
    [seen] = server.seen
    assert seen.target == "/policies?user=aresgate"
    assert basic(seen) == ("zen-key", "")
    assert log.calls[0].path == "/policies"


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (Answer(status=401), "Zenarmor didn't accept the credentials"),
        (Answer(status=500), "Zenarmor answered HTTP 500."),
        (Answer(body="not json"), "doesn't look like Zenarmor's"),
    ],
)
def test_zenarmor_that_does_not_answer_properly_is_explained(
    serve: Serve, answer: Answer, message: str
) -> None:
    result, _, _ = verdict(
        serve,
        "opnsense",
        "zenarmor",
        lambda seen: answer,
        options={"user": "u"},
        secrets={"api_key": "zen-key"},
    )

    assert not result.ok
    assert message in result.message


BUSY = {"num_hosts": 41, "num_local_hosts": 18, "num_flows": 212, "bytes": 1_016_560_334}
QUIET = {"num_hosts": 0, "num_local_hosts": 0, "num_flows": 0, "bytes": 0}
INTERFACES = "/lua/rest/v2/get/ntopng/interfaces.lua"
INTERFACE = "/lua/rest/v2/get/interface/data.lua"


def ntopng_router(
    interfaces: object, data: dict[int, object] | None = None, status: int = 200
) -> Router:
    """ntopng with its list of interfaces, and what each has seen (``data``, by ifid) for the
    request that asks about one; an interface it has no data for is answered with a 400."""

    def route(seen: Seen) -> Answer:
        if seen.path == INTERFACES:
            return json_answer({"rc": 0, "rc_str": "OK", "rsp": interfaces}, status)
        ifid = int(seen.target.partition("ifid=")[2].partition("&")[0] or -1)
        if data is None or ifid not in data:
            return json_answer({"rc": -2, "rc_str": "INVALID_INTERFACE", "rsp": {}}, 400)
        return json_answer({"rc": 0, "rc_str": "OK", "rsp": data[ifid]})

    return route


def test_ntopng_with_a_token_lists_its_interfaces_and_what_the_chosen_one_holds(
    serve: Serve,
) -> None:
    result, server, log = verdict(
        serve,
        "ntopng",
        "api",
        ntopng_router([{"ifid": 0, "ifname": "eth0"}, {"ifid": 1, "name": "eth1"}], {1: BUSY}),
        options={"auth": "token", "interface_id": 1},
        secrets={"token": "tok-abcdef"},
    )

    assert result == Verdict(
        True, "ntopng answered. Interface 1 is eth1: 41 hosts (18 local), 212 flows, 1.0 GB seen."
    )
    first, second = server.seen
    assert first.path == INTERFACES
    assert first.headers["authorization"] == "Token tok-abcdef"
    assert (second.path, second.target.partition("?")[2]) == (INTERFACE, "ifid=1")
    assert [call.path for call in log.calls] == [INTERFACES, INTERFACE]


def test_ntopng_with_a_password_uses_basic_authentication(serve: Serve) -> None:
    result, server, _ = verdict(
        serve,
        "ntopng",
        "api",
        ntopng_router([{"ifid": 0, "ifname": "eth0"}], {0: BUSY}),
        options={"auth": "basic", "username": "admin", "interface_id": 0},
        secrets={"password": "p w"},
    )

    assert result.ok
    assert [basic(seen) for seen in server.seen] == [("admin", "p w")] * 2


def test_ntopng_says_when_the_chosen_interface_has_seen_no_traffic(serve: Serve) -> None:
    result, _, _ = verdict(
        serve,
        "ntopng",
        "api",
        ntopng_router([{"ifid": 1, "ifname": "eth1"}], {1: QUIET}),
        options={"auth": "token", "interface_id": 1},
        secrets={"token": "tok-abcdef"},
    )

    assert result.ok
    assert result.message.startswith(
        "ntopng answered. Interface 1 is eth1, but it hasn't seen any traffic yet"
    )
    assert "choose another" in result.message


@pytest.mark.parametrize(
    "data",
    [None, {1: {"num_hosts": 3}}, {1: "junk"}, {1: {"num_hosts": -1, "num_flows": 1, "bytes": 1}}],
)
def test_ntopng_that_does_not_say_what_the_interface_holds_is_still_a_pass(
    serve: Serve, data: dict[int, object] | None
) -> None:
    result, _, _ = verdict(
        serve,
        "ntopng",
        "api",
        ntopng_router([{"ifid": 1, "ifname": "eth1"}], data),
        options={"auth": "token", "interface_id": 1},
        secrets={"token": "tok-abcdef"},
    )

    assert result == Verdict(True, "ntopng answered. Interface 1 is eth1.")


def test_ntopng_that_drops_the_request_for_what_the_interface_holds_is_still_a_pass(
    serve: Serve,
) -> None:
    def route(seen: Seen) -> Answer:
        if seen.path == INTERFACES:
            return json_answer({"rc": 0, "rsp": [{"ifid": 1, "ifname": "eth1"}]})
        return Answer(drop=True)

    result, _, _ = verdict(
        serve,
        "ntopng",
        "api",
        route,
        options={"auth": "token", "interface_id": 1},
        secrets={"token": "tok-abcdef"},
    )

    assert result == Verdict(True, "ntopng answered. Interface 1 is eth1.")


def test_ntopng_without_the_chosen_interface_lists_the_ones_it_has(serve: Serve) -> None:
    options: dict[str, str | int] = {"auth": "token", "interface_id": 7}
    secrets = {"token": "tok-abcdef"}

    result, server, _ = verdict(
        serve,
        "ntopng",
        "api",
        ntopng_router([{"ifid": 1, "ifname": "lan"}, {"ifid": 0, "ifname": "wan"}, "junk"]),
        options=options,
        secrets=secrets,
    )
    empty, _, _ = verdict(
        serve, "ntopng", "api", ntopng_router([]), options=options, secrets=secrets
    )

    assert not result.ok
    assert result.message == (
        "ntopng answered, but has no interface with ID 7. It has: ID 0: wan, ID 1: lan. "
        "Choose the ones to read under Interfaces. Suggested: IDs 0 and 1."
    )
    assert empty.message == "ntopng answered, but lists no interfaces, so there is nothing to read."
    assert len(server.seen) == 1


def test_ntopng_with_several_interfaces_says_what_each_holds(serve: Serve) -> None:
    result, server, _ = verdict(
        serve,
        "ntopng",
        "api",
        ntopng_router(
            [
                {"ifid": 0, "ifname": "eth0"},
                {"ifid": 1, "ifname": "eth1"},
                {"ifid": 2, "ifname": "eth2"},
            ],
            {0: BUSY, 1: BUSY},
        ),
        options={"auth": "token", "interface_id": "0,1"},
        secrets={"token": "tok-abcdef"},
    )

    assert result == Verdict(
        True,
        "ntopng answered. Interface 0 is eth0: 41 hosts (18 local), 212 flows, 1.0 GB seen. "
        "Interface 1 is eth1: 41 hosts (18 local), 212 flows, 1.0 GB seen.",
    )
    assert [seen.path for seen in server.seen] == [INTERFACES, INTERFACE, INTERFACE]


def test_ntopng_with_several_interfaces_says_which_has_seen_no_traffic(serve: Serve) -> None:
    result, _, _ = verdict(
        serve,
        "ntopng",
        "api",
        ntopng_router(
            [
                {"ifid": 0, "ifname": "eth0"},
                {"ifid": 1, "ifname": "eth1"},
                {"ifid": 2, "ifname": "eth2"},
            ],
            {0: BUSY, 1: QUIET},
        ),
        options={"auth": "token", "interface_id": "0,1,2"},
        secrets={"token": "tok-abcdef"},
    )

    assert result.ok
    assert result.message == (
        "ntopng answered. Interface 0 is eth0: 41 hosts (18 local), 212 flows, 1.0 GB seen. "
        "Interface 1 is eth1 and hasn't seen any traffic yet. Interface 2 is eth2. "
        "Nothing comes in from an interface until it has seen traffic."
    )


def test_ntopng_without_some_of_the_interfaces_chosen_names_them(serve: Serve) -> None:
    listing = ntopng_router([{"ifid": 0, "ifname": "wan"}], {0: BUSY})
    options: dict[str, str | int] = {"auth": "token", "interface_id": "0,3,7"}

    result, _, _ = verdict(
        serve, "ntopng", "api", listing, options=options, secrets={"token": "tok-abcdef"}
    )
    one, _, _ = verdict(
        serve,
        "ntopng",
        "api",
        listing,
        options={"auth": "token", "interface_id": "0,3"},
        secrets={"token": "tok-abcdef"},
    )

    assert not result.ok
    assert result.message == (
        "ntopng answered, but has no interfaces with IDs 3, 7. It has: ID 0: wan. "
        "Choose the ones to read under Interfaces. Suggested: ID 0."
    )
    assert one.message == (
        "ntopng answered, but has no interface with ID 3. It has: ID 0: wan. "
        "Choose the ones to read under Interfaces. Suggested: ID 0."
    )


# An OPNsense firewall's ntopng: its interfaces are numbered from 1, with gaps, and the loopback
# is among them.
FIREWALL = [
    {"ifid": 1, "ifname": "igc0", "name": "WAN", "is_packet_interface": True},
    {"ifid": 2, "ifname": "igc1", "name": "LAN", "is_packet_interface": True},
    {"ifid": 3, "ifname": "lo0", "name": "lo0", "is_packet_interface": True},
    {"ifid": 6, "ifname": "ovpns1", "name": "ovpns1", "is_packet_interface": True},
]
FIREWALL_TRAFFIC: dict[int, object] = {1: BUSY, 2: BUSY, 3: QUIET, 6: QUIET}
FIREWALL_LIST = "ID 1: WAN (igc0), ID 2: LAN (igc1), ID 3: lo0 (loopback), ID 6: ovpns1"


def test_ntopng_that_numbers_its_interfaces_from_one_says_which_to_choose_instead_of_0(
    serve: Serve,
) -> None:
    result, server, _ = verdict(
        serve,
        "ntopng",
        "api",
        ntopng_router(FIREWALL, FIREWALL_TRAFFIC),
        options={"auth": "token", "interface_id": 0},
        secrets={"token": "tok-abcdef"},
    )

    assert not result.ok
    assert result.message == (
        f"ntopng answered, but has no interface with ID 0. It has: {FIREWALL_LIST}. "
        "Choose the ones to read under Interfaces. Suggested: IDs 1, 2 and 6. "
        "lo0 is the loopback, which normally has nothing worth reading."
    )
    assert [seen.path for seen in server.seen] == [INTERFACES]


def test_ntopng_with_no_interface_chosen_reads_all_but_the_loopback(serve: Serve) -> None:
    result, server, _ = verdict(
        serve,
        "ntopng",
        "api",
        ntopng_router(FIREWALL, FIREWALL_TRAFFIC),
        options={"auth": "token", "interface_id": ""},
        secrets={"token": "tok-abcdef"},
    )

    assert result.ok
    assert result.message == (
        "ntopng answered. No interface is chosen, so AresGate reads every one ntopng lists but "
        "the loopback. Interface 1 is WAN (igc0): 41 hosts (18 local), 212 flows, 1.0 GB seen. "
        "Interface 2 is LAN (igc1): 41 hosts (18 local), 212 flows, 1.0 GB seen. "
        "Interface 6 is ovpns1 and hasn't seen any traffic yet. "
        "Nothing comes in from an interface until it has seen traffic."
    )
    asked = [seen.target.partition("ifid=")[2] for seen in server.seen[1:]]
    assert asked == ["1", "2", "6"]


def test_ntopng_with_no_interface_chosen_and_only_one_listed_reads_that_one(
    serve: Serve,
) -> None:
    result, _, _ = verdict(
        serve,
        "ntopng",
        "api",
        ntopng_router([{"ifid": 4, "ifname": "eth0"}], {4: BUSY}),
        options={"auth": "token", "interface_id": ""},
        secrets={"token": "tok-abcdef"},
    )

    assert result == Verdict(
        True,
        "ntopng answered. No interface is chosen, so AresGate reads every one ntopng lists. "
        "Interface 4 is eth0: 41 hosts (18 local), 212 flows, 1.0 GB seen.",
    )


def test_ntopng_with_no_interface_chosen_and_only_a_loopback_reads_it_and_says_why_not_to(
    serve: Serve,
) -> None:
    result, _, _ = verdict(
        serve,
        "ntopng",
        "api",
        ntopng_router([{"ifid": 0, "ifname": "lo"}], {0: BUSY}),
        options={"auth": "token", "interface_id": ""},
        secrets={"token": "tok-abcdef"},
    )

    assert result.ok
    assert result.message.endswith(
        "Interface 0 is lo: 41 hosts (18 local), 212 flows, 1.0 GB seen. "
        "lo is the loopback, which normally has nothing worth reading."
    )


def test_ntopng_with_no_interface_chosen_reads_no_more_than_can_be_chosen(serve: Serve) -> None:
    many = [{"ifid": number, "ifname": f"eth{number}"} for number in range(20)]

    result, server, _ = verdict(
        serve,
        "ntopng",
        "api",
        ntopng_router(many, {number: BUSY for number in range(20)}),
        options={"auth": "token", "interface_id": ""},
        secrets={"token": "tok-abcdef"},
    )

    assert result.ok
    assert "so AresGate reads the first 16 of the 20 ntopng lists." in result.message
    assert len(server.seen) == 1 + 16


@pytest.mark.parametrize(
    ("chosen", "ending"),
    [
        (3, "lo0 is the loopback, which normally has nothing worth reading."),
        ("0,3", "lo0 is the loopback, which normally has nothing worth reading."),
        ("3,4", "lo0 and lo1 are loopbacks, which normally have nothing worth reading."),
    ],
)
def test_ntopng_with_a_loopback_chosen_says_it_is_not_normally_worth_reading(
    serve: Serve, chosen: str | int, ending: str
) -> None:
    listing = [
        {"ifid": 0, "ifname": "igc0"},
        {"ifid": 3, "ifname": "lo0"},
        {"ifid": 4, "ifname": "lo1"},
    ]

    result, _, _ = verdict(
        serve,
        "ntopng",
        "api",
        ntopng_router(listing, {0: BUSY, 3: BUSY, 4: BUSY}),
        options={"auth": "token", "interface_id": chosen},
        secrets={"token": "tok-abcdef"},
    )

    assert result.ok
    assert result.message.endswith(ending)


@pytest.mark.parametrize(
    ("name", "loopback"),
    [
        ("lo", True),
        ("lo0", True),
        ("lo12", True),
        ("igc0", False),
        ("wlo1", False),
        ("lo0.5", False),
        ("br-lo", False),
        ("", False),
    ],
)
def test_the_loopback_is_told_by_the_name_the_system_gives_the_interface(
    name: str, loopback: bool
) -> None:
    assert probes.NtopngInterface(1, name, name, "").loopback is loopback


def test_ntopng_that_refuses_a_login_redirects_to_its_login_page(serve: Serve) -> None:
    result, server, _ = verdict(
        serve,
        "ntopng",
        "api",
        lambda seen: Answer(status=302, headers={"Location": "/lua/login.lua"}),
        options={"auth": "token", "interface_id": 0},
        secrets={"token": "tok-abcdef"},
    )

    assert not result.ok
    assert "redirected to its login page, which it does when the login is refused" in result.message
    assert len(server.seen) == 1


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (Answer(status=403), "ntopng didn't accept the credentials"),
        (Answer(body="[]"), "doesn't look like ntopng's"),
        (Answer(body='{"rc": 0}'), "doesn't look like ntopng's"),
        (Answer(body="nope"), "doesn't look like ntopng's"),
    ],
)
def test_ntopng_that_does_not_answer_properly_is_explained(
    serve: Serve, answer: Answer, message: str
) -> None:
    result, _, _ = verdict(
        serve,
        "ntopng",
        "api",
        lambda seen: answer,
        options={"auth": "token", "interface_id": 0},
        secrets={"token": "tok-abcdef"},
    )

    assert not result.ok
    assert message in result.message


NTOPNG_KEY = ("ntopng", "api", "interface_id")
NTOPNG_OPTIONS: dict[str, str | int] = {"auth": "token", "interface_id": 0}
NTOPNG_SECRETS = {"token": "tok-abcdef"}


def test_ntopng_lists_each_interface_with_what_it_takes_traffic_from_and_has_seen(
    serve: Serve,
) -> None:
    router = ntopng_router(
        [
            {"ifid": 2, "ifname": "eth2", "name": "eth2", "is_pcap_interface": True},
            {
                "ifid": 0,
                "ifname": "eth0",
                "name": "WAN",
                "is_packet_interface": True,
                "is_pcap_interface": False,
                "is_zmq_interface": False,
            },
            {"ifid": 1, "ifname": "tcp://*:5556", "name": "tcp://*:5556", "is_zmq_interface": True},
            {"ifid": 3, "ifname": "br0"},
        ],
        {0: BUSY, 1: {**BUSY, "num_hosts": 1, "num_local_hosts": None}, 2: QUIET},
    )

    result, server, log = lookup(
        serve, NTOPNG_KEY, router, options=NTOPNG_OPTIONS, secrets=NTOPNG_SECRETS
    )

    assert result.ok
    assert result.message == "ntopng lists 4 interfaces."
    assert [(entry.value, entry.label, entry.detail, entry.quiet) for entry in result.entries] == [
        (
            "0",
            "WAN (eth0)",
            "live packet capture · 41 hosts (18 local), 212 flows, 1.0 GB seen",
            False,
        ),
        ("1", "tcp://*:5556", "flows from an exporter · 1 host, 212 flows, 1.0 GB seen", False),
        ("2", "eth2", "from a capture file · no traffic seen yet", True),
        ("3", "br0", "", False),
    ]
    assert not any(entry.loopback for entry in result.entries)
    assert server.seen[0].headers["authorization"] == "Token tok-abcdef"
    assert len(log.calls) == 5


def test_ntopng_lists_the_loopback_as_normally_not_useful(serve: Serve) -> None:
    result, _, _ = lookup(
        serve,
        NTOPNG_KEY,
        ntopng_router(FIREWALL, FIREWALL_TRAFFIC),
        options=NTOPNG_OPTIONS,
        secrets=NTOPNG_SECRETS,
    )

    assert [(entry.value, entry.loopback) for entry in result.entries] == [
        ("1", False),
        ("2", False),
        ("3", True),
        ("6", False),
    ]
    loopback = result.entries[2]
    assert loopback.label == "lo0"
    assert loopback.detail == (
        "loopback, normally not useful · live packet capture · no traffic seen yet"
    )


def test_ntopng_asks_about_what_only_the_first_interfaces_hold(serve: Serve) -> None:
    listed = [
        {"ifid": number, "ifname": f"eth{number}"} for number in range(probes.MAX_DETAILED + 3)
    ]

    result, server, _ = lookup(
        serve,
        NTOPNG_KEY,
        ntopng_router(listed, {number: BUSY for number in range(len(listed))}),
        options=NTOPNG_OPTIONS,
        secrets=NTOPNG_SECRETS,
    )

    assert len(result.entries) == probes.MAX_DETAILED + 3
    assert result.entries[-1].detail == ""
    assert len(server.seen) == probes.MAX_DETAILED + 1


def test_ntopng_with_no_interfaces_says_so(serve: Serve) -> None:
    result, _, _ = lookup(
        serve, NTOPNG_KEY, ntopng_router([]), options=NTOPNG_OPTIONS, secrets=NTOPNG_SECRETS
    )

    assert not result.ok
    assert result.message == "ntopng answered, but lists no interfaces."
    assert result.entries == ()


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (
            Answer(status=302, headers={"Location": "/lua/login.lua"}),
            "redirected to its login page",
        ),
        (Answer(status=403), "ntopng didn't accept the credentials"),
        (Answer(body="nope"), "doesn't look like ntopng's"),
        (Answer(drop=True), "broke, or it isn't a web server"),
    ],
)
def test_ntopng_that_cannot_list_its_interfaces_says_why(
    serve: Serve, answer: Answer, message: str
) -> None:
    result, _, _ = lookup(
        serve, NTOPNG_KEY, lambda seen: answer, options=NTOPNG_OPTIONS, secrets=NTOPNG_SECRETS
    )

    assert not result.ok
    assert message in result.message
    assert result.entries == ()


MANAGER_OPTIONS: dict[str, str | int] = {"username": "wazuh-wui"}
MANAGER_SECRETS = {"password": "pw-123456"}
# What a manager lists to a user whose role may read agents: at least itself, which is agent 000.
ITSELF: dict[str, object] = {
    "data": {"affected_items": [{"id": "000"}], "total_affected_items": 1},
    "error": 0,
}
NOBODY: dict[str, object] = {
    "data": {"affected_items": [], "total_affected_items": 0},
    "error": 0,
}


def wazuh_manager_router(
    jwt: str = "eyJ.token.value", info: object | None = None, agents: object | None = None
) -> Router:
    def route(seen: Seen) -> Answer:
        if seen.path == "/security/user/authenticate":
            return Answer(body=jwt)
        if seen.path == "/agents":
            return json_answer(agents if agents is not None else ITSELF)
        return json_answer(
            info if info is not None else {"data": {"api_version": "4.9.0"}, "error": 0}
        )

    return route


def test_the_wazuh_manager_signs_in_and_asks_about_itself_and_its_agents_with_the_token(
    serve: Serve,
) -> None:
    result, server, log = verdict(
        serve,
        "wazuh",
        "manager",
        wazuh_manager_router(),
        options=MANAGER_OPTIONS,
        secrets=MANAGER_SECRETS,
    )

    assert result == Verdict(
        True, "The Wazuh manager answered: API version 4.9.0, and the user can list its agents."
    )
    login, info, agents = server.seen
    assert (login.method, login.target) == ("POST", "/security/user/authenticate?raw=true")
    assert basic(login) == ("wazuh-wui", "pw-123456")
    assert (info.method, info.path) == ("GET", "/")
    assert info.headers["authorization"] == "Bearer eyJ.token.value"
    assert (agents.method, agents.target) == ("GET", "/agents?limit=1&select=id")
    assert agents.headers["authorization"] == "Bearer eyJ.token.value"
    assert [call.path for call in log.calls] == ["/security/user/authenticate", "/", "/agents"]
    assert "eyJ.token.value" not in repr(log.calls)


def test_a_manager_that_lists_no_agents_to_the_user_says_the_role_is_missing(
    serve: Serve,
) -> None:
    """A user with no role signs in, and the API answers 200 with nothing in the list, where the
    user with agents_readonly sees at least the manager (tried on Wazuh 4.14.1)."""
    result, server, _ = verdict(
        serve,
        "wazuh",
        "manager",
        wazuh_manager_router(agents=NOBODY),
        options=MANAGER_OPTIONS,
        secrets=MANAGER_SECRETS,
    )

    assert result == Verdict(False, probes.NO_AGENTS_LISTED)
    assert "agents_readonly" in result.message
    assert len(server.seen) == 3


@pytest.mark.parametrize("token", ["", "two words", "x" * 5000])
def test_a_token_that_is_not_a_token_is_not_used(serve: Serve, token: str) -> None:
    result, server, _ = verdict(
        serve,
        "wazuh",
        "manager",
        wazuh_manager_router(jwt=token),
        options=MANAGER_OPTIONS,
        secrets=MANAGER_SECRETS,
    )

    assert not result.ok
    assert "doesn't look like the Wazuh manager's" in result.message
    assert len(server.seen) == 1


def test_the_wazuh_manager_refusing_the_password_is_explained(serve: Serve) -> None:
    result, server, _ = verdict(
        serve,
        "wazuh",
        "manager",
        lambda seen: Answer(status=401),
        options=MANAGER_OPTIONS,
        secrets=MANAGER_SECRETS,
    )

    assert not result.ok
    assert result.message.startswith("The Wazuh manager didn't accept the credentials")
    assert len(server.seen) == 1


def test_the_wazuh_manager_refusing_the_token_is_explained(serve: Serve) -> None:
    def route(seen: Seen) -> Answer:
        return Answer(body="tok-123456") if seen.method == "POST" else Answer(status=403)

    result, server, _ = verdict(
        serve, "wazuh", "manager", route, options=MANAGER_OPTIONS, secrets=MANAGER_SECRETS
    )

    assert not result.ok
    assert "(HTTP 403)" in result.message
    assert len(server.seen) == 2


def test_the_wazuh_manager_refusing_to_list_agents_is_explained(serve: Serve) -> None:
    def route(seen: Seen) -> Answer:
        if seen.path == "/agents":
            return Answer(status=403)
        return wazuh_manager_router()(seen)

    result, server, _ = verdict(
        serve, "wazuh", "manager", route, options=MANAGER_OPTIONS, secrets=MANAGER_SECRETS
    )

    assert not result.ok
    assert "(HTTP 403)" in result.message
    assert len(server.seen) == 3


@pytest.mark.parametrize("info", [[], {"data": []}, {"data": {"title": "x"}}, "text"])
def test_the_wazuh_manager_answering_oddly_is_explained(serve: Serve, info: object) -> None:
    result, server, _ = verdict(
        serve,
        "wazuh",
        "manager",
        wazuh_manager_router(info=info),
        options=MANAGER_OPTIONS,
        secrets=MANAGER_SECRETS,
    )

    assert not result.ok
    assert "doesn't look like the Wazuh manager's" in result.message
    assert len(server.seen) == 2


@pytest.mark.parametrize(
    "agents", [[], {"data": []}, {"data": {"affected_items": "000"}}, {"message": "hello"}, "text"]
)
def test_the_wazuh_manager_listing_agents_oddly_is_explained(serve: Serve, agents: object) -> None:
    result, _, _ = verdict(
        serve,
        "wazuh",
        "manager",
        wazuh_manager_router(agents=agents),
        options=MANAGER_OPTIONS,
        secrets=MANAGER_SECRETS,
    )

    assert not result.ok
    assert "doesn't look like the Wazuh manager's" in result.message


INDEXER_OPTIONS: dict[str, str | int] = {"username": "reader"}
INDEXER_SECRETS = {"password": "pw-123456"}
# The two requests of the indexer the security plugin of OpenSearch tells apart, and the
# permission each needs. The answers below are what OpenSearch 2.19.1 gave a user who signed in
# and lacked it, and one who didn't sign in.
ROOT_NEEDS = "cluster:monitor/main"
SEARCH_NEEDS = "indices:data/read/search"


def lacking(permission: str) -> Answer:
    reason = (
        f"no permissions for [{permission}] and "
        "User [name=reader, backend_roles=[], requestedTenant=null]"
    )
    return json_answer(
        {
            "error": {
                "root_cause": [{"type": "security_exception", "reason": reason}],
                "type": "security_exception",
                "reason": reason,
            },
            "status": 403,
        },
        403,
    )


def indexer_security(allowed: set[str], total: object = None) -> Router:
    """An indexer whose user holds these permissions. It answers as OpenSearch does: 401 to a user
    it doesn't know, 403 naming the permission to one who lacks it, and for a search the hits."""

    def route(seen: Seen) -> Answer:
        if basic(seen) != ("reader", "pw-123456"):
            return Answer(status=401, body="Unauthorized")
        searching = (seen.method, seen.path) == ("POST", "/wazuh-alerts-*/_search")
        needed = SEARCH_NEEDS if searching else ROOT_NEEDS
        if needed not in allowed:
            return lacking(needed)
        if searching:
            hits: dict[str, object] = {"max_score": None, "hits": []}
            if total is not None:
                hits["total"] = total
            return json_answer({"took": 1, "timed_out": False, "hits": hits})
        return json_answer({"name": "node-1", "version": {"number": "2.19.1"}})

    return route


def indexer(
    serve: Serve, handler: Router, secrets: dict[str, str] | None = None
) -> tuple[Verdict, StubServer, Log]:
    return verdict(
        serve,
        "wazuh",
        "indexer",
        handler,
        options=INDEXER_OPTIONS,
        secrets=secrets or INDEXER_SECRETS,
    )


def test_the_wazuh_indexer_is_asked_to_search_the_alerts_the_way_the_collector_does(
    serve: Serve,
) -> None:
    result, server, log = indexer(
        serve, indexer_security({SEARCH_NEEDS}, {"value": 1204, "relation": "eq"})
    )

    assert result == Verdict(
        True,
        "The Wazuh indexer answered, and the user can search the alerts. It holds 1,204 alerts.",
    )
    [asked] = server.seen
    assert (asked.method, asked.path) == ("POST", "/wazuh-alerts-*/_search")
    assert json.loads(asked.body) == {"size": 0}
    assert basic(asked) == ("reader", "pw-123456")
    assert [(call.method, call.path) for call in log.calls] == [("POST", "/wazuh-alerts-*/_search")]


def test_a_user_who_may_only_search_the_alerts_passes_without_the_root_page(
    serve: Serve,
) -> None:
    """Wazuh's own example of a read-only role (the cluster permission cluster_composite_ops_ro
    and read on the indices) lets a user search but not ask the root page, which needs
    cluster:monitor/main: OpenSearch answered 403 to it and 200 to the search. The test used to
    ask the root page, and so refused the user the collector can use."""
    result, server, _ = indexer(serve, indexer_security({SEARCH_NEEDS}))

    assert result.ok
    assert [seen.path for seen in server.seen] == ["/wazuh-alerts-*/_search"]


@pytest.mark.parametrize(
    ("total", "sentence"),
    [
        ({"value": 0, "relation": "eq"}, " It holds none yet."),
        ({"value": 1, "relation": "eq"}, " It holds 1 alert."),
        ({"value": 7, "relation": "eq"}, " It holds 7 alerts."),
        ({"value": 10000, "relation": "gte"}, " It holds 10,000 or more."),
        ({"value": 3}, " It holds 3 alerts."),
        (12, " It holds 12 alerts."),
        (None, ""),
        ({"value": -1, "relation": "eq"}, ""),
        ({"value": "many"}, ""),
        ({"value": True}, ""),
        ({}, ""),
        (True, ""),
        ("many", ""),
        (-4, ""),
    ],
)
def test_the_wazuh_indexer_says_how_many_alerts_it_holds_when_it_says_so_clearly(
    serve: Serve, total: object, sentence: str
) -> None:
    result, _, _ = indexer(serve, indexer_security({SEARCH_NEEDS}, total))

    assert result == Verdict(
        True, f"The Wazuh indexer answered, and the user can search the alerts.{sentence}"
    )


def test_a_wrong_password_for_the_wazuh_indexer_is_a_refused_sign_in(serve: Serve) -> None:
    result, _, _ = indexer(
        serve, indexer_security({SEARCH_NEEDS}), secrets={"password": "not-the-password"}
    )

    assert result == Verdict(False, probes.INDEXER_REFUSED)
    assert result.message.startswith("The Wazuh indexer didn't accept the credentials (HTTP 401).")
    assert "Internal users" in result.message
    assert "allowed" not in result.message


def test_a_user_who_may_not_search_the_alerts_is_told_which_permission_to_give(
    serve: Serve,
) -> None:
    result, _, _ = indexer(serve, indexer_security(set()))

    assert result == Verdict(
        False,
        "The Wazuh indexer accepted the sign-in, but the user isn't allowed to read the alerts "
        "(HTTP 403). It says the user has no permission for indices:data/read/search. Give the "
        "user's role the index permission read on wazuh-alerts-*, and map the user to the role "
        "(Mapped users).",
    )


def test_a_permission_of_the_cluster_is_asked_for_under_cluster_permissions(
    serve: Serve,
) -> None:
    result, _, _ = indexer(serve, lambda seen: lacking(ROOT_NEEDS))

    assert not result.ok
    assert "no permission for cluster:monitor/main" in result.message
    assert result.message.endswith("Add it under the user's role, in Cluster permissions.")


@pytest.mark.parametrize(
    "body",
    [
        "",
        "<html>Forbidden</html>",
        "[]",
        '{"status": 403}',
        '{"error": "forbidden"}',
        '{"error": {"reason": 5}}',
        '{"error": {"reason": "no permissions for [two words]"}}',
        '{"error": {"reason": "no permissions for []"}}',
        '{"error": {"reason": "no permissions for [' + "a" * 81 + ']"}}',
        '{"error": {"reason": "no permissions for [<script>alert(1)</script>]"}}',
        '{"error": {"reason": "Forbidden"}}',
    ],
)
def test_a_refusal_that_names_no_permission_quotes_nothing_the_indexer_said(
    serve: Serve, body: str
) -> None:
    result, _, _ = indexer(serve, lambda seen: Answer(status=403, body=body))

    assert result.message == (
        "The Wazuh indexer accepted the sign-in, but the user isn't allowed to read the alerts "
        "(HTTP 403). Give the user's role the index permission read on wazuh-alerts-*, and map "
        "the user to the role (Mapped users)."
    )


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (Answer(status=404), "The Wazuh indexer answered 404"),
        (Answer(status=503), "The Wazuh indexer answered HTTP 503."),
        (Answer(status=302), "The Wazuh indexer redirected the request"),
        (Answer(body='{"hits": "x"}'), "doesn't look like the Wazuh indexer's"),
        (Answer(body='{"hits": {"hits": 3}}'), "doesn't look like the Wazuh indexer's"),
        (Answer(body='{"version": "7"}'), "doesn't look like the Wazuh indexer's"),
        (Answer(body="[]"), "doesn't look like the Wazuh indexer's"),
    ],
)
def test_the_wazuh_indexer_that_does_not_answer_properly_is_explained(
    serve: Serve, answer: Answer, message: str
) -> None:
    result, _, _ = indexer(serve, lambda seen: answer)

    assert not result.ok
    assert message in result.message


@pytest.mark.parametrize("body", ["null", "[]", '[{"id": 1, "value": "192.0.2.1"}]', " null\n"])
def test_crowdsec_accepts_the_key_whether_or_not_anyone_is_banned(serve: Serve, body: str) -> None:
    result, server, log = verdict(
        serve,
        "crowdsec",
        "lapi",
        lambda seen: Answer(body=body),
        secrets={"api_key": "bouncer-key"},
    )

    assert result == Verdict(True, "CrowdSec's local API accepted the key.")
    [seen] = server.seen
    assert seen.target == "/v1/decisions?ip=192.0.2.1"
    assert seen.headers["x-api-key"] == "bouncer-key"
    assert log.calls[0].path == "/v1/decisions"


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (Answer(status=403, body='{"message": "access forbidden"}'), "CrowdSec didn't accept"),
        (Answer(body="<html>"), "doesn't look like CrowdSec's"),
        (Answer(body='{"a": 1}'), "doesn't look like CrowdSec's"),
    ],
)
def test_crowdsec_that_does_not_answer_properly_is_explained(
    serve: Serve, answer: Answer, message: str
) -> None:
    result, _, _ = verdict(
        serve, "crowdsec", "lapi", lambda seen: answer, secrets={"api_key": "bouncer-key"}
    )

    assert not result.ok
    assert message in result.message


def test_otx_accepts_a_key_that_belongs_to_an_account_and_asks_about_no_address(
    serve: Serve,
) -> None:
    result, server, log = verdict(
        serve,
        "otx",
        "api",
        lambda seen: Answer(body='{"username": "someone"}'),
        secrets={"api_key": "otx-key"},
    )

    assert result == Verdict(True, "OTX accepted the key.")
    [seen] = server.seen
    assert seen.target == "/api/v1/users/me"
    assert seen.headers["x-otx-api-key"] == "otx-key"
    assert log.calls[0].path == "/api/v1/users/me"


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (Answer(status=401), "OTX didn't accept the key."),
        (Answer(status=403), "OTX didn't accept the key."),
        (Answer(status=500), "OTX answered HTTP 500."),
        (Answer(body="<html>"), "doesn't look like OTX's"),
        (Answer(body='{"id": 1}'), "doesn't look like OTX's"),
    ],
)
def test_otx_that_does_not_answer_properly_is_explained(
    serve: Serve, answer: Answer, message: str
) -> None:
    result, _, _ = verdict(serve, "otx", "api", lambda seen: answer, secrets={"api_key": "k"})

    assert not result.ok
    assert message in result.message


def test_the_state_of_a_service_is_read_from_the_words_it_uses() -> None:
    state = probes.service_state

    assert state(Reply(200, '{"status": "running"}')) is ModuleState.RUNNING
    assert state(Reply(200, '{"status": "Running", "other": 1}')) is ModuleState.RUNNING
    assert state(Reply(200, '{"status": "stopped"}')) is ModuleState.STOPPED
    assert state(Reply(200, '{"status": "disabled"}')) is ModuleState.STOPPED
    assert state(Reply(200, '{"rows": []}')) is ModuleState.INSTALLED
    assert state(Reply(200, "[]")) is ModuleState.INSTALLED
    assert state(Reply(200, "")) is ModuleState.INSTALLED
    assert state(Reply(404, "")) is ModuleState.NOT_INSTALLED
    assert state(Reply(401, "")) is ModuleState.NO_ACCESS
    assert state(Reply(403, "")) is ModuleState.NO_ACCESS
    assert state(Reply(500, "")) is ModuleState.UNKNOWN
    assert state(Reply(302, "")) is ModuleState.UNKNOWN


def test_what_an_integration_says_is_cut_to_a_short_plain_fact() -> None:
    assert probes.fact("line\nbreak " + "x" * 100) == "line break " + "x" * 49
    assert probes.fact("") == "unknown"
    assert probes.fact(7) == "7"


@pytest.mark.parametrize(
    ("bytes_seen", "text"),
    [(512, "512 B"), (1_500, "1.5 kB"), (2_500_000, "2.5 MB"), (3_200_000_000, "3.2 GB")],
)
def test_sizes_are_said_in_the_unit_that_fits(bytes_seen: int, text: str) -> None:
    assert probes.Traffic(1, None, 1, bytes_seen).describe().endswith(f"{text} seen")


def test_a_size_beyond_the_gigabytes_is_in_terabytes() -> None:
    assert probes.Traffic(2, 1, 3, 4_700_000_000_000).describe() == (
        "2 hosts (1 local), 3 flows, 4.7 TB seen"
    )
