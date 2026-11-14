"""Reading the packets ntopng captured: what the file says, and what is said when it fails."""

import asyncio
import json
import struct
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app import captures
from app.captures import CaptureFailed
from app.config import Settings
from app.integrations import netguard, registry, service
from app.integrations.client import Call, Target
from e2e.stand_ins import (
    Answer,
    Handler,
    Seen,
    ethernet_tcp,
    ethernet_udp,
    ntopng,
    pcap_file,
    sample_ntopng_capture,
)
from tests.ntopng import TOKEN, connect
from tests.stubs import StubServer

HOST = "192.168.1.20"
PEER = "93.184.216.34"
START = 1_700_000_000


def ipv4(protocol: int, body: bytes, *, fragment: int = 0, source: str = HOST) -> bytes:
    """An IPv4 header, then the body."""
    return (
        struct.pack(
            ">BBHHHBBH4s4s",
            0x45,
            0,
            20 + len(body),
            0,
            fragment,
            64,
            protocol,
            0,
            bytes(map(int, source.split("."))),
            bytes(map(int, PEER.split("."))),
        )
        + body
    )


def ipv6(next_header: int, body: bytes) -> bytes:
    source = bytes(15) + b"\x01"
    destination = bytes(15) + b"\x02"
    return struct.pack(">IHBB", 6 << 28, len(body), next_header, 64) + source + destination + body


def ethernet(ethertype: int, body: bytes) -> bytes:
    return bytes(12) + struct.pack(">H", ethertype) + body


def tcp(flags: int, data: bytes = b"") -> bytes:
    return struct.pack(">HHIIBBHHH", 1234, 80, 0, 0, 5 << 4, flags, 1024, 0, 0) + data


def udp(data: bytes = b"") -> bytes:
    return struct.pack(">HHHH", 5000, 53, 8 + len(data), 0) + data


def test_a_capture_is_read_packet_by_packet() -> None:
    capture = captures.parse(sample_ntopng_capture(HOST))

    assert capture.total == 6
    assert capture.skipped == 0
    assert capture.cut is False
    assert capture.protocols == [("TCP", 5), ("UDP", 1)]
    syn, synack, *_, request, _answer, question = capture.packets
    assert (syn.source, syn.destination, syn.source_port, syn.destination_port) == (
        HOST,
        PEER,
        50000,
        80,
    )
    assert (syn.protocol, syn.flags) == ("TCP", "SYN")
    assert synack.flags == "ACK SYN"
    assert request.flags == "ACK PSH"
    assert request.preview.startswith("GET / HTTP/1.1..Host: example.com")
    assert question.protocol == "UDP"
    assert (question.source_port, question.destination_port) == (53123, 53)
    assert syn.at == datetime.fromtimestamp(START, UTC)
    assert capture.packets[1].at == datetime.fromtimestamp(START + 0.1, UTC)
    assert capture.bytes == len(sample_ntopng_capture(HOST))


def test_the_preview_is_cut_short_and_shows_only_what_can_be_read() -> None:
    frame = ethernet_tcp(HOST, PEER, 1, 2, 0x18, b"\x00\xffabc" + b"x" * 200)

    (packet,) = captures.parse(pcap_file([frame])).packets

    assert packet.preview == "..abc" + "x" * (captures.PREVIEW - 5)


def test_only_the_first_packets_are_listed_but_all_are_counted() -> None:
    frame = ethernet_udp(HOST, PEER, 1, 2, b"")

    capture = captures.parse(pcap_file([frame] * (captures.MAX_PACKETS + 5)))

    assert len(capture.packets) == captures.MAX_PACKETS
    assert capture.total == captures.MAX_PACKETS + 5


def test_a_packet_cut_off_at_the_end_is_left_out() -> None:
    whole = ethernet_udp(HOST, PEER, 1, 2, b"hi")
    data = pcap_file([whole, whole])

    capture = captures.parse(data[:-3])

    assert capture.total == 1


def test_a_file_in_the_other_byte_order_is_read() -> None:
    frame = ethernet_udp(HOST, PEER, 1, 2, b"")
    rest = struct.pack(">HHiIII", 2, 4, 0, 0, 65535, 1)
    # A big-endian file starts with the magic number as it is written, a1b2c3d4 (and a1b23c4d in
    # nanoseconds), which a little-endian file has the other way round.
    nano = bytes.fromhex("a1b23c4d") + rest
    micro = bytes.fromhex("a1b2c3d4") + rest

    (a,) = captures.parse(
        nano + struct.pack(">IIII", START, 500_000_000, len(frame), len(frame)) + frame
    ).packets
    (b,) = captures.parse(
        micro + struct.pack(">IIII", START, 250_000, len(frame), len(frame)) + frame
    ).packets

    assert a.at == datetime.fromtimestamp(START + 0.5, UTC)
    assert b.at == datetime.fromtimestamp(START + 0.25, UTC)


def test_a_nanosecond_file_in_the_usual_byte_order_is_read() -> None:
    frame = ethernet_udp(HOST, PEER, 1, 2, b"")
    header = struct.pack("<IHHiIII", 0xA1B23C4D, 2, 4, 0, 0, 65535, 1)
    record = struct.pack("<IIII", START, 500_000_000, len(frame), len(frame))

    (packet,) = captures.parse(header + record + frame).packets

    assert packet.at == datetime.fromtimestamp(START + 0.5, UTC)


def test_other_protocols_are_named_and_have_no_ports() -> None:
    frames = [
        ethernet(0x0800, ipv4(1, b"\x08\x00" + bytes(6))),
        ethernet(0x0800, ipv4(47, bytes(8))),
        ethernet(0x0800, ipv4(6, tcp(0x02), fragment=185)),
    ]

    capture = captures.parse(pcap_file(frames))

    assert [(p.protocol, p.source_port) for p in capture.packets] == [
        ("ICMP", None),
        ("GRE", None),
        ("TCP", None),
    ]
    assert sorted(capture.protocols) == [("GRE", 1), ("ICMP", 1), ("TCP", 1)]


def test_a_protocol_without_a_name_is_given_by_its_number() -> None:
    (packet,) = captures.parse(pcap_file([ethernet(0x0800, ipv4(99, bytes(8)))])).packets

    assert packet.protocol == "IP protocol 99"


def test_a_truncated_header_has_no_ports() -> None:
    frames = [
        ethernet(0x0800, ipv4(6, bytes(10))),
        ethernet(0x0800, ipv4(17, bytes(4))),
    ]

    capture = captures.parse(pcap_file(frames))

    assert [p.source_port for p in capture.packets] == [None, None]


def test_ipv6_is_read_with_its_extension_headers() -> None:
    options = bytes([6, 0]) + bytes(6)  # hop-by-hop: next is TCP, one block of eight
    frames = [
        ethernet(0x86DD, ipv6(17, udp(b"dns"))),
        ethernet(0x86DD, ipv6(0, options + tcp(0x10))),
        ethernet(0x86DD, ipv6(44, bytes([17]) + bytes(7))),
        ethernet(0x86DD, ipv6(58, bytes(8))),
    ]

    capture = captures.parse(pcap_file(frames))

    one, two, three, four = capture.packets
    assert (one.source, one.destination) == ("::1", "::2")
    assert (one.protocol, one.destination_port) == ("UDP", 53)
    assert (two.protocol, two.flags) == ("TCP", "ACK")
    assert (three.protocol, three.source_port) == ("UDP", None)
    assert four.protocol == "ICMPv6"


def test_a_frame_on_a_vlan_is_read_past_its_tag() -> None:
    inner = struct.pack(">HH", 100, 0x0800) + ipv4(17, udp())
    outer = struct.pack(">HH", 200, 0x8100) + inner

    (packet,) = captures.parse(pcap_file([ethernet(0x88A8, outer)])).packets

    assert packet.protocol == "UDP"


def test_arp_says_who_asks_for_whom() -> None:
    def arp(operation: int) -> bytes:
        return (
            struct.pack(">HHBBH", 1, 0x0800, 6, 4, operation)
            + bytes(6)
            + bytes([192, 168, 1, 20])
            + bytes(6)
            + bytes([192, 168, 1, 1])
        )

    capture = captures.parse(
        pcap_file([ethernet(0x0806, arp(1)), ethernet(0x0806, arp(2)), ethernet(0x0806, arp(9))])
    )

    request, reply, other = capture.packets
    assert (request.protocol, request.source, request.destination, request.flags) == (
        "ARP",
        "192.168.1.20",
        "192.168.1.1",
        "who has",
    )
    assert reply.flags == "is at"
    assert other.flags == ""


def test_frames_that_are_not_read_are_counted() -> None:
    short_arp = ethernet(0x0806, bytes(10))
    odd_arp = ethernet(0x0806, struct.pack(">HHBBH", 1, 0x0800, 8, 4, 1) + bytes(20))
    frames = [
        ethernet(0x88CC, bytes(30)),  # LLDP
        bytes(5),  # shorter than an Ethernet header
        short_arp,
        odd_arp,
        ethernet(0x0800, bytes(10)),  # an IPv4 packet that is too short
        ethernet(0x0800, b"\x65" + bytes(30)),  # not version 4
        ethernet(0x86DD, bytes(10)),
        ethernet(0x86DD, b"\x45" + bytes(50)),
        ethernet(0x8100, b"\x00"),  # a VLAN tag that is cut off
    ]

    capture = captures.parse(pcap_file(frames))

    assert capture.packets == []
    assert capture.total == 0
    assert capture.skipped == len(frames)


def test_raw_ip_and_linux_cooked_captures_are_read() -> None:
    raw = captures.parse(
        pcap_file([ipv4(17, udp()), ipv6(17, udp()), b""], link=101),
    )
    cooked_frame = bytes(14) + struct.pack(">H", 0x0800) + ipv4(6, tcp(0x02))
    cooked = captures.parse(pcap_file([cooked_frame, bytes(8)], link=113))

    assert [p.protocol for p in raw.packets] == ["UDP", "UDP"]
    assert raw.skipped == 1
    assert [p.flags for p in cooked.packets] == ["SYN"]
    assert cooked.skipped == 1


def test_what_is_not_a_capture_is_refused_in_words() -> None:
    with pytest.raises(CaptureFailed, match="only 3 bytes"):
        captures.parse(b"abc")
    with pytest.raises(CaptureFailed, match="classic pcap"):
        captures.parse(bytes.fromhex("0a0d0d0a") + bytes(40))
    with pytest.raises(CaptureFailed, match="type 105"):
        captures.parse(pcap_file([], link=105))


def test_it_says_if_an_address_is_one() -> None:
    assert captures.valid_host(" 192.168.1.20 ") == "192.168.1.20"
    assert captures.valid_host("FE80:0::1") == "fe80::1"
    assert captures.valid_host("example.com") is None
    assert captures.valid_host("1.2.3.4; rm") is None


# ---- Asking ntopng ----------------------------------------------------------------------------

LOCAL = netguard.HOME_NETWORK_AND_LOOPBACK


async def nothing(call: Call) -> None:
    return None


def target_of(
    session: Session, settings: Settings, handler: Handler, **options: Any
) -> tuple[Target, StubServer]:
    """A connection to a ntopng that answers as the handler does, ready to use, and the server."""
    server = StubServer(handler)
    connect(session, settings, server.url, **options)
    definition = registry.INTEGRATIONS["ntopng"]
    connection = definition.connection("api")
    assert connection is not None
    row = service.rows_for(session, "ntopng")["api"]
    return service.load_target(session, settings, definition, connection, row), server


def watching(handler: Handler) -> tuple[Handler, list[Seen]]:
    seen: list[Seen] = []

    def handle(request: Seen) -> Answer:
        seen.append(request)
        return handler(request)

    return handle, seen


def take(target: Target, seconds: int = 5) -> captures.Capture:
    return asyncio.run(captures.take(target, nothing, LOCAL, HOST, seconds))


def test_it_asks_for_the_seconds_of_the_host_and_reads_what_comes_back(
    session: Session, settings: Settings
) -> None:
    handle, seen = watching(ntopng(TOKEN, capture=sample_ntopng_capture(HOST)))
    target, server = target_of(session, settings, handle)

    taken = take(target)
    server.stop()

    assert taken.total == 6
    asked = seen[-1].target
    assert asked.startswith(captures.PATH)
    assert "host=192.168.1.20" in asked
    assert "duration=5" in asked
    assert "ifid=0" in asked


def test_the_seconds_are_kept_within_what_is_allowed(session: Session, settings: Settings) -> None:
    handle, seen = watching(ntopng(TOKEN, capture=sample_ntopng_capture(HOST)))
    target, server = target_of(session, settings, handle)

    take(target, 9999)
    take(target, -4)
    server.stop()

    assert f"duration={captures.MAX_SECONDS}" in seen[-2].target
    assert f"duration={captures.MIN_SECONDS}" in seen[-1].target


def test_it_captures_on_the_first_interface_ntopng_lists_when_none_is_chosen(
    session: Session, settings: Settings
) -> None:
    handle, seen = watching(ntopng(TOKEN, capture=sample_ntopng_capture(HOST)))
    target, server = target_of(session, settings, handle, interface_id="")

    take(target, 1)
    server.stop()

    assert "ifid=0" in seen[-1].target
    assert any(item.path.endswith("interfaces.lua") for item in seen)


def test_it_says_when_ntopng_lists_no_interface_to_capture_on(
    session: Session, settings: Settings
) -> None:
    def handle(request: Seen) -> Answer:
        if request.path.endswith("interfaces.lua"):
            return Answer(body=json.dumps({"rc": 0, "rc_str": "OK", "rsp": []}))
        return ntopng(TOKEN)(request)

    target, server = target_of(session, settings, handle, interface_id="")

    with pytest.raises(CaptureFailed, match="lists no interfaces"):
        take(target, 1)
    server.stop()


def test_it_says_when_ntopng_cannot_say_which_interfaces_it_has(
    session: Session, settings: Settings
) -> None:
    def handle(request: Seen) -> Answer:
        if request.path.endswith("interfaces.lua"):
            return Answer(status=302, headers={"Location": "/lua/login.lua"})
        return ntopng(TOKEN)(request)

    target, server = target_of(session, settings, handle, interface_id="")

    with pytest.raises(CaptureFailed, match="login page"):
        take(target, 1)
    server.stop()


def test_a_capture_larger_than_is_read_is_cut_there(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    big = pcap_file([ethernet_udp(HOST, PEER, 1, 2, b"x" * 200)] * 50)
    monkeypatch.setattr(captures, "MAX_BYTES", 1000)
    target, server = target_of(session, settings, ntopng(TOKEN, capture=big))

    taken = take(target, 1)
    server.stop()

    assert taken.cut is True
    assert 0 < taken.total < 50


def sends(reply: Answer) -> Handler:
    """A ntopng that sends this in place of a capture."""

    def handle(request: Seen) -> Answer:
        return reply if request.path == captures.PATH else ntopng(TOKEN)(request)

    return handle


JSON = {"Content-Type": "application/json"}
LOGIN = Answer(status=302, headers={"Location": "/lua/login.lua"})


@pytest.mark.parametrize(
    ("reply", "said"),
    [
        (LOGIN, "login page"),
        (Answer(status=400, body="{}"), "HTTP 400"),
        (Answer(status=500, body="no"), "HTTP 500"),
        (Answer(body=json.dumps({"error": "Not allowed"}), headers=JSON), "Not allowed"),
        (Answer(body="not json", headers=JSON), "sent a message instead of a capture"),
        (Answer(body=json.dumps({"status": "x"}), headers=JSON), "sent a message"),
        (Answer(body=b"not a pcap, though long enough to have a header"), "classic pcap"),
    ],
)
def test_it_says_why_a_capture_could_not_be_had(
    session: Session, settings: Settings, reply: Answer, said: str
) -> None:
    target, server = target_of(session, settings, sends(reply))

    with pytest.raises(CaptureFailed, match=said):
        take(target, 1)
    server.stop()


def test_it_says_when_ntopng_cannot_be_reached(session: Session, settings: Settings) -> None:
    target, server = target_of(session, settings, ntopng(TOKEN))
    server.stop()

    with pytest.raises(CaptureFailed):
        take(target, 1)


def test_it_signs_in_with_a_name_and_password_when_the_connection_does(
    session: Session, settings: Settings
) -> None:
    sent: list[str | None] = []

    def handle(request: Seen) -> Answer:
        sent.append(request.headers.get("authorization"))
        if request.path == captures.PATH:
            return Answer(body=sample_ntopng_capture(HOST))
        return ntopng(TOKEN)(request)

    target, server = target_of(session, settings, handle, basic=True)

    taken = take(target)
    server.stop()

    assert taken.total == 6
    assert sent[-1] is not None
    assert sent[-1].startswith("Basic ")
