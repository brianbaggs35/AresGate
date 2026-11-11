"""The same alert seen by two programs counts once."""

from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.events import twins
from app.events.store import record
from app.models import Event
from tests.helpers import new_event

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
ATTACKER = "203.0.113.9"
DEVICE = "192.168.1.20"
PUBLIC = "93.184.216.34"


def event(**changes: Any) -> Event:
    fields: dict[str, Any] = {
        "id": 1,
        "occurred_at": NOW,
        "source": "opnsense",
        "kind": "alert",
        "severity": 2,
        "summary": "x",
        "src_address": ip_address(ATTACKER),
        "dst_address": ip_address(DEVICE),
        "dst_port": 22,
        "protocol": "tcp",
    }
    fields.update(changes)
    return Event(**fields)


class TestWhetherTwoAlertsAreTheSameTraffic:
    def test_the_same_source_destination_and_port_are(self) -> None:
        assert twins.same_flow(event(), event(id=2, source="wazuh"))

    @pytest.mark.parametrize(
        "changes",
        [
            {"src_address": None},
            {"src_address": ip_address("203.0.113.10")},
            {"protocol": "udp"},
            {"dst_port": 80},
            {"dst_address": ip_address("192.168.1.21")},
        ],
    )
    def test_anything_that_differs_is_not(self, changes: dict[str, Any]) -> None:
        assert not twins.same_flow(event(), event(id=2, source="wazuh", **changes))

    def test_a_missing_protocol_or_port_does_not_tell_them_apart(self) -> None:
        assert twins.same_flow(event(), event(protocol=None, dst_port=None))
        assert twins.same_flow(event(protocol=None), event(dst_port=None))

    def test_with_no_destination_only_the_port_can_tell(self) -> None:
        assert twins.same_flow(event(dst_address=None), event(dst_address=None))
        assert not twins.same_flow(event(dst_address=None, dst_port=None), event(dst_address=None))

    def test_a_translated_destination_is_one_flow_when_the_port_agrees(self) -> None:
        inside = event()
        outside = event(dst_address=ip_address(PUBLIC))

        assert twins.same_flow(inside, outside)
        assert not twins.same_flow(inside, event(dst_address=ip_address(PUBLIC), dst_port=None))

    def test_two_different_internet_destinations_are_not_one_flow(self) -> None:
        assert not twins.same_flow(
            event(dst_address=ip_address("8.8.8.8")), event(dst_address=ip_address(PUBLIC))
        )

    def test_two_different_devices_on_the_network_are_not_one_flow(self) -> None:
        assert not twins.same_flow(
            event(dst_address=ip_address("192.168.1.30")), event(dst_address=ip_address(DEVICE))
        )

    def test_a_report_by_the_reply_is_the_same_flow_seen_from_the_other_end(self) -> None:
        reply = event(
            id=2,
            source="wazuh",
            src_address=ip_address(DEVICE),
            dst_address=ip_address(ATTACKER),
            src_port=22,
            dst_port=51000,
        )
        sent = event(src_port=51000, dst_port=22)

        assert twins.same_flow(sent, reply)
        assert twins.same_flow(reply, sent)

    def test_a_reply_with_no_ports_has_said_nothing_against_it(self) -> None:
        reply = event(id=2, src_address=ip_address(DEVICE), dst_address=ip_address(ATTACKER))

        assert twins.same_flow(event(), reply)

    @pytest.mark.parametrize(
        "changes",
        [
            {"protocol": "udp"},
            {"src_port": 4000},
            {"dst_port": 4000},
            {"src_address": ip_address("192.168.1.99")},
            {"dst_address": ip_address("203.0.113.10")},
        ],
    )
    def test_a_reply_that_does_not_match_is_not_the_same_flow(
        self, changes: dict[str, Any]
    ) -> None:
        sent = event(src_port=51000, dst_port=22)
        reply = {
            "id": 2,
            "src_address": ip_address(DEVICE),
            "dst_address": ip_address(ATTACKER),
            "src_port": 22,
            "dst_port": 51000,
            **changes,
        }

        assert not twins.same_flow(sent, event(**reply))

    def test_a_reply_without_addresses_is_not_one(self) -> None:
        assert not twins._answering(event(dst_address=None), event(id=2))  # pyright: ignore[reportPrivateUsage]


class TestFindingTheOriginal:
    def test_it_is_the_earliest_other_program_within_the_window(self) -> None:
        new = event(id=9, source="wazuh", occurred_at=NOW + timedelta(seconds=30))
        candidates = [event(id=3, source="suricata"), event(id=2)]

        assert twins.find_originals(candidates, new) is candidates[1]

    def test_the_same_program_is_not_a_twin_of_itself(self) -> None:
        assert twins.find_originals([event(id=2)], event(id=9, occurred_at=NOW)) is None

    def test_one_that_came_after_it_is_not_an_original(self) -> None:
        assert twins.find_originals([event(id=12, source="wazuh")], event(id=9)) is None

    def test_one_too_long_before_it_is_not_one(self) -> None:
        late = event(id=9, source="wazuh", occurred_at=NOW + twins.WINDOW + timedelta(seconds=1))

        assert twins.find_originals([event(id=2)], late) is None
        assert twins.find_originals(
            [event(id=2)], event(id=9, source="wazuh", occurred_at=NOW + twins.WINDOW)
        )

    def test_a_different_flow_is_not_one(self) -> None:
        assert twins.find_originals([event(id=2, dst_port=80)], event(id=9, source="wazuh")) is None


class TestMarkingWhatIsStored:
    def store(self, session: Session, settings: Settings, *events: Any) -> list[Event]:
        record(session, settings, list(events), NOW + timedelta(minutes=5))
        session.commit()
        return list(session.scalars(select(Event).order_by(Event.id)))

    def alert(self, number: int, seconds: int = 0, **changes: Any) -> Any:
        fields: dict[str, Any] = {
            "source": "opnsense",
            "connection": "api",
            "identity": (f"alert-{number}",),
            "occurred_at": NOW + timedelta(seconds=seconds),
            "src_address": ATTACKER,
            "dst_address": DEVICE,
            "dst_port": 22,
            "protocol": "tcp",
            **changes,
        }
        return new_event(**fields)

    def test_the_second_program_to_report_it_is_the_twin(
        self, session: Session, settings: Settings
    ) -> None:
        first, second = self.store(
            session,
            settings,
            self.alert(1),
            self.alert(2, 3, source="wazuh", connection="indexer"),
        )

        assert first.twin_of is None
        assert second.twin_of == first.id

    def test_a_program_that_reports_the_reply_is_a_twin_of_the_one_that_saw_the_request(
        self, session: Session, settings: Settings
    ) -> None:
        first, second = self.store(
            session,
            settings,
            self.alert(1, src_port=51000),
            self.alert(
                2,
                3,
                source="wazuh",
                connection="indexer",
                src_address=DEVICE,
                dst_address=ATTACKER,
                src_port=22,
                dst_port=51000,
            ),
        )

        assert second.twin_of == first.id

    def test_a_third_program_is_a_twin_of_the_first(
        self, session: Session, settings: Settings
    ) -> None:
        first, second, third = self.store(
            session,
            settings,
            self.alert(1),
            self.alert(2, 3, source="wazuh", connection="indexer"),
            self.alert(3, 6, source="ntopng", connection="api"),
        )

        assert (second.twin_of, third.twin_of) == (first.id, first.id)

    def test_a_program_saying_it_again_is_not_a_twin(
        self, session: Session, settings: Settings
    ) -> None:
        stored = self.store(session, settings, self.alert(1), self.alert(2, 3))

        assert [each.twin_of for each in stored] == [None, None]

    def test_an_alert_found_later_is_a_twin_of_one_already_stored(
        self, session: Session, settings: Settings
    ) -> None:
        self.store(session, settings, self.alert(1))
        first, second = self.store(
            session, settings, self.alert(2, 30, source="wazuh", connection="indexer")
        )

        assert second.twin_of == first.id

    def test_what_is_not_an_alert_or_names_no_source_is_left_alone(
        self, session: Session, settings: Settings
    ) -> None:
        stored = self.store(
            session,
            settings,
            self.alert(1),
            self.alert(2, 1, source="wazuh", connection="indexer", kind="firewall"),
            self.alert(3, 2, source="ntopng", connection="api", src_address=None),
        )

        assert [each.twin_of for each in stored] == [None, None, None]

    def test_alerts_too_far_apart_are_not_twins(self, session: Session, settings: Settings) -> None:
        stored = self.store(
            session,
            settings,
            self.alert(1),
            self.alert(2, 600, source="wazuh", connection="indexer"),
        )

        assert [each.twin_of for each in stored] == [None, None]

    def test_nothing_stored_marks_nothing(self, session: Session) -> None:
        assert twins.mark(session, [], NOW, NOW) == 0
