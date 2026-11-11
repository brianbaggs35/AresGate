"""Reading what the services on the home network say about themselves.

The exposure scanner (probe.py) asks whether a door is locked. This goes one step further for the
few services that announce themselves to anyone who connects: it reads the certificate a web or
mail server offers, the greeting an SSH or mail server sends and the headers a web server answers
a plain ``HEAD`` with. Nothing is tried that a browser or mail client would not do, no login is
attempted and nothing is changed on the device.

What it reports is only what the service itself said, judged by rules that can be checked: a
certificate that has run out, an SSH server that still speaks protocol 1, a web server that asks
for a password over a connection that anyone on the network can read. It has no list of software
with known flaws, which would be out of date the day it was written; it says what a service
announces so that the owner can look it up, and the AI can say what matters.

It tests the same devices as the exposure scanner, on the same terms (see probe.py): only the
devices AresGate has seen lately, only addresses on the home network, only for an agent the owner
has allowed to and only for a run the owner started.
"""

import re
import socket
import ssl
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Final

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.orm import Session

from app.agents import probe
from app.agents.probe import Hit, Scan, Service
from app.integrations import netguard
from app.integrations.netguard import AddressPolicy
from app.models.base import utcnow

TIMEOUT: Final = 2.0
WORKERS: Final = 16
# How long before a certificate runs out it is worth saying so, and the smallest RSA key that is
# still sound.
EXPIRING_WITHIN: Final = timedelta(days=30)
MIN_RSA_BITS: Final = 2048
# How much of a greeting or of the headers is read, and how long what is said of them may be.
MAX_READ: Final = 2048
MAX_SHOWN: Final = 80

# What each port is read as: a certificate, a greeting the server sends first, or a web page's
# headers. The ports a home network's devices actually answer on.
CERTIFICATES: Final = frozenset({443, 465, 636, 993, 995, 8443})
GREETINGS: Final = frozenset({21, 22, 25})
WEB: Final = frozenset({80, 8000, 8080, 8888})
PORTS: Final = tuple(sorted(CERTIFICATES | GREETINGS | WEB))

VERSION: Final = re.compile(r"\d+\.\d+")

# A reader gives back what a service says wrong or worth knowing, from the address and the port.
Reader = Callable[[str, int, float], list[Service]]


def _service(name: str, severity: str, why: str) -> Service:
    # What is said is about the service, not that its port is open, so it is not phrased as that.
    return Service(name, severity, why, opens=False)


def _shown(text: str) -> str:
    """What a device sent, made safe to show: printable characters only, and not too long."""
    printable = "".join(char if char.isprintable() else " " for char in text)
    return " ".join(printable.split())[:MAX_SHOWN]


# -- what is judged


def judge_certificate(cert: x509.Certificate, now: datetime) -> list[Service]:
    """What is wrong with a certificate a service offers, worst first."""
    found: list[Service] = []
    ends = cert.not_valid_after_utc
    if ends < now:
        found.append(
            _service(
                "Expired certificate",
                "medium",
                f"Its certificate ran out on {ends:%Y-%m-%d}, so browsers and apps warn about it "
                "or refuse it, and people learn to click past warnings.",
            )
        )
    elif ends < now + EXPIRING_WITHIN:
        found.append(
            _service(
                "Certificate about to expire",
                "low",
                f"Its certificate runs out on {ends:%Y-%m-%d}. Renew it before then.",
            )
        )
    key = cert.public_key()
    if isinstance(key, rsa.RSAPublicKey) and key.key_size < MIN_RSA_BITS:
        found.append(
            _service(
                "Weak certificate key",
                "medium",
                f"Its certificate uses an RSA key of {key.key_size} bits; {MIN_RSA_BITS} is the "
                "least that is still sound.",
            )
        )
    if isinstance(cert.signature_hash_algorithm, hashes.MD5 | hashes.SHA1):
        found.append(
            _service(
                "Weak certificate signature",
                "medium",
                f"Its certificate is signed with {cert.signature_hash_algorithm.name.upper()}, "
                "which can be forged.",
            )
        )
    if cert.issuer == cert.subject:
        found.append(
            _service(
                "Self-signed certificate",
                "info",
                "Its certificate is signed by the device itself, as most devices at home are. "
                "Nothing proves who it is, and browsers warn about it.",
            )
        )
    return found


def judge_greeting(text: str) -> list[Service]:
    """What the first line a server sends says: that it still speaks SSH protocol 1, or what
    software and version it announces to anyone who connects."""
    line = _shown(text.splitlines()[0] if text.strip() else "")
    if not line:
        return []
    if line.startswith(("SSH-1.5", "SSH-1.3")):
        return [
            _service(
                "SSH protocol 1",
                "critical",
                f"It greets with “{line}”, so it speaks the first version of SSH, which is "
                "broken and lets a listener take over a session.",
            )
        ]
    if line.startswith("SSH-1.99"):
        return [
            _service(
                "SSH protocol 1 accepted",
                "high",
                f"It greets with “{line}”, which means it accepts the first version of SSH as "
                "well as the second. The first is broken.",
            )
        ]
    if VERSION.search(line):
        return [_announces(line)]
    return []


def _announces(line: str) -> Service:
    return _service(
        "Announces its software",
        "low",
        f"It tells anyone who connects that it is “{line}”. Look that version up to see "
        "whether it has known weaknesses, and update it if so.",
    )


def judge_headers(head: str) -> list[Service]:
    """What a web server's answer to ``HEAD`` says: a password asked for over a connection anyone
    on the network can read, and the software and version it announces."""
    lines = head.splitlines()
    status = lines[0].split() if lines else []
    headers = {
        name.strip().lower(): value.strip()
        for name, _, value in (line.partition(":") for line in lines[1:])
        if value
    }
    found: list[Service] = []
    if (
        len(status) > 1
        and status[1] == "401"
        and "basic" in headers.get("www-authenticate", "").lower()
    ):
        found.append(
            _service(
                "Password sent in the clear",
                "medium",
                "It asks for a password over plain HTTP, so anyone on the network who is "
                "listening can read it. Use its HTTPS address if it has one.",
            )
        )
    for name in ("server", "x-powered-by"):
        value = _shown(headers.get(name, ""))
        if VERSION.search(value):
            found.append(_announces(value))
    return found


# -- what is read


def read_certificate(address: str, port: int, timeout: float, now: datetime) -> list[Service]:
    pem = ssl.get_server_certificate((address, port), timeout=timeout)
    return judge_certificate(x509.load_pem_x509_certificate(pem.encode("ascii")), now)


def read_greeting(address: str, port: int, timeout: float) -> list[Service]:
    with socket.create_connection((address, port), timeout=timeout) as stream:
        stream.settimeout(timeout)
        return judge_greeting(stream.recv(MAX_READ).decode("latin-1"))


def read_headers(address: str, port: int, timeout: float) -> list[Service]:
    request = f"HEAD / HTTP/1.0\r\nHost: {address}\r\nUser-Agent: AresGate\r\n\r\n"
    with socket.create_connection((address, port), timeout=timeout) as stream:
        stream.settimeout(timeout)
        stream.sendall(request.encode("ascii"))
        answer = stream.recv(MAX_READ).decode("latin-1")
    return judge_headers(answer.split("\r\n\r\n")[0])


def look(address: str, port: int, timeout: float) -> list[Service]:
    """What the service on a port says of itself. Nothing is sent but what a browser or a mail
    client sends first, and a service that does not answer, or answers in a way that makes no
    sense, has nothing said of it."""
    try:
        if port in CERTIFICATES:
            return read_certificate(address, port, timeout, utcnow())
        if port in GREETINGS:
            return read_greeting(address, port, timeout)
        return read_headers(address, port, timeout)
    except OSError, ValueError:
        # No answer, a refused connection or a reply that is not a certificate or a header.
        return []


# -- the run


def scan(
    db: Session,
    now: datetime,
    *,
    policy: AddressPolicy = netguard.HOME_NETWORK,
    ports: Sequence[int] = PORTS,
    read: Reader = look,
) -> Scan:
    """Reads each device on each port, a few at a time, and gives back what its services say."""
    chosen, left_out = probe.targets(db, now, policy)
    pairs = [(target, port) for target in chosen for port in ports]

    def read_one(pair: tuple[probe.Target, int]) -> list[Service]:
        return read(pair[0].address, pair[1], TIMEOUT)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        said = list(pool.map(read_one, pairs))
    hits = [
        Hit(target, port, service)
        for (target, port), services in zip(pairs, said, strict=True)
        for service in services
    ]
    hits.sort(
        key=lambda hit: (probe.SEVERITIES.index(hit.service.severity), hit.target.address, hit.port)
    )
    return Scan(len(chosen), left_out, hits)


def summary(found: Scan) -> str:
    """What the reading found, in a few words with no name or address in them."""
    devices = f"{found.tested} device{'' if found.tested == 1 else 's'}"
    if not found.hits:
        return f"read the services of {devices}, nothing worth saying"
    return (
        f"read the services of {devices}, {len(found.hits)} "
        f"thing{'' if len(found.hits) == 1 else 's'} to know"
    )
