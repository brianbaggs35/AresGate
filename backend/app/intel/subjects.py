"""What may be searched for by hand: an internet address, a domain or a web address, and the
refusals for everything else.

Nothing on the home's own network is sent to a service. A name is judged by its text alone:
AresGate never looks a name up in DNS, so a search can't reach a device on the home network either.
"""

import string
from dataclasses import dataclass
from hashlib import sha256
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

type Address = IPv4Address | IPv6Address
type Kind = Literal["ip", "domain", "url"]

# As long as the longest web address a browser takes, which is the longest thing that is searched.
MAX_LENGTH = 2048
MAX_LABEL = 63
MAX_NAME = 253
# Top-level names that only mean something on a network of one's own, or are kept for tests and
# documentation: nothing on the internet has one of them.
INTERNAL_TLDS = frozenset(
    {
        "arpa",
        "corp",
        "example",
        "home",
        "internal",
        "intranet",
        "invalid",
        "lan",
        "local",
        "localdomain",
        "localhost",
        "private",
        "test",
    }
)
LETTERS = frozenset(string.ascii_letters + string.digits + "-")

EMPTY = "Enter an IP address, a domain or a web address that starts with https://."
TOO_LONG = f"Enter at most {MAX_LENGTH} characters."
MALFORMED = "That isn't an IP address, a domain or a web address that starts with https://."
CREDENTIALS = "A web address with a username or password isn't sent to VirusTotal."


class Refusal(ValueError):
    """Why a search isn't sent: what is wrong with it, in words for the person searching."""


@dataclass(frozen=True)
class Subject:
    """What a search asks about, as it is shown and as it is sent."""

    kind: Kind
    # The address as it is written, or the domain, or the web address without its fragment.
    text: str
    # What is looked up in the service: the address, the domain, or a web address's host.
    host: str
    # The internet address, for an address, or for a web address whose host is one.
    address: Address | None

    def recorded(self) -> tuple[Address | None, str | None]:
        """What of the search is kept with its lookup: the address for an address, else the host.
        A web address keeps only its host, not the rest of it."""
        if self.kind == "ip":
            return self.address, None
        return None, self.host

    @property
    def key(self) -> str:
        """What the subject's answer is kept under: its address or domain as text, and for a web
        address the hash of its text, so that the web address itself is kept nowhere."""
        return url_key(self.text) if self.kind == "url" else self.text


def of_address(address: Address) -> Subject:
    """The subject of a lookup about one internet address."""
    return Subject(kind="ip", text=str(address), host=str(address), address=address)


def url_key(url: str) -> str:
    """The identifier of a web address, which VirusTotal uses too: the SHA-256 of its text."""
    return sha256(url.encode()).hexdigest()


def parse(text: str) -> Subject:
    """What the text asks about, or a ``Refusal`` saying why it isn't sent."""
    cleaned = text.strip()
    if not cleaned:
        raise Refusal(EMPTY)
    if len(cleaned) > MAX_LENGTH:
        raise Refusal(TOO_LONG)
    if not cleaned.isprintable() or any(char.isspace() for char in cleaned):
        raise Refusal(MALFORMED)
    if cleaned.lower().startswith(("http://", "https://")):
        return _web_address(cleaned)
    name, address = _host(cleaned)
    if address is not None:
        return of_address(address)
    return Subject(kind="domain", text=name, host=name, address=None)


def _host(text: str) -> tuple[str, Address | None]:
    """The host a text names, and its address if it is one. A name is returned as it is kept."""
    try:
        address = ip_address(text)
    except ValueError:
        return _domain(text), None
    if address.is_multicast or not address.is_global:
        raise Refusal(f"{address} isn't a public internet address, so it isn't sent to VirusTotal.")
    return str(address), address


def _domain(text: str) -> str:
    try:
        name = text.lower().rstrip(".").encode("idna").decode("ascii")
    except UnicodeError as error:
        raise Refusal(MALFORMED) from error
    labels = name.split(".")
    tld = labels[-1]
    if (
        len(name) > MAX_NAME
        or not all(_label_ok(label) for label in labels)
        or not ((tld.isalpha() and len(tld) >= 2) or tld.startswith("xn--"))
    ):
        raise Refusal(MALFORMED)
    if len(labels) < 2 or tld in INTERNAL_TLDS:
        raise Refusal(f"{name} is a name on your own network, so it isn't sent to VirusTotal.")
    return name


def _label_ok(label: str) -> bool:
    return (
        0 < len(label) <= MAX_LABEL
        and set(label) <= LETTERS
        and not label.startswith("-")
        and not label.endswith("-")
    )


def _web_address(text: str) -> Subject:
    try:
        parts = urlsplit(text)
        host, _port = parts.hostname, parts.port
    except ValueError as error:
        raise Refusal(MALFORMED) from error
    if parts.username is not None or parts.password is not None:
        raise Refusal(CREDENTIALS)
    if not host:
        raise Refusal(MALFORMED)
    name, address = _host(host)
    # The fragment never leaves the page, so it is left out of what is sent.
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    return Subject(kind="url", text=url, host=name, address=address)
