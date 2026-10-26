import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collectors import registry as collectors
from app.collectors.ntopng.alerts import FLOWS, HOSTS, LIMIT, WINDOW, Alerts, parse
from app.config import Settings
from app.events.event import Severity
from app.integrations import probes
from app.models import Event, utcnow
from e2e.stand_ins import (
    Answer,
    Seen,
    ntopng,
    sample_ntopng_flow_alerts,
    sample_ntopng_host_alerts,
)
from tests.ntopng import TOKEN, connect
from tests.opnsense import collect, health
from tests.stubs import Serve

BEGAN = 1_761_473_523


def flow(**changes: Any) -> dict[str, Any]:
    """A flow alert as ntopng lists it."""
    record: dict[str, Any] = {
        "row_id": "7",
        "tstamp": {"value": BEGAN, "label": "10:12:03"},
        "alert_id": {"value": "21", "label": "<b>Blacklisted Flow</b>"},
        "severity": {"value": 5, "label": "<i></i>"},
        "msg": {"name": "Blacklisted Flow", "description": "<b>Blacklisted</b> flow"},
        "alert_name": "Blacklisted Flow",
        "cli_ip": {"value": "192.168.1.41", "label": "laptop"},
        "srv_ip": {"value": "203.0.113.9", "label": "203.0.113.9"},
        "cli_port": {"value": "51514", "label": ""},
        "srv_port": {"value": "443", "label": "https"},
        "proto": {"value": "6", "label": "TCP"},
    }
    record.update(changes)
    return record


def host(**changes: Any) -> dict[str, Any]:
    """A host alert as ntopng lists it."""
    record: dict[str, Any] = {
        "row_id": "3",
        "tstamp": {"value": BEGAN, "label": "10:12:03"},
        "alert_id": {"value": "5", "label": "<b>Scan Attacker</b>"},
        "severity": {"value": 4},
        "msg": {"name": "Scan Attacker"},
        "ip": {"value": "192.168.1.41", "label": "laptop"},
        "role": {"label": "Attacker", "value": "attacker"},
    }
    record.update(changes)
    return record


class TestAFlowAlert:
    def test_it_is_an_event_about_the_flow(self) -> None:
        [event] = parse("flow", [flow()])

        assert (event.source, event.connection, event.kind) == ("ntopng", "api", "alert")
        assert event.occurred_at == datetime.fromtimestamp(BEGAN, UTC)
        assert event.severity == Severity.HIGH
        assert event.summary == "Blacklisted Flow: 192.168.1.41:51514 to 203.0.113.9:443"
        assert event.signature == "Blacklisted Flow"
        assert (event.src_address, event.src_port) == ("192.168.1.41", 51514)
        assert (event.dst_address, event.dst_port) == ("203.0.113.9", 443)
        assert event.protocol == "tcp"
        assert event.raw is not None
        assert event.raw["msg"]["description"] == "<b>Blacklisted</b> flow"

    def test_without_a_name_in_msg_it_has_the_alert_name_and_without_either_it_is_an_alert(
        self,
    ) -> None:
        [named] = parse("flow", [flow(msg=None)])
        [bare] = parse("flow", [flow(msg=None, alert_name=None, cli_ip=None, srv_ip=None)])

        assert named.signature == "Blacklisted Flow"
        assert (bare.summary, bare.signature) == ("Alert", None)
        assert (bare.src_address, bare.dst_address) == (None, None)

    def test_ports_and_protocol_it_does_not_give_are_left_out(self) -> None:
        [event] = parse("flow", [flow(cli_port={"value": ""}, srv_port=None, proto={})])

        assert (event.src_port, event.dst_port, event.protocol) == (None, None, None)
        assert event.summary.endswith("192.168.1.41 to 203.0.113.9")

    def test_a_flow_with_one_end_known_says_which(self) -> None:
        [event] = parse("flow", [flow(srv_ip=None)])

        assert event.summary == "Blacklisted Flow: 192.168.1.41:51514"


class TestAHostAlert:
    def test_an_attacker_is_the_source(self) -> None:
        [event] = parse("host", [host()])

        assert event.summary == "Scan Attacker on 192.168.1.41"
        assert (event.src_address, event.dst_address) == ("192.168.1.41", None)
        assert (event.src_port, event.dst_port, event.protocol) == (None, None, None)
        assert event.severity == Severity.MEDIUM

    @pytest.mark.parametrize("role", [{"value": "victim"}, None])
    def test_a_victim_or_a_host_with_no_role_is_the_destination(
        self, role: dict[str, str] | None
    ) -> None:
        [event] = parse("host", [host(role=role)])

        assert (event.src_address, event.dst_address) == (None, "192.168.1.41")

    def test_a_host_alert_that_names_no_host_is_only_its_name(self) -> None:
        [event] = parse("host", [host(ip=None)])

        assert event.summary == "Scan Attacker"


class TestSeverity:
    @pytest.mark.parametrize(
        ("level", "severity"),
        [
            (0, Severity.INFO),
            (2, Severity.INFO),
            (3, Severity.LOW),
            (4, Severity.MEDIUM),
            (5, Severity.HIGH),
            (6, Severity.CRITICAL),
            (8, Severity.CRITICAL),
        ],
    )
    def test_ntopngs_severity_says_how_serious_it_is(self, level: int, severity: Severity) -> None:
        [event] = parse("flow", [flow(severity={"value": level})])

        assert event.severity == severity

    def test_one_without_a_severity_is_only_a_note(self) -> None:
        [event] = parse("flow", [flow(severity=None)])

        assert event.severity == Severity.INFO


class TestWhichAreEvents:
    def test_a_record_that_is_not_an_object_or_has_no_time_is_left_out(self) -> None:
        found = parse(
            "flow",
            ["nonsense", flow(tstamp=None), flow(tstamp={"value": "soon"}), flow(row_id="8")],
        )

        assert [event.identity[1] for event in found] == ["8"]

    def test_the_time_may_come_as_digits(self) -> None:
        [event] = parse("flow", [flow(tstamp={"value": str(BEGAN)})])

        assert event.occurred_at == datetime.fromtimestamp(BEGAN, UTC)

    def test_the_same_alert_read_again_is_the_same_event_and_the_same_facts_twice_are_two(
        self,
    ) -> None:
        [first] = parse("flow", [flow()])
        [again] = parse("flow", [flow(msg={"name": "A new wording"})])
        twice = parse("flow", [flow(), flow()])
        [other_host] = parse("host", [flow()])

        assert first.fingerprint == again.fingerprint
        assert twice[0].fingerprint == first.fingerprint
        assert twice[1].fingerprint != first.fingerprint
        assert other_host.fingerprint != first.fingerprint


def test_it_reads_from_ntopng_and_is_one_of_the_collectors() -> None:
    assert Alerts.reads("ntopng", "api")
    assert not Alerts.reads("wazuh", "indexer")
    assert Alerts.module is None
    assert collectors.find("ntopng-alerts") is not None
    assert Alerts.interval == timedelta(minutes=1)
    assert Alerts.timeout >= Alerts.interval


def stored(session: Session) -> list[Event]:
    session.expire_all()
    return list(session.scalars(select(Event).order_by(Event.occurred_at, Event.id)))


def listing(flows: object, hosts: object = ()) -> Callable[[Seen], Answer]:
    """A ntopng that lists these records as its flow and host alerts, whatever they are."""

    def handle(seen: Seen) -> Answer:
        records = flows if seen.path == FLOWS else hosts
        return Answer(body=json.dumps({"rc": 0, "rc_str": "OK", "rsp": {"records": records}}))

    return handle


class TestRunningAgainstNtopng:
    def test_it_keeps_the_alerts_of_the_last_half_hour_and_reading_them_again_adds_nothing(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        now = datetime.now(UTC)
        started = serve(
            ntopng(
                TOKEN,
                flow_alerts=sample_ntopng_flow_alerts(now),
                host_alerts=sample_ntopng_host_alerts(now),
            )
        )
        connect(session, settings, started.url)

        collect(settings, engine, Alerts())

        assert health(session).last_items == 4
        assert [item.summary for item in stored(session)] == [
            "TLS Certificate Selfsigned: 192.168.1.20:51514 to 198.51.100.30:8443",
            "Scan Victim on 192.168.1.20",
            "Scan Attacker on 192.168.1.41",
            "Blacklisted Flow: 192.168.1.41:51514 to 203.0.113.9:443",
        ]
        assert [(item.severity, str(item.src_address)) for item in stored(session)] == [
            (2, "192.168.1.20"),
            (2, "None"),
            (2, "192.168.1.41"),
            (3, "192.168.1.41"),
        ]

        collect(settings, engine, Alerts())

        assert health(session).last_items == 0
        assert len(stored(session)) == 4

    def test_it_asks_each_kind_for_the_window_newest_first_with_the_token(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started = serve(ntopng(TOKEN))
        connect(session, settings, started.url)
        before = utcnow()

        collect(settings, engine, Alerts())

        flows, hosts = (
            next(item for item in started.seen if item.path == path) for path in (FLOWS, HOSTS)
        )
        for asked in (flows, hosts):
            query = parse_qs(urlsplit(asked.target).query)
            assert asked.method == "GET"
            assert asked.headers["authorization"] == f"Token {TOKEN}"
            assert (query["ifid"], query["status"]) == (["0"], ["any"])
            assert (query["length"], query["sort"], query["order"]) == (
                [str(LIMIT)],
                ["tstamp"],
                ["desc"],
            )
            begin, end = int(query["epoch_begin"][0]), int(query["epoch_end"][0])
            assert abs((end - begin) - WINDOW.total_seconds()) <= 1
            assert abs(end - before.timestamp()) < 30
        assert (health(session).consecutive_failures, health(session).last_items) == (0, 0)

    def test_records_that_are_not_alerts_fail_the_run_unless_some_are(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(listing(["nonsense"], [3])).url)

        collect(settings, engine, Alerts())

        assert health(session).last_error == (
            "It answered, but the alerts aren't in a form AresGate reads."
        )

        recent = {"value": int(utcnow().timestamp())}
        connect(session, settings, serve(listing(["nonsense"], [host(tstamp=recent)])).url)

        collect(settings, engine, Alerts())

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 1)

    def test_an_answer_without_a_list_of_records_fails(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(listing("none")).url)

        collect(settings, engine, Alerts())

        assert health(session).last_error == probes.unexpected("ntopng").message
