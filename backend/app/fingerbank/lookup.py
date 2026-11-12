"""Fingerbank's answer about a hardware address, read from its API.

``GET /api/v2/combinations/interrogate`` takes what is known of a device as a JSON body (here the
``mac`` alone) and answers with the device that matches it most, the manufacturer, the operating
system and a score from 0 to 100 for how sure it is. The key goes in the ``Authorization`` header
as a bearer token, which keeps it out of the address and so out of the API log. An address with no
match is a 404, and a request over the limit is a 429, which says to wait: neither is an error.
Every key is capped at 250 requests a minute, and the free one at fewer an hour (see ``queue``).

Fingerbank's reference lists the fields of the answer but not whether ``manufacturer`` and
``operating_system`` can be null, so each is read as optional.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from app import audit
from app.integrations.client import ApiClient, CallFailed, Recorder, Reply, Target
from app.integrations.netguard import AddressPolicy

PROVIDER = "fingerbank"
# How long lookups wait after Fingerbank answers 429. Its answer says nothing of when to come back.
THROTTLE = timedelta(minutes=5)
# How long they wait after a request that got no answer, or an answer that was no use.
RETRY = timedelta(minutes=1)
MAX_NAME = 200
MAX_PATH = 600
MAX_MAKER = 128
MAX_ID = 2**63 - 1


@dataclass(frozen=True)
class Identity:
    """What Fingerbank says a device is."""

    name: str | None
    path: str | None
    manufacturer: str | None
    operating_system: str | None
    score: int | None
    external_id: int | None


@dataclass(frozen=True)
class Identified:
    identity: Identity


@dataclass(frozen=True)
class Unknown:
    """Fingerbank has no match for the address."""


@dataclass(frozen=True)
class Throttled:
    """Fingerbank asked for fewer requests: nothing is sent until ``until``."""

    until: datetime


@dataclass(frozen=True)
class Failed:
    """No answer came, or it was no use. ``refused`` is whether Fingerbank turned the key down,
    which a person has to put right."""

    message: str
    refused: bool = False


type Answer = Identified | Unknown | Throttled | Failed


def _object(value: object) -> dict[str, object] | None:
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def _text(value: object, limit: int) -> str | None:
    return audit.clean(value, limit) if isinstance(value, str) and value.strip() else None


def _named(value: object, limit: int) -> str | None:
    """The name of one of the answer's objects (``manufacturer``, ``operating_system``)."""
    item = _object(value)
    return None if item is None else _text(item.get("name"), limit)


def _whole(value: object, low: int, high: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        return None
    return value


def parse(root: dict[str, object]) -> Identity | None:
    """The device in Fingerbank's answer, or None if it names nothing, which is no match."""
    device = _object(root.get("device")) or {}
    identity = Identity(
        name=_text(device.get("name"), MAX_NAME),
        path=_text(root.get("device_name"), MAX_PATH),
        manufacturer=_named(root.get("manufacturer"), MAX_MAKER),
        operating_system=_named(root.get("operating_system"), MAX_MAKER),
        score=_whole(root.get("score"), 0, 100),
        external_id=_whole(device.get("id"), 0, MAX_ID),
    )
    return identity if identity.name or identity.path else None


_REFUSED = {
    401: "Fingerbank didn't accept the key. Copy it again from your Fingerbank account.",
    403: "Fingerbank has blocked this key. Its fair usage policy allows one key for each.",
}


def answer_of(reply: Reply, now: datetime) -> Answer:
    """What a reply from Fingerbank says."""
    if reply.status == 404:
        return Unknown()
    if reply.status == 429:
        return Throttled(until=now + THROTTLE)
    if reply.status in _REFUSED:
        return Failed(_REFUSED[reply.status], refused=True)
    if not reply.ok:
        return Failed(f"Fingerbank answered HTTP {reply.status}.")
    root = _object(reply.json())
    if root is None or "device" not in root:
        return Failed("Fingerbank's answer didn't hold a device.")
    identity = parse(root)
    return Unknown() if identity is None else Identified(identity)


async def look_up(client: ApiClient, target: Target, mac: str, now: datetime) -> Answer:
    """Asks what the device with this hardware address is. Raises ``CallFailed`` if no answer
    came at all."""
    reply = await client.request(
        "GET",
        "/api/v2/combinations/interrogate",
        json_body={"mac": mac},
        headers={"Authorization": f"Bearer {target.secrets['api_key']}"},
    )
    return answer_of(reply, now)


async def ask(
    target: Target, record: Recorder, policy: AddressPolicy, mac: str, now: datetime
) -> Answer:
    """Asks Fingerbank over a logged connection. A request that gets no answer is a failure, with
    the reason in words."""
    try:
        async with ApiClient(target, record, policy) as client:
            return await look_up(client, target, mac, now)
    except CallFailed as failure:
        return Failed(str(failure))
