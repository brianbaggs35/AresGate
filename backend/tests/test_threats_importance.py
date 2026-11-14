"""Which devices matter, and what that does to the incidents that touched them."""

from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AssetProfile, Device, DeviceAddress, HostListing, Incident
from app.threats import importance
from app.threats.importance import Touch
from tests.test_incidents_engine import ATTACKER, DEVICE, alert, run, store
from tests.test_threats_families import incident as make_incident

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
OTHER = "192.168.1.30"


def device(
    session: Session,
    number: int,
    address: str,
    *,
    kind: str | None = None,
    importance_: str = "normal",
    hostname: str | None = None,
    seen: datetime = NOW,
) -> Device:
    """A device with one address and, if it has a kind, what the owner said of it."""
    found = Device(
        mac=f"aa:bb:cc:00:00:{number:02x}",
        hostname=hostname,
        first_seen_at=seen,
        last_seen_at=seen,
    )
    session.add(found)
    session.flush()
    session.add(
        DeviceAddress(
            device_id=found.id, address=ip_address(address), first_seen_at=seen, last_seen_at=seen
        )
    )
    if kind is not None:
        session.add(
            AssetProfile(
                key=f"device-{found.id}",
                kind=kind,
                importance=importance_,
                updated_at=NOW,
            )
        )
    session.flush()
    return found


def touching(session: Session, *addresses: str, **changes: Any) -> Incident:
    return make_incident(
        session,
        "203.0.113.9",
        addresses=[ip_address(address) for address in ("203.0.113.9", *addresses)],
        **changes,
    )


def stored(session: Session, found: Incident) -> int:
    session.expire_all()
    value = session.get(Incident, found.id)
    assert value is not None
    return value.importance


class TestWhatAnAssetCountsFor:
    @pytest.mark.parametrize(
        ("said", "kind", "counts"),
        [
            ("critical", "nas", 2),
            ("critical", "guest", 2),
            ("important", "server", 1),
            ("important", "smart_home", 1),
            ("normal", "guest", -1),
            ("normal", "smart_home", -1),
            ("normal", "laptop", 0),
        ],
    )
    def test_what_the_owner_said_counts_over_what_it_is(
        self, said: str, kind: str, counts: int
    ) -> None:
        assert importance.weight(said, kind) == counts

    def test_it_is_said_in_a_word(self) -> None:
        assert [importance.word(each) for each in (2, 1, 0, -1)] == [
            "critical",
            "important",
            "normal",
            "low",
        ]

    def test_the_kinds_that_usually_matter_offer_it(self) -> None:
        assert importance.PRESETS["nas"] == "critical"
        assert importance.PRESETS["router"] == "critical"
        assert importance.PRESETS["camera"] == "important"
        assert set(importance.PRESETS.values()) <= set(importance.IMPORTANCES)


class TestFilingWhatAnIncidentTouched:
    def test_it_is_the_most_important_device_it_touched(self, session: Session) -> None:
        device(session, 1, DEVICE, kind="nas", importance_="critical")
        device(session, 2, OTHER, kind="laptop", importance_="important")
        both = touching(session, DEVICE, OTHER)
        one = touching(session, OTHER)
        none = touching(session)

        assert importance.refresh(session) == 2

        assert (stored(session, both), stored(session, one), stored(session, none)) == (2, 1, 0)

    def test_an_incident_that_touched_only_guests_and_gadgets_is_low(
        self, session: Session
    ) -> None:
        device(session, 1, DEVICE, kind="guest")
        device(session, 2, OTHER, kind="smart_home")
        found = touching(session, DEVICE, OTHER)

        importance.refresh(session)

        assert stored(session, found) == -1

    def test_a_device_nobody_classified_is_a_normal_one(self, session: Session) -> None:
        device(session, 1, DEVICE, kind="guest")
        device(session, 2, OTHER)
        found = touching(session, DEVICE, OTHER)

        importance.refresh(session)

        assert stored(session, found) == 0

    def test_a_device_counts_by_the_address_it_has_now(self, session: Session) -> None:
        old = device(
            session, 1, DEVICE, kind="nas", importance_="critical", seen=NOW - timedelta(days=3)
        )
        device(session, 2, DEVICE, kind="phone", seen=NOW)
        found = touching(session, DEVICE)

        importance.refresh(session)

        assert stored(session, found) == 0
        assert old.id is not None

    def test_a_machine_listed_by_address_counts_when_no_device_has_it(
        self, session: Session
    ) -> None:
        session.add(
            HostListing(
                source="wazuh",
                connection="indexer",
                via="agent",
                key="001",
                hostname="vault",
                address=ip_address(OTHER),
                state="active",
                online=True,
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
        )
        session.flush()
        listing = session.scalars(select(HostListing)).one()
        session.add(
            AssetProfile(
                key=f"host-{listing.id}", kind="server", importance="critical", updated_at=NOW
            )
        )
        found = touching(session, OTHER)
        covered = touching(session, DEVICE)
        device(session, 1, DEVICE, kind="laptop")
        session.add(
            HostListing(
                source="wazuh",
                connection="indexer",
                via="agent",
                key="002",
                address=ip_address(DEVICE),
                state="active",
                online=True,
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
        )
        session.flush()

        importance.refresh(session)

        assert (stored(session, found), stored(session, covered)) == (2, 0)

    def test_only_the_incidents_named_and_going_on_are_filed(self, session: Session) -> None:
        device(session, 1, DEVICE, kind="nas", importance_="critical")
        named = touching(session, DEVICE)
        left = touching(session, DEVICE)
        over = touching(session, DEVICE, status="resolved")

        assert importance.refresh(session, []) == 0
        assert importance.refresh(session, [named.id, over.id]) == 1

        assert (stored(session, named), stored(session, left), stored(session, over)) == (2, 0, 0)

    def test_filing_it_again_changes_nothing_and_not_when_the_incident_was_updated(
        self, session: Session
    ) -> None:
        device(session, 1, DEVICE, kind="nas", importance_="critical")
        found = touching(session, DEVICE)
        before = found.updated_at

        assert importance.refresh(session) == 1
        assert importance.refresh(session) == 0

        session.expire_all()
        again = session.get(Incident, found.id)
        assert again is not None
        assert again.updated_at == before

    def test_the_engine_files_what_a_new_incident_touched(
        self, session: Session, settings: Settings
    ) -> None:
        device(session, 1, DEVICE, kind="nas", importance_="critical")
        session.commit()

        store(session, settings, alert())
        run(session)

        found = session.scalars(select(Incident)).one()
        assert found.subject == ATTACKER
        assert found.importance == 2


class TestRankingThem:
    def test_among_the_same_severity_importance_counts_for_ten_points_a_step(
        self, session: Session
    ) -> None:
        plain = touching(session, confidence=60, importance=0)
        nas = touching(session, confidence=45, importance=2)
        guest = touching(session, confidence=70, importance=-1)
        important = touching(session, confidence=55, importance=1)

        ranked = session.scalars(
            select(Incident.id).order_by(importance.rank().desc(), Incident.id)
        ).all()

        # The NAS's 45 + 20 and the important device's 55 + 10 are 65, over the plain one's 60 and
        # the guest's 70 - 10.
        assert ranked == [nas.id, important.id, plain.id, guest.id]


class TestSayingWhy:
    def test_the_device_that_makes_it_matter_is_named(self, session: Session) -> None:
        device(session, 1, DEVICE, kind="nas", importance_="critical", hostname="vault")
        device(session, 2, OTHER, kind="guest", hostname="visitor")
        nas = touching(session, DEVICE, importance=2)
        guest = touching(session, OTHER, importance=-1)
        plain = touching(session, importance=0)

        found = importance.touches(session, [nas, guest, plain])

        assert found == {
            nas.id: Touch("vault", "Storage (NAS)", "critical"),
            guest.id: Touch("visitor", "Guest's device", "low"),
        }

    def test_an_incident_with_nothing_that_matters_has_nothing_to_say(
        self, session: Session
    ) -> None:
        assert importance.touches(session, [touching(session, importance=0)]) == {}

    def test_a_device_with_no_name_is_called_by_its_maker_or_its_address(
        self, session: Session
    ) -> None:
        one = device(session, 1, DEVICE, kind="nas", importance_="critical")
        one.vendor = "Synology"
        device(session, 2, OTHER, kind="router", importance_="critical")
        first = touching(session, DEVICE, importance=2)
        second = touching(session, OTHER, importance=2)

        found = importance.touches(session, [first, second])

        assert found[first.id].name == "Synology"
        assert found[second.id].name == OTHER

    def test_a_machine_listed_by_address_is_named_by_its_host_name(self, session: Session) -> None:
        session.add(
            HostListing(
                source="wazuh",
                connection="indexer",
                via="agent",
                key="001",
                hostname="vault",
                address=ip_address(OTHER),
                state="active",
                online=True,
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
        )
        session.flush()
        listing = session.scalars(select(HostListing)).one()
        session.add(
            AssetProfile(
                key=f"host-{listing.id}", kind="server", importance="important", updated_at=NOW
            )
        )
        found = touching(session, OTHER, importance=1)
        bare = touching(session, "192.168.1.99", importance=1)
        session.flush()

        said = importance.touches(session, [found, bare])

        assert said == {found.id: Touch("vault", "Server", "important")}

    def test_it_is_said_in_a_sentence(self) -> None:
        assert (
            importance.sentence(Touch("vault", "Storage (NAS)", "critical"))
            == "It touched vault, a storage (nas) you marked critical."
        )
        assert importance.sentence(Touch("visitor", "Guest's device", "low")) == (
            "It only touched visitor, a guest's device, which matters less, so it takes more proof."
        )
