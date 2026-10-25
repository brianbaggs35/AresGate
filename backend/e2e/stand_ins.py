"""Web servers on this machine that answer like the systems AresGate connects to, with or without
TLS. The backend's tests use them to make real connections, and the Playwright tests start them
through the harness (``/api/__test__/stand-ins``), so the web app can connect to something.

They are only as faithful as the products' documentation: the paths, the way of signing in and
the shape of the answers that AresGate relies on.
"""

import base64
import json
import ssl
import tempfile
import threading
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.integrations.netguard import fingerprint_of
from app.integrations.registry import OPNSENSE_MODULES


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
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            context.minimum_version = ssl.TLSVersion.TLSv1_3
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


def _json(body: object, status: int = 200) -> Answer:
    return Answer(
        status=status, body=json.dumps(body), headers={"Content-Type": "application/json"}
    )


def _basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def ntopng(token: str) -> Handler:
    """ntopng's REST API with one authentication token. A login it refuses is sent to its login
    page, as ntopng does, not answered with a 401."""

    def handle(seen: Seen) -> Answer:
        if (
            seen.path == "/lua/rest/v2/get/ntopng/interfaces.lua"
            and seen.headers.get("authorization") == f"Token {token}"
        ):
            return _json({"rc": 0, "rsp": [{"ifid": 0, "ifname": "eth0"}]})
        return Answer(status=302, headers={"Location": "/lua/login.lua"})

    return handle


def crowdsec(api_key: str) -> Handler:
    """CrowdSec's local API, which asks for decisions about an address with a bouncer's key."""

    def handle(seen: Seen) -> Answer:
        if seen.path != "/v1/decisions":
            return _json({"message": "not found"}, 404)
        if seen.headers.get("x-api-key") != api_key:
            return _json({"message": "access forbidden"}, 403)
        return Answer(body="null", headers={"Content-Type": "application/json"})

    return handle


def _opnsense_time(zone: timedelta) -> str:
    """The time as OPNsense shows it, which is PHP's ``D M j G:i:s T Y``, in a time zone that is
    ``zone`` ahead of UTC."""
    now = datetime.now(UTC) + zone
    return f"{now:%a %b} {now.day} {now.hour}:{now:%M:%S} XYZ {now:%Y}"


# What the sample firewall log holds: the action, interface, protocol, source address and port,
# destination address and port, and the description of the rule.
_SAMPLE_LINES = (
    ("block", "igb0", "tcp", "198.51.100.7", "51514", "192.0.2.10", "443", "Default deny"),
    ("pass", "igb1", "udp", "192.0.2.20", "40000", "192.0.2.1", "53", "Allow DNS"),
    ("pass", "igb1", "tcp", "192.0.2.21", "40001", "203.0.113.9", "443", "Allow web"),
)


def sample_firewall_log() -> list[dict[str, str]]:
    """Three lines of an OPNsense firewall log from the last half a minute, newest first, in the
    form its API answers with: a block of traffic from outside, then two passes."""
    now = datetime.now(UTC)
    log: list[dict[str, str]] = []
    for number, line in enumerate(_SAMPLE_LINES):
        action, interface, protocol, source, source_port, destination, destination_port, label = (
            line
        )
        log.append(
            {
                "__timestamp__": f"{now - timedelta(seconds=5 * (number + 1)):%Y-%m-%dT%H:%M:%S}",
                "__host__": "fw.home.arpa",
                "__digest__": f"{number:032x}",
                "rid": f"{number:032x}",
                "rulenr": str(number + 1),
                "interface": interface,
                "action": action,
                "dir": "in",
                "ipversion": "4",
                "protonum": "6" if protocol == "tcp" else "17",
                "protoname": protocol,
                "src": source,
                "srcport": source_port,
                "dst": destination,
                "dstport": destination_port,
                "label": label,
            }
        )
    return log


def sample_suricata_alerts() -> list[dict[str, object]]:
    """Two alerts of OPNsense's intrusion detection from the last minute, newest first, in the
    form its API gives them: Suricata's own record with the signature, its number and what was
    done flattened onto it."""
    now = datetime.now(UTC)
    alerts: list[dict[str, object]] = []
    for number, (signature, sid, action, source) in enumerate(
        (
            ("ET SCAN Potential SSH Scan", 2001219, "allowed", "198.51.100.7"),
            ("ET MALWARE Known Bad Checkin", 2024897, "blocked", "203.0.113.50"),
        )
    ):
        moment = now - timedelta(seconds=20 * (number + 1))
        alerts.append(
            {
                "timestamp": f"{moment:%Y-%m-%dT%H:%M:%S.%f}+0000",
                "flow_id": 1000000000000000 + number,
                "in_iface": "igb0",
                "event_type": "alert",
                "src_ip": source,
                "src_port": 51000 + number,
                "dest_ip": "192.0.2.10",
                "dest_port": 22,
                "proto": "TCP",
                "alert": signature,
                "alert_sid": sid,
                "alert_action": action,
                "payload": "c2VjcmV0",
                "filepos": 4096 * (number + 1),
                "fileid": "",
            }
        )
    return alerts


def _rows_asked(body: bytes) -> int:
    """How many rows a search asks for, which OPNsense gives all of (up to 9999) if it isn't
    said."""
    try:
        asked = json.loads(body)["rowCount"]
    except ValueError, KeyError, TypeError:
        return 9999
    return asked if isinstance(asked, int) and asked > 0 else 9999


def opnsense(
    api_key: str,
    api_secret: str,
    services: Collection[str],
    *,
    firewall_log: Sequence[Mapping[str, str]] = (),
    suricata_alerts: Sequence[Mapping[str, object]] = (),
    zone: timedelta = timedelta(0),
) -> Handler:
    """OPNsense's API with one key and secret. The services named are installed and running; the
    others answer 404, as a plugin that isn't installed does. It has a clock in a time zone that
    is ``zone`` ahead of UTC, the lines given in its firewall log, newest first, and, if Suricata
    is installed, the alerts given."""
    expected = _basic(api_key, api_secret)
    paths = {module.path: module.key for module in OPNSENSE_MODULES if module.path}

    def handle(seen: Seen) -> Answer:
        if seen.headers.get("authorization") != expected:
            return _json({"status": 401, "message": "Authentication Failed"}, 401)
        if seen.path == "/api/diagnostics/system/system_information":
            return _json({"name": "fw.home.arpa", "versions": ["OPNsense 25.7.1-amd64"]})
        if seen.path == "/api/diagnostics/system/system_time":
            return _json({"uptime": "1 day, 02:03:04", "datetime": _opnsense_time(zone)})
        if seen.path == "/api/diagnostics/firewall/log":
            limit = parse_qs(urlsplit(seen.target).query).get("limit", ["0"])[0]
            return _json(list(firewall_log)[: int(limit) or None])
        if seen.path == "/api/ids/service/query_alerts" and "suricata" in services:
            # A search is a POST: asked any other way, OPNsense answers with an empty list.
            if seen.method != "POST":
                return _json([])
            rows = list(suricata_alerts)[: _rows_asked(seen.body)]
            return _json({"filters": {}, "rows": rows, "rowCount": len(rows), "current": 1})
        if paths.get(seen.path) in services:
            return _json({"status": "running"})
        return _json({"status": 404, "message": "Not found"}, 404)

    return handle


def zenarmor(api_key: str) -> Handler:
    """Zenarmor's API, with its key as the user name of basic authentication and no password."""
    expected = _basic(api_key, "")

    def handle(seen: Seen) -> Answer:
        if seen.path != "/policies" or seen.headers.get("authorization") != expected:
            return _json({"message": "Unauthorized"}, 401)
        return _json({"policies": []})

    return handle


Kind = Literal["opnsense", "zenarmor", "ntopng", "crowdsec"]


@dataclass(frozen=True)
class Running:
    """A stand-in that is answering."""

    id: str
    kind: Kind
    url: str
    # The SHA-256 fingerprint of its certificate, if it has one, to pin it with.
    fingerprint: str | None


class StandIns:
    """The stand-ins started for a test, so the next test can stop them. OPNsense and Zenarmor
    only speak https, with a certificate they made for themselves, as they do at home."""

    def __init__(self) -> None:
        self._running: dict[str, StubServer] = {}
        self._lock = threading.Lock()

    def start(
        self,
        kind: Kind,
        *,
        token: str = "",
        api_key: str = "",
        api_secret: str = "",
        services: Collection[str] = (),
    ) -> Running:
        handlers: dict[Kind, Handler] = {
            "ntopng": ntopng(token),
            "crowdsec": crowdsec(api_key),
            "opnsense": opnsense(
                api_key,
                api_secret,
                services,
                firewall_log=sample_firewall_log(),
                suricata_alerts=sample_suricata_alerts(),
            ),
            "zenarmor": zenarmor(api_key),
        }
        certificate = make_certificate("fw.home.arpa") if kind in ("opnsense", "zenarmor") else None
        server = StubServer(handlers[kind], certificate)
        identifier = uuid4().hex
        with self._lock:
            self._running[identifier] = server
        return Running(
            id=identifier,
            kind=kind,
            url=server.url,
            fingerprint=certificate.fingerprint if certificate else None,
        )

    def stop_all(self) -> None:
        with self._lock:
            servers = list(self._running.values())
            self._running.clear()
        for server in servers:
            server.stop()
