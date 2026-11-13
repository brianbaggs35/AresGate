"""Alerts by email: the mail server to send through, and the sending.

Email is a destination like a Discord channel, and what it is told is decided by the same rules, so
a message is built once, in the form Discord takes (see ``app.alerts.message``), and ``render``
turns that into an email: the title is the subject, and the description and fields are the text,
with Discord's bold and links written out as plain words.

The mail server is one the owner runs or rents (their own relay, or their email provider's). It is
set once for every email destination. Its password is a secret, sealed in the credential store
like an integration's (see ``app.security.credential_store``): this module is handed it in the
clear only to sign in, and no message, log line or error here ever holds it.

A connection that signs in is made only over an encrypted one: STARTTLS or SSL, with the server's
certificate checked against the system's authorities. A server on the owner's own network that has
no encryption can be used without signing in. The server's address is checked before connecting
(``SERVER_POLICY``): it may be on the home network or on the internet, but not this machine, a
link-local address or a cloud provider's metadata service.
"""

import asyncio
import html
import ipaddress
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Final, cast

from app.alerts.discord import Sent
from app.alerts.discord import message as discord_message
from app.integrations import netguard
from app.models.alerts import SMTP_SECURITIES

# What the page offers when a security is chosen: the port that is usual for it.
DEFAULT_PORTS: Final = {"starttls": 587, "ssl": 465, "none": 25}
# A server that doesn't answer in this long is taken as unreachable.
TIMEOUT: Final = 20.0
MAX_HOST: Final = 253
MAX_ADDRESS: Final = 254
MAX_USERNAME: Final = 254
MAX_PASSWORD: Final = 1024
MAX_SUBJECT: Final = 150
# What the mail's subject begins with, so that it can be filtered.
SUBJECT_PREFIX: Final = "[AresGate] "

# Everything but the machine itself and what is never a mail server: loopback, link-local, the
# unspecified and multicast ranges and cloud metadata. (The home network and the internet are
# both fine: a relay may be either.)
SERVER_POLICY: Final = netguard.AddressPolicy(
    allowed=(ipaddress.ip_network("0.0.0.0/0"), ipaddress.ip_network("::/0")),
    refused=(
        *netguard.THIS_COMPUTER,
        *(ipaddress.ip_network(each) for each in ("0.0.0.0/8", "::/128", "fe80::/10", "ff00::/8")),
        # Multicast and the reserved addresses above it, as (address, prefix length).
        ipaddress.IPv4Network((0xE0000000, 3)),
        # Cloud metadata also holds the IPv4 link-local range.
        *netguard.CLOUD_METADATA,
    ),
    problem="isn't a mail server's address",
    advice="Use your mail provider's server, or one on your own network.",
)

_HOST: Final = re.compile(
    r"^(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)
_ADDRESS: Final = re.compile(r"^[^\s@<>()\[\],;:\\\"']{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}$")
_CONTROL: Final = re.compile(r"[\x00-\x1f\x7f]")
_MARKDOWN: Final = re.compile(r"\*\*|__|`")
_LINK: Final = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


class InvalidSettings(ValueError):
    """A setting that can't be used. ``field`` is the one at fault and the message says what to
    change; it never repeats a password."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class Server:
    """The mail server to send through, with its password in the clear. Only the sending code is
    given one."""

    host: str
    port: int
    security: str
    username: str | None
    password: str | None
    sender: str

    def __repr__(self) -> str:
        return f"Server(host={self.host!r}, port={self.port}, security={self.security!r})"


@dataclass(frozen=True)
class Mailbox:
    """Where one email destination's messages go: through which server, and to whom."""

    server: Server
    recipient: str


def check_address(text: str, field: str) -> str:
    """An email address, checked. Raises ``InvalidSettings``."""
    address = text.strip()
    if not address:
        raise InvalidSettings(field, "Enter an email address.")
    if len(address) > MAX_ADDRESS or not _ADDRESS.fullmatch(address):
        raise InvalidSettings(
            field, "That doesn't look like an email address, such as you@example.com."
        )
    return address


def check_server(
    host: str, port: int, security: str, username: str | None, sender: str, *, has_password: bool
) -> tuple[str, str | None, str]:
    """The settings of a mail server, checked. Returns the host, the user name (None when there is
    none) and the sender, cleaned. Raises ``InvalidSettings``."""
    name = host.strip().lower().rstrip(".")
    if not name or len(name) > MAX_HOST or not _HOST.fullmatch(name):
        raise InvalidSettings("host", "Enter the mail server's name, such as smtp.example.com.")
    if not 1 <= port <= 65535:
        raise InvalidSettings("port", "The port is a number from 1 to 65535.")
    if security not in SMTP_SECURITIES:
        raise InvalidSettings("security", "Choose STARTTLS, SSL or none.")
    user = (username or "").strip() or None
    if user is not None and (len(user) > MAX_USERNAME or _CONTROL.search(user)):
        raise InvalidSettings("username", "That user name can't be used.")
    if (user is not None or has_password) and security == "none":
        raise InvalidSettings(
            "security",
            "A user name and password are only sent over an encrypted connection. Choose "
            "STARTTLS or SSL, or leave them out for a server that needs none.",
        )
    if has_password and user is None:
        raise InvalidSettings("username", "A password needs the user name it belongs to.")
    return name, user, check_address(sender, "sender")


def check_password(password: str) -> str:
    """A password, checked for what can't go in a sign-in. Raises ``InvalidSettings``."""
    if not password or len(password) > MAX_PASSWORD or _CONTROL.search(password):
        raise InvalidSettings("password", "That password can't be used.")
    return password


def check_message(name: str, at: datetime) -> dict[str, object]:
    """What the Test button sends to an email destination: plain, harmless, and says where it came
    from."""
    return discord_message(
        title="AresGate can email you",
        description=(
            f"This is a test message for “{name}”. If you can read it, alerts can be sent to "
            "this address. Nothing is wrong."
        ),
        footer="AresGate · test message",
        at=at,
    )


def _plain(text: str) -> str:
    """Discord's writing as plain words: bold and code marks dropped, a link as its words and then
    where it goes."""
    return _MARKDOWN.sub("", _LINK.sub(r"\1 (\2)", text))


def _line(text: str) -> str:
    """One line of text with nothing in it that could start another header."""
    return _CONTROL.sub(" ", text).strip()


def _mapping(value: object) -> dict[str, object]:
    """A JSON object as a dict, or an empty one for anything else."""
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _items(value: object) -> list[object]:
    """A JSON list as a list, or an empty one for anything else."""
    return cast("list[object]", value) if isinstance(value, list) else []


def _embed(payload: dict[str, object]) -> dict[str, object]:
    embeds = _items(payload.get("embeds"))
    return _mapping(embeds[0]) if embeds else {}


def render(payload: dict[str, object], server: Server, recipient: str) -> EmailMessage:
    """A message in the form Discord takes, as an email: its title is the subject, and its text and
    fields are the body, in plain text with the same in HTML beside it."""
    embed = _embed(payload)
    title = _plain(str(embed.get("title") or "AresGate"))
    description = _plain(str(embed.get("description") or ""))
    lines = [title, "", description] if description else [title]
    html_parts = (
        [f"<p>{html.escape(description).replace(chr(10), '<br>')}</p>"] if description else []
    )
    for each in _items(embed.get("fields")):
        field = _mapping(each)
        name, value = _plain(str(field.get("name", ""))), _plain(str(field.get("value", "")))
        lines += ["", f"{name}: {value}"]
        html_parts.append(f"<p><b>{html.escape(name)}</b>: {html.escape(value)}</p>")
    link = embed.get("url")
    if isinstance(link, str) and link.startswith(("http://", "https://")):
        lines += ["", link]
        html_parts.append(f'<p><a href="{html.escape(link)}">{html.escape(link)}</a></p>')
    footer_text = _plain(str(_mapping(embed.get("footer")).get("text", "")))
    if footer_text:
        lines += ["", "-- ", footer_text]
        html_parts.append(f"<p><small>{html.escape(footer_text)}</small></p>")
    mail = EmailMessage()
    mail["Subject"] = SUBJECT_PREFIX + _line(title)[: MAX_SUBJECT - len(SUBJECT_PREFIX)]
    mail["From"] = server.sender
    mail["To"] = recipient
    mail["Date"] = formatdate(localtime=False)
    mail["Message-ID"] = make_msgid(domain=server.sender.rpartition("@")[2])
    mail["Auto-Submitted"] = "auto-generated"
    mail.set_content("\n".join(lines) + "\n")
    mail.add_alternative(
        f"<html><body><h2>{html.escape(title)}</h2>{''.join(html_parts)}</body></html>",
        subtype="html",
    )
    return mail


def _problem(error: Exception) -> Sent:
    """What went wrong in words, and whether trying again could help. Holds nothing secret."""
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return Sent(
            ok=False,
            status=error.smtp_code,
            problem="The mail server didn't accept the user name and password. Check the mail "
            "server's settings.",
            gone=True,
        )
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return Sent(
            ok=False,
            status=None,
            problem="The mail server refused the recipient's address. Check it.",
            gone=True,
        )
    if isinstance(error, smtplib.SMTPSenderRefused):
        return Sent(
            ok=False,
            status=error.smtp_code,
            problem="The mail server refused the sender's address. Use one it lets you send from.",
            gone=True,
        )
    if isinstance(error, smtplib.SMTPResponseException):
        # 4xx: the server asked to try again later. 5xx: it won't take the message.
        return Sent(
            ok=False,
            status=error.smtp_code,
            problem=f"The mail server answered {error.smtp_code}, so the message wasn't sent.",
            retry=400 <= error.smtp_code < 500,
        )
    if isinstance(error, netguard.NotFound):
        # A name that doesn't resolve may resolve again: DNS fails for a moment now and then.
        return Sent(ok=False, status=None, problem=str(error), retry=True)
    if isinstance(error, netguard.Refused):
        return Sent(ok=False, status=None, problem=str(error), gone=True)
    if isinstance(error, ssl.SSLError):
        return Sent(
            ok=False,
            status=None,
            problem="Couldn't make an encrypted connection: the mail server's certificate isn't "
            "one a trusted authority signed for its name, or it doesn't offer encryption on "
            "that port.",
        )
    if isinstance(error, smtplib.SMTPNotSupportedError):
        return Sent(
            ok=False,
            status=None,
            problem="The mail server doesn't offer STARTTLS or signing in on this connection. "
            "Check the security setting and the port.",
            gone=True,
        )
    return Sent(
        ok=False,
        status=None,
        problem="Couldn't reach the mail server. Check its name and port.",
        retry=True,
    )


def _deliver(server: Server, mail: EmailMessage) -> Sent:
    """Sends one message, or says why not. Runs in a thread: smtplib waits on the network."""
    try:
        netguard.named_problem(SERVER_POLICY, server.host, server.port)
        netguard.allowed_addresses(
            SERVER_POLICY, server.host, netguard.lookup(server.host, server.port)
        )
        context = ssl.create_default_context()
        connection: smtplib.SMTP
        if server.security == "ssl":
            connection = smtplib.SMTP_SSL(
                server.host, server.port, timeout=TIMEOUT, context=context
            )
        else:
            connection = smtplib.SMTP(server.host, server.port, timeout=TIMEOUT)
        with connection:
            connection.ehlo()
            if server.security == "starttls":
                connection.starttls(context=context)
                connection.ehlo()
            if server.username and server.password:
                connection.login(server.username, server.password)
            connection.send_message(mail)
    except (smtplib.SMTPException, OSError, netguard.Refused) as error:
        return _problem(error)
    return Sent(ok=True, status=250)


async def send(box: Mailbox, payload: dict[str, object]) -> Sent:
    """Sends a message, built in the form Discord takes, to a mailbox. Never raises: how it went
    is in what is returned."""
    try:
        mail = render(payload, box.server, box.recipient)
    except ValueError, KeyError:
        return Sent(ok=False, status=None, problem="The message couldn't be written as an email.")
    return await asyncio.to_thread(_deliver, box.server, mail)
