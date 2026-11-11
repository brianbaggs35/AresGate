"""Reading what a service says about itself: what is judged, what is sent and that nothing is
read from a device that is not on the home network."""

import socket
import ssl
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import cache
from typing import cast

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID
from sqlalchemy.orm import Session

from app.agents import fingerprint, probe
from app.integrations import netguard
from tests.test_agents_probe import NOW, device


@cache
def key(bits: int) -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(65537, bits)


def name(common: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common)])


def certificate(
    *,
    ends: datetime = NOW + timedelta(days=365),
    bits: int = 2048,
    own: bool = True,
    curve: bool = False,
) -> x509.Certificate:
    private = ec.generate_private_key(ec.SECP256R1()) if curve else key(bits)
    return (
        x509.CertificateBuilder()
        .subject_name(name("nas"))
        .issuer_name(name("nas") if own else name("a certificate authority"))
        .public_key(private.public_key())
        .serial_number(1)
        .not_valid_before(ends - timedelta(days=700))
        .not_valid_after(ends)
        .sign(private, hashes.SHA256())
    )


class Signed:
    """A certificate as it is, except for how it says it was signed: no library will sign with
    SHA-1 any more, and a device that was made long ago did."""

    def __init__(self, real: x509.Certificate, algorithm: hashes.HashAlgorithm) -> None:
        self.real = real
        self.signature_hash_algorithm = algorithm

    def __getattr__(self, attribute: str) -> object:
        return getattr(self.real, attribute)


def names(found: list[probe.Service]) -> list[str]:
    return [service.name for service in found]


class TestCertificates:
    def test_a_sound_certificate_from_an_authority_has_nothing_said_of_it(self) -> None:
        assert fingerprint.judge_certificate(certificate(own=False), NOW) == []

    def test_a_certificate_that_has_run_out_is_said_to_have(self) -> None:
        [found] = fingerprint.judge_certificate(
            certificate(ends=NOW - timedelta(days=3), own=False), NOW
        )

        assert (found.name, found.severity) == ("Expired certificate", "medium")
        assert "ran out on 2026-11-07" in found.why
        assert found.opens is False

    def test_one_that_is_about_to_is_said_to_be_while_there_is_time(self) -> None:
        [found] = fingerprint.judge_certificate(
            certificate(ends=NOW + timedelta(days=10), own=False), NOW
        )

        assert (found.name, found.severity) == ("Certificate about to expire", "low")
        assert "runs out on 2026-11-20" in found.why

    def test_a_short_key_and_an_old_signature_are_each_said(self) -> None:
        old = Signed(certificate(bits=1024, own=False), hashes.SHA1())  # noqa: S303

        found = fingerprint.judge_certificate(cast("x509.Certificate", old), NOW)

        assert names(found) == ["Weak certificate key", "Weak certificate signature"]
        assert "1024 bits" in found[0].why
        assert "SHA1" in found[1].why

    def test_a_certificate_signed_by_the_device_itself_is_information_only(self) -> None:
        [found] = fingerprint.judge_certificate(certificate(), NOW)

        assert (found.name, found.severity) == ("Self-signed certificate", "info")

    def test_a_key_that_is_not_rsa_is_not_judged_by_its_size(self) -> None:
        assert fingerprint.judge_certificate(certificate(curve=True, own=False), NOW) == []

    def test_what_is_wrong_with_it_comes_before_that_it_is_self_signed(self) -> None:
        found = fingerprint.judge_certificate(certificate(ends=NOW - timedelta(days=1)), NOW)

        assert names(found) == ["Expired certificate", "Self-signed certificate"]


class TestGreetings:
    @pytest.mark.parametrize(
        ("greeting", "name", "severity"),
        [
            ("SSH-1.5-old\n", "SSH protocol 1", "critical"),
            ("SSH-1.3-older\r\n", "SSH protocol 1", "critical"),
            ("SSH-1.99-OpenSSH_3.9\n", "SSH protocol 1 accepted", "high"),
            ("SSH-2.0-OpenSSH_9.6p1\n", "Announces its software", "low"),
            ("220 ProFTPD 1.3.5 Server ready.\r\n", "Announces its software", "low"),
        ],
    )
    def test_what_a_server_says_first_is_judged(
        self, greeting: str, name: str, severity: str
    ) -> None:
        [found] = fingerprint.judge_greeting(greeting)

        assert (found.name, found.severity) == (name, severity)

    def test_a_greeting_that_names_no_version_says_nothing(self) -> None:
        assert fingerprint.judge_greeting("220 mail ESMTP ready\r\n") == []

    def test_no_greeting_says_nothing(self) -> None:
        assert fingerprint.judge_greeting("") == []
        assert fingerprint.judge_greeting("  \n") == []

    def test_what_a_device_sent_is_shown_only_as_printable_text_and_not_at_length(self) -> None:
        [found] = fingerprint.judge_greeting("SSH-2.0-Odd\x00\x1b[31m_1.2 " + "x" * 200)

        assert "\x00" not in found.why
        assert "\x1b" not in found.why
        assert len(found.why) < 250


class TestHeaders:
    def test_a_password_asked_for_in_the_clear_is_said_to_be(self) -> None:
        [found] = fingerprint.judge_headers(
            'HTTP/1.0 401 Unauthorized\r\nWWW-Authenticate: Basic realm="router"'
        )

        assert (found.name, found.severity) == ("Password sent in the clear", "medium")

    def test_a_server_that_names_its_software_and_version_is_said_to(self) -> None:
        found = fingerprint.judge_headers(
            "HTTP/1.1 200 OK\r\nServer: Apache/2.4.7 (Ubuntu)\r\nX-Powered-By: PHP/5.5.9"
        )

        assert names(found) == ["Announces its software"] * 2
        assert "Apache/2.4.7 (Ubuntu)" in found[0].why
        assert "PHP/5.5.9" in found[1].why

    def test_a_401_that_is_not_basic_and_a_server_with_no_version_say_nothing(self) -> None:
        assert fingerprint.judge_headers("HTTP/1.1 401 No\r\nWWW-Authenticate: Digest") == []
        assert fingerprint.judge_headers("HTTP/1.1 200 OK\r\nServer: nginx") == []

    def test_a_reply_that_is_not_http_says_nothing(self) -> None:
        assert fingerprint.judge_headers("") == []
        assert fingerprint.judge_headers("garbage") == []


def serve(reply: bytes, *, reads: bool = False) -> tuple[int, list[bytes], threading.Thread]:
    """A server on this machine that says ``reply`` to whoever connects, once, and what it was
    sent."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(5)
    received: list[bytes] = []

    def answer() -> None:
        with listener:
            try:
                connection, _ = listener.accept()
            except OSError:  # pragma: no cover - only if the test never connects
                return
            with connection:
                connection.settimeout(2)
                if reads:
                    received.append(connection.recv(1000))
                connection.sendall(reply)

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    return listener.getsockname()[1], received, thread


class TestLooking:
    def test_an_ssh_server_is_listened_to_and_nothing_is_sent_to_it(self) -> None:
        port, received, thread = serve(b"SSH-2.0-OpenSSH_9.6p1\r\n")

        found = fingerprint.read_greeting("127.0.0.1", port, 2.0)

        thread.join(5)
        assert names(found) == ["Announces its software"]
        assert received == []

    def test_a_web_server_is_sent_one_head_and_no_login(self) -> None:
        port, received, thread = serve(
            b"HTTP/1.0 200 OK\r\nServer: lighttpd/1.4.35\r\n\r\nbody", reads=True
        )

        found = fingerprint.read_headers("127.0.0.1", port, 2.0)

        thread.join(5)
        assert names(found) == ["Announces its software"]
        [request] = received
        assert request.startswith(b"HEAD / HTTP/1.0\r\n")
        assert b"User-Agent: AresGate" in request
        assert b"Authorization" not in request

    def test_a_certificate_is_read_and_judged_as_of_now(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pem = certificate(ends=NOW - timedelta(days=1), own=False).public_bytes(
            serialization.Encoding.PEM
        )

        def served(address: tuple[str, int], timeout: float) -> str:
            return pem.decode()

        monkeypatch.setattr(ssl, "get_server_certificate", served)

        assert names(fingerprint.read_certificate("192.168.1.5", 443, 2.0, NOW)) == [
            "Expired certificate"
        ]

    def test_each_port_is_read_the_way_its_service_speaks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        said: list[str] = []

        def speaking(kind: str) -> Callable[..., list[probe.Service]]:
            def read(*args: object) -> list[probe.Service]:
                said.append(kind)
                return []

            return read

        monkeypatch.setattr(fingerprint, "read_certificate", speaking("certificate"))
        monkeypatch.setattr(fingerprint, "read_greeting", speaking("greeting"))
        monkeypatch.setattr(fingerprint, "read_headers", speaking("headers"))

        for port in (443, 22, 80):
            fingerprint.look("192.168.1.5", port, 1.0)

        assert said == ["certificate", "greeting", "headers"]

    @pytest.mark.parametrize("kind", ["CERTIFICATES", "GREETINGS", "WEB"])
    def test_a_service_that_does_not_answer_has_nothing_said_of_it(
        self, kind: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with socket.socket() as spare:
            spare.bind(("127.0.0.1", 0))
            port = spare.getsockname()[1]
        # A port nothing listens on, read as each kind of service in turn. The ports a machine
        # really answers on (an SSH server runs on the build machines) are not used.
        monkeypatch.setattr(fingerprint, kind, frozenset({port}))
        for other in {"CERTIFICATES", "GREETINGS", "WEB"} - {kind}:
            monkeypatch.setattr(fingerprint, other, frozenset[int]())

        assert fingerprint.look("127.0.0.1", port, 0.5) == []

    def test_a_reply_that_is_not_a_certificate_has_nothing_said_of_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:

        def served(address: tuple[str, int], timeout: float) -> str:
            return "not pem"

        monkeypatch.setattr(ssl, "get_server_certificate", served)

        assert fingerprint.look("192.168.1.5", 443, 1.0) == []


class TestScanning:
    def test_what_each_device_says_is_gathered_the_most_serious_first(
        self, session: Session
    ) -> None:
        device(session, 1, "192.168.1.10", name="nas")
        device(session, 2, "192.168.1.11")
        asked: list[tuple[str, int]] = []
        weak = probe.Service("Weak certificate key", "medium", "Short.", opens=False)
        loud = probe.Service("SSH protocol 1", "critical", "Broken.", opens=False)

        def read(address: str, port: int, timeout: float) -> list[probe.Service]:
            asked.append((address, port))
            return {("192.168.1.10", 443): [weak], ("192.168.1.11", 22): [loud]}.get(
                (address, port), []
            )

        found = fingerprint.scan(session, NOW, read=read)

        assert found.tested == 2
        assert len(asked) == 2 * len(fingerprint.PORTS)
        assert [(hit.target.address, hit.port, hit.service.name) for hit in found.hits] == [
            ("192.168.1.11", 22, "SSH protocol 1"),
            ("192.168.1.10", 443, "Weak certificate key"),
        ]
        assert probe.line(found.hits[0]) == "SSH protocol 1 on 192.168.1.11, port 22. Broken."
        assert found.hits[1].headline == "Weak certificate key on nas (192.168.1.10), port 443"
        assert fingerprint.summary(found) == "read the services of 2 devices, 2 things to know"

    def test_only_the_ports_asked_for_are_read(self, session: Session) -> None:
        device(session, 1, "192.168.1.10")
        asked: list[int] = []

        def read(address: str, port: int, timeout: float) -> list[probe.Service]:
            asked.append(port)
            return []

        found = fingerprint.scan(session, NOW, ports=(443,), read=read)

        assert asked == [443]
        assert found.hits == []
        assert fingerprint.summary(found) == "read the services of 1 device, nothing worth saying"

    def test_one_thing_is_not_plural(self, session: Session) -> None:
        device(session, 1, "192.168.1.10")
        said = probe.Service("Self-signed certificate", "info", "Itself.", opens=False)

        found = fingerprint.scan(
            session, NOW, ports=(443,), read=lambda address, port, timeout: [said]
        )

        assert fingerprint.summary(found) == "read the services of 1 device, 1 thing to know"

    def test_nothing_is_read_past_the_policy(self, session: Session) -> None:
        device(session, 1, "127.0.0.1")
        asked: list[str] = []

        def read(address: str, port: int, timeout: float) -> list[probe.Service]:
            asked.append(address)
            return []

        fingerprint.scan(session, NOW, read=read)
        assert asked == []

        fingerprint.scan(session, NOW, policy=netguard.HOME_NETWORK_AND_LOOPBACK, read=read)
        assert set(asked) == {"127.0.0.1"}


def test_an_open_port_is_worded_as_one_and_what_a_service_says_is_not() -> None:
    target = probe.Target(1, "camera", "192.168.1.5")

    opened = probe.Hit(target, 23, probe.PORTS[23])
    said = probe.Hit(target, 443, probe.Service("Expired certificate", "medium", "Old.", False))

    assert opened.headline == "Telnet is open on camera (192.168.1.5)"
    assert said.headline == "Expired certificate on camera (192.168.1.5), port 443"
