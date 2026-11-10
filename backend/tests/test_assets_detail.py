"""An asset's page: what the detail endpoint says of one asset, and the traffic it is worked out
from. The keys are the ones the Assets list gives, as the page is reached from it."""

from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets import detail, inventory
from app.config import Settings
from app.events.event import Severity
from app.intel import store as intel_store
from app.intel import subjects, virustotal
from app.metrics.store import record as record_samples
from app.models import DeviceAddress, IntegrationConnection, Interface, User, utcnow
from e2e import factories
from e2e.factories import AssetSpec, EventSpec, HostSpec, IncidentSpec, Listed, VerdictSpec
from tests.helpers import new_sample

BASE = "/api/assets"
LAPTOP = "00:11:22:0a:0b:0c"
PHONE = "02:aa:bb:cc:dd:ee"
DESKTOP = "00:11:22:0a:0b:0e"
LAPTOP_IP = "192.168.1.20"
# What ntopng read of the laptop, an hour apart, the last one now: its counters rise, and the sent
# one starts again before the last reading, which is what it has sent since.
SENT = (1000, 3000, 1000, 4000)
RECEIVED = (500, 600, 700, 900)


def stock(session: Session) -> None:
    """A home network with a laptop that had another address before, a phone with none, a desktop,
    and the laptop's Wazuh agent, as the integrations list them."""
    session.add(Interface(name="Home", role="home", networks=["192.168.1.0/24"], position=0))
    session.add(
        IntegrationConnection(integration="opnsense", connection="api", base_url="https://fw.lan")
    )
    factories.assets(
        session,
        utcnow(),
        [
            AssetSpec(
                hostname="laptop",
                mac=LAPTOP,
                vendor="Example Devices Inc.",
                addresses=(LAPTOP_IP,),
                earlier=("192.168.1.19",),
                listed=(Listed("opnsense", "arp", 1), Listed("opnsense", "dhcp", 4)),
            ),
            AssetSpec(hostname="phone", mac=PHONE, listed=(Listed("opnsense", "dhcp", 30),)),
            AssetSpec(hostname="desktop", mac=DESKTOP, addresses=("192.168.1.30",)),
        ],
        [HostSpec("002", hostname="laptop", address=LAPTOP_IP)],
    )
    session.commit()


def key_of(session: Session, name: str) -> str:
    """The key the Assets list gives the asset with this name."""
    return next(item.key for item in inventory.load(session, utcnow()).assets if item.name == name)


def page_of(client: TestClient, session: Session, name: str) -> Any:
    return client.get(f"{BASE}/{key_of(session, name)}").json()


def record_traffic(session: Session, settings: Settings, now: datetime) -> datetime:
    """Records the laptop's ntopng counters, with the desktop's, which must not count towards the
    laptop, and a firewall's sent count for the laptop, which is not ntopng's. Returns the start of
    the current hour."""
    base = now.replace(minute=0, second=0, microsecond=0)
    factories.traffic(
        session,
        settings,
        now,
        [
            factories.TrafficSpec(LAPTOP_IP, sent=SENT, received=RECEIVED),
            factories.TrafficSpec("192.168.1.30", sent=(0, 5_000_000, 0, 9_000_000)),
        ],
    )
    record_samples(
        session,
        settings,
        [
            new_sample(
                source="opnsense",
                connection="api",
                name="host.bytes_sent",
                value=1,
                sampled_at=base - timedelta(hours=1),
                labels={"host": LAPTOP_IP},
            ),
            new_sample(
                source="opnsense",
                connection="api",
                name="host.bytes_sent",
                value=1_000_000_000,
                sampled_at=base,
                labels={"host": LAPTOP_IP},
            ),
        ],
        now,
    )
    session.commit()
    return base


def test_it_is_for_someone_signed_in(client: TestClient, account: User) -> None:
    assert client.get(f"{BASE}/device-1").status_code == 401


@pytest.mark.parametrize("key", ["device-999", "host-999"])
def test_an_asset_that_is_not_on_the_list_has_no_page(
    client: TestClient, csrf_token: str, session: Session, key: str
) -> None:
    stock(session)

    assert client.get(f"{BASE}/{key}").status_code == 404


def test_an_asset_on_the_internet_side_has_no_page(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    stock(session)
    factories.assets(
        session,
        utcnow(),
        [
            AssetSpec(
                vendor="Example Cable Inc.",
                mac="00:11:22:0a:0b:0f",
                addresses=("9.9.9.1",),
                listed=(Listed("opnsense", "arp", 1),),
            )
        ],
        [],
    )
    session.commit()
    device = session.scalars(
        select(DeviceAddress.device_id).where(DeviceAddress.address == ip_address("9.9.9.1"))
    ).one()

    assert client.get(f"{BASE}/device-{device}").status_code == 404


@pytest.mark.parametrize(
    "key",
    ["laptop", "device-0", "device-01", "host-", "dev-1", "device-12345678901234567890"],
)
def test_a_key_that_is_not_one_is_refused(client: TestClient, csrf_token: str, key: str) -> None:
    assert client.get(f"{BASE}/{key}").status_code == 422


def test_a_device_page_says_what_it_is_and_where_it_has_been_seen(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    stock(session)

    body = page_of(client, session, "laptop")

    assert (body["asset"]["kind"], body["asset"]["name"], body["asset"]["status"]) == (
        "device",
        "laptop",
        "online",
    )
    current, earlier = body["addresses"]
    assert (current["address"], current["current"]) == (LAPTOP_IP, True)
    assert (earlier["address"], earlier["current"]) == ("192.168.1.19", False)
    assert datetime.fromisoformat(earlier["last_seen_at"]) < datetime.fromisoformat(
        current["last_seen_at"]
    )
    assert body["networks"] == [{"id": body["asset"]["interfaces"][0], "name": "Home"}]
    assert [(item["source_name"], item["via"]) for item in body["asset"]["listings"]] == [
        ("OPNsense", "arp"),
        ("OPNsense", "dhcp"),
        ("Wazuh", "agent"),
    ]
    phone = page_of(client, session, "phone")
    assert (phone["networks"], phone["addresses"]) == ([], [])


def test_traffic_is_not_measured_until_ntopng_has_read_it(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    stock(session)

    for name in ("laptop", "phone"):
        traffic = page_of(client, session, name)["traffic"]
        assert (traffic["measured"], traffic["sent_day"], traffic["received_week"]) == (
            False,
            0.0,
            0.0,
        )
        assert all(item["sent"] is None for item in traffic["hours"] + traffic["days"])


def test_each_hour_is_the_rise_in_what_ntopng_counted(session: Session, settings: Settings) -> None:
    stock(session)
    now = utcnow()
    base = record_traffic(session, settings, now)

    found = detail.load(session, key_of(session, "laptop"), now)

    assert found is not None
    traffic = found.traffic
    assert traffic.measured is True
    assert (len(traffic.hours), len(traffic.days)) == (168, 7)
    assert traffic.hours[-1].at == base
    # The first reading of each counter has nothing before it to rise from, so its hour is not
    # measured, and the sent counter's reset counts what it has sent since.
    assert traffic.hours[0].sent is None
    assert [item.sent for item in traffic.hours[-4:]] == [None, 2000.0, 1000.0, 3000.0]
    assert [item.received for item in traffic.hours[-4:]] == [None, 100.0, 100.0, 200.0]
    assert (traffic.days[-1].sent, traffic.days[-1].received) == (6000.0, 400.0)


def test_the_day_and_the_week_add_up_what_was_measured(
    client: TestClient, csrf_token: str, session: Session, settings: Settings
) -> None:
    stock(session)
    record_traffic(session, settings, utcnow())

    traffic = page_of(client, session, "laptop")["traffic"]

    assert traffic["measured"] is True
    assert (traffic["sent_day"], traffic["received_day"]) == (6000.0, 400.0)
    assert (traffic["sent_week"], traffic["received_week"]) == (6000.0, 400.0)
    assert (len(traffic["hours"]), len(traffic["days"])) == (24, 7)


def test_events_its_addresses_were_in_are_listed_latest_first_with_who_sent_them(
    client: TestClient, csrf_token: str, session: Session, settings: Settings
) -> None:
    stock(session)
    factories.events(
        session,
        settings,
        utcnow(),
        [
            EventSpec(
                src_address=LAPTOP_IP,
                dst_address="52.1.2.3",
                dst_port=443,
                protocol="tcp",
                summary="Allowed tcp to 52.1.2.3:443",
                seconds_ago=120,
            ),
            EventSpec(
                source="wazuh",
                connection="indexer",
                kind="alert",
                severity=Severity.HIGH,
                src_address="52.1.2.4",
                src_port=22,
                dst_address=LAPTOP_IP,
                summary="sshd: authentication failed",
                seconds_ago=60,
            ),
            EventSpec(dst_address=LAPTOP_IP, summary="Blocked from nowhere", seconds_ago=180),
            EventSpec(src_address=LAPTOP_IP, summary="Blocked to nowhere", seconds_ago=240),
            EventSpec(
                src_address=LAPTOP_IP,
                dst_address="52.1.2.3",
                summary="Two days old",
                seconds_ago=2 * 24 * 3600,
            ),
            EventSpec(
                src_address=LAPTOP_IP,
                dst_address="52.1.2.3",
                summary="Eight days old",
                seconds_ago=8 * 24 * 3600,
            ),
            EventSpec(src_address="192.168.1.30", dst_address="52.1.2.5", summary="Not its"),
        ],
    )
    session.commit()

    body = page_of(client, session, "laptop")

    assert [(item["summary"], item["outbound"]) for item in body["events"]] == [
        ("sshd: authentication failed", False),
        ("Allowed tcp to 52.1.2.3:443", True),
        ("Blocked from nowhere", False),
        ("Blocked to nowhere", True),
        ("Two days old", True),
    ]
    assert (body["events_day"], body["events_week"]) == (4, 5)
    assert body["events"][0]["source_name"] == "Wazuh"
    assert [item["severity"] for item in body["events"][:2]] == ["high", "info"]
    assert (body["events"][2]["src_address"], body["events"][2]["dst_address"]) == (
        None,
        LAPTOP_IP,
    )
    assert (body["events"][3]["src_address"], body["events"][3]["dst_address"]) == (
        LAPTOP_IP,
        None,
    )


def test_only_the_latest_events_are_shown_but_all_of_them_are_counted(
    client: TestClient, csrf_token: str, session: Session, settings: Settings
) -> None:
    stock(session)
    factories.events(
        session,
        settings,
        utcnow(),
        [EventSpec(src_address=LAPTOP_IP, dst_address="52.1.2.3", repeat=30)],
    )
    session.commit()

    body = page_of(client, session, "laptop")

    assert (len(body["events"]), body["events_day"], body["events_week"]) == (25, 30, 30)


def test_it_talks_to_and_is_contacted_by_the_addresses_it_was_seen_with(
    client: TestClient, csrf_token: str, session: Session, settings: Settings
) -> None:
    stock(session)
    factories.events(
        session,
        settings,
        utcnow(),
        [
            EventSpec(src_address=LAPTOP_IP, dst_address="52.1.2.3", repeat=3, seconds_ago=120),
            EventSpec(src_address=LAPTOP_IP, dst_address="52.1.2.4", seconds_ago=120),
            # Between its own addresses, and with nobody at the other end: neither is a peer.
            EventSpec(src_address=LAPTOP_IP, dst_address="192.168.1.19", seconds_ago=120),
            EventSpec(src_address="192.168.1.19", dst_address=LAPTOP_IP, seconds_ago=120),
            EventSpec(src_address=LAPTOP_IP, seconds_ago=120),
            # A week ago is too long ago to be a peer now.
            EventSpec(src_address=LAPTOP_IP, dst_address="52.1.2.7", seconds_ago=8 * 24 * 3600),
            EventSpec(src_address="52.1.2.9", dst_address=LAPTOP_IP, repeat=2, seconds_ago=120),
            EventSpec(src_address="192.168.1.30", dst_address=LAPTOP_IP, seconds_ago=120),
        ],
    )
    session.commit()

    body = page_of(client, session, "laptop")

    assert [(item["address"], item["events"]) for item in body["talks_to"]] == [
        ("52.1.2.3", 3),
        ("52.1.2.4", 1),
    ]
    assert [(item["address"], item["events"]) for item in body["contacted_by"]] == [
        ("52.1.2.9", 2),
        ("192.168.1.30", 1),
    ]


REPORT = virustotal.Report(
    malicious=4,
    suspicious=1,
    harmless=60,
    undetected=20,
    reputation=-9,
    analysed_at=datetime(2026, 11, 7, tzinfo=UTC),
    country="NL",
    owner="Example Hosting",
)


def test_each_peer_says_which_ports_were_used_at_the_far_end_the_most_used_first(
    client: TestClient, csrf_token: str, session: Session, settings: Settings
) -> None:
    stock(session)
    factories.events(
        session,
        settings,
        utcnow(),
        [
            EventSpec(
                src_address=LAPTOP_IP,
                dst_address="52.1.2.3",
                dst_port=443,
                protocol="tcp",
                repeat=3,
            ),
            EventSpec(
                src_address=LAPTOP_IP, dst_address="52.1.2.3", dst_port=53, protocol="udp", repeat=2
            ),
            # Without a port, and to other peers' ports, they add to no port of this peer.
            EventSpec(src_address=LAPTOP_IP, dst_address="52.1.2.3"),
            EventSpec(src_address=LAPTOP_IP, dst_address="52.1.2.4", dst_port=22, protocol="tcp"),
            # Contacted by: the port is the one on the asset that the peer reached.
            EventSpec(
                src_address="52.1.2.9",
                dst_address=LAPTOP_IP,
                dst_port=3389,
                protocol="tcp",
                repeat=2,
            ),
        ]
        + [
            EventSpec(src_address=LAPTOP_IP, dst_address="52.1.2.5", dst_port=1000 + n, repeat=1)
            for n in range(6)
        ],
    )
    session.commit()

    body = page_of(client, session, "laptop")

    ports = {
        item["address"]: [(p["port"], p["protocol"], p["events"]) for p in item["ports"]]
        for item in body["talks_to"] + body["contacted_by"]
    }
    assert ports["52.1.2.3"] == [(443, "tcp", 3), (53, "udp", 2)]
    assert ports["52.1.2.4"] == [(22, "tcp", 1)]
    assert len(ports["52.1.2.5"]) == detail.PORTS_SHOWN
    assert ports["52.1.2.9"] == [(3389, "tcp", 2)]


def test_a_peer_with_no_port_has_none_listed(
    client: TestClient, csrf_token: str, session: Session, settings: Settings
) -> None:
    stock(session)
    factories.events(
        session, settings, utcnow(), [EventSpec(src_address=LAPTOP_IP, dst_address="52.1.2.3")]
    )
    session.commit()

    [peer] = page_of(client, session, "laptop")["talks_to"]

    assert peer["ports"] == []


def test_a_peer_shows_what_threat_intelligence_kept_of_it_and_asks_nothing(
    client: TestClient, csrf_token: str, session: Session, settings: Settings
) -> None:
    stock(session)
    factories.events(
        session,
        settings,
        utcnow(),
        [
            EventSpec(src_address=LAPTOP_IP, dst_address="52.1.2.3", repeat=3),
            EventSpec(src_address=LAPTOP_IP, dst_address="52.1.2.4", repeat=2),
            EventSpec(src_address=LAPTOP_IP, dst_address="52.1.2.6"),
            EventSpec(src_address=LAPTOP_IP, dst_address="192.168.1.30"),
        ],
    )
    now = utcnow()
    intel_store.keep(
        session,
        virustotal.PROVIDER,
        subjects.parse("52.1.2.3"),
        virustotal.Reported(REPORT),
        now,
    )
    intel_store.keep(
        session, virustotal.PROVIDER, subjects.parse("52.1.2.4"), virustotal.Unknown(), now
    )
    # Kept for a private address, which is never asked about, so never shown.
    intel_store.keep(
        session,
        virustotal.PROVIDER,
        subjects.of_address(ip_address("192.168.1.30")),
        virustotal.Reported(REPORT),
        now,
    )
    session.commit()

    peers = {item["address"]: item for item in page_of(client, session, "laptop")["talks_to"]}

    flagged = peers["52.1.2.3"]["standing"]
    assert (flagged["judgement"], flagged["malicious"], flagged["suspicious"]) == (
        "malicious",
        4,
        1,
    )
    assert (flagged["engines"], flagged["owner"], flagged["country"]) == (
        85,
        "Example Hosting",
        "NL",
    )
    assert peers["52.1.2.3"]["internal"] is False
    assert peers["52.1.2.4"]["standing"]["judgement"] == "unknown"
    assert peers["52.1.2.6"]["standing"] is None
    assert (peers["192.168.1.30"]["internal"], peers["192.168.1.30"]["standing"]) == (True, None)


def test_incidents_its_addresses_are_in_are_listed(
    client: TestClient, csrf_token: str, session: Session, settings: Settings
) -> None:
    stock(session)
    factories.incidents(
        session,
        settings,
        utcnow(),
        [
            IncidentSpec(address="9.9.9.9", device=LAPTOP_IP),
            # Ten hours on, so that it is an incident of its own: close attacks of one kind are one.
            IncidentSpec(address="9.9.9.8", device="192.168.1.30", minutes_ago=600),
        ],
    )
    session.commit()

    body = page_of(client, session, "laptop")
    desktop = page_of(client, session, "desktop")

    assert [(item["sources"], item["status"]) for item in body["incidents"]] == [
        (["wazuh"], "open")
    ]
    assert body["incidents"][0]["signal_count"] >= 1
    assert body["incidents"][0]["severity"] == "high"
    assert [item["id"] for item in desktop["incidents"]] != [
        item["id"] for item in body["incidents"]
    ]
    assert len(desktop["incidents"]) == 1


def test_the_verdicts_given_about_its_addresses_are_listed_latest_first(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    stock(session)
    factories.verdicts(
        session,
        [
            VerdictSpec(
                verdict="not_suspicious",
                address=LAPTOP_IP,
                destination="52.1.2.0/24",
                note="Its own cloud",
            ),
            VerdictSpec(verdict="low_priority", address=LAPTOP_IP, signature="Port scan"),
            VerdictSpec(verdict="threat", address="192.168.1.30", note="Not the laptop"),
        ],
    )
    session.commit()

    body = page_of(client, session, "laptop")

    assert [
        (item["verdict"], item["destination"], item["signature"], item["note"])
        for item in body["verdicts"]
    ] == [
        ("low_priority", None, "Port scan", None),
        ("not_suspicious", "52.1.2.0/24", None, "Its own cloud"),
    ]
    assert {item["address"] for item in body["verdicts"]} == {LAPTOP_IP}


def test_a_machine_is_on_its_own_page_with_what_its_programs_say(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    factories.assets(
        session,
        utcnow(),
        [],
        [
            HostSpec("003", hostname="printer", address="192.168.1.50"),
            HostSpec("009", hostname="kiosk"),
        ],
    )
    session.commit()

    printer = page_of(client, session, "printer")
    kiosk = page_of(client, session, "kiosk")

    assert printer["asset"]["kind"] == "host"
    assert [(item["address"], item["current"]) for item in printer["addresses"]] == [
        ("192.168.1.50", True)
    ]
    # A machine's own address has the machine's times: it has no rows of a device's.
    assert printer["addresses"][0]["first_seen_at"] == printer["asset"]["first_seen_at"]
    assert printer["traffic"]["measured"] is False
    assert (kiosk["asset"]["kind"], kiosk["addresses"], kiosk["networks"]) == ("host", [], [])
    assert (kiosk["events"], kiosk["events_day"], kiosk["events_week"]) == ([], 0, 0)
    assert (kiosk["talks_to"], kiosk["contacted_by"]) == ([], [])
    assert (kiosk["incidents"], kiosk["verdicts"], kiosk["traffic"]["measured"]) == (
        [],
        [],
        False,
    )


def test_an_address_a_machine_brought_in_has_the_times_of_the_device(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    stock(session)
    factories.assets(
        session,
        utcnow(),
        [],
        [HostSpec("004", hostname="laptop", address="192.168.1.99")],
    )
    session.commit()

    body = page_of(client, session, "laptop")
    brought_in = next(item for item in body["addresses"] if item["address"] == "192.168.1.99")

    assert (brought_in["first_seen_at"], brought_in["last_seen_at"]) == (
        body["asset"]["first_seen_at"],
        body["asset"]["last_seen_at"],
    )
