import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collectors import registry as collectors
from app.collectors.ntopng import protocols
from app.collectors.ntopng.protocols import Protocols, busiest
from app.config import Settings
from app.integrations import probes
from app.models import MetricSample, MetricSeries
from e2e.stand_ins import Answer, Seen, answers, ntopng, sample_ntopng_extras, sample_ntopng_hosts
from tests.ntopng import TOKEN, connect
from tests.opnsense import collect, health
from tests.stubs import Serve
from tests.test_ai_service import NOW


def test_it_reads_from_ntopng_and_is_one_of_the_collectors() -> None:
    assert Protocols.reads("ntopng", "api")
    assert not Protocols.reads("opnsense", "api")
    assert collectors.find("ntopng-protocols") is not None
    assert Protocols.interval == timedelta(minutes=5)
    assert Protocols.timeout <= Protocols.interval


def stored(session: Session) -> dict[tuple[str, tuple[tuple[str, str], ...]], float]:
    session.expire_all()
    rows = session.execute(
        select(MetricSeries.name, MetricSeries.labels, MetricSample.value).join(
            MetricSeries, MetricSeries.id == MetricSample.series_id
        )
    )
    return {(name, tuple(sorted(labels.items()))): value for name, labels, value in rows}


def stand_in(**more: Any) -> Callable[[Seen], Answer]:
    return ntopng(TOKEN, sample_ntopng_hosts(NOW), extras=sample_ntopng_extras(NOW), **more)


class TestRunningAgainstNtopng:
    def test_it_keeps_the_bytes_of_each_protocol_of_the_interface_and_of_each_host(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(stand_in()).url)

        collect(settings, engine, Protocols())

        found = stored(session)
        eth0 = (("interface", "eth0"),)
        assert found["interface.l7_bytes", (*eth0, ("protocol", "TLS"))] == 612_340_221
        assert found["interface.l7_bytes", (*eth0, ("protocol", "QUIC"))] == 204_220_113
        web = (("host", "192.168.1.20"),)
        assert found["host.l7_bytes", (*web, ("protocol", "SSH"))] == 88_340
        laptop = (("host", "192.168.1.41"),)
        assert found["host.l7_bytes", (*laptop, ("protocol", "YouTube"))] == 512_220_113
        assert health(session).last_items == 9

    def test_a_host_ntopng_has_forgotten_is_skipped_and_the_others_are_read(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(stand_in()).url)

        collect(settings, engine, Protocols())

        assert health(session).last_error is None
        assert not any(("host", "192.168.2.15") in labels for _name, labels in stored(session))

    def test_when_no_host_can_be_read_that_is_a_failure(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        extras = {
            path: answer
            for path, answer in sample_ntopng_extras(NOW).items()
            if not path.endswith("host/l7/stats.lua")
        }
        connect(
            session, settings, serve(ntopng(TOKEN, sample_ntopng_hosts(NOW), extras=extras)).url
        )

        collect(settings, engine, Protocols())

        assert health(session).last_error is not None

    def test_a_network_with_no_hosts_still_has_its_interface(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(ntopng(TOKEN, (), extras=sample_ntopng_extras(NOW))).url)

        collect(settings, engine, Protocols())

        assert health(session).last_error is None
        assert health(session).last_items == 3

    def test_an_interface_that_has_seen_nothing_has_no_protocols(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(
            session,
            settings,
            serve(ntopng(TOKEN, (), extras=sample_ntopng_extras(NOW), busy_ids=())).url,
        )

        collect(settings, engine, Protocols())

        assert health(session).last_items == 0

    def test_without_the_name_of_the_interface_it_is_known_by_its_number(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        inner = stand_in()

        def handle(seen: Seen) -> Answer:
            if seen.path.endswith("interfaces.lua"):
                return Answer(drop=True)
            return inner(seen)

        connect(session, settings, serve(handle).url)

        collect(settings, engine, Protocols())

        assert ("interface.l7_bytes", (("interface", "0"), ("protocol", "TLS"))) in stored(session)

    def test_an_answer_that_is_not_a_list_is_not_taken_for_one(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(
            session,
            settings,
            serve(lambda seen: Answer(body=json.dumps({"rc": 0, "rsp": {"data": []}}))).url,
        )

        collect(settings, engine, Protocols())

        assert health(session).last_error == probes.unexpected("ntopng").message


class TestTheProtocolsOfAnAnswer:
    def test_an_entry_without_a_name_or_a_number_of_bytes_is_left_out(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        sample = [
            {"label": "TLS", "value": 10},
            {"label": "", "value": 5},
            {"label": "DNS", "value": "many"},
            {"label": "SSH"},
            "text",
        ]
        extras = {"/lua/rest/v2/get/interface/l7/stats.lua": answers(sample)}
        connect(session, settings, serve(ntopng(TOKEN, (), extras=extras)).url)

        collect(settings, engine, Protocols())

        assert health(session).last_items == 1

    def test_only_the_largest_are_kept(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        serve: Serve,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(protocols, "PROTOCOLS", 2)
        connect(session, settings, serve(ntopng(TOKEN, (), extras=sample_ntopng_extras(NOW))).url)

        collect(settings, engine, Protocols())

        assert [labels[1][1] for _name, labels in stored(session)] == ["TLS", "QUIC"]


class TestTheBusiestHosts:
    def test_the_hosts_with_the_most_bytes_come_first_and_a_host_without_an_address_is_left_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hosts = [
            {"ip": "192.168.1.1", "bytes": {"total": 5}},
            {"ip": "192.168.1.2", "bytes": {"total": 50}},
            {"ip": "192.168.1.3"},
            {"bytes": {"total": 500}},
        ]

        assert busiest(hosts) == ["192.168.1.2", "192.168.1.1", "192.168.1.3"]
        monkeypatch.setattr(protocols, "HOSTS", 1)
        assert busiest(hosts) == ["192.168.1.2"]
