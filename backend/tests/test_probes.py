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
    assert (
        result.message
        == "ntopng answered, but has no interface with ID 7. It has: ID 0: wan, ID 1: lan."
    )
    assert empty.message.endswith("It has: none.")
    assert len(server.seen) == 1


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
    assert server.seen[0].headers["authorization"] == "Token tok-abcdef"
    assert len(log.calls) == 5


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


def wazuh_manager_router(jwt: str = "eyJ.token.value", info: object | None = None) -> Router:
    def route(seen: Seen) -> Answer:
        if seen.path == "/security/user/authenticate":
            return Answer(body=jwt)
        return json_answer(
            info if info is not None else {"data": {"api_version": "4.9.0"}, "error": 0}
        )

    return route


def test_the_wazuh_manager_signs_in_and_asks_about_itself_with_the_token(serve: Serve) -> None:
    result, server, log = verdict(
        serve,
        "wazuh",
        "manager",
        wazuh_manager_router(),
        options=MANAGER_OPTIONS,
        secrets=MANAGER_SECRETS,
    )

    assert result == Verdict(True, "The Wazuh manager answered: API version 4.9.0.")
    login, info = server.seen
    assert (login.method, login.target) == ("POST", "/security/user/authenticate?raw=true")
    assert basic(login) == ("wazuh-wui", "pw-123456")
    assert (info.method, info.path) == ("GET", "/")
    assert info.headers["authorization"] == "Bearer eyJ.token.value"
    assert [call.path for call in log.calls] == ["/security/user/authenticate", "/"]
    assert "eyJ.token.value" not in repr(log.calls)


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


@pytest.mark.parametrize("info", [[], {"data": []}, {"data": {"title": "x"}}, "text"])
def test_the_wazuh_manager_answering_oddly_is_explained(serve: Serve, info: object) -> None:
    result, _, _ = verdict(
        serve,
        "wazuh",
        "manager",
        wazuh_manager_router(info=info),
        options=MANAGER_OPTIONS,
        secrets=MANAGER_SECRETS,
    )

    assert not result.ok
    assert "doesn't look like the Wazuh manager's" in result.message


def test_the_wazuh_indexer_names_its_version(serve: Serve) -> None:
    result, server, _ = verdict(
        serve,
        "wazuh",
        "indexer",
        lambda seen: json_answer({"name": "node-1", "version": {"number": "7.10.2"}}),
        options={"username": "reader"},
        secrets={"password": "pw-123456"},
    )

    assert result == Verdict(True, "The Wazuh indexer answered: version 7.10.2.")
    assert basic(server.seen[0]) == ("reader", "pw-123456")
    assert server.seen[0].path == "/"


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (Answer(status=401), "The Wazuh indexer didn't accept the credentials"),
        (Answer(body='{"version": "7"}'), "doesn't look like the Wazuh indexer's"),
        (Answer(body="[]"), "doesn't look like the Wazuh indexer's"),
    ],
)
def test_the_wazuh_indexer_that_does_not_answer_properly_is_explained(
    serve: Serve, answer: Answer, message: str
) -> None:
    result, _, _ = verdict(
        serve,
        "wazuh",
        "indexer",
        lambda seen: answer,
        options={"username": "reader"},
        secrets={"password": "pw-123456"},
    )

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
