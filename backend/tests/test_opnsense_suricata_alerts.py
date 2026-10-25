import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors import registry as collectors
from app.collectors.opnsense.suricata_alerts import SuricataAlerts, parse
from app.collectors.scheduler import Scheduler
from app.config import Settings
from app.events.event import Severity
from app.integrations import netguard, registry, service
from app.integrations.apilog import ApiLogRecorder
from app.integrations.service import Submission
from app.models import CollectorHealth, Event, utcnow
from e2e.stand_ins import opnsense
from tests.stubs import Answer, Certificate, Seen, Serve, make_certificate

NOW = datetime(2026, 10, 23, 18, 0, 30, tzinfo=UTC)
KEY, SECRET = "firewall-key", "firewall-secret"


def alert(at: datetime = NOW, **changes: Any) -> dict[str, Any]:
    """An alert as OPNsense's query gives it: Suricata's record with the signature, its number and
    the action flattened onto it."""
    row: dict[str, Any] = {
        "timestamp": f"{at:%Y-%m-%dT%H:%M:%S.%f}+0000",
        "flow_id": 1234567890123456,
        "in_iface": "igb0",
        "event_type": "alert",
        "src_ip": "198.51.100.7",
        "src_port": 51514,
        "dest_ip": "192.0.2.10",
        "dest_port": 22,
        "proto": "TCP",
        "alert": "ET SCAN Potential SSH Scan",
        "alert_sid": 2001219,
        "alert_action": "allowed",
        "app_proto": "ssh",
        "payload": "c2VjcmV0IGJ5dGVz",
        "payload_printable": "secret bytes",
        "packet": "AAECAw==",
        "packet_info": {"linktype": 1},
        "stream": 0,
        "filepos": 4096,
        "fileid": "",
    }
    row.update(changes)
    return row


class TestReadingAlerts:
    def test_an_alert_becomes_an_event(self) -> None:
        [event] = parse([alert()])

        assert (event.source, event.connection, event.kind) == ("opnsense", "api", "alert")
        assert event.occurred_at == NOW
        assert event.severity == Severity.MEDIUM
        assert event.signature == "ET SCAN Potential SSH Scan"
        assert (event.src_address, event.src_port) == ("198.51.100.7", 51514)
        assert (event.dst_address, event.dst_port) == ("192.0.2.10", 22)
        assert event.protocol == "tcp"
        assert event.summary == (
            "ET SCAN Potential SSH Scan (allowed): tcp 198.51.100.7:51514 to 192.0.2.10:22"
        )

    def test_an_alert_that_suricata_stopped_is_the_lesser_worry(self) -> None:
        [event] = parse([alert(alert_action="blocked")])

        assert event.severity == Severity.LOW
        assert "(blocked)" in event.summary

    def test_the_record_is_kept_without_the_packet_and_where_it_sat_in_the_file(self) -> None:
        [event] = parse([alert()])

        assert event.raw is not None
        assert event.raw["flow_id"] == 1234567890123456
        assert event.raw["app_proto"] == "ssh"
        assert event.raw["alert_sid"] == 2001219
        assert not {"payload", "payload_printable", "packet", "packet_info", "stream"} & set(
            event.raw
        )
        assert not {"filepos", "fileid"} & set(event.raw)

    @pytest.mark.parametrize(
        ("stamp", "expected"),
        [
            ("2026-10-23T15:00:30.123456-0300", datetime(2026, 10, 23, 18, 0, 30, 123456, UTC)),
            ("2026-10-23T18:00:30+00:00", NOW),
            ("2026-10-23T18:00:30Z", NOW),
            ("2026-10-24T02:30:30+0830", NOW),
        ],
    )
    def test_the_time_is_taken_in_the_zone_it_was_written_in(
        self, stamp: str, expected: datetime
    ) -> None:
        [event] = parse([alert(timestamp=stamp)])

        assert event.occurred_at == expected

    def test_a_row_that_cant_be_read_is_left_out_and_the_rest_are_kept(self) -> None:
        rows: list[object] = [
            "not an object",
            None,
            ["list"],
            alert(timestamp="yesterday"),
            alert(timestamp=""),
            # Its zone isn't said, so what it means isn't known.
            alert(timestamp="2026-10-23T18:00:30"),
            {"alert": "no time"},
            alert(alert="the one that can be read"),
        ]

        events = parse(rows)

        assert [event.signature for event in events] == ["the one that can be read"]

    def test_nothing_is_nothing(self) -> None:
        assert parse([]) == []

    def test_an_alert_with_little_on_it_still_says_what_it_can(self) -> None:
        stamp = alert()["timestamp"]

        [bare] = parse([{"timestamp": stamp}])
        [named] = parse([{"timestamp": stamp, "alert": "ET INFO Something", "proto": "ICMP"}])

        assert bare.summary == "Suricata alert"
        assert bare.signature is None
        assert (bare.src_address, bare.dst_address, bare.protocol) == (None, None, None)
        assert bare.severity == Severity.MEDIUM
        assert named.summary == "ET INFO Something: icmp"

    def test_ports_that_arent_numbers_are_left_out(self) -> None:
        [event] = parse([alert(src_port="abc", dest_port=None, proto="ICMP")])

        assert (event.src_port, event.dst_port) == (None, None)
        assert event.summary == (
            "ET SCAN Potential SSH Scan (allowed): icmp 198.51.100.7 to 192.0.2.10"
        )

    def test_an_ipv6_address_is_in_brackets_before_its_port(self) -> None:
        [event] = parse([alert(src_ip="2001:db8::7", dest_ip="2001:db8::10")])

        assert event.summary == (
            "ET SCAN Potential SSH Scan (allowed): tcp [2001:db8::7]:51514 to [2001:db8::10]:22"
        )


class TestAlertsThatLookAlike:
    def test_identical_alerts_are_as_many_events_as_there_are_alerts(self) -> None:
        events = parse([alert(), alert(), alert()])

        assert len({event.fingerprint for event in events}) == 3

    def test_alerts_that_differ_in_any_of_their_facts_are_different_events(self) -> None:
        events = parse(
            [
                alert(),
                alert(flow_id=1),
                alert(alert_sid=2),
                alert(src_port=1),
                alert(timestamp="2026-10-23T18:00:30.000001+0000"),
            ]
        )

        assert len({event.fingerprint for event in events}) == 5

    def test_alerts_that_differ_only_in_what_is_kept_beside_them_are_the_same_event(self) -> None:
        [first] = parse([alert(filepos=1, app_proto="ssh")])
        [again] = parse([alert(filepos=99, app_proto="http")])

        assert first.fingerprint == again.fingerprint

    def test_reading_again_with_a_longer_window_finds_the_same_events(self) -> None:
        first = parse([alert(), alert()])
        second = parse([alert()] * 4)

        assert {event.fingerprint for event in first} < {event.fingerprint for event in second}


class TestAsAScheduledCollector:
    def test_it_reads_from_the_firewalls_api_when_suricata_is_in_use(self) -> None:
        assert SuricataAlerts.reads("opnsense", "api")
        assert not SuricataAlerts.reads("opnsense", "zenarmor")
        assert not SuricataAlerts.reads("wazuh", "indexer")
        assert SuricataAlerts.module == "suricata"

    def test_it_is_one_of_the_collectors(self) -> None:
        assert collectors.find("opnsense-suricata-alerts") is not None
        assert SuricataAlerts.interval == timedelta(minutes=1)
        assert SuricataAlerts.timeout >= SuricataAlerts.interval


def connect(
    session: Session, settings: Settings, server_url: str, certificate: Certificate
) -> None:
    submission = Submission(
        url=server_url,
        tls_mode="pinned",
        tls_ca_pem=None,
        tls_fingerprint=certificate.fingerprint,
        options={},
        secrets={"api_key": KEY, "api_secret": SECRET},
    )
    service.save(
        session,
        settings,
        netguard.HOME_NETWORK_AND_LOOPBACK,
        registry.INTEGRATIONS["opnsense"],
        {"api": submission},
        utcnow(),
    )
    session.commit()


def collect(settings: Settings, engine: Engine) -> None:
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    scheduler = Scheduler(
        settings,
        maker,
        ApiLogRecorder(maker),
        netguard.HOME_NETWORK_AND_LOOPBACK,
        collectors=(SuricataAlerts(),),
    )
    asyncio.run(scheduler.run_once())


def health(session: Session) -> CollectorHealth:
    session.expire_all()
    return session.scalars(select(CollectorHealth)).one()


def stored_events(session: Session) -> list[Event]:
    session.expire_all()
    return list(session.scalars(select(Event).order_by(Event.occurred_at, Event.id)))


def answering(reply: object, *, status: int = 200) -> Callable[[Seen], Answer]:
    return lambda seen: Answer(status=status, body=json.dumps(reply))


def rows_of(*rows: object) -> dict[str, object]:
    return {"filters": {}, "rows": list(rows), "rowCount": len(rows), "current": 1}


class TestRunningAgainstTheFirewall:
    def test_it_stores_the_alerts_and_reading_them_again_adds_nothing(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        now = utcnow().replace(microsecond=0)
        alerts = [
            alert(now - timedelta(seconds=10), alert_action="blocked", flow_id=2),
            alert(now - timedelta(seconds=30), flow_id=1),
        ]
        certificate = make_certificate()
        handler = opnsense(KEY, SECRET, {"suricata"}, suricata_alerts=alerts)
        connect(session, settings, serve(handler, certificate).url, certificate)

        collect(settings, engine)

        assert health(session).last_items == 2
        stored = stored_events(session)
        assert [item.occurred_at for item in stored] == [
            now - timedelta(seconds=30),
            now - timedelta(seconds=10),
        ]
        assert [(item.kind, item.severity) for item in stored] == [("alert", 2), ("alert", 1)]
        assert all(item.raw and "payload" not in item.raw for item in stored)

        collect(settings, engine)

        assert health(session).last_items == 0
        assert len(stored_events(session)) == 2

    def test_it_asks_with_a_post_for_the_newest_five_hundred(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        server = serve(opnsense(KEY, SECRET, {"suricata"}), certificate)
        connect(session, settings, server.url, certificate)

        collect(settings, engine)

        asked = [item for item in server.seen if item.path.endswith("query_alerts")]
        assert [(item.method, item.target) for item in asked] == [
            ("POST", "/api/ids/service/query_alerts")
        ]
        assert json.loads(asked[0].body) == {"rowCount": 500, "current": 1}
        assert asked[0].headers["authorization"].startswith("Basic ")
        assert asked[0].headers["content-type"].startswith("application/json")
        assert (health(session).consecutive_failures, health(session).last_items) == (0, 0)

    def test_some_unreadable_rows_among_good_ones_are_just_skipped(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        rows = rows_of(alert(utcnow()), alert(timestamp="yesterday"), "nonsense")
        certificate = make_certificate()
        connect(session, settings, serve(answering(rows), certificate).url, certificate)

        collect(settings, engine)

        record = health(session)
        assert (record.consecutive_failures, record.last_items) == (0, 1)

    def test_rows_that_are_all_unreadable_say_so_instead_of_looking_like_a_quiet_network(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        rows = rows_of(alert(timestamp="yesterday"), "nonsense")
        certificate = make_certificate()
        connect(session, settings, serve(answering(rows), certificate).url, certificate)

        collect(settings, engine)

        assert "alerts aren't in a form AresGate reads" in (health(session).last_error or "")

    def test_an_empty_list_means_opnsense_couldnt_ask_suricata(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        connect(session, settings, serve(answering([]), certificate).url, certificate)

        collect(settings, engine)

        error = health(session).last_error or ""
        assert "can't ask the intrusion detection service" in error
        assert stored_events(session) == []

    @pytest.mark.parametrize("reply", [{"status": "ok"}, {"rows": "many"}, ["row"], "text"])
    def test_an_answer_that_isnt_a_list_of_rows_is_not_the_alert_query(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve, reply: object
    ) -> None:
        certificate = make_certificate()
        connect(session, settings, serve(answering(reply), certificate).url, certificate)

        collect(settings, engine)

        assert "doesn't look like OPNsense's" in (health(session).last_error or "")

    def test_a_plugin_that_isnt_installed_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        server = serve(opnsense(KEY, SECRET, set()), certificate)
        connect(session, settings, server.url, certificate)

        collect(settings, engine)

        assert "answered 404" in (health(session).last_error or "")

    def test_a_user_who_may_not_use_it_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        server = serve(answering({"status": 403}, status=403), certificate)
        connect(session, settings, server.url, certificate)

        collect(settings, engine)

        assert "didn't accept the credentials" in (health(session).last_error or "")
        assert stored_events(session) == []
