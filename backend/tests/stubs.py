"""Web servers on this machine that answer like the systems AresGate connects to, with or without
TLS, for tests that need real connections."""

import ssl
import tempfile
import threading
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path
from typing import Protocol

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.integrations.netguard import fingerprint_of


@dataclass
class Seen:
    """A request the server received."""

    method: str
    target: str
    headers: dict[str, str]
    body: bytes

    @property
    def path(self) -> str:
        return self.target.partition("?")[0]


@dataclass
class Answer:
    status: int = 200
    body: str | bytes = ""
    headers: dict[str, str] = field(default_factory=lambda: {})
    # Close the connection without answering.
    drop: bool = False
    # Wait this long (seconds) before answering.
    delay: float = 0.0


Handler = Callable[[Seen], Answer]


class Serve(Protocol):
    """The ``serve`` fixture: starts a server that answers like an integration."""

    @abstractmethod
    def __call__(self, handler: Handler, certificate: Certificate | None = None) -> StubServer:
        """Starts the server, which is stopped when the test ends."""


@dataclass(frozen=True)
class Certificate:
    pem: str
    key_pem: str
    der: bytes

    @property
    def fingerprint(self) -> str:
        return fingerprint_of(self.der)


def make_certificate(name: str = "localhost", days: int = 30) -> Certificate:
    """A self-signed certificate for localhost and 127.0.0.1."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(name), x509.IPAddress(ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    return Certificate(
        pem=certificate.public_bytes(serialization.Encoding.PEM).decode(),
        key_pem=key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
        der=certificate.public_bytes(serialization.Encoding.DER),
    )


class _Server(ThreadingHTTPServer):
    def handle_error(self, request: object, client_address: object) -> None:
        # A client that doesn't like the certificate hangs up mid-handshake: that's a test, not
        # a problem.
        pass


class StubServer:
    """Answers every request with what ``handler`` says, and keeps what it was asked."""

    def __init__(self, handler: Handler, certificate: Certificate | None = None) -> None:
        self.seen: list[Seen] = []
        self.certificate = certificate
        outer = self

        class Requests(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _answer(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                seen = Seen(
                    self.command,
                    self.path,
                    {name.lower(): value for name, value in self.headers.items()},
                    self.rfile.read(length) if length else b"",
                )
                outer.seen.append(seen)
                answer = handler(seen)
                if answer.delay:
                    threading.Event().wait(answer.delay)
                if answer.drop:
                    self.close_connection = True
                    return
                body = answer.body.encode() if isinstance(answer.body, str) else answer.body
                self.send_response(answer.status)
                self.send_header("Content-Length", str(len(body)))
                for name, value in answer.headers.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = _answer

            def log_message(self, format: str, *args: object) -> None:
                pass

        self._server = _Server(("127.0.0.1", 0), Requests)
        self._server.daemon_threads = True
        self._directory: tempfile.TemporaryDirectory[str] | None = None
        if certificate:
            self._directory = tempfile.TemporaryDirectory()
            chain, key = (
                Path(self._directory.name, "chain.pem"),
                Path(self._directory.name, "key.pem"),
            )
            chain.write_text(certificate.pem)
            key.write_text(certificate.key_pem)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(chain, key)
            self._server.socket = context.wrap_socket(self._server.socket, server_side=True)
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self._thread.start()

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def url(self) -> str:
        return f"{'https' if self.certificate else 'http'}://127.0.0.1:{self.port}"

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(5)
        if self._directory:
            self._directory.cleanup()
