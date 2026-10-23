"""Keeping AresGate's requests on the home network, and knowing who answers them.

An integration's address is typed in by whoever is signed in, and AresGate then sends requests
(carrying an API key) to it. Left unchecked, that is a way to make AresGate call anything its
network can reach, such as a cloud provider's metadata service. So:

- only addresses in the private ranges are reachable (``HOME_NETWORK``), and the cloud metadata
  addresses stay refused even if the ranges are widened;
- the address is looked up once, checked, and the connection is made to that same address, so a
  name that answers differently the second time can't get past the check;
- a certificate is checked against the certificates the computer trusts, or against a certificate
  authority pasted in, or against one pinned fingerprint: it is never skipped. The pinned
  fingerprint is checked before anything is sent, so a key never goes to a system that isn't the
  one pinned.
"""

import asyncio
import hashlib
import hmac
import ipaddress
import socket
import ssl
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from urllib.parse import urlsplit

import httpcore2
import httpx2
from cryptography import x509
from cryptography.hazmat.primitives import serialization

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

MAX_URL = 255
MAX_CA_PEM = 32768
MAX_CA_CERTIFICATES = 10


class Refused(Exception):
    """AresGate won't connect. The message says why, in words for whoever is setting it up."""


def _networks(*cidrs: str) -> tuple[IPNetwork, ...]:
    return tuple(ipaddress.ip_network(cidr) for cidr in cidrs)


def _unmapped(address: IPAddress) -> IPAddress:
    """An IPv4 address written the IPv6 way (``::ffff:10.0.0.1``) is the IPv4 address."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


@dataclass(frozen=True)
class AddressPolicy:
    """Which addresses AresGate may connect to: those in ``allowed``, except any in ``refused``."""

    allowed: tuple[IPNetwork, ...]
    refused: tuple[IPNetwork, ...] = ()

    def allows(self, address: IPAddress) -> bool:
        address = _unmapped(address)
        return any(address in network for network in self.allowed) and not self.refuses(address)

    def refuses(self, address: IPAddress) -> bool:
        """Whether the address is one that stays refused however far ``allowed`` reaches."""
        address = _unmapped(address)
        return any(address in network for network in self.refused)


# What cloud providers answer on to tell a machine about itself, and so what a stolen request
# would most want to reach: AWS, Azure, Google Cloud and others (169.254.169.254), AWS over IPv6
# and Alibaba Cloud.
CLOUD_METADATA = _networks("169.254.0.0/16", "fd00:ec2::/32", "100.100.100.200/32")
# RFC 1918, and the IPv6 unique local addresses. Not loopback, which in a container is the
# container itself, and not link-local or the shared address space ISPs use.
HOME_NETWORK = AddressPolicy(
    allowed=_networks("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"),
    refused=CLOUD_METADATA,
)
# For the test server only: the end-to-end harness points integrations at stand-ins on the same
# machine. The product never uses it.
HOME_NETWORK_AND_LOOPBACK = AddressPolicy(
    allowed=(*HOME_NETWORK.allowed, *_networks("127.0.0.0/8", "::1/128")),
    refused=CLOUD_METADATA,
)


@dataclass(frozen=True)
class Origin:
    """Where an integration is: https://host:port, and nothing after it."""

    scheme: str
    host: str
    port: int

    @property
    def url(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        default = 443 if self.scheme == "https" else 80
        return f"{self.scheme}://{host}" + ("" if self.port == default else f":{self.port}")


def _is_hostname(host: str) -> bool:
    return len(host) <= 253 and all(
        0 < len(label) <= 63
        and label.isascii()
        and label.replace("-", "").isalnum()
        and not label.startswith("-")
        and not label.endswith("-")
        for label in host.split(".")
    )


def parse_origin(url: str, *, allow_http: bool) -> Origin:
    """An address typed in, checked for its shape. Raises ``Refused`` saying what to change.
    Where the host really is isn't looked at here: ``check_reachable`` does that."""
    text = url.strip()
    if len(text) > MAX_URL:
        raise Refused("That address is too long.")
    try:
        parts = urlsplit(text)
        port = parts.port
        host = parts.hostname
    except ValueError as error:
        raise Refused("That isn't a web address. Use the form https://host:port.") from error
    if parts.scheme not in ("https", "http") or not host:
        raise Refused("Start the address with https:// and the host, such as https://192.168.1.1.")
    if parts.scheme == "http" and not allow_http:
        raise Refused("This one is only offered over https://, so that what is sent stays private.")
    if (
        parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in ("", "/")
    ):
        raise Refused("Use only the scheme, host and port, with no user name, path or query.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not _is_hostname(host):
            raise Refused("That isn't a host name or an IP address.") from None
    return Origin(parts.scheme, host, port or (443 if parts.scheme == "https" else 80))


class NotFound(Refused):
    pass


def lookup(host: str, port: int) -> list[IPAddress]:
    """Where a name or address leads, without repeats."""
    try:
        found = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise NotFound(f"Couldn't find {host}. Check the address and that DNS knows it.") from error
    return _addresses(found)


async def lookup_async(host: str, port: int) -> list[IPAddress]:
    try:
        found = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise NotFound(f"Couldn't find {host}. Check the address and that DNS knows it.") from error
    return _addresses(found)


def _addresses(found: Iterable[tuple[object, ...]]) -> list[IPAddress]:
    seen: dict[IPAddress, None] = {}
    for item in found:
        sockaddr = item[4]
        if isinstance(sockaddr, tuple) and isinstance(sockaddr[0], str):
            # An IPv6 address can come with a "%interface" on the end, which isn't part of it.
            seen[ipaddress.ip_address(sockaddr[0].partition("%")[0])] = None
    return list(seen)


def allowed_addresses(
    policy: AddressPolicy, host: str, addresses: list[IPAddress]
) -> list[IPAddress]:
    """The addresses, if every one is allowed. A name that leads somewhere that isn't allowed is
    refused outright, even when it also leads somewhere that is."""
    for address in addresses:
        if not policy.allows(address):
            # An address that was typed in is not "at" itself.
            subject = f"{address}" if host == str(address) else f"{host} is at {address}, which"
            reason = (
                "is in a range cloud providers use for their metadata services"
                if policy.refuses(address)
                else "isn't a private network address"
            )
            raise Refused(
                f"{subject} {reason}, so AresGate won't connect to it. Integrations have to be "
                "on your own network."
            )
    return addresses


def check_reachable(policy: AddressPolicy, origin: Origin) -> None:
    """Refuses an address that leads outside the private ranges, or leads nowhere."""
    allowed_addresses(policy, origin.host, lookup(origin.host, origin.port))


def _with_colons(digits: str) -> str:
    return ":".join(digits[index : index + 2] for index in range(0, len(digits), 2))


def fingerprint_of(der: bytes) -> str:
    """A certificate's SHA-256 fingerprint the way OPNsense, browsers and openssl show it."""
    return _with_colons(hashlib.sha256(der).hexdigest().upper())


def normalize_fingerprint(text: str) -> str | None:
    """A SHA-256 fingerprint typed or pasted in any usual form (colons, spaces, either case),
    in the one form AresGate keeps. None if it isn't one."""
    digits = "".join(character for character in text if character not in ": -\t").upper()
    if len(digits) != 64 or any(character not in "0123456789ABCDEF" for character in digits):
        return None
    return _with_colons(digits)


def clean_ca_pem(text: str) -> str:
    """Certificate authority certificates pasted in, checked and written out in one form.
    Raises ``ValueError`` saying what is wrong."""
    if len(text) > MAX_CA_PEM:
        raise ValueError("That is too long to be a certificate.")
    if "PRIVATE KEY" in text:
        raise ValueError(
            "That includes a private key. Paste only the certificate, the part between "
            "BEGIN CERTIFICATE and END CERTIFICATE."
        )
    try:
        certificates = x509.load_pem_x509_certificates(text.encode())
    except ValueError as error:
        raise ValueError(
            "That isn't a certificate in PEM form, the text that starts with "
            "-----BEGIN CERTIFICATE-----."
        ) from error
    if len(certificates) > MAX_CA_CERTIFICATES:
        raise ValueError(f"Paste at most {MAX_CA_CERTIFICATES} certificates.")
    return "".join(
        certificate.public_bytes(serialization.Encoding.PEM).decode()
        for certificate in certificates
    )


def _unverified_context() -> ssl.SSLContext:
    """A context that accepts any certificate. Only for the two places that check it some other
    way: looking at what a system presents so a person can decide to trust it, and a pinned
    fingerprint, which is compared before anything is sent."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def tls_context(mode: str, ca_pem: str | None) -> ssl.SSLContext:
    """How to check who answers: the certificates the computer trusts, or only the certificate
    authority pasted in. (A pinned fingerprint is checked by ``GuardedBackend`` instead.)"""
    if mode == "pinned":
        return _unverified_context()
    context = ssl.create_default_context(cadata=ca_pem if mode == "ca" else None)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def peer_certificate(stream: httpcore2.AsyncNetworkStream) -> bytes | None:
    """The certificate the other end presented (DER), once the connection is encrypted."""
    ssl_object = stream.get_extra_info("ssl_object")
    return cast("bytes | None", ssl_object.getpeercert(binary_form=True)) if ssl_object else None


class _PinnedStream(httpcore2.AsyncNetworkStream):
    """A connection that, once it is encrypted, only carries on if the system at the other end
    presented the pinned certificate."""

    def __init__(self, stream: httpcore2.AsyncNetworkStream, pin: str) -> None:
        self._stream = stream
        self._pin = pin

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return await self._stream.read(max_bytes, timeout)

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        await self._stream.write(buffer, timeout)

    async def aclose(self) -> None:
        await self._stream.aclose()

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        secured = await self._stream.start_tls(ssl_context, server_hostname, timeout)
        der = peer_certificate(secured)
        presented = fingerprint_of(der) if der else "unknown"
        if not hmac.compare_digest(presented, self._pin):
            await secured.aclose()
            raise Refused(
                f"The certificate it presented isn't the pinned one. Its fingerprint is "
                f"{presented}. If the certificate was renewed, pin the new one."
            )
        return secured

    def get_extra_info(self, info: str) -> object:
        return self._stream.get_extra_info(info)


class GuardedBackend(httpcore2.AsyncNetworkBackend):
    """Opens connections only to allowed addresses, to the address it looked up and checked,
    and, given a pinned fingerprint, only carries on with a system that presents that
    certificate."""

    def __init__(self, policy: AddressPolicy, pin: str | None = None) -> None:
        self._policy = policy
        self._pin = pin
        # httpcore2 declares AnyIOBackend twice, for when anyio is missing, and type checkers pick
        # the stand-in.
        self._inner = cast("httpcore2.AsyncNetworkBackend", httpcore2.AnyIOBackend())

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        addresses = allowed_addresses(self._policy, host, await lookup_async(host, port))
        failure: Exception | None = None
        for address in addresses:
            try:
                stream = await self._inner.connect_tcp(
                    str(address), port, timeout, local_address, socket_options
                )
            except (httpcore2.ConnectError, httpcore2.ConnectTimeout) as error:
                failure = error
                continue
            return _PinnedStream(stream, self._pin) if self._pin else stream
        raise failure or Refused(f"Couldn't connect to {host}.")


class GuardedTransport(httpx2.AsyncHTTPTransport):
    """An HTTP transport that connects through a ``GuardedBackend``."""

    def __init__(self, ssl_context: ssl.SSLContext, backend: httpcore2.AsyncNetworkBackend) -> None:
        super().__init__(verify=ssl_context)
        self._pool = httpcore2.AsyncConnectionPool(
            ssl_context=ssl_context,
            network_backend=backend,
            max_connections=4,
            max_keepalive_connections=2,
            keepalive_expiry=30.0,
        )


@dataclass(frozen=True)
class CertificateInfo:
    """What a system presented when asked, for a person to compare with what it shows itself."""

    fingerprint: str
    subject: str
    issuer: str
    not_before: datetime
    not_after: datetime
    names: list[str]


def describe_certificate(der: bytes) -> CertificateInfo:
    certificate = x509.load_der_x509_certificate(der)
    try:
        alternative = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        names = [str(name) for name in alternative.value.get_values_for_type(x509.DNSName)]
        names += [str(name) for name in alternative.value.get_values_for_type(x509.IPAddress)]
    except x509.ExtensionNotFound:
        names = []
    return CertificateInfo(
        fingerprint=fingerprint_of(der),
        subject=certificate.subject.rfc4514_string()[:200],
        issuer=certificate.issuer.rfc4514_string()[:200],
        not_before=certificate.not_valid_before_utc.astimezone(UTC),
        not_after=certificate.not_valid_after_utc.astimezone(UTC),
        names=names[:20],
    )


async def look_up_certificate(
    policy: AddressPolicy, origin: Origin, timeout: float = 10.0
) -> CertificateInfo:
    """Connects, takes the certificate the system presents and hangs up, without sending
    anything. Whatever is presented is accepted, because this is how someone gets to see it and
    decide whether to trust it."""
    where = f"{origin.host}:{origin.port}"
    try:
        stream = await GuardedBackend(policy).connect_tcp(origin.host, origin.port, timeout)
        secured = await stream.start_tls(_unverified_context(), origin.host, timeout)
    except httpcore2.ConnectTimeout as error:
        raise Refused(f"{where} didn't answer in time.") from error
    except httpcore2.ConnectError as error:
        raise Refused(f"Couldn't make a secure connection to {where}.") from error
    try:
        der = peer_certificate(secured)
    finally:
        await secured.aclose()
    if der is None:
        raise Refused(f"{origin.host} didn't present a certificate.")
    return describe_certificate(der)
