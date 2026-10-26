import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collectors import registry as collectors
from app.collectors.ntopng import hosts
from app.collectors.ntopng.hosts import Hosts, measure, sightings
from app.config import Settings
from app.integrations import probes
from app.models import Device, DeviceAddress, MetricSample, MetricSeries
from e2e.stand_ins import Answer, Seen, ntopng, sample_ntopng_hosts
from tests.ntopng import TOKEN, connect
from tests.opnsense import collect, health
from tests.stubs import Serve

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def host(**changes: Any) -> dict[str, Any]:
    """A host as ntopng's active hosts answer gives it."""
    row: dict[str, Any] = {
        "ip": "192.168.1.20",
        "mac": "52:54:00:aa:bb:20",
        "name": "web1",
        "bytes": {"total": 300, "sent": 200, "recvd": 100},
        "thpt": {"pps": 3.5, "bps": 8200.0},
        "num_flows": {"total": 6, "as_client": 5, "as_server": 1},
        "score": {"total": 12, "as_client": 12, "as_server": 0},
        "is_broadcast_domain": True,
    }
    row.update(changes)
    return row


def measured(row: dict[str, Any]) -> dict[str, float]:
    return {name: value for name, value in measure(row).items() if value is not None}


class TestMeasuring:
    def test_a_host_is_measured_by_what_it_has_sent_and_received_and_its_flows_and_score(
        self,
    ) -> None:
        assert measured(host()) == {
            "host.bytes_sent": 200,
            "host.bytes_received": 100,
            "host.throughput_bps": 8200.0,
            "host.flows": 6,
            "host.score": 12,
        }

    def test_what_ntopng_leaves_out_or_gives_as_something_else_is_not_a_reading(self) -> None:
        assert measured(host(bytes=None, thpt="fast", num_flows={}, score={"total": True})) == {}


class TestDevices:
    def test_a_host_in_the_broadcast_domain_with_a_mac_address_is_a_device(self) -> None:
        [found] = sightings([host()], NOW)

        assert (found.mac, str(found.address), found.hostname, found.seen_at) == (
            "52:54:00:aa:bb:20",
            "192.168.1.20",
            "web1",
            NOW,
        )

    def test_a_host_behind_a_router_is_not_one_because_its_mac_address_is_the_routers(self) -> None:
        assert (
            sightings([host(is_broadcast_domain=False), host(is_broadcast_domain=None)], NOW) == []
        )

    def test_a_host_without_a_usable_mac_address_is_not_one(self) -> None:
        assert (
            sightings([host(mac=None), host(mac="not a mac"), host(mac="ff:ff:ff:ff:ff:ff")], NOW)
            == []
        )

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("web1", "web1"),
            ("printer [192.168.1.30]", "printer"),
            ("192.168.1.20", None),
            ("192.168.1.20@7", None),
            ("", None),
            (None, None),
        ],
    )
    def test_the_name_is_the_one_ntopng_has_and_not_the_address_it_falls_back_to(
        self, name: str | None, expected: str | None
    ) -> None:
        [found] = sightings([host(name=name)], NOW)

        assert found.hostname == expected


def test_it_reads_from_ntopng_and_is_one_of_the_collectors() -> None:
    assert Hosts.reads("ntopng", "api")
    assert not Hosts.reads("opnsense", "api")
    assert Hosts.module is None
    assert collectors.find("ntopng-hosts") is not None
    assert Hosts.interval == timedelta(minutes=1)
    assert Hosts.timeout >= Hosts.interval


def listing(rows: object) -> Callable[[Seen], Answer]:
    """A ntopng that lists these rows as its hosts, whatever they are."""

    def handle(seen: Seen) -> Answer:
        return Answer(body=json.dumps({"rc": 0, "rc_str": "OK", "rsp": {"data": rows}}))

    return handle


def series_values(session: Session) -> dict[tuple[str, str], list[float]]:
    session.expire_all()
    rows = session.execute(
        select(MetricSeries.name, MetricSeries.labels, MetricSample.value)
        .join(MetricSeries, MetricSeries.id == MetricSample.series_id)
        .order_by(MetricSample.sampled_at)
    )
    found: dict[tuple[str, str], list[float]] = {}
    for name, labels, value in rows:
        found.setdefault((name, labels["host"]), []).append(value)
    return found


class TestRunningAgainstNtopng:
    def test_it_measures_the_local_hosts_and_keeps_the_devices_among_them(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started = serve(ntopng(TOKEN, sample_ntopng_hosts(datetime.now(UTC))))
        connect(session, settings, started.url)

        collect(settings, engine, Hosts())

        assert health(session).last_items == 3
        found = series_values(session)
        assert len(found) == 15
        assert found[("host.bytes_sent", "192.168.1.20")] == [48_213_907]
        assert found[("host.bytes_received", "192.168.1.41")] == [88_340]
        assert ("host.bytes_sent", "8.241.92.250") not in found
        session.expire_all()
        assert sorted(item.hostname or "" for item in session.scalars(select(Device))) == [
            "",
            "web1",
        ]
        assert sorted(str(item.address) for item in session.scalars(select(DeviceAddress))) == [
            "192.168.1.20",
            "192.168.1.41",
        ]

        collect(settings, engine, Hosts())

        assert health(session).last_items == 3
        assert len(session.scalars(select(Device)).all()) == 2
        assert len(series_values(session)[("host.bytes_sent", "192.168.1.20")]) == 2

    def test_it_asks_for_the_local_hosts_of_the_interface_all_at_once_with_the_token(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started = serve(ntopng(TOKEN, sample_ntopng_hosts(NOW)))
        connect(session, settings, started.url, interface_id=0)

        collect(settings, engine, Hosts())

        [asked] = [item for item in started.seen if item.path.endswith("host/active.lua")]
        assert asked.method == "GET"
        assert parse_qs(urlsplit(asked.target).query) == {
            "ifid": ["0"],
            "mode": ["local"],
            "all": ["true"],
        }
        assert asked.headers["authorization"] == f"Token {TOKEN}"

    def test_it_can_sign_in_with_a_user_name_and_password_instead(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started = serve(listing([host()]))
        connect(session, settings, started.url, basic=True)

        collect(settings, engine, Hosts())

        [asked] = started.seen
        assert asked.headers["authorization"].startswith("Basic ")
        assert (health(session).consecutive_failures, health(session).last_items) == (0, 1)

    def test_no_hosts_is_a_quiet_network(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(listing([])).url)

        collect(settings, engine, Hosts())

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 0)

    def test_a_host_without_an_address_has_no_readings_but_is_still_listed(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(listing([host(ip=None), host()])).url)

        collect(settings, engine, Hosts())

        assert health(session).last_items == 2
        assert {address for _, address in series_values(session)} == {"192.168.1.20"}

    def test_it_keeps_no_more_hosts_than_the_limit(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        serve: Serve,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(hosts, "LIMIT", 2)
        rows = [
            host(ip=f"192.168.1.{number}", mac=f"52:54:00:aa:bb:{number:02x}")
            for number in range(10, 15)
        ]
        connect(session, settings, serve(listing(rows)).url)

        collect(settings, engine, Hosts())

        assert health(session).last_items == 2

    def test_a_row_that_is_not_a_host_is_left_out_and_when_none_is_it_fails(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(listing(["nonsense", host()])).url)

        collect(settings, engine, Hosts())

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 1)

        connect(session, settings, serve(listing(["nonsense", 3])).url)

        collect(settings, engine, Hosts())

        assert (
            health(session).last_error
            == "It answered, but the hosts aren't in a form AresGate reads."
        )

    @pytest.mark.parametrize("answer", [{"rc": 0, "rsp": []}, {"rc": 0, "rsp": {"data": "all"}}])
    def test_an_answer_without_a_list_of_hosts_fails(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        serve: Serve,
        answer: dict[str, Any],
    ) -> None:
        connect(session, settings, serve(lambda seen: Answer(body=json.dumps(answer))).url)

        collect(settings, engine, Hosts())

        assert health(session).last_error == probes.unexpected("ntopng").message
