"""Looking through what NVD and Fingerbank said, which asks neither anything."""

from datetime import UTC, date, datetime, timedelta
from ipaddress import ip_address

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Device, DeviceAddress, DeviceIdentity, NvdCve

CVES = "/api/threat-intel/cves"
DEVICES = "/api/threat-intel/devices"
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def cve(session: Session, cve_id: str, minutes: int, **fields: object) -> NvdCve:
    row = NvdCve(
        **{"state": "found", **fields},
        cve_id=cve_id,
        checked_at=NOW - timedelta(minutes=minutes),
    )
    session.add(row)
    return row


def three_cves(session: Session) -> None:
    cve(
        session,
        "CVE-2021-44228",
        1,
        status="Analyzed",
        cvss_version="3.1",
        score=10.0,
        severity="CRITICAL",
        vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
        description="Apache Log4j2 JNDI features do not protect against attacker controlled LDAP.",
        weaknesses=["CWE-502", "CWE-917"],
        exploited=True,
        exploited_on=date(2021, 12, 10),
        action_due=date(2021, 12, 24),
        required_action="Apply updates per vendor instructions.",
        kev_name="Apache Log4j2 Remote Code Execution Vulnerability",
        published_at=NOW - timedelta(days=900),
    )
    cve(
        session,
        "CVE-2024-0001",
        2,
        cvss_version="3.1",
        score=5.3,
        severity="MEDIUM",
        description="A 100%_odd flaw in a printer.",
        weaknesses=["CWE-79"],
    )
    cve(session, "CVE-2026-9999", 3, state="unknown", weaknesses=[])
    session.commit()


def test_the_cves_kept_need_a_sign_in(client: TestClient) -> None:
    assert client.get(CVES).status_code == 401
    assert client.get(DEVICES).status_code == 401


def test_the_cves_kept_come_with_what_nvd_said_and_the_notice_it_asks_for(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    three_cves(session)

    body = client.get(CVES).json()

    assert body["notice"].startswith("This product uses data from the NVD API")
    assert body["total"] == 3
    assert body["counts"] == {
        "critical": 1,
        "high": 0,
        "medium": 1,
        "low": 0,
        "unrated": 1,
        "exploited": 1,
    }
    assert [item["cve_id"] for item in body["items"]] == [
        "CVE-2021-44228",
        "CVE-2024-0001",
        "CVE-2026-9999",
    ]
    first, _, unknown = body["items"]
    assert (first["rating"], first["score"], first["exploited"]) == ("critical", 10.0, True)
    assert first["weaknesses"] == ["CWE-502", "CWE-917"]
    assert first["kev_name"] == "Apache Log4j2 Remote Code Execution Vulnerability"
    assert first["link"] == "https://nvd.nist.gov/vuln/detail/CVE-2021-44228"
    assert (unknown["state"], unknown["rating"], unknown["score"]) == ("unknown", "unrated", None)


def test_the_cves_are_narrowed_by_rating_or_by_being_exploited_and_the_counts_stay_whole(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    three_cves(session)

    medium = client.get(CVES, params={"rating": "medium"}).json()
    unrated = client.get(CVES, params={"rating": "unrated"}).json()
    exploited = client.get(CVES, params={"exploited": "true"}).json()

    assert [item["cve_id"] for item in medium["items"]] == ["CVE-2024-0001"]
    assert medium["total"] == 1
    assert medium["counts"]["critical"] == 1
    assert [item["cve_id"] for item in unrated["items"]] == ["CVE-2026-9999"]
    assert [item["cve_id"] for item in exploited["items"]] == ["CVE-2021-44228"]


def test_a_score_of_none_is_unrated(client: TestClient, csrf_token: str, session: Session) -> None:
    cve(session, "CVE-2020-0001", 1, score=0.0, severity="NONE", weaknesses=[])
    session.commit()

    [item] = client.get(CVES).json()["items"]

    assert item["rating"] == "unrated"
    assert client.get(CVES).json()["counts"]["unrated"] == 1


def test_the_cves_are_found_by_identifier_description_name_or_weakness_and_nothing_is_a_wildcard(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    three_cves(session)

    def found(text: str) -> list[str]:
        return [item["cve_id"] for item in client.get(CVES, params={"q": text}).json()["items"]]

    assert found("2021-44") == ["CVE-2021-44228"]
    assert found("log4j2") == ["CVE-2021-44228"]
    assert found("remote code") == ["CVE-2021-44228"]
    assert found("cwe-79") == ["CVE-2024-0001"]
    assert found("100%_odd") == ["CVE-2024-0001"]
    assert found("%") == ["CVE-2024-0001"]
    assert found("\\") == []
    assert found("nothing like it") == []


def test_the_cves_come_a_page_at_a_time(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    three_cves(session)

    first = client.get(CVES, params={"limit": 2}).json()
    second = client.get(CVES, params={"limit": 2, "offset": 2}).json()

    assert (first["total"], len(first["items"])) == (3, 2)
    assert [item["cve_id"] for item in second["items"]] == ["CVE-2026-9999"]
    assert client.get(CVES, params={"limit": 0}).status_code == 422
    assert client.get(CVES, params={"rating": "huge"}).status_code == 422


def identified(
    session: Session, mac: str, minutes: int, state: str = "identified", **fields: object
) -> Device:
    device = Device(
        mac=mac,
        hostname=str(fields.pop("hostname", "")) or None,
        vendor=str(fields.pop("vendor", "")) or None,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    session.add(device)
    session.flush()
    session.add(
        DeviceIdentity(
            device_id=device.id,
            source="fingerbank",
            state=state,
            reason="asset",
            checked_at=NOW - timedelta(minutes=minutes),
            **fields,
        )
    )
    return device


def three_devices(session: Session) -> None:
    phone = identified(
        session,
        "aa:bb:cc:00:11:22",
        1,
        hostname="annes-phone",
        vendor="Apple",
        name="Apple iPhone 16",
        path="Phone, Tablet, or Wearable/Apple iOS/Apple iPhone/Apple iPhone 16",
        manufacturer="Apple Inc.",
        operating_system="Apple iOS",
        score=87,
        external_id=1234,
    )
    session.add_all(
        [
            DeviceAddress(
                device_id=phone.id,
                address=ip_address("192.168.1.20"),
                first_seen_at=NOW,
                last_seen_at=NOW - timedelta(days=1),
            ),
            DeviceAddress(
                device_id=phone.id,
                address=ip_address("192.168.1.21"),
                first_seen_at=NOW,
                last_seen_at=NOW,
            ),
        ]
    )
    identified(session, "aa:bb:cc:00:11:33", 2, state="unknown", hostname="mystery")
    identified(session, "02:bb:cc:00:11:44", 3, state="private")
    session.commit()


def test_the_devices_kept_come_with_what_fingerbank_said_and_the_address_they_had_last(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    three_devices(session)

    body = client.get(DEVICES).json()

    assert body["total"] == 3
    assert body["counts"] == {"identified": 1, "unknown": 1, "private": 1}
    assert [item["state"] for item in body["items"]] == ["identified", "unknown", "private"]
    phone = body["items"][0]
    assert (phone["name"], phone["manufacturer"], phone["operating_system"]) == (
        "Apple iPhone 16",
        "Apple Inc.",
        "Apple iOS",
    )
    assert (phone["score"], phone["hostname"], phone["vendor"]) == (87, "annes-phone", "Apple")
    assert (phone["mac"], phone["address"]) == ("aa:bb:cc:00:11:22", "192.168.1.21")
    assert phone["reason"] == "asset"
    assert body["items"][1]["address"] is None


def test_the_devices_are_narrowed_by_state_and_found_by_what_they_are_or_where_they_are(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    three_devices(session)

    def found(**params: object) -> list[str]:
        items = client.get(DEVICES, params=params).json()["items"]  # type: ignore[arg-type]
        return [item["mac"] for item in items]

    assert found(state="unknown") == ["aa:bb:cc:00:11:33"]
    assert found(q="iphone") == ["aa:bb:cc:00:11:22"]
    assert found(q="ios") == ["aa:bb:cc:00:11:22"]
    assert found(q="annes") == ["aa:bb:cc:00:11:22"]
    assert found(q="apple inc") == ["aa:bb:cc:00:11:22"]
    assert found(q="02:bb") == ["02:bb:cc:00:11:44"]
    assert found(q="192.168.1.21") == ["aa:bb:cc:00:11:22"]
    assert found(q="%") == []
    assert found(q="iphone", state="private") == []
    counts = client.get(DEVICES, params={"q": "iphone", "state": "private"}).json()["counts"]
    assert counts == {"identified": 1, "unknown": 0, "private": 0}


def test_the_devices_come_a_page_at_a_time(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    three_devices(session)

    page = client.get(DEVICES, params={"limit": 1, "offset": 1}).json()

    assert (page["total"], [item["state"] for item in page["items"]]) == (3, ["unknown"])
    assert client.get(DEVICES, params={"state": "gone"}).status_code == 422
