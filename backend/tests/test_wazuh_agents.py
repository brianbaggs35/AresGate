import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collectors import registry as collectors
from app.collectors.wazuh.agents import LIMIT, Agents, samples, silent
from app.config import Settings
from app.events.event import Severity
from app.models import Event, MetricSample, MetricSeries
from e2e.stand_ins import sample_wazuh_agents, wazuh
from tests.opnsense import answering, collect, health
from tests.stubs import Answer, Certificate, Seen, Serve, StubServer, make_certificate
from tests.wazuh import PASSWORD, USER, connect

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def agent(**changes: Any) -> dict[str, Any]:
    """An agent as the manager's API lists it, here one that stopped reporting."""
    row: dict[str, Any] = {
        "id": "002",
        "name": "laptop",
        "ip": "192.168.1.41",
        "status": "disconnected",
        "lastKeepAlive": "2026-10-26T10:00:00+00:00",
    }
    row.update(changes)
    return row


def counts(found: list[Any]) -> dict[str, float]:
    return {item.labels["status"]: item.value for item in found}


class TestCountingAgents:
    def test_every_state_is_counted_even_when_no_agent_is_in_it(self) -> None:
        found = samples([agent(status="active"), agent(id="3", status="active")], NOW)

        assert counts(found) == {
            "active": 2,
            "disconnected": 0,
            "pending": 0,
            "never_connected": 0,
        }
        assert all(
            (item.source, item.connection, item.name, item.sampled_at)
            == ("wazuh", "manager", "agents.count", NOW)
            for item in found
        )

    def test_no_agents_is_four_zeros(self) -> None:
        assert list(counts(samples([], NOW)).values()) == [0, 0, 0, 0]

    def test_a_state_it_has_no_word_for_here_is_counted_under_its_own_name(self) -> None:
        found = samples(
            [agent(status="Upgrading"), agent(status=None), agent(status="active")], NOW
        )

        assert counts(found) == {
            "active": 1,
            "disconnected": 0,
            "pending": 0,
            "never_connected": 0,
            "unknown": 1,
            "upgrading": 1,
        }


class TestAgentsThatWentQuiet:
    def test_a_disconnected_agent_is_an_event_dated_by_when_it_was_last_heard_from(self) -> None:
        [event] = silent([agent()])

        assert (event.source, event.connection, event.kind) == ("wazuh", "manager", "agent")
        assert event.occurred_at == datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
        assert event.severity == Severity.INFO
        assert event.summary == "laptop (192.168.1.41) stopped reporting to Wazuh"
        assert event.signature == "agent disconnected"
        assert (event.src_address, event.dst_address) == (None, "192.168.1.41")
        assert event.raw == agent()

    @pytest.mark.parametrize("status", ["active", "pending", "never_connected", None])
    def test_an_agent_that_is_not_disconnected_is_no_event(self, status: str | None) -> None:
        assert silent([agent(status=status)]) == []

    @pytest.mark.parametrize("stamp", [None, "", "yesterday", "2026-10-26T10:00:00", 1761473523])
    def test_one_with_no_time_to_date_it_by_is_left_out(self, stamp: object) -> None:
        assert silent([agent(lastKeepAlive=stamp), agent(id="3")]) == silent([agent(id="3")])
        assert len(silent([agent(lastKeepAlive=stamp)])) == 0

    def test_a_status_in_capitals_is_the_same_status(self) -> None:
        assert len(silent([agent(status="Disconnected")])) == 1

    def test_the_agent_is_named_by_what_is_known_of_it(self) -> None:
        [named] = silent([agent(ip=None)])
        [addressed] = silent([agent(name=None)])
        [bare] = silent([agent(name=None, ip=None)])

        assert named.summary == "laptop stopped reporting to Wazuh"
        assert addressed.summary == "192.168.1.41 stopped reporting to Wazuh"
        assert bare.summary == "agent 002 stopped reporting to Wazuh"
        assert (bare.dst_address, named.dst_address) == (None, None)

    def test_the_same_silence_read_again_is_the_same_event_and_a_new_one_is_another(self) -> None:
        [first] = silent([agent()])
        [again] = silent([agent(name="laptop renamed")])
        [later] = silent([agent(lastKeepAlive="2026-10-26T11:00:00+00:00")])

        assert first.fingerprint == again.fingerprint
        assert first.fingerprint != later.fingerprint

    def test_a_time_in_another_zone_is_the_same_moment(self) -> None:
        [event] = silent([agent(lastKeepAlive="2026-10-26T07:00:00-03:00")])

        assert event.occurred_at == datetime(2026, 10, 26, 10, 0, tzinfo=UTC)


def test_it_reads_from_the_manager_and_is_one_of_the_collectors() -> None:
    assert Agents.reads("wazuh", "manager")
    assert not Agents.reads("wazuh", "indexer")
    assert not Agents.reads("opnsense", "api")
    assert Agents.module is None
    assert collectors.find("wazuh-agents") is not None
    assert Agents.interval == timedelta(minutes=1)
    assert Agents.timeout >= Agents.interval


def stored_events(session: Session) -> list[Event]:
    session.expire_all()
    return list(session.scalars(select(Event).order_by(Event.occurred_at, Event.id)))


def stored_counts(session: Session) -> list[dict[str, float]]:
    """The counts each run stored, oldest first: the number for each state."""
    session.expire_all()
    rows = session.execute(
        select(MetricSample.sampled_at, MetricSeries.labels, MetricSample.value)
        .join(MetricSeries, MetricSeries.id == MetricSample.series_id)
        .where(MetricSeries.name == "agents.count")
        .order_by(MetricSample.sampled_at, MetricSeries.id)
    )
    runs: dict[datetime, dict[str, float]] = {}
    for sampled_at, labels, value in rows:
        runs.setdefault(sampled_at, {})[labels["status"]] = value
    return list(runs.values())


def server(serve: Serve, agents: list[dict[str, object]]) -> tuple[StubServer, Certificate]:
    certificate = make_certificate()
    return serve(wazuh(USER, PASSWORD, [], agents), certificate), certificate


def listing(rows: Sequence[object]) -> Callable[[Seen], Answer]:
    """A manager that gives a token to anyone and lists these rows as its agents, whatever they
    are."""

    def handle(seen: Seen) -> Answer:
        if seen.method == "POST":
            return Answer(body="a.token.value")
        return Answer(body=json.dumps({"data": {"affected_items": rows}}))

    return handle


class TestRunningAgainstWazuh:
    def test_it_counts_the_agents_and_notes_the_one_that_stopped(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started, certificate = server(serve, sample_wazuh_agents(datetime.now(UTC)))
        connect(session, settings, started.url, certificate)

        collect(settings, engine, Agents())

        assert health(session).last_items == 1
        assert stored_counts(session) == [
            {"active": 2, "disconnected": 1, "pending": 0, "never_connected": 1}
        ]
        [event] = stored_events(session)
        assert event.summary == "laptop (192.168.1.41) stopped reporting to Wazuh"

        collect(settings, engine, Agents())

        assert health(session).last_items == 0
        assert len(stored_events(session)) == 1
        assert len(stored_counts(session)) == 2

    def test_it_signs_in_for_a_token_and_asks_for_the_agents_with_it(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started, certificate = server(serve, sample_wazuh_agents(NOW))
        connect(session, settings, started.url, certificate)

        collect(settings, engine, Agents())

        [signed_in, asked] = started.seen
        assert (signed_in.method, signed_in.target) == (
            "POST",
            "/security/user/authenticate?raw=true",
        )
        assert signed_in.headers["authorization"].startswith("Basic ")
        assert (asked.method, asked.path) == ("GET", "/agents")
        assert asked.headers["authorization"].startswith("Bearer ")
        assert f"limit={LIMIT}" in asked.target
        assert "select=id%2Cname%2Cip%2Cstatus%2ClastKeepAlive" in asked.target

    def test_the_token_is_kept_out_of_the_api_log_and_the_health_record(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started, certificate = server(serve, sample_wazuh_agents(NOW))
        connect(session, settings, started.url, certificate)

        collect(settings, engine, Agents())

        token = started.seen[1].headers["authorization"].removeprefix("Bearer ")
        assert token not in (health(session).last_error or "")

    def test_a_manager_with_only_itself_has_no_agents_to_count(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        manager = [agent(id="000", name="wazuh-server", status="active", lastKeepAlive=None)]
        started, certificate = server(serve, manager)
        connect(session, settings, started.url, certificate)

        collect(settings, engine, Agents())

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 0)
        assert stored_counts(session) == [
            {"active": 0, "disconnected": 0, "pending": 0, "never_connected": 0}
        ]
        assert stored_events(session) == []

    def test_a_row_that_isnt_an_agent_is_skipped_among_good_ones(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        rows = ["nonsense", {"name": "no id"}, agent(), agent(id="000")]
        certificate = make_certificate()
        connect(session, settings, serve(listing(rows), certificate).url, certificate)

        collect(settings, engine, Agents())

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 1)
        assert stored_counts(session)[0]["disconnected"] == 1

    def test_rows_that_are_all_unreadable_say_so_instead_of_looking_like_a_quiet_network(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        connect(session, settings, serve(listing(["nonsense", 3]), certificate).url, certificate)

        collect(settings, engine, Agents())

        record = health(session)
        assert record.consecutive_failures == 1
        assert record.last_error == "It answered, but the agents aren't in a form AresGate reads."
        assert stored_counts(session) == []

    @pytest.mark.parametrize(
        "reply", [["nothing"], {"data": []}, {"data": {"total": 3}}, {"message": "hello"}]
    )
    def test_an_answer_that_isnt_a_list_of_agents_is_not_the_manager(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve, reply: object
    ) -> None:
        certificate = make_certificate()
        connect(session, settings, serve(answering(reply), certificate).url, certificate)

        collect(settings, engine, Agents())

        record = health(session)
        assert record.consecutive_failures == 1
        # The first thing asked for is a token, which isn't a JSON answer at all.
        assert record.last_error is not None

    def test_a_login_it_refuses_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        connect(
            session, settings, serve(wazuh("someone else", PASSWORD), certificate).url, certificate
        )

        collect(settings, engine, Agents())

        record = health(session)
        assert record.consecutive_failures == 1
        assert record.last_error is not None
        assert "didn't accept the credentials" in record.last_error

    def test_a_token_that_is_not_a_token_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        handler = serve(lambda seen: Answer(body="<html>a login page</html>"), certificate)
        connect(session, settings, handler.url, certificate)

        collect(settings, engine, Agents())

        assert health(session).last_error == (
            "It answered, but the answer doesn't look like the Wazuh manager's."
        )

    def test_a_list_it_refuses_is_reported_with_its_status(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        def handle(seen: Seen) -> Answer:
            if seen.method == "POST":
                return Answer(body="a.token.value")
            return Answer(status=403, body="{}")

        certificate = make_certificate()
        connect(session, settings, serve(handle, certificate).url, certificate)

        collect(settings, engine, Agents())

        error = health(session).last_error or ""
        assert "didn't accept the credentials" in error
        assert "HTTP 403" in error
