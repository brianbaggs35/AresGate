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
from typing import Any, Literal, cast
from urllib.parse import parse_qs, unquote, urlsplit
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


def ntopng(
    token: str,
    hosts: Sequence[Mapping[str, object]] = (),
    interface: Mapping[str, object] | None = None,
    flow_alerts: Sequence[Mapping[str, object]] = (),
    host_alerts: Sequence[Mapping[str, object]] = (),
) -> Handler:
    """ntopng's REST API with one authentication token. A login it refuses is sent to its login
    page, as ntopng does, not answered with a 401, and so is anything it doesn't have. Every
    answer is wrapped as ntopng wraps them, with ``rc`` and ``rsp``. It has one interface, ``0``,
    and gives the hosts of the local network when asked for ``mode=local``, and the alerts that
    began between the times asked for, newest first and no more than ``length``."""

    def handle(seen: Seen) -> Answer:
        if seen.headers.get("authorization") != f"Token {token}":
            return Answer(status=302, headers={"Location": "/lua/login.lua"})
        query = parse_qs(urlsplit(seen.target).query)
        if seen.path == "/lua/rest/v2/get/ntopng/interfaces.lua":
            return _ntopng_answer([{"ifid": 0, "ifname": "eth0"}])
        answers: dict[str, Callable[[], Answer]] = {
            "/lua/rest/v2/get/host/active.lua": lambda: _ntopng_hosts(query, hosts),
            "/lua/rest/v2/get/interface/data.lua": lambda: _ntopng_answer(interface or {}),
            "/lua/rest/v2/get/flow/alert/list.lua": lambda: _ntopng_alerts(query, flow_alerts),
            "/lua/rest/v2/get/host/alert/list.lua": lambda: _ntopng_alerts(query, host_alerts),
        }
        if seen.path not in answers:
            return Answer(status=302, headers={"Location": "/lua/login.lua"})
        if query.get("ifid") != ["0"]:
            return _ntopng_answer({}, "INVALID_INTERFACE", -2)
        return answers[seen.path]()

    return handle


def _ntopng_hosts(
    query: Mapping[str, Sequence[str]], hosts: Sequence[Mapping[str, object]]
) -> Answer:
    local = query.get("mode") == ["local"]
    found = [host for host in hosts if host.get("is_localhost") or not local]
    return _ntopng_answer({"perPage": -1, "currentPage": 0, "data": found})


def _ntopng_answer(rsp: object, rc_str: str = "OK", rc: int = 0, **more: object) -> Answer:
    hr = "Success" if rc == 0 else rc_str
    return _json({"rc": rc, "rc_str": rc_str, "rc_str_hr": hr, "rsp": rsp, **more})


def _ntopng_alerts(
    query: Mapping[str, Sequence[str]], alerts: Sequence[Mapping[str, object]]
) -> Answer:
    begin, end = (int(query.get(key, ["0"])[0]) for key in ("epoch_begin", "epoch_end"))
    found = sorted(
        (alert for alert in alerts if begin <= _ntopng_began(alert) <= end),
        key=_ntopng_began,
        reverse=True,
    )
    records = found[: int(query.get("length", ["100"])[0])]
    return _ntopng_answer(
        {"records": records, "stats": {}},
        draw=0,
        recordsTotal=len(found),
        recordsFiltered=len(found),
    )


def _ntopng_began(alert: Mapping[str, object]) -> int:
    return int(cast("Mapping[str, int]", alert["tstamp"])["value"])


def sample_ntopng_hosts(now: datetime) -> list[dict[str, object]]:
    """Four hosts in the form ntopng's active hosts answer gives them: two devices in the
    broadcast domain, one with a name and one only with an address, a local host behind a router
    (whose MAC address is the router's, so it is no device) and a remote host, which a question
    about the local network leaves out."""

    def host(
        address: str, mac: str, name: str, *, sent: int, received: int, **more: object
    ) -> dict[str, object]:
        return {
            "key": address.replace(".", "__"),
            "ip": address,
            "mac": mac,
            "name": name,
            "vlan": 0,
            "os": 0,
            "country": "",
            "is_blacklisted": False,
            "first_seen": int((now - timedelta(hours=5)).timestamp()),
            "last_seen": int(now.timestamp()),
            "num_alerts": 0,
            "score": {"total": 12, "as_client": 12, "as_server": 0},
            "thpt": {"pps": 3.5, "bps": 8200.0},
            "bytes": {"total": sent + received, "sent": sent, "recvd": received},
            "num_flows": {"total": 6, "as_client": 5, "as_server": 1},
            "is_localhost": True,
            "is_multicast": False,
            "is_broadcast": False,
            "is_broadcast_domain": True,
            **more,
        }

    return [
        host("192.168.1.20", "52:54:00:aa:bb:20", "web1", sent=48_213_907, received=9_120_433),
        host("192.168.1.41", "52:54:00:aa:bb:41", "192.168.1.41", sent=1_204_330, received=88_340),
        host(
            "192.168.2.15",
            "52:54:00:00:00:01",
            "printer [192.168.2.15]",
            sent=5_120,
            received=2_048,
            is_broadcast_domain=False,
        ),
        host(
            "8.241.92.250",
            "52:54:00:00:00:01",
            "8.241.92.250",
            sent=2_322_624,
            received=34_148,
            is_localhost=False,
            is_broadcast_domain=False,
            country="US",
        ),
    ]


def sample_ntopng_interface() -> dict[str, object]:
    """What ntopng's interface data answer holds, as its documentation shows it (the members that
    AresGate reads, with plausible numbers)."""
    return {
        "ifid": "0",
        "ifname": "eth0",
        "speed": 1000,
        "bytes_download": 912_340_221,
        "bytes_upload": 104_220_113,
        "packets_download": 1_204_330,
        "packets_upload": 988_120,
        "drops": 3,
        "local2remote": 84_220_113,
        "remote2local": 902_340_221,
        "num_hosts": 41,
        "num_local_hosts": 18,
        "num_devices": 16,
        "num_flows": 212,
        "engaged_alerts": 2,
        "throughput_bps": 149.56,
    }


def _ntopng_alert(
    now: datetime, minutes: float, row_id: int, severity: int, name: str, **more: object
) -> dict[str, object]:
    began = int((now - timedelta(minutes=minutes)).timestamp())
    return {
        "row_id": str(row_id),
        "tstamp": {"value": began, "label": "just now"},
        "alert_id": {"value": str(10 + row_id), "label": f"<b>{name}</b>"},
        "score": {"value": 100, "label": "100"},
        "severity": {"value": severity, "label": "<i class='fas'></i>"},
        "count": 1,
        "msg": {"name": name, "fullname": f"<b>{name}</b>", "description": f"<b>{name}</b> found"},
        **more,
    }


def sample_ntopng_flow_alerts(now: datetime) -> list[dict[str, object]]:
    """Three alerts for flows, as ntopng lists them: a device talking to a blacklisted address
    and a self-signed certificate, newest first, and one from two hours ago, which a search of
    the last half hour leaves out."""

    def flow(
        minutes: float, row_id: int, severity: int, name: str, client: str, server: str, port: int
    ) -> dict[str, object]:
        return _ntopng_alert(
            now,
            minutes,
            row_id,
            severity,
            name,
            family="flow",
            alert_name=name,
            cli_ip={"value": client, "ip": client, "label": client, "country": ""},
            srv_ip={"value": server, "ip": server, "label": server, "country": "US"},
            cli_port={"value": "51514", "label": ""},
            srv_port={"value": str(port), "label": "https"},
            proto={"value": "6", "label": "TCP"},
            total_bytes=4_096,
        )

    return [
        flow(1, 101, 5, "Blacklisted Flow", "192.168.1.41", "203.0.113.9", 443),
        flow(8, 100, 4, "TLS Certificate Selfsigned", "192.168.1.20", "198.51.100.30", 8443),
        flow(120, 99, 5, "Blacklisted Flow", "192.168.1.41", "203.0.113.10", 443),
    ]


def sample_ntopng_host_alerts(now: datetime) -> list[dict[str, object]]:
    """Two alerts for hosts: one that scanned others, and one that was scanned."""

    def host(minutes: float, row_id: int, name: str, address: str, role: str) -> dict[str, object]:
        return _ntopng_alert(
            now,
            minutes,
            row_id,
            4,
            name,
            family="host",
            alert_name=name,
            ip={"value": address, "label": address, "is_local": True},
            role={"label": role, "value": role},
        )

    return [
        host(4, 52, "Scan Attacker", "192.168.1.41", "attacker"),
        host(6, 51, "Scan Victim", "192.168.1.20", "victim"),
    ]


def crowdsec(api_key: str, decisions: Sequence[Mapping[str, object]] = ()) -> Handler:
    """CrowdSec's local API, with a bouncer's key. A question about one address has no decisions
    to give. One that names the origins it wants is answered with the decisions of those origins,
    as the real API does, and ``null`` when there are none."""

    def handle(seen: Seen) -> Answer:
        if seen.path != "/v1/decisions":
            return _json({"message": "not found"}, 404)
        if seen.headers.get("x-api-key") != api_key:
            return _json({"message": "access forbidden"}, 403)
        origins = parse_qs(urlsplit(seen.target).query).get("origins")
        if origins:
            wanted = origins[0].split(",")
            chosen = [item for item in decisions if item.get("origin") in wanted]
            if chosen:
                return _json(chosen)
        return Answer(body="null", headers={"Content-Type": "application/json"})

    return handle


def sample_crowdsec_decisions() -> list[dict[str, object]]:
    """Five decisions in force, in the form CrowdSec's local API reports them: a scenario that
    fired here banned an address, a ban by hand of a whole range, a captcha for another address
    (the remedy is not always a ban), a ban from the community blocklist, which is not about this
    network, and an address banned by an import from a file."""
    return [
        {
            "id": 101,
            "origin": "crowdsec",
            "type": "ban",
            "scope": "Ip",
            "value": "198.51.100.7",
            "duration": "3h59m12s",
            "scenario": "crowdsecurity/ssh-bf",
            "simulated": False,
        },
        {
            "id": 102,
            "origin": "cscli",
            "type": "ban",
            "scope": "Range",
            "value": "203.0.113.0/24",
            "duration": "23h58m1s",
            "scenario": "manual 'ban' from 'localhost'",
            "simulated": False,
        },
        {
            "id": 103,
            "origin": "crowdsec",
            "type": "captcha",
            "scope": "Ip",
            "value": "192.0.2.77",
            "duration": "1h2m3s",
            "scenario": "crowdsecurity/http-crawl-non_statics",
            "simulated": False,
        },
        {
            "id": 104,
            "origin": "CAPI",
            "type": "ban",
            "scope": "Ip",
            "value": "192.0.2.99",
            "duration": "142h3m",
            "scenario": "crowdsecurity/http-probing",
            "simulated": False,
        },
        {
            "id": 105,
            "origin": "cscli-import",
            "type": "ban",
            "scope": "Ip",
            "value": "192.0.2.150",
            "duration": "167h59m",
            "scenario": "imported from a file",
            "simulated": False,
        },
    ]


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


def anthropic(api_key: str, models: Collection[str] = ()) -> Handler:
    """Anthropic's Messages API: a key in ``x-api-key``, a version header, and an answer of one
    text block with the tokens counted in ``usage``."""

    def handle(seen: Seen) -> Answer:
        if seen.path != "/v1/messages" or seen.method != "POST":
            return _json({"type": "error", "error": {"type": "not_found_error"}}, 404)
        if seen.headers.get("x-api-key") != api_key or "anthropic-version" not in seen.headers:
            return _json({"type": "error", "error": {"type": "authentication_error"}}, 401)
        asked = json.loads(seen.body)
        if asked.get("model") not in models or not isinstance(asked.get("max_tokens"), int):
            return _json({"type": "error", "error": {"type": "not_found_error"}}, 404)
        return _json(
            {
                "id": "msg_stand_in",
                "type": "message",
                "role": "assistant",
                "model": asked["model"],
                "content": [{"type": "text", "text": "OK"}],
                "stop_reason": "max_tokens",
                "usage": {"input_tokens": 14, "output_tokens": 1},
            }
        )

    return handle


def openai(api_key: str, models: Collection[str] = ()) -> Handler:
    """OpenAI's Responses API: a bearer key, at least 16 output tokens asked for, no reasoning
    effort "none" for the models that can't do without, and an answer that says how it ended with
    the tokens counted in ``usage``."""

    def handle(seen: Seen) -> Answer:
        if seen.path != "/v1/responses" or seen.method != "POST":
            return _json({"error": {"type": "invalid_request_error"}}, 404)
        if seen.headers.get("authorization") != f"Bearer {api_key}":
            return _json(
                {"error": {"type": "invalid_request_error", "code": "invalid_api_key"}}, 401
            )
        asked = json.loads(seen.body)
        limit = asked.get("max_output_tokens")
        if asked.get("model") not in models or not isinstance(limit, int) or limit < 16:
            return _json({"error": {"type": "invalid_request_error"}}, 400)
        # Astra and Sol always think, and are refused when asked not to.
        reasoning = cast("dict[str, object]", asked.get("reasoning") or {})
        if reasoning.get("effort") == "none" and asked["model"] in {"gpt-6-astra", "gpt-6.1-sol"}:
            return _json({"error": {"type": "invalid_request_error"}}, 400)
        return _json(
            {
                "id": "resp_stand_in",
                "object": "response",
                "status": "completed",
                "model": asked["model"],
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "OK"}],
                    }
                ],
                "usage": {"input_tokens": 16, "output_tokens": 2, "total_tokens": 18},
            }
        )

    return handle


def ollama(api_key: str = "", models: Collection[str] = (), paid: Collection[str] = ()) -> Handler:
    """Ollama's API: the models it has at ``/api/tags`` and an answer from ``/api/chat``. With a
    key (Ollama's cloud) a bearer key is needed, and without one (an Ollama at home) none is.
    The ``paid`` models are listed but answer 402, as a cloud model does for a plan without it."""

    def handle(seen: Seen) -> Answer:
        if api_key and seen.headers.get("authorization") != f"Bearer {api_key}":
            return _json({"error": "unauthorized"}, 401)
        if seen.path == "/api/tags" and seen.method == "GET":
            return _json(
                {
                    "models": [
                        {
                            "name": name,
                            "model": name,
                            "modified_at": "2026-10-01T12:00:00Z",
                            "size": 4_700_000_000,
                            "details": {
                                "format": "gguf",
                                "family": name.split(":")[0],
                                "parameter_size": "8.0B",
                                "quantization_level": "Q4_K_M",
                            },
                        }
                        for name in sorted(models)
                    ]
                }
            )
        if seen.path == "/api/chat" and seen.method == "POST":
            asked = json.loads(seen.body)
            if asked.get("model") not in models:
                return _json({"error": f"model '{asked.get('model')}' not found"}, 404)
            if asked["model"] in paid:
                return _json({"error": "this model requires a subscription"}, 402)
            return _json(
                {
                    "model": asked["model"],
                    "message": {"role": "assistant", "content": "OK"},
                    "done": True,
                    "done_reason": "length",
                    "prompt_eval_count": 12,
                    "eval_count": 1,
                }
            )
        return _json({"error": "not found"}, 404)

    return handle


def wazuh(
    username: str,
    password: str,
    alerts: Sequence[Mapping[str, object]] = (),
    agents: Sequence[Mapping[str, object]] = (),
) -> Handler:
    """Wazuh's manager API and its indexer in one server, which at home are two on ports of their
    own. Each is told by how a request signs in: the manager gives a token for a user and
    password and then wants it as a bearer, and the indexer wants the user and password on every
    request. It keeps the alerts of ``alerts`` that are newer than the search asks for."""
    token = "eyJhbGciOiJFUzUxMiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhcmVzZ2F0ZSJ9.c3RhbmQtaW4"  # nosec B105: made up
    login = _basic(username, password)

    def handle(seen: Seen) -> Answer:
        credential = seen.headers.get("authorization")
        path = unquote(seen.path)
        if path == "/security/user/authenticate" and seen.method == "POST":
            if credential != login:
                return _json({"title": "Unauthorized", "detail": "Invalid credentials"}, 401)
            return Answer(body=token, headers={"Content-Type": "text/plain"})
        if credential == f"Bearer {token}":
            if path == "/":
                return _json({"data": {"title": "Wazuh App REST API", "api_version": "4.9.2"}})
            if path == "/agents":
                return _wazuh_agents(seen, agents)
        elif credential == login:
            if path == "/":
                return _json(
                    {
                        "name": "node-1",
                        "cluster_name": "wazuh-indexer-cluster",
                        "version": {"number": "7.10.2", "distribution": "opensearch"},
                        "tagline": "The OpenSearch Project: https://opensearch.org/",
                    }
                )
            if path == "/wazuh-alerts-*/_search" and seen.method == "POST":
                return _wazuh_search(seen, alerts)
        else:
            return _json({"title": "Unauthorized", "detail": "Invalid credentials"}, 401)
        return _json({"title": "Not Found", "detail": "No such resource"}, 404)

    return handle


def _wazuh_agents(seen: Seen, agents: Sequence[Mapping[str, object]]) -> Answer:
    query = parse_qs(urlsplit(seen.target).query)
    limit = int(query.get("limit", ["500"])[0])
    selected = query["select"][0].split(",") if "select" in query else None
    items = [
        {key: value for key, value in agent.items() if selected is None or key in selected}
        for agent in agents[:limit]
    ]
    return _json(
        {
            "data": {
                "affected_items": items,
                "total_affected_items": len(agents),
                "total_failed_items": 0,
                "failed_items": [],
            },
            "message": "All selected agents information was returned",
            "error": 0,
        }
    )


def _wazuh_search(seen: Seen, alerts: Sequence[Mapping[str, object]]) -> Answer:
    asked: dict[str, Any] = json.loads(seen.body or b"{}")
    bound = asked.get("query", {}).get("range", {}).get("timestamp", {}).get("gte")
    since = datetime.fromisoformat(bound) if bound else datetime.min.replace(tzinfo=UTC)
    found = sorted(
        (hit for hit in alerts if _alert_time(hit) >= since), key=_alert_time, reverse=True
    )
    return _json(
        {
            "took": 1,
            "timed_out": False,
            "hits": {"max_score": None, "hits": found[: int(asked.get("size", 10))]},
        }
    )


def _alert_time(hit: Mapping[str, object]) -> datetime:
    alert = cast("Mapping[str, object]", hit["_source"])
    return datetime.fromisoformat(str(alert["timestamp"]))


def sample_wazuh_alerts(now: datetime) -> list[dict[str, object]]:
    """Five alerts as the indexer holds them, the way Wazuh's manager writes them: a login by a
    user that doesn't exist, the same address trying again until a rule for that fires, a changed
    file, a routine login, and one from two hours ago, which a search of the last half hour
    leaves out."""

    def at(minutes: float) -> str:
        return (now - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.123+0000")

    web = {"id": "001", "name": "web1", "ip": "192.168.1.20"}
    nas = {"id": "004", "name": "nas", "ip": "192.168.1.30"}
    return [
        {
            "_index": "wazuh-alerts-4.x-2026.10.26",
            "_id": "wz-alert-1",
            "_source": {
                "timestamp": at(2),
                "rule": {
                    "id": "5710",
                    "level": 5,
                    "description": "sshd: Attempt to login using a non-existent user",
                    "groups": ["syslog", "sshd", "authentication_failed"],
                },
                "agent": web,
                "manager": {"name": "wazuh-server"},
                "id": "1761473523.482",
                "full_log": "Oct 26 10:12:03 web1 sshd[811]: Invalid user admin from 198.51.100.7",
                "decoder": {"name": "sshd"},
                "data": {"srcip": "198.51.100.7", "srcport": "51514", "srcuser": "admin"},
                "location": "/var/log/auth.log",
            },
        },
        {
            "_index": "wazuh-alerts-4.x-2026.10.26",
            "_id": "wz-alert-2",
            "_source": {
                "timestamp": at(5),
                "rule": {
                    "id": "5712",
                    "level": 10,
                    "description": "sshd: brute force trying to get access to the system.",
                    "groups": ["syslog", "sshd", "authentication_failures"],
                },
                "agent": web,
                "manager": {"name": "wazuh-server"},
                "id": "1761473403.311",
                "full_log": "Oct 26 10:10:03 web1 sshd[811]: Failed password for invalid user",
                "decoder": {"name": "sshd"},
                "data": {"srcip": "198.51.100.7"},
                "location": "/var/log/auth.log",
            },
        },
        {
            "_index": "wazuh-alerts-4.x-2026.10.26",
            "_id": "wz-alert-3",
            "_source": {
                "timestamp": at(9),
                "rule": {
                    "id": "550",
                    "level": 7,
                    "description": "Integrity checksum changed.",
                    "groups": ["ossec", "syscheck", "syscheck_entry_modified"],
                },
                "agent": web,
                "manager": {"name": "wazuh-server"},
                "id": "1761473163.907",
                "syscheck": {"path": "/etc/passwd", "event": "modified"},
                "decoder": {"name": "syscheck_integrity_changed"},
                "location": "syscheck",
            },
        },
        {
            "_index": "wazuh-alerts-4.x-2026.10.26",
            "_id": "wz-alert-4",
            "_source": {
                "timestamp": at(14),
                "rule": {
                    "id": "5501",
                    "level": 3,
                    "description": "PAM: Login session opened.",
                    "groups": ["pam", "syslog", "authentication_success"],
                },
                "agent": nas,
                "manager": {"name": "wazuh-server"},
                "id": "1761472863.201",
                "decoder": {"name": "pam"},
                "data": {"dstuser": "root"},
                "location": "/var/log/auth.log",
            },
        },
        {
            "_index": "wazuh-alerts-4.x-2026.10.26",
            "_id": "wz-alert-5",
            "_source": {
                "timestamp": at(120),
                "rule": {
                    "id": "5710",
                    "level": 5,
                    "description": "sshd: Attempt to login using a non-existent user",
                    "groups": ["syslog", "sshd", "authentication_failed"],
                },
                "agent": web,
                "manager": {"name": "wazuh-server"},
                "id": "1761466323.100",
                "decoder": {"name": "sshd"},
                "data": {"srcip": "203.0.113.50"},
                "location": "/var/log/auth.log",
            },
        },
    ]


def sample_wazuh_agents(now: datetime) -> list[dict[str, object]]:
    """The manager's list of agents: itself (which is always agent 000), two that are reporting,
    a laptop that stopped two hours ago, and a camera gateway that never connected."""

    def heard(minutes: float) -> str:
        return (now - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    return [
        {"id": "000", "name": "wazuh-server", "ip": "127.0.0.1", "status": "active"},
        {
            "id": "001",
            "name": "web1",
            "ip": "192.168.1.20",
            "status": "active",
            "lastKeepAlive": heard(0.1),
        },
        {
            "id": "002",
            "name": "laptop",
            "ip": "192.168.1.41",
            "status": "disconnected",
            "lastKeepAlive": heard(120),
        },
        {"id": "003", "name": "camera-gw", "ip": "any", "status": "never_connected"},
        {
            "id": "004",
            "name": "nas",
            "ip": "192.168.1.30",
            "status": "active",
            "lastKeepAlive": heard(0.2),
        },
    ]


Kind = Literal[
    "opnsense", "zenarmor", "ntopng", "crowdsec", "wazuh", "anthropic", "openai", "ollama"
]


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
        username: str = "",
        password: str = "",
        models: Collection[str] = (),
        paid: Collection[str] = (),
    ) -> Running:
        now = datetime.now(UTC)
        handlers: dict[Kind, Handler] = {
            "ntopng": ntopng(
                token,
                sample_ntopng_hosts(now),
                sample_ntopng_interface(),
                sample_ntopng_flow_alerts(now),
                sample_ntopng_host_alerts(now),
            ),
            "crowdsec": crowdsec(api_key, sample_crowdsec_decisions()),
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
            "wazuh": wazuh(username, password, sample_wazuh_alerts(now), sample_wazuh_agents(now)),
            "anthropic": anthropic(api_key, models),
            "openai": openai(api_key, models),
            "ollama": ollama(api_key, models, paid),
        }
        names: dict[Kind, str] = {
            "opnsense": "fw.home.arpa",
            "zenarmor": "fw.home.arpa",
            "wazuh": "wazuh.home.arpa",
        }
        certificate = make_certificate(names[kind]) if kind in names else None
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
