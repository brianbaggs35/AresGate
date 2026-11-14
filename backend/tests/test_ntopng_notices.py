import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collectors import registry as collectors
from app.collectors.ntopng.notices import FAMILIES, Notices, parse
from app.config import Settings
from app.events.event import Severity
from app.models import Event
from e2e.stand_ins import Answer, Seen, answers, ntopng, sample_ntopng_extras
from tests.ntopng import TOKEN, connect
from tests.opnsense import collect, health
from tests.stubs import Serve

BEGAN = 1_761_473_523


def record(**changes: Any) -> dict[str, Any]:
    """An alert as ntopng lists the ones that are not about a flow or a host."""
    row: dict[str, Any] = {
        "row_id": "4",
        "tstamp": {"value": BEGAN, "label": "10:12:03"},
        "alert_id": {"value": "12"},
        "severity": {"value": 4},
        "msg": {"name": "Process Restarted"},
    }
    row.update(changes)
    return row


def test_it_reads_from_ntopng_and_is_one_of_the_collectors() -> None:
    assert Notices.reads("ntopng", "api")
    assert not Notices.reads("opnsense", "api")
    assert collectors.find("ntopng-notices") is not None
    assert Notices.interval == timedelta(minutes=1)
    assert Notices.timeout >= Notices.interval


class TestANotice:
    def test_it_is_an_event_that_can_never_become_an_incident(self) -> None:
        [event] = parse("system", [record()])

        assert (event.source, event.connection, event.kind) == ("ntopng", "api", "notice")
        assert event.occurred_at == datetime.fromtimestamp(BEGAN, UTC)
        assert event.severity == Severity.MEDIUM
        assert event.summary == "Process Restarted"
        assert event.signature == "Process Restarted"
        assert (event.src_address, event.dst_address, event.iface) == (None, None, None)
        assert event.raw is not None
        assert event.raw["family"] == "system"

    def test_an_interface_alert_says_which_interface_and_in_which_it_came(self) -> None:
        [event] = parse("interface", [record(subtype={"value": "0", "name": "eth0"})], "eth0")

        assert event.summary == "Process Restarted: eth0"
        assert event.iface == "eth0"

    def test_an_interface_alert_without_a_name_has_its_number(self) -> None:
        [event] = parse("interface", [record(subtype={"value": "3"})])

        assert event.summary == "Process Restarted: 3"

    def test_a_network_alert_says_which_network_by_its_alias_or_its_name(self) -> None:
        [aliased, plain] = parse(
            "network",
            [record(name="192.168.1.0/24", alias="LAN"), record(row_id="5", name="10.0.0.0/8")],
        )

        assert aliased.summary == "Process Restarted: LAN"
        assert plain.summary == "Process Restarted: 10.0.0.0/8"

    def test_a_device_alert_says_which_device_by_its_name_and_its_address(self) -> None:
        address = {"value": "52:54:00:aa:bb:41"}
        named, nameless, unaddressed = parse(
            "device",
            [
                record(address=address, name="laptop"),
                record(row_id="5", address=address),
                record(row_id="6", name="phone"),
            ],
        )

        assert named.summary == "Process Restarted: laptop (52:54:00:aa:bb:41)"
        assert nameless.summary == "Process Restarted: 52:54:00:aa:bb:41"
        assert unaddressed.summary == "Process Restarted: phone"

    def test_one_with_no_name_is_an_alert_and_the_name_in_the_record_is_used_before_that(
        self,
    ) -> None:
        [nameless, named] = parse(
            "system", [record(msg=None), record(row_id="5", msg=None, alert_name="Disk Full")]
        )

        assert nameless.summary == "Alert"
        assert nameless.signature is None
        assert named.summary == "Disk Full"

    def test_one_that_is_not_an_object_or_has_no_time_is_left_out(self) -> None:
        assert (
            parse("system", ["text", record(tstamp=None), record(tstamp={"value": "soon"})]) == []
        )

    def test_two_that_say_the_same_are_told_apart_and_stay_the_same_when_read_again(self) -> None:
        first, second = parse("system", [record(), record()])
        again, _ = parse("system", [record(), record()])

        assert first.fingerprint != second.fingerprint
        assert first.fingerprint == again.fingerprint

    def test_a_severity_below_a_notice_is_information(self) -> None:
        [event] = parse("system", [record(severity=None)])

        assert event.severity == Severity.INFO


class TestRunningAgainstNtopng:
    def test_it_keeps_the_alerts_of_the_interface_the_network_the_device_and_ntopng_itself(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(
            session,
            settings,
            serve(ntopng(TOKEN, extras=sample_ntopng_extras(datetime.now(UTC)))).url,
        )

        collect(settings, engine, Notices())

        assert health(session).last_items == 4
        events = {event.signature: event for event in session.scalars(select(Event))}
        assert {event.kind for event in events.values()} == {"notice"}
        assert events["Interface Dropped Packets"].summary == ("Interface Dropped Packets: eth0")
        assert events["Network SYN Flood"].summary == "Network SYN Flood: LAN"
        assert events["Device Connection"].summary == (
            "Device Connection: laptop (52:54:00:aa:bb:41)"
        )
        assert events["Process Restarted"].iface is None

    def test_a_system_alert_is_asked_for_once_however_many_interfaces_there_are(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        asked: list[str] = []
        inner = ntopng(TOKEN, extras=sample_ntopng_extras(datetime.now(UTC)))

        def handle(seen: Seen) -> Answer:
            asked.append(seen.path)
            return inner(seen)

        connect(session, settings, serve(handle).url, interface_id="")

        collect(settings, engine, Notices())

        assert asked.count(FAMILIES["system"]) == 1
        assert asked.count(FAMILIES["interface"]) == 2

    def test_an_account_that_may_not_see_one_kind_still_has_the_others(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        inner = ntopng(TOKEN, extras=sample_ntopng_extras(datetime.now(UTC)))

        def handle(seen: Seen) -> Answer:
            if seen.path == FAMILIES["system"]:
                return Answer(body=json.dumps({"rc": -3, "rc_str": "NOT_GRANTED", "rsp": {}}))
            return inner(seen)

        connect(session, settings, serve(handle).url)

        collect(settings, engine, Notices())

        assert health(session).last_error is None
        assert health(session).last_items == 3

    def test_an_account_that_may_see_none_of_them_has_the_reason(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(
            session,
            settings,
            serve(
                lambda seen: Answer(body=json.dumps({"rc": -3, "rc_str": "NOT_GRANTED", "rsp": {}}))
            ).url,
        )

        collect(settings, engine, Notices())

        assert health(session).last_error == "ntopng answered with the error NOT_GRANTED."

    @pytest.mark.parametrize("rsp", [{"stats": {}}, ["x"]])
    def test_an_answer_without_a_list_of_alerts_is_not_taken_for_one(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve, rsp: Any
    ) -> None:
        extras = {path: answers(rsp) for path in FAMILIES.values()}
        connect(session, settings, serve(ntopng(TOKEN, extras=extras)).url)

        collect(settings, engine, Notices())

        assert health(session).last_error is not None

    def test_alerts_that_are_not_in_a_form_it_reads_are_a_failure(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        extras = {path: answers({"records": ["text"]}) for path in FAMILIES.values()}
        connect(session, settings, serve(ntopng(TOKEN, extras=extras)).url)

        collect(settings, engine, Notices())

        assert health(session).last_error == (
            "It answered, but the alerts aren't in a form AresGate reads."
        )
