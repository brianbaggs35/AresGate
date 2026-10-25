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


def sample_system_time() -> dict[str, str]:
    """What OPNsense's dashboard says about the time: how long it has been up, its load averages
    and its clock."""
    return {"uptime": "1 day, 02:03:04", "loadavg": "0.31, 0.30, 0.27", "datetime": ""}


def sample_system_resources() -> dict[str, object]:
    """The memory of a firewall with 8 GiB, three quarters of a gigabyte of it in use."""
    return {"memory": {"total": 8589934592, "used": 805306368, "total_frmt": "8192"}}


def sample_system_disk() -> dict[str, object]:
    """The disk of a firewall with a 120 GB disk, 15% full, and the file systems that aren't on
    it."""
    return {
        "devices": [
            {
                "device": "/dev/gpt/rootfs",
                "type": "ufs",
                "total_bytes": 120_000_000_000,
                "used_bytes": 18_000_000_000,
                "available_bytes": 102_000_000_000,
                "used_pct": 15,
                "mountpoint": "/",
            },
            {"device": "devfs", "type": "devfs", "used_pct": 0, "mountpoint": "/dev"},
        ]
    }


def sample_activity() -> dict[str, object]:
    """What ``top`` says about a firewall that is 4% busy."""
    return {
        "headers": [
            "last pid: 4242;  load averages:  0.31,  0.30,  0.27  up 1+02:03:04    12:00:00",
            "52 threads:   2 running, 50 sleeping",
            "CPU:  2.1% user,  0.0% nice,  1.4% system,  0.5% interrupt, 96.0% idle",
            "Mem: 64M Active, 410M Inact, 805M Wired, 7G Free",
        ],
        "details": [],
    }


def sample_interface_statistics() -> dict[str, object]:
    """The counters of the two interfaces of a firewall, each listed for itself and for its
    address, and of its loopback, which isn't kept."""
    link = {"flags": "0x8843", "mtu": 1500, "network": "<Link#1>"}
    return {
        "statistics": {
            "[WAN] (igb0) / 00:00:5e:00:53:01": {
                **link,
                "name": "igb0",
                "address": "00:00:5e:00:53:01",
                "received-packets": 1_200_000,
                "received-errors": 0,
                "dropped-packets": 3,
                "received-bytes": 900_000_000,
                "sent-packets": 800_000,
                "send-errors": 1,
                "sent-bytes": 120_000_000,
                "collisions": 0,
            },
            "[WAN] (igb0) / 203.0.113.0/24": {
                "name": "igb0",
                "network": "203.0.113.0/24",
                "address": "203.0.113.2",
                "received-packets": 1_100_000,
                "received-bytes": 850_000_000,
                "sent-packets": 700_000,
                "sent-bytes": 100_000_000,
            },
            "[LAN] (igb1) / 00:00:5e:00:53:02": {
                **link,
                "name": "igb1",
                "address": "00:00:5e:00:53:02",
                "received-packets": 700_000,
                "received-errors": 0,
                "dropped-packets": 0,
                "received-bytes": 100_000_000,
                "sent-packets": 1_100_000,
                "send-errors": 0,
                "sent-bytes": 880_000_000,
                "collisions": 0,
            },
            "[lo0] / lo0": {
                "name": "lo0",
                "network": "<Link#3>",
                "address": "lo0",
                "received-bytes": 5_000,
                "sent-bytes": 5_000,
            },
        }
    }


def sample_gateways() -> dict[str, object]:
    """A firewall with one gateway, which is up and answers in a few milliseconds."""
    return {
        "items": [
            {
                "name": "WAN_DHCP",
                "address": "203.0.113.1",
                "status": "none",
                "status_translated": "Online",
                "loss": "0.0 %",
                "delay": "4.2 ms",
                "stddev": "0.6 ms",
                "monitor": "203.0.113.1",
            }
        ],
        "status": "ok",
    }


def sample_arp_table() -> list[dict[str, object]]:
    """The ARP table of a firewall with a laptop (whose address FreeBSD writes without its leading
    zeros), a phone, an address that stopped answering, and its own address, which is permanent."""
    return [
        {
            "mac": "0:11:22:a:b:c",
            "ip": "192.168.1.20",
            "intf": "igb1",
            "intf_description": "LAN",
            "expired": False,
            "expires": 1176,
            "permanent": False,
            "type": "ethernet",
            "manufacturer": "Example Devices Inc.",
            "hostname": "?",
        },
        {
            "mac": "ac:de:48:00:00:02",
            "ip": "192.168.1.21",
            "intf": "igb1",
            "intf_description": "LAN",
            "expired": False,
            "expires": 640,
            "permanent": False,
            "type": "ethernet",
            "manufacturer": "",
            "hostname": "phone.lan",
        },
        {
            "mac": "ac:de:48:00:00:03",
            "ip": "192.168.1.22",
            "intf": "igb1",
            "intf_description": "LAN",
            "expired": True,
            "expires": 0,
            "permanent": False,
            "type": "ethernet",
            "manufacturer": "",
            "hostname": "?",
        },
        {
            "mac": "ac:de:48:00:00:01",
            "ip": "192.168.1.1",
            "intf": "igb1",
            "intf_description": "LAN",
            "expired": False,
            "expires": -1,
            "permanent": True,
            "type": "ethernet",
            "manufacturer": "",
            "hostname": "?",
        },
    ]


def sample_dnsmasq_leases() -> list[dict[str, object]]:
    """Two leases of Dnsmasq: the laptop of the ARP table, which has a name, and a printer that
    has none; and one of an IPv6 client that gave no hardware address."""
    return [
        {
            "address": "192.168.1.20",
            "hwaddr": "00:11:22:0a:0b:0c",
            "hostname": "laptop",
            "mac_info": "Example Devices Inc.",
            "expire": 1_900_000_000,
            "if": "igb1",
            "if_name": "lan",
            "client_id": "01:00:11:22:0a:0b:0c",
            "iaid": "",
            "is_reserved": [],
            "lease_type": "dynamic",
        },
        {
            "address": "192.168.1.30",
            "hwaddr": "f0:ad:4e:00:00:01",
            "hostname": "*",
            "mac_info": "Example Printers Ltd.",
            "expire": 1_900_000_000,
            "if": "igb1",
            "if_name": "lan",
            "client_id": "*",
            "iaid": "",
            "is_reserved": [],
            "lease_type": "dynamic",
        },
        {
            "address": "fd00::1234",
            "hwaddr": "",
            "hostname": "*",
            "mac_info": "",
            "expire": 1_900_000_000,
            "if": "igb1",
            "if_name": "lan",
            "client_id": "00:02:00:00:ab:11:22:33",
            "iaid": "1234",
            "is_reserved": [],
            "lease_type": "dynamic",
        },
    ]


def sample_kea_leases() -> list[dict[str, object]]:
    """Two IPv4 leases of Kea: a camera, and one that ran out and waits to be cleared away."""
    return [
        {
            "address": "192.168.1.40",
            "hwaddr": "00:1a:2b:00:00:01",
            "hostname": "camera.lan.",
            "mac_info": "Example Cameras Corp.",
            "state": 0,
            "valid_lifetime": 3600,
            "expire": 1_900_000_000,
            "if": "igb1",
            "if_name": "lan",
            "is_reserved": [],
            "lease_type": "dynamic",
        },
        {
            "address": "192.168.1.41",
            "hwaddr": "00:1a:2b:00:00:02",
            "hostname": "",
            "mac_info": "Example Cameras Corp.",
            "state": 2,
            "valid_lifetime": 3600,
            "expire": 1_800_000_000,
            "if": "igb1",
            "if_name": "lan",
            "is_reserved": [],
            "lease_type": "dynamic",
        },
    ]


def _lease_search(rows: Sequence[Mapping[str, object]]) -> Answer:
    """What a search of leases answers with."""
    return _json({"total": len(rows), "rowCount": len(rows), "current": 1, "rows": list(rows)})


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
    arp_table: Sequence[Mapping[str, object]] = (),
    dnsmasq_leases: Sequence[Mapping[str, object]] = (),
    kea_leases: Sequence[Mapping[str, object]] = (),
    zone: timedelta = timedelta(0),
) -> Handler:
    """OPNsense's API with one key and secret. The services named are installed and running; the
    others answer 404, as a plugin that isn't installed does. It has a clock in a time zone that
    is ``zone`` ahead of UTC, the lines given in its firewall log, newest first, the entries
    given in its ARP table and, if Suricata, Dnsmasq or Kea is installed, its alerts or leases."""
    expected = _basic(api_key, api_secret)
    paths = {module.path: module.key for module in OPNSENSE_MODULES if module.path}

    def handle(seen: Seen) -> Answer:
        if seen.headers.get("authorization") != expected:
            return _json({"status": 401, "message": "Authentication Failed"}, 401)
        if seen.path == "/api/diagnostics/system/system_information":
            return _json({"name": "fw.home.arpa", "versions": ["OPNsense 25.7.1-amd64"]})
        if seen.path == "/api/diagnostics/system/system_time":
            return _json({**sample_system_time(), "datetime": _opnsense_time(zone)})
        if seen.path == "/api/diagnostics/system/system_resources":
            return _json(sample_system_resources())
        if seen.path == "/api/diagnostics/system/system_disk":
            return _json(sample_system_disk())
        if seen.path == "/api/diagnostics/activity/get_activity":
            return _json(sample_activity())
        if seen.path == "/api/diagnostics/interface/get_interface_statistics":
            return _json(sample_interface_statistics())
        if seen.path == "/api/routes/gateway/status":
            return _json(sample_gateways())
        if seen.path == "/api/diagnostics/interface/get_arp":
            return _json(list(arp_table))
        if seen.path == "/api/dnsmasq/leases/search" and "dnsmasq" in services:
            return _lease_search(dnsmasq_leases)
        if seen.path == "/api/kea/leases4/search" and "kea" in services:
            return _lease_search(kea_leases)
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
                arp_table=sample_arp_table(),
                dnsmasq_leases=sample_dnsmasq_leases(),
                kea_leases=sample_kea_leases(),
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
