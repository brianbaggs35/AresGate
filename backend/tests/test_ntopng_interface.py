import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collectors import registry as collectors
from app.collectors.ntopng.interface import InterfaceTraffic
from app.config import Settings
from app.integrations import probes
from app.models import MetricSample, MetricSeries
from e2e.stand_ins import Answer, Seen, ntopng, sample_ntopng_interface
from tests.ntopng import TOKEN, connect
from tests.opnsense import collect, health
from tests.stubs import Serve


def test_it_reads_from_ntopng_and_is_one_of_the_collectors() -> None:
    assert InterfaceTraffic.reads("ntopng", "api")
    assert not InterfaceTraffic.reads("opnsense", "api")
    assert InterfaceTraffic.module is None
    assert collectors.find("ntopng-interface") is not None
    assert InterfaceTraffic.interval == timedelta(minutes=1)
    assert InterfaceTraffic.timeout >= InterfaceTraffic.interval


def answering(rsp: object) -> Callable[[Seen], Answer]:
    return lambda seen: Answer(body=json.dumps({"rc": 0, "rc_str": "OK", "rsp": rsp}))


def stored(session: Session) -> dict[str, tuple[float, dict[str, str]]]:
    session.expire_all()
    rows = session.execute(
        select(MetricSeries.name, MetricSample.value, MetricSeries.labels).join(
            MetricSeries, MetricSeries.id == MetricSample.series_id
        )
    )
    return {name: (value, labels) for name, value, labels in rows}


class TestRunningAgainstNtopng:
    def test_it_keeps_the_counters_and_the_sizes_of_the_interface(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(ntopng(TOKEN, interface=sample_ntopng_interface())).url)

        collect(settings, engine, InterfaceTraffic())

        assert health(session).last_items == 12
        found = stored(session)
        assert found["interface.bytes_in"] == (912_340_221, {"interface": "eth0"})
        assert found["interface.bytes_out"][0] == 104_220_113
        assert found["interface.bytes_local_to_remote"][0] == 84_220_113
        assert found["interface.hosts"][0] == 41
        assert found["interface.alerts_engaged"][0] == 2
        assert "interface.throughput_bps" not in found

    def test_it_asks_for_the_interface_the_connection_watches(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started = serve(ntopng(TOKEN, interface=sample_ntopng_interface()))
        connect(session, settings, started.url)

        collect(settings, engine, InterfaceTraffic())

        [asked] = [item for item in started.seen if item.path.endswith("interface/data.lua")]
        assert asked.target.endswith("data.lua?ifid=0")
        assert asked.headers["authorization"] == f"Token {TOKEN}"

    def test_what_it_has_no_number_for_is_left_out_and_an_interface_without_a_name_is_its_id(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        rsp: dict[str, Any] = {"bytes_download": 5, "bytes_upload": "n/a", "num_hosts": True}
        connect(session, settings, serve(answering(rsp)).url, interface_id=3)

        collect(settings, engine, InterfaceTraffic())

        assert stored(session) == {"interface.bytes_in": (5, {"interface": "3"})}

    def test_an_interface_that_has_seen_nothing_says_so_instead_of_keeping_zeros(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        quiet = {
            "ifname": "eth1",
            "bytes_download": 0,
            "bytes_upload": 0,
            "num_hosts": 0,
            "num_flows": 0,
        }
        connect(session, settings, serve(answering(quiet)).url, interface_id=1)

        collect(settings, engine, InterfaceTraffic())

        assert health(session).last_error == (
            "ntopng's interface eth1 hasn't seen any traffic yet, so there is nothing to read "
            "from it. If it isn't the interface you mean, choose another under Interface in "
            "the connection's settings."
        )
        assert stored(session) == {}

    def test_an_interface_that_does_not_give_all_the_counts_is_not_called_quiet(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        rsp: dict[str, Any] = {"ifname": "eth1", "bytes_download": 0, "bytes_upload": 0}
        connect(session, settings, serve(answering(rsp)).url, interface_id=1)

        collect(settings, engine, InterfaceTraffic())

        assert health(session).last_error is None
        assert stored(session)["interface.bytes_in"] == (0, {"interface": "eth1"})

    def test_an_interface_with_hosts_but_no_bytes_yet_is_not_quiet(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        rsp: dict[str, Any] = {
            "ifname": "eth1",
            "bytes_download": 0,
            "bytes_upload": 0,
            "num_hosts": 3,
            "num_flows": 0,
        }
        connect(session, settings, serve(answering(rsp)).url, interface_id=1)

        collect(settings, engine, InterfaceTraffic())

        assert health(session).last_error is None

    def test_an_answer_without_anything_to_read_fails(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(answering({"ifname": "eth0"})).url)

        collect(settings, engine, InterfaceTraffic())

        assert health(session).last_error == (
            "It answered, but the interface isn't in a form AresGate reads."
        )

    def test_an_answer_that_is_not_an_object_fails(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(answering([1, 2])).url)

        collect(settings, engine, InterfaceTraffic())

        assert health(session).last_error == probes.unexpected("ntopng").message
