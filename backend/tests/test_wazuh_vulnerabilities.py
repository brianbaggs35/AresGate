import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collectors import registry as collectors
from app.collectors.wazuh import indexer
from app.collectors.wazuh.vulnerabilities import INDEX, LIMIT, Vulnerabilities
from app.config import Settings
from app.events.event import Severity
from app.models import Event, HostListing
from e2e.stand_ins import sample_wazuh_states, wazuh
from tests.opnsense import answering, collect, health
from tests.stubs import Answer, Seen, Serve, make_certificate
from tests.wazuh import PASSWORD, USER, connect

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def flaw(**changes: Any) -> dict[str, Any]:
    """A document of the indexer's vulnerabilities index: a flaw in nginx on web1."""
    document: dict[str, Any] = {
        "agent": {"id": "001", "name": "web1", "version": "v4.14.1"},
        "host": {"os": {"full": "Ubuntu 24.04.1 LTS"}},
        "package": {"name": "nginx", "version": "1.24.0-2ubuntu7", "type": "deb"},
        "vulnerability": {
            "id": "CVE-2024-7347",
            "severity": "Medium",
            "score": {"base": 4.7, "version": "3.1"},
            "description": "Buffer over-read in nginx.",
        },
    }
    document.update(changes)
    return document


def found(documents: list[Any]) -> dict[str, Any]:
    return {
        "hits": {
            "total": {"value": len(documents), "relation": "eq"},
            "hits": [{"_id": str(at), "_source": item} for at, item in enumerate(documents)],
        }
    }


def run_on(
    session: Session, settings: Settings, engine: Engine, serve: Serve, documents: list[Any]
) -> None:
    certificate = make_certificate()
    connect(session, settings, serve(answering(found(documents)), certificate).url, certificate)
    collect(settings, engine, Vulnerabilities())


def events(session: Session) -> list[Event]:
    session.expire_all()
    return list(session.scalars(select(Event).order_by(Event.id)))


class TestTheEvent:
    def test_a_flaw_is_an_event_of_its_own_kind_naming_the_cve_the_package_and_the_machine(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run_on(session, settings, engine, serve, [flaw()])

        [event] = events(session)
        assert (event.source, event.connection, event.kind) == (
            "wazuh",
            "indexer",
            "vulnerability",
        )
        assert event.severity == Severity.MEDIUM
        assert event.signature == "CVE-2024-7347"
        assert event.summary == "CVE-2024-7347 in nginx 1.24.0-2ubuntu7 on web1 (Medium, CVSS 4.7)"
        assert event.raw is not None
        assert event.raw["vulnerability"]["description"] == "Buffer over-read in nginx."
        assert health(session).last_items == 1

    @pytest.mark.parametrize(
        ("level", "severity"),
        [
            ("Critical", Severity.CRITICAL),
            ("High", Severity.HIGH),
            ("medium", Severity.MEDIUM),
            ("LOW", Severity.LOW),
            ("Untriaged", Severity.INFO),
            ("", Severity.INFO),
        ],
    )
    def test_how_serious_it_is_follows_what_wazuh_rates_it_whatever_the_case(
        self,
        level: str,
        severity: Severity,
        session: Session,
        settings: Settings,
        engine: Engine,
        serve: Serve,
    ) -> None:
        document = flaw()
        document["vulnerability"]["severity"] = level

        run_on(session, settings, engine, serve, [document])

        assert events(session)[0].severity == severity

    def test_a_flaw_that_is_not_rated_says_so(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        document = flaw()
        del document["vulnerability"]["severity"]
        del document["vulnerability"]["score"]
        del document["package"]["version"]

        run_on(session, settings, engine, serve, [document])

        assert events(session)[0].summary == "CVE-2024-7347 in nginx on web1 (not rated)"

    def test_a_score_that_is_not_a_number_is_left_out(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        document = flaw()
        document["vulnerability"]["score"] = {"base": True}

        run_on(session, settings, engine, serve, [document])

        assert events(session)[0].summary.endswith("(Medium)")

    def test_a_machine_with_no_name_is_called_by_its_number(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run_on(session, settings, engine, serve, [flaw(agent={"id": "007"})])

        assert " on agent 007 " in events(session)[0].summary

    def test_it_is_told_by_the_agent_the_cve_and_the_package_with_its_version(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        newer = flaw()
        newer["package"]["version"] = "1.26.0"
        elsewhere = flaw(agent={"id": "004", "name": "nas"})

        run_on(session, settings, engine, serve, [flaw(), flaw(), newer, elsewhere])

        assert len(events(session)) == 3
        assert health(session).last_items == 3

    def test_read_again_it_is_not_new_and_it_is_dated_by_the_run_that_first_saw_it(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run_on(session, settings, engine, serve, [flaw()])
        first = events(session)[0].occurred_at

        collect(settings, engine, Vulnerabilities())

        assert health(session).last_items == 0
        assert [event.occurred_at for event in events(session)] == [first]
        assert abs(first - datetime.now(UTC)) < timedelta(minutes=5)

    def test_a_flaw_is_about_the_address_the_manager_listed_for_the_agent(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        session.add(
            HostListing(
                source="wazuh",
                connection="manager",
                via="agent",
                key="001",
                address="192.168.1.20",
                state="active",
                online=True,
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
        )
        session.commit()

        run_on(session, settings, engine, serve, [flaw(), flaw(agent={"id": "009"})])

        [known, unknown] = events(session)
        assert str(known.dst_address) == "192.168.1.20"
        assert unknown.dst_address is None

    @pytest.mark.parametrize("missing", ["agent", "vulnerability", "package"])
    def test_a_document_that_does_not_say_which_flaw_in_what_on_whom_is_left_out(
        self,
        missing: str,
        session: Session,
        settings: Settings,
        engine: Engine,
        serve: Serve,
    ) -> None:
        broken = flaw()
        del broken[missing]

        run_on(session, settings, engine, serve, [broken, flaw()])

        assert len(events(session)) == 1
        assert health(session).consecutive_failures == 0

    def test_documents_that_are_all_unreadable_say_so(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run_on(session, settings, engine, serve, [flaw(agent={})])

        record = health(session)
        assert record.consecutive_failures == 1
        assert record.last_error == (
            "It answered, but the vulnerabilities aren't in a form AresGate reads."
        )

    def test_an_indexer_with_no_vulnerabilities_is_a_quiet_network(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run_on(session, settings, engine, serve, [])

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 0)


class TestAskingTheIndexer:
    def test_it_asks_for_the_highest_scores_of_the_vulnerabilities_indices(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        asked: list[Seen] = []

        def handle(seen: Seen) -> Answer:
            asked.append(seen)
            return Answer(body=json.dumps(found([])))

        certificate = make_certificate()
        connect(session, settings, serve(handle, certificate).url, certificate)

        collect(settings, engine, Vulnerabilities())

        [seen] = asked
        assert (seen.method, seen.path) == ("POST", f"/{INDEX}/_search")
        assert json.loads(seen.body) == {
            "track_total_hits": True,
            "size": LIMIT,
            "sort": [{"vulnerability.score.base": {"order": "desc"}}],
            "query": {"match_all": {}},
        }
        assert seen.headers["authorization"].startswith("Basic ")

    def test_it_reads_the_stand_in_and_finds_each_machine_it_lists(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        started = serve(wazuh(USER, PASSWORD, states=sample_wazuh_states()), certificate)
        connect(session, settings, started.url, certificate)

        collect(settings, engine, Vulnerabilities())

        assert [event.signature for event in events(session)] == [
            "CVE-2024-7347",
            "CVE-2024-13176",
            "CVE-2025-0001",
        ]
        assert [event.severity for event in events(session)] == [
            Severity.MEDIUM,
            Severity.HIGH,
            Severity.CRITICAL,
        ]

    def test_a_user_who_may_not_read_the_states_indices_is_told_what_to_allow(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        reason = "no permissions for [indices:data/read/search] and User [name=aresgate]"
        certificate = make_certificate()
        connect(
            session,
            settings,
            serve(answering({"error": {"reason": reason}}, status=403), certificate).url,
            certificate,
        )

        collect(settings, engine, Vulnerabilities())

        error = health(session).last_error or ""
        assert "isn't allowed to read what the agents report (HTTP 403)" in error
        assert "read on wazuh-states-*" in error
        assert "wazuh-alerts" not in error

    def test_an_answer_that_is_not_a_search_is_not_the_indexer(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        connect(session, settings, serve(answering({"hits": 3}), certificate).url, certificate)

        collect(settings, engine, Vulnerabilities())

        assert health(session).consecutive_failures == 1
        assert "doesn't look like" in (health(session).last_error or "")

    def test_hits_that_are_all_unreadable_say_so(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        reply = {"hits": {"total": {"value": 2}, "hits": ["nonsense", {"_source": 3}]}}
        certificate = make_certificate()
        connect(session, settings, serve(answering(reply), certificate).url, certificate)

        collect(settings, engine, Vulnerabilities())

        assert health(session).last_error == (
            "It answered, but what the agents report isn't in a form AresGate reads."
        )


class TestWhichAgent:
    def test_it_is_the_agent_of_the_document(self) -> None:
        assert indexer.agent_of({"agent": {"id": "001", "name": "web1"}}) == ("001", "web1")

    def test_a_pre_release_of_wazuh_5_nests_it_under_wazuh(self) -> None:
        document = {"wazuh": {"agent": {"id": "002", "name": "nas"}}}

        assert indexer.agent_of(document) == ("002", "nas")

    def test_a_document_that_says_nothing_of_one_has_none(self) -> None:
        assert indexer.agent_of({"agent": "web1"}) == ("", "")

    @pytest.mark.parametrize(
        ("total", "count"),
        [({"value": 5, "relation": "eq"}, 5), (7, 7), (True, 0), ("9", 0), (None, 0)],
    )
    def test_how_many_matched_is_read_as_a_number_or_as_none(
        self, total: object, count: int
    ) -> None:
        assert indexer.how_many(total) == count


def test_it_reads_from_the_indexer_and_is_one_of_the_collectors() -> None:
    collector = Vulnerabilities()

    assert (collector.integration, collector.connection) == ("wazuh", "indexer")
    assert collectors.find("wazuh-vulnerabilities") is not None
    assert collector.reads("wazuh", "indexer")
    assert not collector.reads("wazuh", "manager")
