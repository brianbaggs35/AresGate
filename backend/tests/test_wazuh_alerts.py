import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collectors import registry as collectors
from app.collectors.wazuh.alerts import LIMIT, WINDOW, Alerts, parse
from app.config import Settings
from app.events.event import Severity
from app.models import Event, utcnow
from e2e.stand_ins import sample_wazuh_agents, sample_wazuh_alerts, wazuh
from tests.opnsense import answering, collect, health
from tests.stubs import Answer, Certificate, Serve, StubServer, make_certificate
from tests.wazuh import PASSWORD, USER, connect

NOW = datetime(2026, 10, 26, 10, 12, 3, 482000, tzinfo=UTC)


def hit(**changes: Any) -> dict[str, Any]:
    """A document of the indexer's ``wazuh-alerts-*`` index: an alert of a failed login."""
    document: dict[str, Any] = {
        "_index": "wazuh-alerts-4.x-2026.10.26",
        "_id": "wz-alert-1",
        "_source": {
            "timestamp": "2026-10-26T10:12:03.482+0000",
            "rule": {
                "id": "5710",
                "level": 5,
                "description": "sshd: Attempt to login using a non-existent user",
                "groups": ["syslog", "sshd", "authentication_failed"],
            },
            "agent": {"id": "001", "name": "web1", "ip": "192.168.1.20"},
            "manager": {"name": "wazuh-server"},
            "id": "1761473523.482",
            "full_log": "Oct 26 10:12:03 web1 sshd[811]: Invalid user admin from 198.51.100.7",
            "decoder": {"name": "sshd"},
            "data": {"srcip": "198.51.100.7", "srcport": "51514", "protocol": "TCP"},
            "location": "/var/log/auth.log",
        },
    }
    document.update(changes)
    return document


def with_source(**changes: Any) -> dict[str, Any]:
    """The same document with these members of the alert changed, or left out when ``None``."""
    document = hit()
    for key, value in changes.items():
        if value is None:
            del document["_source"][key]
        else:
            document["_source"][key] = value
    return document


class TestReadingAlerts:
    def test_an_alert_becomes_an_event(self) -> None:
        [event] = parse([hit()])

        assert (event.source, event.connection, event.kind) == ("wazuh", "indexer", "alert")
        assert event.occurred_at == NOW
        assert event.severity == Severity.LOW
        assert event.signature == "sshd: Attempt to login using a non-existent user"
        assert event.summary == (
            "sshd: Attempt to login using a non-existent user on web1 (rule 5710, level 5)"
        )
        assert (event.src_address, event.src_port) == ("198.51.100.7", 51514)
        assert (event.dst_address, event.dst_port) == ("192.168.1.20", None)
        assert event.protocol == "tcp"
        assert event.raw == hit()["_source"]

    def test_it_keeps_the_log_line_the_alert_was_raised_for(self) -> None:
        [event] = parse([hit()])

        assert event.raw is not None
        assert event.raw["full_log"].startswith("Oct 26 10:12:03 web1 sshd")

    @pytest.mark.parametrize(
        ("level", "severity"),
        [
            (0, Severity.INFO),
            (3, Severity.INFO),
            (4, Severity.LOW),
            (6, Severity.LOW),
            (7, Severity.MEDIUM),
            (10, Severity.MEDIUM),
            (11, Severity.HIGH),
            (13, Severity.HIGH),
            (14, Severity.CRITICAL),
            (16, Severity.CRITICAL),
        ],
    )
    def test_its_rule_level_says_how_serious_it_is(self, level: int, severity: Severity) -> None:
        rule = {"id": "1", "level": level, "description": "a rule"}

        [event] = parse([with_source(rule=rule)])

        assert event.severity == severity
        assert f"level {level}" in event.summary

    def test_a_level_given_as_text_is_read_and_one_that_is_not_a_number_is_only_a_note(
        self,
    ) -> None:
        [text] = parse([with_source(rule={"id": "1", "level": "14", "description": "a rule"})])
        [odd] = parse([with_source(rule={"id": "1", "level": "high", "description": "a rule"})])

        assert text.severity == Severity.CRITICAL
        assert odd.severity == Severity.INFO
        assert odd.summary == "a rule on web1 (rule 1)"

    def test_an_alert_that_names_a_destination_keeps_it_and_the_agents_address_is_the_fallback(
        self,
    ) -> None:
        data = {"srcip": "198.51.100.7", "dstip": "192.0.2.10", "dstport": 443}

        [named] = parse([with_source(data=data)])
        [about_the_host] = parse([with_source(data={"srcip": "198.51.100.7"})])

        assert (named.dst_address, named.dst_port) == ("192.0.2.10", 443)
        assert about_the_host.dst_address == "192.168.1.20"

    def test_an_alert_with_no_address_at_all_has_none(self) -> None:
        [event] = parse([with_source(data=None, agent=None)])

        assert (event.src_address, event.dst_address) == (None, None)

    def test_ports_that_arent_numbers_are_left_out(self) -> None:
        [event] = parse([with_source(data={"srcip": "198.51.100.7", "srcport": "abc"})])

        assert event.src_port is None

    def test_an_address_that_isnt_one_is_dropped_without_losing_the_event(self) -> None:
        [event] = parse([with_source(data={"srcip": "unknown"})])

        assert event.row(NOW)["src_address"] is None

    def test_an_alert_with_little_on_it_still_says_what_it_can(self) -> None:
        [event] = parse([{"_id": "1", "_source": {"timestamp": "2026-10-26T10:12:03.482+0000"}}])

        assert event.summary == "Alert"
        assert event.signature is None
        assert event.severity == Severity.INFO
        assert (event.src_address, event.dst_address, event.protocol) == (None, None, None)

    def test_the_host_and_the_rule_are_left_out_of_the_summary_when_not_given(self) -> None:
        [no_host] = parse([with_source(agent=None)])
        [no_rule_id] = parse([with_source(rule={"level": 5, "description": "a rule"})])

        assert no_host.summary.endswith("existent user (rule 5710, level 5)")
        assert "on " not in no_host.summary
        assert no_rule_id.summary == "a rule on web1 (level 5)"

    @pytest.mark.parametrize(
        "stamp",
        ["2026-10-26T10:12:03.482+0000", "2026-10-26T10:12:03.482Z", "2026-10-26T10:12:03+00:00"],
    )
    def test_the_time_is_read_in_the_forms_wazuh_and_the_indexer_give(self, stamp: str) -> None:
        [event] = parse([with_source(timestamp=stamp)])

        assert event.occurred_at.replace(microsecond=0) == NOW.replace(microsecond=0)

    def test_a_time_in_another_zone_is_the_same_moment(self) -> None:
        [event] = parse([with_source(timestamp="2026-10-26T07:12:03.482-0300")])

        assert event.occurred_at == NOW

    @pytest.mark.parametrize(
        "document",
        [
            "nonsense",
            None,
            {"_source": hit()["_source"]},
            {"_id": "", "_source": hit()["_source"]},
            {"_id": ["x"], "_source": hit()["_source"]},
            {"_id": "x"},
            {"_id": "x", "_source": "nonsense"},
            with_source(timestamp=None),
            with_source(timestamp="yesterday"),
            with_source(timestamp="2026-10-26T10:12:03"),
            with_source(timestamp=1761473523),
        ],
    )
    def test_a_hit_that_cant_be_read_is_left_out_and_the_rest_are_kept(
        self, document: object
    ) -> None:
        events = parse([hit(_id="a"), document, hit(_id="b")])

        assert [event.identity for event in events] == [("a",), ("b",)]

    def test_nothing_is_nothing(self) -> None:
        assert parse([]) == []

    def test_an_alert_is_told_by_its_documents_id_and_not_by_what_it_says(self) -> None:
        [first] = parse([hit()])
        [again] = parse([with_source(full_log="something else") | {"_id": "wz-alert-1"}])
        [other] = parse([hit(_id="wz-alert-2")])

        assert first.fingerprint == again.fingerprint
        assert first.fingerprint != other.fingerprint

    def test_it_reads_from_the_indexer_and_is_one_of_the_collectors(self) -> None:
        assert Alerts.reads("wazuh", "indexer")
        assert not Alerts.reads("wazuh", "manager")
        assert not Alerts.reads("opnsense", "api")
        assert Alerts.module is None
        assert collectors.find("wazuh-alerts") is not None
        assert Alerts.interval == timedelta(minutes=1)
        assert Alerts.timeout >= Alerts.interval


def stored_events(session: Session) -> list[Event]:
    session.expire_all()
    return list(session.scalars(select(Event).order_by(Event.occurred_at, Event.id)))


def server(
    serve: Serve, alerts: list[dict[str, object]] | None = None
) -> tuple[StubServer, Certificate]:
    """A Wazuh with these alerts, started with a certificate of its own."""
    certificate = make_certificate()
    started = serve(wazuh(USER, PASSWORD, alerts or [], []), certificate)
    return started, certificate


class TestRunningAgainstWazuh:
    def test_it_stores_the_alerts_of_the_last_half_hour_and_reading_them_again_adds_nothing(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started, certificate = server(serve, sample_wazuh_alerts(utcnow()))
        connect(session, settings, started.url, certificate)

        collect(settings, engine, Alerts())

        assert health(session).last_items == 4
        stored = stored_events(session)
        assert [item.summary for item in stored] == [
            "PAM: Login session opened. on nas (rule 5501, level 3)",
            "Integrity checksum changed. on web1 (rule 550, level 7)",
            "sshd: brute force trying to get access to the system. on web1 (rule 5712, level 10)",
            "sshd: Attempt to login using a non-existent user on web1 (rule 5710, level 5)",
        ]
        assert [(item.kind, item.severity) for item in stored] == [
            ("alert", 0),
            ("alert", 2),
            ("alert", 2),
            ("alert", 1),
        ]
        assert [str(item.src_address) for item in stored] == [
            "None",
            "None",
            "198.51.100.7",
            "198.51.100.7",
        ]

        collect(settings, engine, Alerts())

        assert health(session).last_items == 0
        assert len(stored_events(session)) == 4

    def test_it_asks_the_indexer_for_the_newest_alerts_of_a_window_with_the_users_login(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started, certificate = server(serve)
        connect(session, settings, started.url, certificate)
        before = utcnow()

        collect(settings, engine, Alerts())

        [asked] = [item for item in started.seen if item.path.endswith("_search")]
        assert (asked.method, asked.path) == ("POST", "/wazuh-alerts-*/_search")
        assert asked.headers["authorization"].startswith("Basic ")
        body = json.loads(asked.body)
        assert body["size"] == LIMIT
        assert body["sort"] == [{"timestamp": {"order": "desc"}}]
        since = datetime.fromisoformat(body["query"]["range"]["timestamp"]["gte"])
        assert abs(since - (before - WINDOW)) < timedelta(seconds=30)
        assert (health(session).consecutive_failures, health(session).last_items) == (0, 0)

    def test_no_alerts_is_a_quiet_network(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        reply: dict[str, Any] = {"took": 1, "timed_out": False, "hits": {"hits": []}}
        certificate = make_certificate()
        connect(session, settings, serve(answering(reply), certificate).url, certificate)

        collect(settings, engine, Alerts())

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 0)
        assert stored_events(session) == []

    def test_some_unreadable_hits_among_good_ones_are_just_skipped(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        reply = {"hits": {"hits": [hit(_id="a"), "nonsense", {"_id": "b"}]}}
        certificate = make_certificate()
        connect(session, settings, serve(answering(reply), certificate).url, certificate)

        collect(settings, engine, Alerts())

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 1)

    def test_hits_that_are_all_unreadable_say_so_instead_of_looking_like_a_quiet_network(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        reply: dict[str, Any] = {"hits": {"hits": ["nonsense", {"_id": "b"}]}}
        certificate = make_certificate()
        connect(session, settings, serve(answering(reply), certificate).url, certificate)

        collect(settings, engine, Alerts())

        record = health(session)
        assert record.consecutive_failures == 1
        assert record.last_error == "It answered, but the alerts aren't in a form AresGate reads."
        assert stored_events(session) == []

    @pytest.mark.parametrize(
        "reply", [["nothing"], {"hits": []}, {"hits": {"total": 3}}, {"message": "hello"}]
    )
    def test_an_answer_that_isnt_a_search_result_is_not_the_indexer(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve, reply: object
    ) -> None:
        certificate = make_certificate()
        connect(session, settings, serve(answering(reply), certificate).url, certificate)

        collect(settings, engine, Alerts())

        record = health(session)
        assert record.consecutive_failures == 1
        assert (
            record.last_error
            == "It answered, but the answer doesn't look like The Wazuh indexer's."
        )

    def test_a_login_it_refuses_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        refusing = serve(wazuh("someone else", PASSWORD), certificate)
        connect(session, settings, refusing.url, certificate)

        collect(settings, engine, Alerts())

        record = health(session)
        assert record.consecutive_failures == 1
        assert record.last_error is not None
        assert "didn't accept the credentials" in record.last_error

    def test_a_failure_of_the_indexer_is_reported_with_its_status(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        failing = serve(lambda seen: Answer(status=503, body="{}"), certificate)
        connect(session, settings, failing.url, certificate)

        collect(settings, engine, Alerts())

        assert health(session).last_error == "The Wazuh indexer answered HTTP 503."


def test_the_samples_are_alerts_of_wazuh_with_the_agents_they_are_about() -> None:
    alerts = sample_wazuh_alerts(NOW)
    agents = {agent["name"] for agent in sample_wazuh_agents(NOW)}

    assert len({item["_id"] for item in alerts}) == len(alerts)
    assert all(parse([item]) for item in alerts)
    assert {item["_source"]["agent"]["name"] for item in alerts} <= agents  # type: ignore[index]
