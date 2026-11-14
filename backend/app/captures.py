"""A short look at the packets of one host, taken by ntopng and read here.

``GET /lua/rest/v2/get/pcap/live_traffic.lua`` takes the interface (``ifid``), a ``host`` and a
``duration`` in seconds (at most 600, 60 when it is missing or wrong) and answers with a classic
libpcap file of what the interface carried to and from the host in that time. It is allowed for the
user ntopng has given "download PCAP" (an administrator has it); a user without it gets an object
with an ``error``. Read from ntopng's source (``scripts/lua/rest/v2/get/pcap/live_traffic.lua``),
and not tried against a live ntopng.

AresGate keeps nothing of it. The answer is read up to ``MAX_BYTES``, the packets in it are
decoded to what a person reads (who sent it to whom, over what, how long, the flags of a TCP
segment and the first bytes it carried), and the file is thrown away. Which packets those are is
only what ntopng saw, so a host behind a router is seen with the router's frames, and encrypted
traffic is seen as it is: bytes."""

import ipaddress
import json
import struct
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Final

from app.integrations import probes
from app.integrations.client import ApiClient, CallFailed, Recorder, Target
from app.integrations.netguard import AddressPolicy
from app.integrations.registry import chosen_numbers

PRODUCT: Final = "ntopng"
PATH: Final = "/lua/rest/v2/get/pcap/live_traffic.lua"
# How long a capture may be asked for. ntopng allows ten minutes; a few seconds says what a host
# is doing, and a longer one holds the connection open and the interface busy.
MIN_SECONDS: Final = 1
MAX_SECONDS: Final = 30
# The most of the answer that is read, and the most packets that are listed from it.
MAX_BYTES: Final = 2 * 1024 * 1024
MAX_PACKETS: Final = 300
# How much of what a packet carried is shown.
PREVIEW: Final = 48

_GLOBAL_HEADER: Final = 24
_RECORD_HEADER: Final = 16
# (byte order, divisor of the fraction of a second) by the magic number at the start of the file.
_MAGIC: Final = {
    0xA1B2C3D4: ("<", 1_000_000),
    0xA1B23C4D: ("<", 1_000_000_000),
    0xD4C3B2A1: (">", 1_000_000),
    0x4D3CB2A1: (">", 1_000_000_000),
}
_ETHERNET: Final = 1
_RAW_IP: Final = 101
_LINUX_COOKED: Final = 113
_ETHERTYPE_IPV4: Final = 0x0800
_ETHERTYPE_IPV6: Final = 0x86DD
_ETHERTYPE_ARP: Final = 0x0806
_VLAN: Final = (0x8100, 0x88A8)
_PROTOCOLS: Final = {1: "ICMP", 2: "IGMP", 6: "TCP", 17: "UDP", 47: "GRE", 50: "ESP", 58: "ICMPv6"}
_TCP_FLAGS: Final = (
    (0x80, "CWR"),
    (0x40, "ECE"),
    (0x20, "URG"),
    (0x10, "ACK"),
    (0x08, "PSH"),
    (0x04, "RST"),
    (0x02, "SYN"),
    (0x01, "FIN"),
)
# IPv6 headers that are followed by another: hop-by-hop, routing and destination options.
_IPV6_OPTIONS: Final = (0, 43, 60)
_IPV6_FRAGMENT: Final = 44


class CaptureFailed(Exception):
    """No capture could be had. The message says why, in words for the person who asked."""


@dataclass(frozen=True)
class Packet:
    at: datetime
    source: str
    destination: str
    protocol: str
    source_port: int | None
    destination_port: int | None
    # The size of the packet on the wire.
    length: int
    # The flags of a TCP segment, such as SYN or ACK PSH.
    flags: str
    # The first bytes of what it carried after its headers, with what isn't printable as a dot.
    preview: str


@dataclass(frozen=True)
class Capture:
    packets: list[Packet]
    # How many packets the capture held that could be read, of which ``packets`` has the first.
    total: int
    # Packets that aren't IP or ARP, which are counted and not shown.
    skipped: int
    bytes: int
    # ntopng sent more than AresGate reads, so the end of the capture is missing.
    cut: bool
    # How many packets of each protocol, the most first.
    protocols: list[tuple[str, int]]


@dataclass(frozen=True)
class _Segment:
    protocol: str
    source: str
    destination: str
    source_port: int | None = None
    destination_port: int | None = None
    flags: str = ""
    payload: bytes = b""


def valid_host(text: str) -> str | None:
    """The address in its usual form, or None if it isn't an IPv4 or IPv6 address."""
    try:
        return str(ipaddress.ip_address(text.strip()))
    except ValueError:
        return None


def _preview(payload: bytes) -> str:
    return "".join(chr(byte) if 32 <= byte < 127 else "." for byte in payload[:PREVIEW])


def _transport(protocol: int, source: str, destination: str, data: bytes) -> _Segment:
    name = _PROTOCOLS.get(protocol, f"IP protocol {protocol}")
    if protocol == 6 and len(data) >= 20:
        source_port, destination_port = struct.unpack(">HH", data[:4])
        offset = (data[12] >> 4) * 4
        flags = " ".join(label for bit, label in _TCP_FLAGS if data[13] & bit)
        return _Segment(
            name, source, destination, source_port, destination_port, flags, data[offset:]
        )
    if protocol == 17 and len(data) >= 8:
        source_port, destination_port = struct.unpack(">HH", data[:4])
        return _Segment(name, source, destination, source_port, destination_port, "", data[8:])
    return _Segment(name, source, destination)


def _ipv4(data: bytes) -> _Segment | None:
    if len(data) < 20 or data[0] >> 4 != 4:
        return None
    header = (data[0] & 15) * 4
    source = str(ipaddress.IPv4Address(data[12:16]))
    destination = str(ipaddress.IPv4Address(data[16:20]))
    fragment = struct.unpack(">H", data[6:8])[0] & 0x1FFF
    if fragment:
        return _Segment(_PROTOCOLS.get(data[9], f"IP protocol {data[9]}"), source, destination)
    return _transport(data[9], source, destination, data[header:])


def _ipv6(data: bytes) -> _Segment | None:
    if len(data) < 40 or data[0] >> 4 != 6:
        return None
    source = str(ipaddress.IPv6Address(data[8:24]))
    destination = str(ipaddress.IPv6Address(data[24:40]))
    following, rest = data[6], data[40:]
    while following in _IPV6_OPTIONS and len(rest) >= 8:
        following, rest = rest[0], rest[(rest[1] + 1) * 8 :]
    if following == _IPV6_FRAGMENT and len(rest) >= 8:
        return _Segment(_PROTOCOLS.get(rest[0], f"IP protocol {rest[0]}"), source, destination)
    return _transport(following, source, destination, rest)


# What an ARP request or reply is, by its operation number.
_ARP_OPERATIONS: Final = {1: "who has", 2: "is at"}


def _arp(data: bytes) -> _Segment | None:
    """Who asks for whom: the sender's and the target's address of an Ethernet and IPv4 request."""
    if len(data) < 28 or data[4] != 6 or data[5] != 4:
        return None
    return _Segment(
        "ARP",
        str(ipaddress.IPv4Address(data[14:18])),
        str(ipaddress.IPv4Address(data[24:28])),
        flags=_ARP_OPERATIONS.get(data[7], ""),
    )


def _network(ethertype: int, data: bytes) -> _Segment | None:
    reader: Callable[[bytes], _Segment | None] | None = {
        _ETHERTYPE_IPV4: _ipv4,
        _ETHERTYPE_IPV6: _ipv6,
        _ETHERTYPE_ARP: _arp,
    }.get(ethertype)
    return reader(data) if reader else None


def _frame(link: int, data: bytes) -> _Segment | None:
    """What one packet of the capture says, or None if it isn't one that is read."""
    if link == _RAW_IP:
        return _ipv4(data) if data[:1] and data[0] >> 4 == 4 else _ipv6(data)
    if link == _LINUX_COOKED:
        return _network(struct.unpack(">H", data[14:16])[0], data[16:]) if len(data) >= 16 else None
    if len(data) < 14:
        return None
    ethertype, rest = struct.unpack(">H", data[12:14])[0], data[14:]
    # A frame on a VLAN carries the tag, then the type it really holds.
    while ethertype in _VLAN and len(rest) >= 4:
        ethertype, rest = struct.unpack(">H", rest[2:4])[0], rest[4:]
    return _network(ethertype, rest)


def parse(data: bytes) -> Capture:
    """Reads a capture file. A packet cut off at the end of what was read is left out. Raises
    ``CaptureFailed`` for a file that isn't a classic pcap of Ethernet, raw IP or Linux cooked
    frames."""
    if len(data) < _GLOBAL_HEADER:
        raise CaptureFailed("ntopng sent no capture, only " + f"{len(data)} bytes.")
    magic = struct.unpack("<I", data[:4])[0]
    if magic not in _MAGIC:
        raise CaptureFailed(
            "What ntopng sent isn't a packet capture AresGate reads (a classic pcap file)."
        )
    order, divisor = _MAGIC[magic]
    link = struct.unpack(f"{order}I", data[20:24])[0]
    if link not in (_ETHERNET, _RAW_IP, _LINUX_COOKED):
        raise CaptureFailed(
            f"ntopng's capture holds frames of a kind (type {link}) AresGate can't read."
        )
    packets: list[Packet] = []
    total = skipped = 0
    protocols: Counter[str] = Counter()
    at = _GLOBAL_HEADER
    while at + _RECORD_HEADER <= len(data):
        seconds, fraction, kept, wire = struct.unpack(
            f"{order}IIII", data[at : at + _RECORD_HEADER]
        )
        frame = data[at + _RECORD_HEADER : at + _RECORD_HEADER + kept]
        if len(frame) < kept:
            break
        at += _RECORD_HEADER + kept
        segment = _frame(link, frame)
        if segment is None:
            skipped += 1
            continue
        total += 1
        protocols[segment.protocol] += 1
        if len(packets) < MAX_PACKETS:
            packets.append(
                Packet(
                    datetime.fromtimestamp(seconds + fraction / divisor, UTC),
                    segment.source,
                    segment.destination,
                    segment.protocol,
                    segment.source_port,
                    segment.destination_port,
                    wire,
                    segment.flags,
                    _preview(segment.payload),
                )
            )
    return Capture(packets, total, skipped, len(data), False, protocols.most_common())


async def interface_of(client: ApiClient, target: Target) -> int:
    """The interface to capture on: the first one the connection reads, or else the first ntopng
    lists that isn't the loopback."""
    chosen = chosen_numbers(target.options["interface_id"])
    if chosen:
        return chosen[0]
    listed = await probes.ntopng_interfaces(client, target)
    if isinstance(listed, probes.Verdict):
        raise CaptureFailed(listed.message)
    found = probes.default_interfaces(listed)
    if not found:
        raise CaptureFailed("ntopng lists no interfaces, so there is nothing to capture on.")
    return found[0].ifid


async def take(
    target: Target, recorder: Recorder, policy: AddressPolicy, host: str, seconds: int
) -> Capture:
    """Asks ntopng for ``seconds`` of the host's packets and reads them. Raises ``CaptureFailed``
    with why it couldn't."""
    seconds = max(MIN_SECONDS, min(MAX_SECONDS, seconds))
    try:
        # Quiet or not, ntopng answers when the time is up, so the wait is the capture and a margin.
        async with ApiClient(
            target, recorder, policy, deadline=seconds + 20.0, read_timeout=seconds + 10.0
        ) as client:
            query = {
                "ifid": str(await interface_of(client, target)),
                "host": host,
                "duration": str(seconds),
            }
            reply = await probes.ntopng_get(client, target, PATH, query, keep_bytes=MAX_BYTES)
    except CallFailed as failure:
        raise CaptureFailed(str(failure)) from None
    if 300 <= reply.status < 400:
        raise CaptureFailed(probes.NTOPNG_LOGIN_REFUSED)
    if reply.status == HTTPStatus.BAD_REQUEST:
        raise CaptureFailed(
            "ntopng refused the request (HTTP 400). Check the interfaces chosen in the "
            "connection's settings."
        )
    if reply.status >= HTTPStatus.BAD_REQUEST:
        problem = probes.problem(reply, PRODUCT)
        raise CaptureFailed(
            problem.message if problem else f"{PRODUCT} answered HTTP {reply.status}."
        )
    if "json" in reply.headers.get("content-type", ""):
        raise CaptureFailed(_said(reply.content))
    capture = parse(reply.content)
    return Capture(
        capture.packets,
        capture.total,
        capture.skipped,
        capture.bytes,
        reply.cut,
        capture.protocols,
    )


def _said(content: bytes) -> str:
    """What ntopng says when it sends a message in place of a capture: it hasn't allowed the user
    to download packets, or it couldn't."""
    try:
        answer = probes.as_object(json.loads(content))
    except ValueError:
        answer = None
    reason = probes.fact(answer.get("error"), 200) if answer and "error" in answer else None
    return (
        f"ntopng didn't send a capture: {reason}. The user AresGate signs in as needs "
        "ntopng's permission to download PCAP files."
        if reason
        else "ntopng sent a message instead of a capture."
    )
