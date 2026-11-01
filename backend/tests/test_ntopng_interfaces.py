"""What the ntopng collectors do when the connection reads more than one interface."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collectors.ntopng import api
from app.collectors.ntopng.alerts import FLOWS, HOSTS, Alerts
from app.collectors.ntopng.hosts import Hosts
from app.collectors.ntopng.interface import InterfaceTraffic
from app.config import Settings
from app.integrations import probes
from app.integrations.client import CallFailed
from app.models import Device, Event, MetricSample, MetricSeries
from e2e.stand_ins import Answer, Seen
from tests.ntopng import connect
from tests.opnsense import collect, health
from tests.stubs import Serve

LISTED = [
    {"ifid": 0, "ifname": "eth0", "name": "eth0", "is_packet_interface": True},
    {"ifid": 1, "ifname": "eth1", "name": "LAN", "is_packet_interface": True},
]
BUSY = {"ifname": "eth0", "bytes_download": 9, "bytes_upload": 5, "num_hosts": 4, "num_flows": 7}
QUIET = {"ifname": "eth1", "bytes_download": 0, "bytes_upload": 0, "num_hosts": 0, "num_flows": 0}
INTERFACES = "/lua/rest/v2/get/ntopng/interfaces.lua"
DATA = "/lua/rest/v2/get/interface/data.lua"
HOST_LIST = "/lua/rest/v2/get/host/active.lua"
NOW = int(datetime.now(UTC).timestamp())


def asked_about(seen: Seen) -> str:
    return parse_qs(urlsplit(seen.target).query).get("ifid", [""])[0]


def wrapped(rsp: object) -> Answer:
    return Answer(body=json.dumps({"rc": 0, "rc_str": "OK", "rsp": rsp}))


def two_interfaces(answers: dict[tuple[str, str], object]) -> Callable[[Seen], Answer]:
    """A ntopng that lists two interfaces and answers each request by its path and ifid; the
    alerts it has nothing for are none."""

    def handle(seen: Seen) -> Answer:
        if seen.path == INTERFACES:
            return wrapped(LISTED)
        nothing: dict[str, Any] = {"records": []} if seen.path in (FLOWS, HOSTS) else {}
        return wrapped(answers.get((seen.path, asked_about(seen)), nothing))

    return handle


def alert(row: str, host: str, **changes: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "row_id": row,
        "tstamp": {"value": NOW - 60},
        "alert_id": {"value": "5"},
        "severity": {"value": 4},
        "msg": {"name": "Scan Attacker"},
        "ip": {"value": host},
        "role": {"value": "attacker"},
    }
    return record | changes


def kept(session: Session) -> list[tuple[str | None, str]]:
    session.expire_all()
    return sorted((event.iface, str(event.src_address)) for event in session.scalars(select(Event)))  # type: ignore[type-var]


class TestAlerts:
    def test_each_chosen_interface_is_read_and_its_alerts_say_which_it_came_in_on(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started = serve(
            two_interfaces(
                {
                    (HOSTS, "0"): {"records": [alert("1", "192.168.1.41")]},
                    (HOSTS, "1"): {"records": [alert("1", "192.168.20.5")]},
                    (FLOWS, "1"): {"records": []},
                }
            )
        )
        connect(session, settings, started.url, interface_id="0,1")

        collect(settings, engine, Alerts())

        assert health(session).last_items == 2
        assert kept(session) == [("eth0", "192.168.1.41"), ("eth1", "192.168.20.5")]
        asked = [(item.path, asked_about(item)) for item in started.seen if item.path != INTERFACES]
        assert asked == [(FLOWS, "0"), (HOSTS, "0"), (FLOWS, "1"), (HOSTS, "1")]

    def test_one_interface_is_one_and_says_its_name_too(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started = serve(two_interfaces({(HOSTS, "1"): {"records": [alert("1", "192.168.20.5")]}}))
        connect(session, settings, started.url, interface_id=1)

        collect(settings, engine, Alerts())

        assert kept(session) == [("eth1", "192.168.20.5")]
        assert {asked_about(item) for item in started.seen if item.path != INTERFACES} == {"1"}

    def test_an_alert_is_kept_without_a_port_when_ntopng_will_not_list_its_interfaces(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        def handle(seen: Seen) -> Answer:
            if seen.path == INTERFACES:
                return Answer(status=500)
            records = [alert("1", "192.168.1.41")] if seen.path == HOSTS else []
            return wrapped({"records": records})

        connect(session, settings, serve(handle).url)

        collect(settings, engine, Alerts())

        assert health(session).last_error is None
        assert kept(session)[0] == (None, "192.168.1.41")

    def test_a_request_that_gets_no_answer_for_the_names_does_not_stop_the_alerts(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        serve: Serve,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def unreachable(*args: object) -> None:
            raise CallFailed("No answer.")

        monkeypatch.setattr(probes, "ntopng_interfaces", unreachable)
        connect(
            session,
            settings,
            serve(two_interfaces({(HOSTS, "0"): {"records": [alert("1", "192.168.1.41")]}})).url,
        )

        collect(settings, engine, Alerts())

        assert kept(session) == [(None, "192.168.1.41")]

    def test_an_interface_without_a_system_name_is_left_without_one(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        def handle(seen: Seen) -> Answer:
            if seen.path == INTERFACES:
                return wrapped([{"ifid": 0, "ifname": "", "name": "Lab"}])
            records = [alert("1", "192.168.1.41")] if seen.path == HOSTS else []
            return wrapped({"records": records})

        connect(session, settings, serve(handle).url)

        collect(settings, engine, Alerts())

        assert kept(session) == [(None, "192.168.1.41")]

    def test_what_is_not_alerts_on_any_interface_fails_the_run(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started = serve(
            two_interfaces({(FLOWS, "1"): {"records": ["nonsense"]}, (HOSTS, "0"): {"records": []}})
        )
        connect(session, settings, started.url, interface_id="0,1")

        collect(settings, engine, Alerts())

        assert health(session).last_error == (
            "It answered, but the alerts aren't in a form AresGate reads."
        )


def series(session: Session) -> list[tuple[str, str, float]]:
    session.expire_all()
    rows = session.execute(
        select(MetricSeries.name, MetricSeries.labels["interface"].astext, MetricSample.value)
        .join(MetricSeries, MetricSeries.id == MetricSample.series_id)
        .where(MetricSeries.name == "interface.bytes_in")
    )
    return sorted((name, port, value) for name, port, value in rows)


class TestInterfaceTraffic:
    def test_each_interface_is_kept_under_its_own_name(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        other = BUSY | {"ifname": "eth1", "bytes_download": 70}
        started = serve(two_interfaces({(DATA, "0"): BUSY, (DATA, "1"): other}))
        connect(session, settings, started.url, interface_id="0,1")

        collect(settings, engine, InterfaceTraffic())

        assert series(session) == [
            ("interface.bytes_in", "eth0", 9.0),
            ("interface.bytes_in", "eth1", 70.0),
        ]
        assert health(session).last_items == 8

    def test_a_quiet_interface_is_left_out_while_another_has_something_to_read(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started = serve(two_interfaces({(DATA, "0"): BUSY, (DATA, "1"): QUIET}))
        connect(session, settings, started.url, interface_id="0,1")

        collect(settings, engine, InterfaceTraffic())

        assert health(session).last_error is None
        assert series(session) == [("interface.bytes_in", "eth0", 9.0)]

    def test_when_every_interface_is_quiet_that_is_said(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        quiet = QUIET | {"ifname": "eth0"}
        started = serve(two_interfaces({(DATA, "0"): quiet, (DATA, "1"): QUIET}))
        connect(session, settings, started.url, interface_id="0,1")

        collect(settings, engine, InterfaceTraffic())

        assert health(session).last_error == (
            "ntopng's interfaces eth0, eth1 haven't seen any traffic yet, so there is nothing "
            "to read from them. If they aren't the interfaces you mean, choose others under "
            "Interfaces in the connection's settings."
        )
        assert series(session) == []

    def test_an_interface_that_gives_nothing_it_reads_fails_the_run(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started = serve(two_interfaces({(DATA, "0"): "junk"}))
        connect(session, settings, started.url, interface_id="0,1")

        collect(settings, engine, InterfaceTraffic())

        assert health(session).last_error == probes.unexpected("ntopng").message


class TestHosts:
    def test_the_hosts_of_every_chosen_interface_are_read_and_the_devices_among_them_kept(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        def host(address: str, mac: str) -> dict[str, Any]:
            return {"ip": address, "mac": mac, "is_broadcast_domain": True, "name": address}

        started = serve(
            two_interfaces(
                {
                    (HOST_LIST, "0"): {"data": [host("192.168.1.41", "AA:BB:CC:00:00:01")]},
                    (HOST_LIST, "1"): {"data": [host("192.168.20.5", "AA:BB:CC:00:00:02")]},
                }
            )
        )
        connect(session, settings, started.url, interface_id="0,1")

        collect(settings, engine, Hosts())

        assert health(session).last_items == 2
        assert len(session.scalars(select(Device)).all()) == 2
        asked = [asked_about(item) for item in started.seen if item.path == HOST_LIST]
        assert asked == ["0", "1"]

    def test_hosts_that_are_not_in_a_form_it_reads_on_any_interface_fail_the_run(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started = serve(
            two_interfaces({(HOST_LIST, "0"): {"data": []}, (HOST_LIST, "1"): {"data": [3]}})
        )
        connect(session, settings, started.url, interface_id="0,1")

        collect(settings, engine, Hosts())

        assert health(session).last_error == (
            "It answered, but the hosts aren't in a form AresGate reads."
        )

    def test_an_answer_without_a_list_of_hosts_fails(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(two_interfaces({(HOST_LIST, "0"): "none"})).url)

        collect(settings, engine, Hosts())

        assert health(session).last_error == probes.unexpected("ntopng").message


def test_a_connection_saved_before_several_could_be_chosen_reads_its_one_interface() -> None:
    assert api.registry.chosen_numbers(0) == [0]
    assert api.registry.chosen_numbers(3) == [3]
