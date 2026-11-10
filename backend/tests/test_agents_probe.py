"""Testing the devices on the network: which devices, which ports, and that nothing but a
connection is made."""

import socket
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

from sqlalchemy.orm import Session

from app.agents import probe
from app.integrations import netguard
from app.models import Device, DeviceAddress

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def device(
    session: Session,
    number: int,
    *addresses: str,
    name: str | None = None,
    seen: timedelta = timedelta(minutes=5),
) -> Device:
    found = Device(
        mac=f"aa:bb:cc:00:00:{number:02x}",
        hostname=name,
        first_seen_at=NOW - timedelta(days=30),
        last_seen_at=NOW - seen,
    )
    session.add(found)
    session.flush()
    for index, address in enumerate(addresses):
        session.add(
            DeviceAddress(
                device_id=found.id,
                address=ip_address(address),
                first_seen_at=NOW - timedelta(days=30),
                last_seen_at=NOW - timedelta(minutes=index + 1),
            )
        )
    session.flush()
    return found


def test_the_devices_tested_are_the_ones_seen_lately_at_an_address_on_the_home_network(
    session: Session,
) -> None:
    device(session, 1, "192.168.1.10", name="nas")
    device(session, 2, "8.8.8.8")
    device(session, 3, "192.168.1.30", seen=probe.SEEN_WITHIN + timedelta(days=1))
    device(session, 4, "fe80::1")
    device(session, 5, "10.0.0.5", "192.168.1.11")

    chosen, left_out = probe.targets(session, NOW, netguard.HOME_NETWORK)

    assert [(target.name, target.address) for target in chosen] == [
        ("nas", "192.168.1.10"),
        (None, "10.0.0.5"),
    ]
    assert left_out == 0


def test_an_address_two_devices_have_had_is_tested_once(session: Session) -> None:
    device(session, 1, "192.168.1.10", seen=timedelta(minutes=1))
    device(session, 2, "192.168.1.10", seen=timedelta(minutes=2))

    chosen, _ = probe.targets(session, NOW, netguard.HOME_NETWORK)

    assert [target.address for target in chosen] == ["192.168.1.10"]


def test_no_more_than_the_limit_are_tested_and_the_rest_are_counted(session: Session) -> None:
    for number in range(probe.MAX_HOSTS + 3):
        device(session, number, f"192.168.1.{number + 10}", seen=timedelta(minutes=number))

    chosen, left_out = probe.targets(session, NOW, netguard.HOME_NETWORK)

    assert len(chosen) == probe.MAX_HOSTS
    assert left_out == 3


def test_a_scan_reports_the_ports_that_answered_the_most_serious_first(session: Session) -> None:
    device(session, 1, "192.168.1.10", name="camera")
    device(session, 2, "192.168.1.11")
    asked: list[tuple[str, int, float]] = []

    def connect(address: str, port: int, timeout: float) -> bool:
        asked.append((address, port, timeout))
        return (address, port) in {
            ("192.168.1.10", 23),
            ("192.168.1.10", 80),
            ("192.168.1.11", 6379),
        }

    found = probe.scan(session, NOW, connect=connect)

    assert found.tested == 2
    assert len(asked) == 2 * len(probe.PORTS)
    assert {timeout for _, _, timeout in asked} == {probe.TIMEOUT}
    assert [(hit.target.address, hit.port) for hit in found.hits] == [
        ("192.168.1.10", 23),
        ("192.168.1.11", 6379),
        ("192.168.1.10", 80),
    ]
    assert probe.line(found.hits[0]) == (
        "camera (192.168.1.10): port 23 (Telnet) is open. "
        "A remote login that sends everything, passwords included, in the clear."
    )
    assert probe.summary(found) == "tested 2 devices, 3 open ports"


def test_a_scan_that_finds_nothing_says_so(session: Session) -> None:
    device(session, 1, "192.168.1.10")

    found = probe.scan(session, NOW, connect=lambda address, port, timeout: False)

    assert found.hits == []
    assert probe.summary(found) == "tested 1 device, nothing risky answered"


def test_one_open_port_is_not_plural(session: Session) -> None:
    device(session, 1, "192.168.1.10")

    found = probe.scan(session, NOW, connect=lambda address, port, timeout: port == 22)

    assert probe.summary(found) == "tested 1 device, 1 open port"


def test_a_scan_does_not_reach_past_the_policy(session: Session) -> None:
    device(session, 1, "127.0.0.1")
    asked: list[str] = []

    def connect(address: str, port: int, timeout: float) -> bool:
        asked.append(address)
        return False

    probe.scan(session, NOW, connect=connect)
    assert asked == []

    probe.scan(session, NOW, policy=netguard.HOME_NETWORK_AND_LOOPBACK, connect=connect)
    assert set(asked) == {"127.0.0.1"}


def test_a_connection_is_made_and_closed_and_nothing_is_sent() -> None:
    received: list[bytes] = []
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        listener.settimeout(2)

        assert probe.connects("127.0.0.1", port, 1.0) is True

        connection, _ = listener.accept()
        with connection:
            connection.settimeout(1)
            received.append(connection.recv(100))
    assert received == [b""]


def test_a_closed_port_is_not_open() -> None:
    with socket.socket() as spare:
        spare.bind(("127.0.0.1", 0))
        port = spare.getsockname()[1]

    assert probe.connects("127.0.0.1", port, 0.5) is False


def test_a_device_with_no_name_is_known_by_its_address() -> None:
    assert probe.Target(1, None, "192.168.1.5").label == "192.168.1.5"
