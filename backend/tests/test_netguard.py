import asyncio
import hashlib
import ipaddress
import socket
import ssl
from typing import Any

import httpcore2
import httpx2
import pytest

from app.integrations import netguard
from app.integrations.client import in_chain
from app.integrations.netguard import (
    HOME_NETWORK,
    HOME_NETWORK_AND_LOOPBACK,
    OLLAMA_IN_CONTAINER,
    OLLAMA_ON_THIS_COMPUTER,
    PUBLIC_INTERNET,
    PUBLIC_INTERNET_AND_LOOPBACK,
    GuardedBackend,
    GuardedTransport,
    NotFound,
    Origin,
    Refused,
    allowed_addresses,
    parse_origin,
)
from tests.stubs import Answer, Certificate, Serve, StubServer, make_certificate


def ok(_: object) -> Answer:
    return Answer(body="hello")


@pytest.mark.parametrize(
    ("url", "scheme", "host", "port", "normal"),
    [
        ("https://192.168.1.1", "https", "192.168.1.1", 443, "https://192.168.1.1"),
        ("  https://192.168.1.1/ ", "https", "192.168.1.1", 443, "https://192.168.1.1"),
        ("https://192.168.1.3:55000", "https", "192.168.1.3", 55000, "https://192.168.1.3:55000"),
        ("http://fw.home.arpa:3000", "http", "fw.home.arpa", 3000, "http://fw.home.arpa:3000"),
        ("http://10.0.0.2", "http", "10.0.0.2", 80, "http://10.0.0.2"),
        ("HTTPS://FW.Example.COM", "https", "fw.example.com", 443, "https://fw.example.com"),
        ("https://[fd00::1]:8443", "https", "fd00::1", 8443, "https://[fd00::1]:8443"),
        ("https://[fd00::1]", "https", "fd00::1", 443, "https://[fd00::1]"),
    ],
)
def test_an_address_is_read_into_its_parts(
    url: str, scheme: str, host: str, port: int, normal: str
) -> None:
    origin = parse_origin(url, allow_http=True)

    assert origin == Origin(scheme, host, port)
    assert origin.url == normal


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("", "Start the address with https://"),
        ("192.168.1.1", "Start the address with https://"),
        ("ftp://192.168.1.1", "Start the address with https://"),
        ("https://", "Start the address with https://"),
        ("https://user:pass@192.168.1.1", "no user name, path or query"),
        ("https://192.168.1.1/api", "no user name, path or query"),
        ("https://192.168.1.1?x=1", "no user name, path or query"),
        ("https://192.168.1.1#top", "no user name, path or query"),
        ("https://192.168.1.1:99999", "That isn't a web address"),
        ("https://192.168.1.1:abc", "That isn't a web address"),
        ("https://[fd00::1", "That isn't a web address"),
        ("https://not_a_host", "That isn't a host name or an IP address"),
        ("https://-bad.example", "That isn't a host name or an IP address"),
        ("https://bad-.example", "That isn't a host name or an IP address"),
        ("https://a..b", "That isn't a host name or an IP address"),
        ("https://" + "a" * 64 + ".example", "That isn't a host name or an IP address"),
        ("https://" + "a" * 300, "too long"),
    ],
)
def test_an_address_that_is_not_a_plain_origin_is_refused(url: str, message: str) -> None:
    with pytest.raises(Refused, match=message):
        parse_origin(url, allow_http=True)


def test_http_is_refused_where_the_product_does_not_speak_it() -> None:
    with pytest.raises(Refused, match="only offered over https://"):
        parse_origin("http://192.168.1.1", allow_http=False)


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "172.31.255.254",
        "192.168.0.1",
        "192.168.255.254",
        "fd00::1",
        "fc00::5",
        "::ffff:192.168.1.1",
    ],
)
def test_private_addresses_are_allowed(address: str) -> None:
    assert HOME_NETWORK.allows(ipaddress.ip_address(address))


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "::1",
        "0.0.0.0",  # noqa: S104
        "8.8.8.8",
        "1.1.1.1",
        "172.15.255.255",
        "172.32.0.1",
        "11.0.0.1",
        "192.169.0.1",
        "100.64.0.1",
        "100.100.100.200",
        "169.254.169.254",
        "169.254.0.1",
        "fe80::1",
        "fd00:ec2::254",
        "fd00:ec2::253",
        "2001:db8::1",
        "::ffff:127.0.0.1",
        "::ffff:8.8.8.8",
        "::ffff:169.254.169.254",
    ],
)
def test_everything_else_is_refused(address: str) -> None:
    assert not HOME_NETWORK.allows(ipaddress.ip_address(address))


def test_the_test_server_policy_adds_only_loopback() -> None:
    assert HOME_NETWORK_AND_LOOPBACK.allows(ipaddress.ip_address("127.0.0.1"))
    assert HOME_NETWORK_AND_LOOPBACK.allows(ipaddress.ip_address("::1"))
    assert HOME_NETWORK_AND_LOOPBACK.allows(ipaddress.ip_address("10.0.0.1"))
    assert not HOME_NETWORK_AND_LOOPBACK.allows(ipaddress.ip_address("169.254.169.254"))
    assert not HOME_NETWORK_AND_LOOPBACK.allows(ipaddress.ip_address("8.8.8.8"))


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "127.1.2.3", "::1", "::ffff:127.0.0.1", "192.168.1.50", "10.0.0.2"]
)
def test_an_ollama_may_be_on_the_computer_that_runs_aresgate(address: str) -> None:
    assert OLLAMA_ON_THIS_COMPUTER.allows(ipaddress.ip_address(address))


@pytest.mark.parametrize(
    "address",
    ["8.8.8.8", "169.254.169.254", "fd00:ec2::254", "100.64.0.1", "0.0.0.0", "fe80::1"],  # noqa: S104
)
def test_an_ollama_is_still_only_on_this_computer_or_the_home_network(address: str) -> None:
    assert not OLLAMA_ON_THIS_COMPUTER.allows(ipaddress.ip_address(address))
    assert not OLLAMA_IN_CONTAINER.allows(ipaddress.ip_address(address))


@pytest.mark.parametrize("address", ["127.0.0.1", "::1", "::ffff:127.0.0.1"])
def test_in_the_container_localhost_is_the_container_and_an_ollama_is_not_there(
    address: str,
) -> None:
    assert not OLLAMA_IN_CONTAINER.allows(ipaddress.ip_address(address))
    assert OLLAMA_IN_CONTAINER.allows(ipaddress.ip_address("192.168.65.254"))
    assert OLLAMA_IN_CONTAINER.allows(ipaddress.ip_address("172.17.0.1"))


def test_in_the_container_a_refusal_of_localhost_says_how_to_reach_the_computer() -> None:
    loopback_v6 = [ipaddress.ip_address("::1")]
    loopback_v4 = [ipaddress.ip_address("127.0.0.1")]

    with pytest.raises(Refused) as name:
        allowed_addresses(OLLAMA_IN_CONTAINER, "localhost", loopback_v6)
    with pytest.raises(Refused) as typed:
        allowed_addresses(OLLAMA_IN_CONTAINER, "127.0.0.1", loopback_v4)

    assert str(name.value) == (
        "localhost is at ::1, which is AresGate's container, not your computer, so AresGate "
        "won't connect to it. Ollama has to be on your own network. For one on the computer that "
        "runs AresGate, use host.docker.internal instead of localhost, such as "
        "http://host.docker.internal:11434."
    )
    assert str(typed.value).startswith(
        "127.0.0.1 is AresGate's container, not your computer, so AresGate won't connect to it."
    )


def test_an_ollama_that_is_refused_is_told_where_it_may_be() -> None:
    on_the_internet = [ipaddress.ip_address("8.8.8.8")]
    cloud_metadata = [ipaddress.ip_address("169.254.169.254")]

    with pytest.raises(Refused) as refused:
        allowed_addresses(OLLAMA_ON_THIS_COMPUTER, "8.8.8.8", on_the_internet)
    with pytest.raises(Refused) as metadata:
        allowed_addresses(OLLAMA_IN_CONTAINER, "169.254.169.254", cloud_metadata)

    assert str(refused.value) == (
        "8.8.8.8 isn't a private network address, so AresGate won't connect to it. "
        "Ollama has to be on this computer or on your own network."
    )
    # A cloud provider's metadata service says what it is, whatever else is said of loopback.
    assert "metadata services" in str(metadata.value)


@pytest.mark.parametrize(
    "address",
    ["8.8.8.8", "1.1.1.1", "160.79.104.10", "172.15.255.255", "172.32.0.1", "2606:4700::1111"],
)
def test_the_internet_is_where_an_ai_provider_may_be(address: str) -> None:
    assert PUBLIC_INTERNET.allows(ipaddress.ip_address(address))
    assert PUBLIC_INTERNET_AND_LOOPBACK.allows(ipaddress.ip_address(address))


@pytest.mark.parametrize(
    "address",
    [
        "0.0.0.0",  # noqa: S104
        "10.0.0.1",
        "100.64.0.1",
        "127.0.0.1",
        "169.254.169.254",
        "172.16.0.1",
        "192.168.1.1",
        "224.0.0.1",
        "255.255.255.255",
        "::",
        "::1",
        "fc00::5",
        "fd00:ec2::254",
        "fe80::1",
        "ff02::1",
        "::ffff:10.0.0.1",
        "::ffff:127.0.0.1",
    ],
)
def test_the_inside_of_a_network_is_not(address: str) -> None:
    assert not PUBLIC_INTERNET.allows(ipaddress.ip_address(address))


def test_the_test_server_policy_for_providers_adds_only_loopback() -> None:
    assert PUBLIC_INTERNET_AND_LOOPBACK.allows(ipaddress.ip_address("127.0.0.1"))
    assert PUBLIC_INTERNET_AND_LOOPBACK.allows(ipaddress.ip_address("::1"))
    assert not PUBLIC_INTERNET_AND_LOOPBACK.allows(ipaddress.ip_address("192.168.1.1"))
    assert not PUBLIC_INTERNET_AND_LOOPBACK.allows(ipaddress.ip_address("169.254.169.254"))


def test_a_refusal_says_where_the_thing_it_is_for_should_be() -> None:
    public = [ipaddress.ip_address("8.8.8.8")]
    private = [ipaddress.ip_address("192.168.1.1")]
    metadata_address = [ipaddress.ip_address("169.254.169.254")]

    with pytest.raises(Refused) as home:
        allowed_addresses(HOME_NETWORK, "8.8.8.8", public)
    with pytest.raises(Refused) as internet:
        allowed_addresses(PUBLIC_INTERNET, "api.example.com", private)
    with pytest.raises(Refused) as metadata:
        allowed_addresses(PUBLIC_INTERNET, "169.254.169.254", metadata_address)

    assert str(home.value) == (
        "8.8.8.8 isn't a private network address, so AresGate won't connect to it. "
        "Integrations have to be on your own network."
    )
    assert str(internet.value) == (
        "api.example.com is at 192.168.1.1, which isn't an address on the internet, so AresGate "
        "won't connect to it. AI providers are on the internet, not on your own network."
    )
    assert "metadata services" in str(metadata.value)


def fake_lookup(monkeypatch: pytest.MonkeyPatch, *addresses: str) -> None:
    def getaddrinfo(host: str, port: int, *_: Any, **__: Any) -> list[tuple[Any, ...]]:
        return [
            (socket.AF_INET6 if ":" in item else socket.AF_INET, 1, 6, "", (item, port))
            for item in addresses
        ]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


def test_a_name_leads_to_its_addresses_without_repeats(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_lookup(monkeypatch, "10.0.0.5", "10.0.0.5", "fe80::1%eth0")

    assert netguard.lookup("fw.example", 443) == [
        ipaddress.ip_address("10.0.0.5"),
        ipaddress.ip_address("fe80::1"),
    ]
    assert asyncio.run(netguard.lookup_async("fw.example", 443)) == netguard.lookup(
        "fw.example", 443
    )


def test_an_answer_that_is_not_an_internet_address_is_left_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def getaddrinfo(host: str, port: int, *_: Any, **__: Any) -> list[tuple[Any, ...]]:
        return [
            (socket.AF_UNIX, 1, 0, "", "/run/socket"),
            (socket.AF_INET, 1, 6, "", ("10.0.0.5", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

    assert netguard.lookup("fw.example", 443) == [ipaddress.ip_address("10.0.0.5")]


def test_a_name_that_leads_nowhere_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def getaddrinfo(*_: Any, **__: Any) -> list[Any]:
        raise socket.gaierror("no such name")

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

    with pytest.raises(NotFound, match=r"Couldn't find fw\.example"):
        netguard.lookup("fw.example", 443)
    lookup = netguard.lookup_async("fw.example", 443)

    with pytest.raises(NotFound, match=r"Couldn't find fw\.example"):
        asyncio.run(lookup)


def test_a_name_that_also_leads_somewhere_forbidden_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_lookup(monkeypatch, "192.168.1.5", "169.254.169.254")

    origin = Origin("https", "fw.example", 443)

    with pytest.raises(Refused, match=r"fw.example is at 169.254.169.254, which is in a range"):
        netguard.check_reachable(HOME_NETWORK, origin)


def test_an_ip_address_is_checked_without_asking_dns() -> None:
    netguard.check_reachable(HOME_NETWORK, Origin("https", "192.168.1.1", 443))
    # What was typed in isn't "at" itself, and the metadata ranges are named as such.
    loopback = Origin("https", "127.0.0.1", 443)
    metadata = Origin("http", "169.254.169.254", 80)
    with pytest.raises(Refused, match=r"^127\.0\.0\.1 isn't a private network address"):
        netguard.check_reachable(HOME_NETWORK, loopback)
    with pytest.raises(Refused, match=r"^169\.254\.169\.254 is in a range cloud providers use"):
        netguard.check_reachable(HOME_NETWORK, metadata)


def test_fingerprints_are_written_the_way_other_tools_show_them() -> None:
    assert netguard.fingerprint_of(b"") == (
        "E3:B0:C4:42:98:FC:1C:14:9A:FB:F4:C8:99:6F:B9:24:"
        "27:AE:41:E4:64:9B:93:4C:A4:95:99:1B:78:52:B8:55"
    )


@pytest.mark.parametrize(
    "text",
    [
        netguard.fingerprint_of(b""),
        hashlib.sha256(b"").hexdigest(),
        " ".join(f"{byte:02x}" for byte in hashlib.sha256(b"").digest()),
        netguard.fingerprint_of(b"").replace(":", "-"),
    ],
)
def test_a_fingerprint_is_accepted_in_any_usual_form(text: str) -> None:
    assert netguard.normalize_fingerprint(text) == netguard.fingerprint_of(b"")


@pytest.mark.parametrize("text", ["", "abc", "zz" * 32, "ab" * 31, "ab" * 33])
def test_something_that_is_not_a_fingerprint_is_not_accepted(text: str) -> None:
    assert netguard.normalize_fingerprint(text) is None


def test_pasted_certificates_are_checked_and_written_out_the_same_way() -> None:
    first, second = make_certificate("a.example"), make_certificate("b.example")

    cleaned = netguard.clean_ca_pem(f"  junk before\n{first.pem}\nand between\n{second.pem}")

    assert cleaned == first.pem + second.pem
    assert netguard.clean_ca_pem(cleaned) == cleaned


def test_a_private_key_is_not_taken_as_a_certificate() -> None:
    certificate = make_certificate()

    with pytest.raises(ValueError, match="includes a private key"):
        netguard.clean_ca_pem(certificate.pem + certificate.key_pem)


@pytest.mark.parametrize(
    "text", ["", "hello", "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----"]
)
def test_text_that_is_not_a_certificate_is_refused(text: str) -> None:
    with pytest.raises(ValueError, match="isn't a certificate in PEM form"):
        netguard.clean_ca_pem(text)


def test_too_much_text_or_too_many_certificates_are_refused() -> None:
    with pytest.raises(ValueError, match="too long"):
        netguard.clean_ca_pem("x" * (netguard.MAX_CA_PEM + 1))
    many = make_certificate().pem * (netguard.MAX_CA_CERTIFICATES + 1)
    with pytest.raises(ValueError, match="at most 10 certificates"):
        netguard.clean_ca_pem(many)


def test_the_tls_modes_check_the_certificate_in_their_own_way() -> None:
    certificate = make_certificate()

    system = netguard.tls_context("system", None)
    authority = netguard.tls_context("ca", certificate.pem)
    pinned = netguard.tls_context("pinned", None)

    assert system.verify_mode == ssl.CERT_REQUIRED
    assert system.check_hostname
    assert authority.verify_mode == ssl.CERT_REQUIRED
    assert authority.check_hostname
    # Only the certificate pasted in, not the certificates the computer trusts.
    assert authority.cert_store_stats()["x509"] == 1
    # Pinned: the fingerprint is compared before anything is sent, in ``GuardedBackend``.
    assert pinned.verify_mode == ssl.CERT_NONE
    assert all(
        context.minimum_version >= ssl.TLSVersion.TLSv1_2 for context in (system, authority, pinned)
    )


def fetch(
    server: StubServer,
    *,
    mode: str = "system",
    ca_pem: str | None = None,
    pin: str | None = None,
    policy: netguard.AddressPolicy = HOME_NETWORK_AND_LOOPBACK,
    url: str | None = None,
) -> httpx2.Response:
    async def get() -> httpx2.Response:
        transport = GuardedTransport(
            netguard.tls_context(mode, ca_pem), GuardedBackend(policy, pin)
        )
        async with httpx2.AsyncClient(transport=transport, trust_env=False) as client:
            return await client.get((url or server.url) + "/")

    return asyncio.run(get())


def test_a_request_to_an_address_that_is_not_allowed_is_never_made(serve: Serve) -> None:
    server = serve(ok)

    with pytest.raises(Refused, match=r"127\.0\.0\.1 isn't a private"):
        fetch(server, policy=HOME_NETWORK)

    assert server.seen == []


def test_a_request_goes_to_the_address_that_was_checked(
    serve: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = serve(ok)
    looked_up: list[str] = []

    def getaddrinfo(host: str, port: int, *_: Any, **__: Any) -> list[tuple[Any, ...]]:
        looked_up.append(host)
        return [(socket.AF_INET, 1, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

    reply = fetch(server, url=f"http://firewall.home.arpa:{server.port}")

    assert reply.text == "hello"
    assert looked_up == ["firewall.home.arpa"]
    assert server.seen[0].headers["host"] == f"firewall.home.arpa:{server.port}"


def test_the_next_address_is_tried_when_the_first_does_not_answer(
    serve: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = serve(ok)

    async def lookup(host: str, port: int) -> list[netguard.IPAddress]:
        return [ipaddress.ip_address("127.0.0.2"), ipaddress.ip_address("127.0.0.1")]

    monkeypatch.setattr(netguard, "lookup_async", lookup)

    assert fetch(server).text == "hello"


def test_when_no_address_answers_the_last_failure_is_raised(
    serve: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = serve(ok)
    server.stop()

    with pytest.raises(httpx2.ConnectError):
        fetch(server)


def test_an_untrusted_certificate_is_refused_by_default(serve: Serve) -> None:
    server = serve(ok, make_certificate())

    with pytest.raises(httpx2.ConnectError) as raised:
        fetch(server)

    assert in_chain(raised.value, ssl.SSLCertVerificationError)
    assert server.seen == []


def test_a_pasted_certificate_authority_is_trusted(serve: Serve) -> None:
    certificate = make_certificate()
    server = serve(ok, certificate)

    assert fetch(server, mode="ca", ca_pem=certificate.pem).text == "hello"


def test_another_certificate_authority_is_not(serve: Serve) -> None:
    server = serve(ok, make_certificate())

    another = make_certificate().pem

    with pytest.raises(httpx2.ConnectError):
        fetch(server, mode="ca", ca_pem=another)


def test_the_certificate_pinned_is_trusted_and_anything_else_is_not(serve: Serve) -> None:
    certificate = make_certificate()
    server = serve(ok, certificate)

    assert fetch(server, mode="pinned", pin=certificate.fingerprint).text == "hello"
    assert len(server.seen) == 1

    other = make_certificate()
    with pytest.raises(Refused, match="isn't the pinned one") as refused:
        fetch(server, mode="pinned", pin=other.fingerprint)
    assert certificate.fingerprint in str(refused.value)
    # The request, with its key, was never sent to a system that isn't the one pinned.
    assert len(server.seen) == 1


def test_a_pin_changes_nothing_for_a_plain_connection(serve: Serve) -> None:
    server = serve(ok)

    assert fetch(server, mode="pinned", pin="AA:BB").text == "hello"


def test_a_missingpeer_certificate_does_not_match_the_pin() -> None:
    class Bare(httpcore2.AsyncNetworkStream):
        def get_extra_info(self, info: str) -> object:
            return None

        async def aclose(self) -> None:
            pass

    assert netguard.peer_certificate(Bare()) is None


def test_the_certificate_a_system_presents_can_be_looked_at(serve: Serve) -> None:
    certificate = make_certificate("fw.example")
    server = serve(ok, certificate)
    origin = netguard.parse_origin(server.url, allow_http=False)

    found = asyncio.run(netguard.look_up_certificate(HOME_NETWORK_AND_LOOPBACK, origin))

    assert found.fingerprint == certificate.fingerprint
    assert found.subject == "CN=fw.example"
    assert found.issuer == "CN=fw.example"
    assert found.names == ["fw.example", "127.0.0.1"]
    assert found.not_before < found.not_after
    assert server.seen == []


def test_looking_at_a_certificate_respects_the_allowed_addresses(serve: Serve) -> None:
    server = serve(ok, make_certificate())
    origin = netguard.parse_origin(server.url, allow_http=False)

    lookup = netguard.look_up_certificate(HOME_NETWORK, origin)

    with pytest.raises(Refused, match="isn't a private network address"):
        asyncio.run(lookup)


def test_looking_at_a_certificate_says_when_nothing_answers(serve: Serve) -> None:
    server = serve(ok, make_certificate())
    origin = netguard.parse_origin(server.url, allow_http=False)
    server.stop()

    lookup = netguard.look_up_certificate(HOME_NETWORK_AND_LOOPBACK, origin)

    with pytest.raises(Refused, match="Couldn't make a secure connection"):
        asyncio.run(lookup)


def test_looking_at_a_certificate_says_when_nothing_answers_in_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def connect_tcp(*_: Any, **__: Any) -> None:
        raise httpcore2.ConnectTimeout()

    monkeypatch.setattr(GuardedBackend, "connect_tcp", connect_tcp)

    origin = Origin("https", "192.168.1.1", 443)
    lookup = netguard.look_up_certificate(HOME_NETWORK, origin)

    with pytest.raises(Refused, match="didn't answer in time"):
        asyncio.run(lookup)


def test_a_plain_web_server_has_no_certificate_to_look_at(serve: Serve) -> None:
    server = serve(ok)
    origin = Origin("https", "127.0.0.1", server.port)

    lookup = netguard.look_up_certificate(HOME_NETWORK_AND_LOOPBACK, origin)

    with pytest.raises(Refused, match="Couldn't make a secure connection"):
        asyncio.run(lookup)


def no_certificate(stream: httpcore2.AsyncNetworkStream) -> None:
    return None


def test_a_system_that_presents_no_certificate_is_refused(
    serve: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = serve(ok, make_certificate())
    origin = netguard.parse_origin(server.url, allow_http=False)
    monkeypatch.setattr(netguard, "peer_certificate", no_certificate)

    lookup = netguard.look_up_certificate(HOME_NETWORK_AND_LOOPBACK, origin)

    with pytest.raises(Refused, match="didn't present a certificate"):
        asyncio.run(lookup)


def test_a_certificate_without_names_is_described_without_them() -> None:
    from datetime import UTC, datetime, timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "OPNsense.localdomain")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )

    found = netguard.describe_certificate(certificate.public_bytes(serialization.Encoding.DER))

    assert found.names == []
    assert found.subject == "CN=OPNsense.localdomain"


def test_certificates_are_made_for_the_tests_only_in_pem_and_der() -> None:
    certificate: Certificate = make_certificate()

    assert certificate.pem.startswith("-----BEGIN CERTIFICATE-----")
    assert certificate.fingerprint == netguard.fingerprint_of(certificate.der)
