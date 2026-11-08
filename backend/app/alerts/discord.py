"""Discord webhooks: checking the address of one, building a message and sending it.

A webhook is an address that anyone who has it can post to a channel with, and there is no
other sign-in: the token in the address is the whole secret. So the address is kept sealed (see
``app.security.credential_store``), it is never shown again, and it is checked three times:
when it is typed in, again every time it is opened to send, and by the network guard, which
only lets the request reach an address on the internet, never one on the home network or the
machine itself.

What this is built from (Discord's developer documentation, read 2026-11-01):

- Execute Webhook, https://docs.discord.com/developers/resources/webhook: ``POST
  /webhooks/{webhook.id}/{webhook.token}``; ``content`` up to 2000 characters and ``embeds`` up to
  10; ``wait=false`` (the default) answers 204 No Content, ``wait=true`` "waits for server
  confirmation of message send before response, and returns the created message body" (which has
  the message's ``id``); ``allowed_mentions`` controls who a message may ping; a webhook needs no
  sign-in.
- Edit Webhook Message, same page: ``PATCH /webhooks/{webhook.id}/{webhook.token}/messages/
  {message.id}`` takes the same ``embeds`` and ``allowed_mentions`` and returns the message. The
  page does not say whether the ``embeds`` sent replace the old or are merged with them, so the
  whole embed is sent again.
- JSON error codes, https://docs.discord.com/developers/topics/opcodes-and-status-codes: an error
  body has ``code`` and ``message``; 10008 is "Unknown message" (the message was deleted) and 10015
  "Unknown webhook".
- Embed fields, https://docs.discord.com/developers/resources/message: up to 25 fields, ``inline``
  is a boolean.
- Rate limits, https://docs.discord.com/developers/topics/rate-limits: a 429 answers with a body
  that has ``retry_after`` (seconds, a float) and ``global``; webhooks are limited per webhook;
  a webhook that answers 404 "should not" be used again; 401, 403 and 429 count toward a limit of
  10,000 invalid requests per 10 minutes, past which the address is blocked for a while.
- Message embeds, https://docs.discord.com/developers/resources/message: title 256, description
  4096, field name 256, field value 1024, footer 2048 characters, 6000 in all; ``color`` is an
  integer; ``timestamp`` is ISO 8601; ``"parse": []`` in ``allowed_mentions`` stops every ping.
- Reference, https://docs.discord.com/developers/reference: the base is https://discord.com/api
  and a version may be left out (then it is the current default); the User-Agent should read
  ``DiscordBot ($url, $versionNumber)``, and requests without one "may be blocked".

What is inferred and not tried against Discord: that ``discordapp.com`` still takes webhooks (it
is Discord's older name, and addresses made then use it; the pages above name only discord.com),
that the token is made of letters, digits, ``-`` and ``_`` (the pages give no format; the
patterns below are wide), that a wrong token answers 401 (the pages say only that 404 is a webhook
that is gone), that a 5xx can be tried again, that editing a message replaces its embed, and that
an edit of a deleted message answers 404 with code 10008.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import cast
from urllib.parse import urlsplit

from app import __version__
from app.integrations import netguard
from app.integrations.client import ApiClient, CallFailed, Recorder, Target
from app.integrations.client import Call as LoggedCall
from app.integrations.netguard import AddressPolicy, Origin

# Where Discord's API is. A webhook address made by Discord names one of these.
HOSTS = ("discord.com", "discordapp.com")
MAX_URL = 400
# A snowflake is a 64-bit number, which has 17 to 19 digits today; room is left for more.
_ID = re.compile(r"\d{15,25}")
# What the token is made of is not documented. This is wider than what Discord makes.
_TOKEN = re.compile(r"[A-Za-z0-9_-]{16,160}")
_VERSION = re.compile(r"v\d{1,3}")
# What AresGate calls itself in a message, in place of the webhook's own name.
USERNAME = "AresGate"
# Shown in place of the address in the API log, which keeps the path of every request.
LOGGED_PATH = "/api/webhooks/…"
# Embed colours: Discord takes a number.
BLUE = 0x3B82F6
RED = 0xEF4444
AMBER = 0xF59E0B
# The limits of a message, from the pages above.
MAX_TITLE = 256
MAX_DESCRIPTION = 4096
MAX_FIELDS = 25
MAX_FIELD_NAME = 256
MAX_FIELD_VALUE = 1024
GREY = 0x6B7280
GREEN = 0x22C55E
# The longest Discord is believed when it says how long to wait, in seconds.
MAX_WAIT = 3600
USER_AGENT = f"DiscordBot (https://github.com/brianbaggs35/AresGate, {__version__})"


class InvalidWebhook(ValueError):
    """An address that isn't a Discord webhook. The message says what to change and never repeats
    the address, which is a secret."""


@dataclass(frozen=True)
class Webhook:
    """A Discord webhook address taken apart. ``token`` is the secret."""

    host: str
    id: str
    token: str
    version: str | None = None

    @property
    def path(self) -> str:
        version = f"/{self.version}" if self.version else ""
        return f"/api{version}/webhooks/{self.id}/{self.token}"

    @property
    def url(self) -> str:
        return f"https://{self.host}{self.path}"

    @property
    def hint(self) -> str:
        """The end of the number, which tells one webhook from another and reveals nothing."""
        return f"…{self.id[-4:]}"


def parse(address: str) -> Webhook:
    """A webhook address, as Discord gives it ("Copy Webhook URL"), checked. Raises
    ``InvalidWebhook`` saying what is wrong."""
    text = address.strip()
    if not text:
        raise InvalidWebhook("Paste the webhook address from Discord.")
    if len(text) > MAX_URL:
        raise InvalidWebhook("That is too long to be a Discord webhook address.")
    try:
        parts = urlsplit(text)
        port = parts.port
        host = parts.hostname
    except ValueError:
        raise InvalidWebhook(
            "That isn't a web address. Paste the whole webhook address from Discord."
        ) from None
    if parts.scheme != "https" or not host:
        raise InvalidWebhook("A webhook address starts with https://.")
    if host not in HOSTS:
        raise InvalidWebhook(
            f"That isn't a Discord address. Webhooks are at {' or '.join(HOSTS)}, and AresGate "
            "sends alerts to nowhere else."
        )
    if parts.username or parts.password or port not in (None, 443) or parts.query or parts.fragment:
        raise InvalidWebhook(
            "Paste the address exactly as Discord shows it, with no user name, port or "
            "question mark in it."
        )
    segments = parts.path.rstrip("/").split("/")
    # ["", "api", "webhooks", id, token] or ["", "api", "v10", "webhooks", id, token]
    version = segments[2] if len(segments) == 6 and _VERSION.fullmatch(segments[2]) else None
    rest = segments[:2] + segments[3:] if version else segments
    if (
        len(rest) != 5
        or rest[:3] != ["", "api", "webhooks"]
        or not _ID.fullmatch(rest[3])
        or not _TOKEN.fullmatch(rest[4])
    ):
        raise InvalidWebhook(
            "That doesn't look like a webhook address. It ends with /api/webhooks/ and then a "
            "number and a long token. In Discord, open the channel's settings, then "
            "Integrations, then Webhooks, and choose Copy Webhook URL."
        )
    return Webhook(host=host, id=rest[3], token=rest[4], version=version)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


# A field of an embed: its name, its value and whether it sits beside the next.
Field = tuple[str, str, bool]


def message(
    *,
    title: str,
    description: str,
    color: int = BLUE,
    footer: str | None = None,
    link: str | None = None,
    fields: Sequence[Field] = (),
    at: datetime | None = None,
) -> dict[str, object]:
    """A message of one embed, within the limits Discord sets, that can ping no one however it
    is worded (``"parse": []``)."""
    embed: dict[str, object] = {
        "title": _clip(title, MAX_TITLE),
        "description": _clip(description, MAX_DESCRIPTION),
        "color": color,
    }
    if fields:
        embed["fields"] = [
            {
                "name": _clip(name, MAX_FIELD_NAME),
                "value": _clip(value, MAX_FIELD_VALUE),
                "inline": inline,
            }
            for name, value, inline in fields[:MAX_FIELDS]
        ]
    if link:
        embed["url"] = link
    if footer:
        embed["footer"] = {"text": _clip(footer, 2048)}
    if at:
        embed["timestamp"] = at.isoformat()
    return {"username": USERNAME, "allowed_mentions": {"parse": []}, "embeds": [embed]}


def check_message(name: str, at: datetime) -> dict[str, object]:
    """What the Test button sends: plain, harmless, and says where it came from."""
    return message(
        title="AresGate can reach this channel",
        description=(
            f"This is a test message for “{name}”. If you can read it, alerts can be sent "
            "here. Nothing is wrong."
        ),
        footer="AresGate · test message",
        at=at,
    )


@dataclass(frozen=True)
class Sent:
    """How sending went."""

    ok: bool
    # What Discord answered, if it did.
    status: int | None
    # In words for the owner: why it didn't go through. Holds nothing secret.
    problem: str | None = None
    # Whether trying again later could work: Discord was busy, had a fault, or didn't answer.
    retry: bool = False
    # How long Discord asked to wait, in seconds.
    retry_after: float | None = None
    # The webhook itself is no good (deleted, or its token is wrong), so trying again will not
    # help and the address has to be replaced.
    gone: bool = False
    # How long Discord's headers say the next message has to wait: it got this one, but the
    # allowance for now is spent.
    pause: float | None = None
    # What Discord called the message, when it was asked to say (``wait``).
    message_id: str | None = None
    # An edit of a message that is gone (someone deleted it in Discord): the webhook is fine, and
    # there is nothing to change.
    missing: bool = False


def _retry_after(body: object) -> float | None:
    if isinstance(body, Mapping):
        value = cast("Mapping[str, object]", body).get("retry_after")
        if isinstance(value, int | float) and not isinstance(value, bool) and value >= 0:
            return float(value)
    return None


def _seconds(value: str | None) -> float | None:
    """A number of seconds a header gives, or none if it gives no such number."""
    try:
        seconds = float(value) if value is not None else None
    except ValueError:
        return None
    return seconds if seconds is not None and 0 <= seconds < MAX_WAIT else None


def _spent(headers: Mapping[str, str]) -> float | None:
    """How long to wait before the next message, if the headers say none are left: Discord sends
    ``X-RateLimit-Remaining`` and ``X-RateLimit-Reset-After`` with its answers."""
    if headers.get("x-ratelimit-remaining") != "0":
        return None
    return _seconds(headers.get("x-ratelimit-reset-after"))


def _snowflake(body: object) -> str | None:
    """The ``id`` of the message in an answer, if it has one that looks like Discord's."""
    if isinstance(body, Mapping):
        found = cast("Mapping[str, object]", body).get("id")
        if isinstance(found, str) and _ID.fullmatch(found):
            return found
    return None


def _code_of(body: object) -> int | None:
    if isinstance(body, Mapping):
        code = cast("Mapping[str, object]", body).get("code")
        if isinstance(code, int) and not isinstance(code, bool):
            return code
    return None


def judge(status: int, body: object, headers: Mapping[str, str] | None = None) -> Sent:
    """What an answer from Discord means for sending."""
    seen = headers or {}
    if status in (200, 204):
        return Sent(True, status, pause=_spent(seen), message_id=_snowflake(body))
    if status == 429:
        # The page says to rely on the header or the field; the field is the more exact.
        wait = _retry_after(body)
        if wait is None:
            wait = _seconds(seen.get("retry-after"))
        how_long = f" for {wait:g} seconds" if wait is not None else " for a moment"
        return Sent(
            False,
            status,
            f"Discord is limiting how fast messages can be sent here (HTTP 429). Wait{how_long}.",
            retry=True,
            retry_after=wait,
        )
    if status in (401, 403, 404):
        return Sent(
            False,
            status,
            f"Discord doesn't accept this webhook (HTTP {status}). It was most likely deleted in "
            "Discord, or its address changed. Make a new webhook and replace the address here.",
            gone=True,
        )
    if status >= 500:
        return Sent(
            False,
            status,
            f"Discord had a fault of its own (HTTP {status}). It can be tried again.",
            retry=True,
        )
    return Sent(
        False,
        status,
        f"Discord refused the message (HTTP {status}). This is a fault in AresGate, so please "
        "report it.",
    )


# Discord's code for an edit of a message that is not there.
UNKNOWN_MESSAGE = 10008


def judge_edit(status: int, body: object, headers: Mapping[str, str] | None = None) -> Sent:
    """What an answer from Discord means for editing a message. A 404 with the code for an unknown
    message is the message having been deleted, which is not a fault of the webhook."""
    if status == 404 and _code_of(body) == UNKNOWN_MESSAGE:
        return Sent(
            False,
            status,
            "The message was deleted in Discord, so there was nothing to update.",
            missing=True,
        )
    return judge(status, body, headers)


def _origin(override: str | None) -> Origin:
    """Where Discord is. The end-to-end harness points it at a stand-in on its own machine."""
    if override:
        return netguard.parse_origin(override, allow_http=True)
    return Origin("https", HOSTS[0], 443)


def _without_address(record: Recorder) -> Recorder:
    """A recorder that leaves the webhook's address out of the log: the path of the request holds
    the token."""

    async def keep(call: LoggedCall) -> None:
        await record(replace(call, path=LOGGED_PATH))

    return keep


async def _call(
    method: str,
    path: str,
    webhook: Webhook,
    payload: Mapping[str, object],
    *,
    query: Mapping[str, str] | None,
    connection: str,
    recorder: Recorder,
    policy: AddressPolicy,
    origin: str | None,
    edit: bool,
) -> Sent:
    target = Target(
        integration="discord",
        connection=connection,
        origin=_origin(origin),
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options={},
        secrets={"token": webhook.token},
    )
    async with ApiClient(target, _without_address(recorder), policy) as client:
        try:
            reply = await client.request(
                method,
                path,
                query=query,
                json_body=payload,
                headers={"User-Agent": USER_AGENT},
            )
        except CallFailed as failure:
            return Sent(False, None, str(failure), retry=True)
    judge_it = judge_edit if edit else judge
    return judge_it(reply.status, reply.json(), reply.headers)


async def send(
    webhook: Webhook,
    payload: Mapping[str, object],
    *,
    connection: str,
    recorder: Recorder,
    policy: AddressPolicy,
    origin: str | None = None,
    wait: bool = False,
) -> Sent:
    """Posts a message to a webhook and says how it went. Never raises for Discord's answer, or
    for none. Every request is logged, without the address. With ``wait`` Discord answers with the
    message it made, and ``Sent.message_id`` is its name, which is how it is edited later."""
    return await _call(
        "POST",
        webhook.path,
        webhook,
        payload,
        query={"wait": "true"} if wait else None,
        connection=connection,
        recorder=recorder,
        policy=policy,
        origin=origin,
        edit=False,
    )


async def edit(
    webhook: Webhook,
    message_id: str,
    payload: Mapping[str, object],
    *,
    connection: str,
    recorder: Recorder,
    policy: AddressPolicy,
    origin: str | None = None,
) -> Sent:
    """Changes a message already sent to a webhook, and says how it went. ``message_id`` came from
    Discord, but it is checked all the same, since it becomes part of the address."""
    if not _ID.fullmatch(message_id):
        return Sent(False, None, "That isn't the name of a Discord message.")
    return await _call(
        "PATCH",
        f"{webhook.path}/messages/{message_id}",
        webhook,
        payload,
        query=None,
        connection=connection,
        recorder=recorder,
        policy=policy,
        origin=origin,
        edit=True,
    )
