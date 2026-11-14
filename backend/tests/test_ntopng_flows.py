import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collectors import registry as collectors
from app.collectors.ntopng.flows import Flows, parse
from app.config import Settings
from app.events.event import Severity
from app.integrations import probes
from app.models import Event
from e2e.stand_ins import Answer, answers, ntopng, sample_ntopng_extras
from tests.ntopng import TOKEN, connect
from tests.opnsense import collect, health
from tests.stubs import Serve

BEGAN = 1_761_473_523


def flow(**changes: Any) -> dict[str, Any]:
    """A flow as ntopng's active flows answer gives it."""
    row: dict[str, Any] = {
        "key": "9001",
        "first_seen": BEGAN,
        "client": {"ip": "192.168.1.41", "port": 51514},
        "server": {"ip": "203.0.113.9", "port": 443},
        "protocol": {"l4": "TCP", "l7": "TLS"},
        "bytes": 4096,
        "score": "11.2 K",
    }
    row.update(changes)
    return row


def test_it_reads_from_ntopng_and_is_one_of_the_collectors() -> None:
    assert Flows.reads("ntopng", "api")
    assert not Flows.reads("opnsense", "api")
    assert collectors.find("ntopng-flows") is not None
    assert Flows.interval == timedelta(minutes=1)
    assert Flows.timeout >= Flows.interval


class TestAFlow:
    def test_it_is_an_event_of_its_own_kind_about_who_talked_to_whom(self) -> None:
        [event] = parse([flow()], "eth0")

        assert (event.source, event.connection, event.kind) == ("ntopng", "api", "flow")
        assert event.severity == Severity.INFO
        assert event.occurred_at == datetime.fromtimestamp(BEGAN, UTC)
        assert event.summary == "TLS: 192.168.1.41:51514 to 203.0.113.9:443"
        assert event.signature == "TLS"
        assert (event.src_address, event.src_port) == ("192.168.1.41", 51514)
        assert (event.dst_address, event.dst_port) == ("203.0.113.9", 443)
        assert (event.protocol, event.iface) == ("tcp", "eth0")
        assert event.raw is not None
        assert event.raw["bytes"] == 4096

    def test_the_same_flow_is_the_same_event_and_a_later_one_with_its_key_is_another(self) -> None:
        [first] = parse([flow()], "eth0")
        [again] = parse([flow(bytes=9)], "eth0")
        [later] = parse([flow(first_seen=BEGAN + 600)], "eth0")

        assert first.fingerprint == again.fingerprint
        assert first.fingerprint != later.fingerprint

    def test_one_that_says_nothing_of_where_it_went_is_still_a_flow(self) -> None:
        [event] = parse([flow(client=None, server=None, protocol=None)])

        assert (event.summary, event.signature, event.protocol, event.iface) == (
            "Flow",
            None,
            None,
            None,
        )

    def test_one_with_no_protocol_name_is_named_by_where_it_went(self) -> None:
        [event] = parse([flow(protocol={"l4": "UDP"})])

        assert event.summary == "Flow: 192.168.1.41:51514 to 203.0.113.9:443"
        assert event.protocol == "udp"

    def test_one_that_has_no_key_or_no_time_or_a_score_of_nothing_is_left_out(self) -> None:
        assert (
            parse(["text", flow(key=""), flow(first_seen=None), flow(score="0"), flow(score=0)])
            == []
        )

    def test_a_score_ntopng_formats_for_a_page_still_counts(self) -> None:
        assert len(parse([flow(score="1.2 K"), flow(score=None), flow(score=5)])) == 3


class TestRunningAgainstNtopng:
    def test_it_keeps_the_flows_with_a_score_as_events(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(
            session,
            settings,
            serve(ntopng(TOKEN, extras=sample_ntopng_extras(datetime.now(UTC)))).url,
        )

        collect(settings, engine, Flows())

        assert health(session).last_items == 2
        events = session.scalars(select(Event).order_by(Event.summary)).all()
        assert [event.kind for event in events] == ["flow", "flow"]
        assert [event.summary for event in events] == [
            "TLS: 192.168.1.20:40222 to 198.51.100.30:8443",
            "TLS: 192.168.1.41:51514 to 203.0.113.9:443",
        ]
        assert {event.iface for event in events} == {"eth0"}

    def test_it_asks_for_the_flows_with_the_highest_score(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        asked: list[str] = []

        def handle(seen: Any) -> Answer:
            asked.append(seen.target)
            if seen.path.endswith("interfaces.lua"):
                return Answer(body=json.dumps({"rc": 0, "rsp": [{"ifid": 0, "ifname": "eth0"}]}))
            return Answer(body=json.dumps({"rc": 0, "rsp": {"data": []}}))

        connect(session, settings, serve(handle).url)

        collect(settings, engine, Flows())

        [flows] = [target for target in asked if "flow/active" in target]
        for part in ("ifid=0", "sortColumn=column_score", "sortOrder=desc", "perPage=100"):
            assert part in flows
        assert health(session).last_items == 0

    def test_an_interface_that_has_seen_nothing_has_no_flows(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(
            session,
            settings,
            serve(ntopng(TOKEN, extras=sample_ntopng_extras(datetime.now(UTC)), busy_ids=())).url,
        )

        collect(settings, engine, Flows())

        assert health(session).last_items == 0

    def test_flows_that_all_have_no_score_are_not_a_failure(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        extras = {"/lua/rest/v2/get/flow/active.lua": answers({"data": [flow(score="0")]})}
        connect(session, settings, serve(ntopng(TOKEN, extras=extras)).url)

        collect(settings, engine, Flows())

        assert health(session).last_error is None

    def test_flows_that_are_not_in_a_form_it_reads_are_a_failure(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        extras = {"/lua/rest/v2/get/flow/active.lua": answers({"data": ["text"]})}
        connect(session, settings, serve(ntopng(TOKEN, extras=extras)).url)

        collect(settings, engine, Flows())

        assert health(session).last_error == (
            "It answered, but the flows aren't in a form AresGate reads."
        )

    def test_an_answer_without_a_list_of_flows_is_not_taken_for_one(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        extras = {"/lua/rest/v2/get/flow/active.lua": answers({"totalRows": 0})}
        connect(session, settings, serve(ntopng(TOKEN, extras=extras)).url)

        collect(settings, engine, Flows())

        assert health(session).last_error == probes.unexpected("ntopng").message
