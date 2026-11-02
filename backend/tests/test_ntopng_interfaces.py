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


# An OPNsense firewall's ntopng: it numbers its interfaces from 1, with gaps, and the loopback is
# among them.
FIREWALL = [
    {"ifid": 1, "ifname": "igc0", "name": "WAN", "is_packet_interface": True},
    {"ifid": 2, "ifname": "igc1", "name": "LAN", "is_packet_interface": True},
    {"ifid": 3, "ifname": "lo0", "name": "lo0", "is_packet_interface": True},
    {"ifid": 6, "ifname": "ovpns1", "name": "ovpns1", "is_packet_interface": True},
]


def firewall(answers: dict[tuple[str, str], object]) -> Callable[[Seen], Answer]:
    """The firewall's ntopng, which answers each request by its path and ifid, and refuses an
    interface it doesn't have with a 400, as ntopng does."""

    def handle(seen: Seen) -> Answer:
        if seen.path == INTERFACES:
            return wrapped(FIREWALL)
        if asked_about(seen) not in {str(item["ifid"]) for item in FIREWALL}:
            return Answer(
                status=400, body=json.dumps({"rc": -2, "rc_str": "INVALID_INTERFACE", "rsp": {}})
            )
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


class TestNothingChosen:
    """A connection with no interface chosen reads every one ntopng lists but the loopback, which
    it asks ntopng for, since ntopng numbers its interfaces itself and not always from 0."""

    def test_the_alerts_of_every_interface_but_the_loopback_are_read(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started = serve(
            firewall(
                {
                    (HOSTS, "1"): {"records": [alert("1", "192.168.1.41")]},
                    (HOSTS, "6"): {"records": [alert("1", "10.8.0.2")]},
                }
            )
        )
        connect(session, settings, started.url, interface_id="")

        collect(settings, engine, Alerts())

        assert health(session).last_error is None
        assert kept(session) == [("igc0", "192.168.1.41"), ("ovpns1", "10.8.0.2")]
        asked = {asked_about(item) for item in started.seen if item.path != INTERFACES}
        assert asked == {"1", "2", "6"}

    def test_the_traffic_of_every_interface_but_the_loopback_is_kept(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        other = BUSY | {"ifname": "igc1", "bytes_download": 70}
        started = serve(
            firewall(
                {(DATA, "1"): BUSY | {"ifname": "igc0"}, (DATA, "2"): other, (DATA, "6"): QUIET}
            )
        )
        connect(session, settings, started.url, interface_id="")

        collect(settings, engine, InterfaceTraffic())

        assert health(session).last_error is None
        assert series(session) == [
            ("interface.bytes_in", "igc0", 9.0),
            ("interface.bytes_in", "igc1", 70.0),
        ]
        assert {asked_about(item) for item in started.seen if item.path == DATA} == {"1", "2", "6"}

    def test_the_hosts_of_every_interface_but_the_loopback_are_read(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started = serve(firewall({(HOST_LIST, number): {"data": []} for number in "126"}))
        connect(session, settings, started.url, interface_id="")

        collect(settings, engine, Hosts())

        asked = [asked_about(item) for item in started.seen if item.path == HOST_LIST]
        assert asked == ["1", "2", "6"]

    def test_a_loopback_that_is_the_only_interface_is_read(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        def handle(seen: Seen) -> Answer:
            if seen.path == INTERFACES:
                return wrapped([{"ifid": 0, "ifname": "lo"}])
            return wrapped({"data": []})

        started = serve(handle)
        connect(session, settings, started.url, interface_id="")

        collect(settings, engine, Hosts())

        assert [asked_about(item) for item in started.seen if item.path == HOST_LIST] == ["0"]

    def test_a_ntopng_that_will_not_list_its_interfaces_says_why_nothing_is_read(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(lambda seen: Answer(status=302)).url, interface_id="")

        collect(settings, engine, Hosts())

        assert health(session).last_error == probes.NTOPNG_LOGIN_REFUSED

    def test_a_ntopng_that_lists_no_interfaces_has_nothing_to_read(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(lambda seen: wrapped([])).url, interface_id="")

        collect(settings, engine, Hosts())

        assert (
            health(session).last_error == "ntopng lists no interfaces, so there is nothing to read."
        )

    def test_a_saved_0_that_ntopng_does_not_have_is_named_with_the_loopback_flagged(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(firewall({})).url, interface_id=0)

        collect(settings, engine, Hosts())

        assert health(session).last_error == (
            "ntopng has no interface 0, so it refused the request. It has: ID 1: WAN (igc0), "
            "ID 2: LAN (igc1), ID 3: lo0 (loopback), ID 6: ovpns1. Choose the interfaces to "
            "read under Interfaces in the connection's settings."
        )


def test_a_connection_saved_before_several_could_be_chosen_reads_its_one_interface() -> None:
    assert api.registry.chosen_numbers(0) == [0]
    assert api.registry.chosen_numbers(3) == [3]
