from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collectors import registry as collectors
from app.collectors.crowdsec.decisions import LIMIT, Decisions, parse
from app.config import Settings
from app.events.event import Severity
from app.integrations import netguard, registry, service
from app.integrations.service import Submission
from app.models import Event, MetricSample, MetricSeries, utcnow
from e2e.stand_ins import crowdsec, sample_crowdsec_decisions
from tests.opnsense import answering, collect, health
from tests.stubs import Answer, Seen, Serve

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
KEY = "bouncer-key"


def decision(**changes: Any) -> dict[str, Any]:
    """A decision as CrowdSec's local API gives it."""
    row: dict[str, Any] = {
        "id": 101,
        "origin": "crowdsec",
        "type": "ban",
        "scope": "Ip",
        "value": "198.51.100.7",
        "duration": "3h59m12s",
        "scenario": "crowdsecurity/ssh-bf",
        "simulated": False,
    }
    row.update(changes)
    return row


class TestReadingDecisions:
    def test_a_ban_becomes_an_event(self) -> None:
        [event] = parse([decision()], NOW)

        assert (event.source, event.connection, event.kind) == ("crowdsec", "lapi", "decision")
        assert event.occurred_at == NOW
        assert event.severity == Severity.MEDIUM
        assert event.signature == "crowdsecurity/ssh-bf"
        assert event.src_address == "198.51.100.7"
        assert (event.src_port, event.dst_address, event.dst_port) == (None, None, None)
        assert event.summary == "Ban 198.51.100.7 for 3h59m12s: crowdsecurity/ssh-bf"
        assert event.raw == decision()

    def test_a_ban_of_a_range_has_no_address_to_the_event_but_says_it_in_the_summary(self) -> None:
        [event] = parse([decision(scope="Range", value="203.0.113.0/24", origin="cscli")], NOW)

        assert event.src_address is None
        assert event.summary.startswith("Ban 203.0.113.0/24 for ")

    @pytest.mark.parametrize(("scope", "kept"), [("Ip", True), ("ip", True), ("Country", False)])
    def test_only_an_address_is_the_source_of_an_attack(self, scope: str, kept: bool) -> None:
        [event] = parse([decision(scope=scope, value="198.51.100.7")], NOW)

        assert (event.src_address == "198.51.100.7") is kept

    def test_a_remedy_that_is_not_a_ban_is_the_lesser_worry(self) -> None:
        [event] = parse([decision(type="captcha")], NOW)

        assert event.severity == Severity.LOW
        assert event.summary.startswith("Captcha 198.51.100.7")

    def test_a_ban_that_was_only_simulated_is_a_note(self) -> None:
        [event] = parse([decision(simulated=True)], NOW)

        assert event.severity == Severity.INFO
        assert "(simulated)" in event.summary

    def test_a_decision_with_little_on_it_still_says_what_it_can(self) -> None:
        [event] = parse([{"id": 7, "value": "198.51.100.7"}], NOW)

        assert event.summary == "Ban 198.51.100.7"
        assert event.signature is None
        assert event.severity == Severity.MEDIUM
        assert event.src_address is None

    @pytest.mark.parametrize(
        "row",
        [
            "nonsense",
            None,
            {"value": "198.51.100.7"},
            {"id": 5},
            {"id": True, "value": "198.51.100.7"},
            {"id": [1], "value": "198.51.100.7"},
            {"id": 5, "value": ""},
        ],
    )
    def test_a_row_that_cant_be_read_is_left_out_and_the_rest_are_kept(self, row: object) -> None:
        events = parse([decision(id=1), row, decision(id=2, value="198.51.100.8")], NOW)

        assert [event.src_address for event in events] == ["198.51.100.7", "198.51.100.8"]

    def test_nothing_is_nothing(self) -> None:
        assert parse([], NOW) == []

    def test_a_decision_is_the_same_event_each_time_it_is_read(self) -> None:
        [first] = parse([decision(duration="3h59m12s")], NOW)
        [later] = parse([decision(duration="2h1m")], datetime(2026, 10, 26, 14, tzinfo=UTC))

        assert first.fingerprint == later.fingerprint

    def test_a_number_reused_for_another_ban_is_another_event(self) -> None:
        [first] = parse([decision()], NOW)
        [again] = parse([decision(value="198.51.100.9")], NOW)
        [other] = parse([decision(scenario="crowdsecurity/http-bf")], NOW)

        assert len({first.fingerprint, again.fingerprint, other.fingerprint}) == 3

    def test_it_reads_from_the_local_api_and_is_one_of_the_collectors(self) -> None:
        assert Decisions.reads("crowdsec", "lapi")
        assert not Decisions.reads("crowdsec", "other")
        assert not Decisions.reads("opnsense", "api")
        assert Decisions.module is None
        assert collectors.find("crowdsec-decisions") is not None


def connect(session: Session, settings: Settings, url: str) -> None:
    """Saves a connection to the local API at the address, with a bouncer's key."""
    submission = Submission(
        url=url,
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options={},
        secrets={"api_key": KEY},
    )
    service.save(
        session,
        settings,
        netguard.HOME_NETWORK_AND_LOOPBACK,
        registry.INTEGRATIONS["crowdsec"],
        {"lapi": submission},
        utcnow(),
    )
    session.commit()


def stored_events(session: Session) -> list[Event]:
    session.expire_all()
    return list(session.scalars(select(Event).order_by(Event.summary)))


def active(session: Session) -> list[float]:
    """The number of bans each run counted, oldest first."""
    session.expire_all()
    rows = session.execute(
        select(MetricSample.value)
        .join(MetricSeries, MetricSeries.id == MetricSample.series_id)
        .where(MetricSeries.name == "decisions.active")
        .order_by(MetricSample.sampled_at)
    )
    return [value for (value,) in rows]


def handler_for(decisions: Sequence[dict[str, Any]]) -> Callable[[Seen], Answer]:
    return crowdsec(KEY, decisions)


class TestRunningAgainstCrowdsec:
    def test_it_stores_the_bans_made_here_and_reading_them_again_adds_nothing(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(handler_for(sample_crowdsec_decisions())).url)

        collect(settings, engine, Decisions())

        assert health(session).last_items == 3
        stored = stored_events(session)
        assert [item.summary for item in stored] == [
            "Ban 198.51.100.7 for 3h59m12s: crowdsecurity/ssh-bf",
            "Ban 203.0.113.0/24 for 23h58m1s: manual 'ban' from 'localhost'",
            "Captcha 192.0.2.77 for 1h2m3s: crowdsecurity/http-crawl-non_statics",
        ]
        assert [(item.kind, item.severity) for item in stored] == [
            ("decision", 2),
            ("decision", 2),
            ("decision", 1),
        ]
        assert [str(item.src_address) for item in stored] == [
            "198.51.100.7",
            "None",
            "192.0.2.77",
        ]
        assert active(session) == [3]

        collect(settings, engine, Decisions())

        assert health(session).last_items == 0
        assert len(stored_events(session)) == 3
        assert active(session) == [3, 3]

    def test_it_asks_for_what_was_decided_here_and_not_the_community_blocklist(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        server = serve(handler_for(sample_crowdsec_decisions()))
        connect(session, settings, server.url)

        collect(settings, engine, Decisions())

        [asked] = [item for item in server.seen if item.path == "/v1/decisions"]
        assert asked.method == "GET"
        assert parse_qs(urlsplit(asked.target).query) == {"origins": ["crowdsec,cscli"]}
        assert asked.headers["x-api-key"] == KEY
        assert (health(session).consecutive_failures, health(session).last_items) == (0, 3)

    def test_no_bans_is_a_quiet_network_with_none_banned(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(handler_for([])).url)

        collect(settings, engine, Decisions())

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 0)
        assert stored_events(session) == []
        assert active(session) == [0]

    def test_an_empty_list_is_the_same(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(answering([])).url)

        collect(settings, engine, Decisions())

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 0)
        assert active(session) == [0]

    def test_some_unreadable_rows_among_good_ones_are_just_skipped(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(answering([decision(), "nonsense", {"id": 3}])).url)

        collect(settings, engine, Decisions())

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 1)
        assert active(session) == [1]

    def test_rows_that_are_all_unreadable_say_so_instead_of_looking_like_a_quiet_network(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(answering(["nonsense", {"id": 3}])).url)

        collect(settings, engine, Decisions())

        record = health(session)
        assert record.consecutive_failures == 1
        assert record.last_error == "It answered, but the bans aren't in a form AresGate reads."
        assert stored_events(session) == []
        assert active(session) == []

    def test_an_answer_that_isnt_a_list_is_not_the_local_api(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(answering({"message": "hello"})).url)

        collect(settings, engine, Decisions())

        record = health(session)
        assert record.consecutive_failures == 1
        assert record.last_error == "It answered, but the answer doesn't look like CrowdSec's."

    def test_a_key_it_refuses_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(crowdsec("another-key", [decision()])).url)

        collect(settings, engine, Decisions())

        record = health(session)
        assert record.consecutive_failures == 1
        assert record.last_error is not None
        assert "didn't accept the credentials" in record.last_error

    def test_it_keeps_no_more_than_a_thousand_a_run(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        many = [
            decision(id=number, value=f"10.0.{number // 250}.{number % 250}")
            for number in range(LIMIT + 5)
        ]
        connect(session, settings, serve(handler_for(many)).url)

        collect(settings, engine, Decisions())

        assert health(session).last_items == LIMIT
        assert active(session) == [float(LIMIT)]
