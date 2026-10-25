import asyncio
import json
from collections.abc import Callable, Mapping
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors import registry as collectors
from app.collectors.base import Collector
from app.collectors.opnsense.cpu_usage import CpuUsage, busy_percent
from app.collectors.opnsense.gateway_status import GatewayStatus
from app.collectors.opnsense.interface_traffic import InterfaceTraffic, interfaces
from app.collectors.opnsense.readings import leading_number, number
from app.collectors.opnsense.system_health import SystemHealth, uptime_seconds
from app.collectors.scheduler import Scheduler
from app.config import Settings
from app.integrations import netguard, registry, service
from app.integrations.apilog import ApiLogRecorder
from app.integrations.service import Submission
from app.models import CollectorHealth, MetricSample, MetricSeries, utcnow
from e2e import stand_ins
from e2e.stand_ins import opnsense
from tests.stubs import Answer, Certificate, Seen, Serve, make_certificate

KEY, SECRET = "firewall-key", "firewall-secret"
TIME = "/api/diagnostics/system/system_time"
RESOURCES = "/api/diagnostics/system/system_resources"
DISK = "/api/diagnostics/system/system_disk"
ACTIVITY = "/api/diagnostics/activity/get_activity"
STATISTICS = "/api/diagnostics/interface/get_interface_statistics"
GATEWAYS = "/api/routes/gateway/status"


class TestReadingNumbers:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (3, 3.0),
            (0.31, 0.31),
            (-2, -2.0),
            ("42", 42.0),
            (" 0.30 ", 0.3),
            ("-1.5", -1.5),
            (True, None),
            (None, None),
            ("N/A", None),
            ("~", None),
            ("", None),
            ("1e3", None),
            ("1_000", None),
            ("nan", None),
            ("inf", None),
            (float("nan"), None),
            (float("inf"), None),
            (10**400, None),
            ([1], None),
            ({"a": 1}, None),
        ],
    )
    def test_a_number_is_one_that_opnsense_gave_as_a_number_or_as_digits(
        self, value: object, expected: float | None
    ) -> None:
        assert number(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("1.2 ms", 1.2),
            ("0.0 %", 0.0),
            ("12 ms", 12.0),
            ("3%", 3.0),
            ("0.6ms", 0.6),
            (" 4.2 ms ", 4.2),
            ("~", None),
            ("ms", None),
            ("", None),
            ("1.2.3 ms", None),
            ("12abc3", None),
            (7, 7.0),
            (None, None),
            (True, None),
        ],
    )
    def test_a_reading_starts_with_its_number(self, value: object, expected: float | None) -> None:
        assert leading_number(value) == expected


class TestUptime:
    @pytest.mark.parametrize(
        ("shown", "seconds"),
        [
            ("1 day, 02:03:04", 86400 + 2 * 3600 + 3 * 60 + 4),
            ("12 days, 10:00:00", 12 * 86400 + 10 * 3600),
            ("00:42:10", 42 * 60 + 10),
            ("9:05:01", 9 * 3600 + 5 * 60 + 1),
            # The word for days is whatever language the firewall is set to.
            ("3 jours, 01:00:00", 3 * 86400 + 3600),
            ("2 Tage, 00:00:30", 2 * 86400 + 30),
            (" 00:00:05 ", 5),
        ],
    )
    def test_it_is_read_from_the_text_the_dashboard_shows(self, shown: str, seconds: int) -> None:
        assert uptime_seconds(shown) == seconds

    @pytest.mark.parametrize("shown", ["", "N/A", "1 day", "02:03", "x:y:z", None, 5, ["00:00:01"]])
    def test_what_is_not_a_time_is_not_an_uptime(self, shown: object) -> None:
        assert uptime_seconds(shown) is None


class TestProcessorUse:
    @pytest.mark.parametrize(
        ("idle", "busy"), [("96.0", 4.0), ("100", 0.0), ("0.0", 100.0), ("97.93", 2.07)]
    )
    def test_it_is_what_is_not_idle(self, idle: str, busy: float) -> None:
        line = f"CPU:  2.1% user,  0.0% nice,  1.4% system,  0.5% interrupt, {idle}% idle"

        assert busy_percent({"headers": ["last pid: 1", line]}) == busy

    @pytest.mark.parametrize(
        "answer",
        [
            None,
            [],
            {},
            {"headers": "CPU: 1% idle"},
            {"headers": []},
            {"headers": ["Mem: 1M Active", 7, None]},
            {"headers": ["CPU: busy"]},
            {"headers": ["CPU:  0.0% user, 140.0% idle"]},
            {"headers": ["Hello CPU: 3.0% idle"]},
        ],
    )
    def test_without_the_line_that_says_where_the_time_went_there_is_nothing(
        self, answer: object
    ) -> None:
        assert busy_percent(answer) is None


class TestInterfaces:
    def test_an_interface_is_taken_from_the_row_that_counts_all_it_carried(self) -> None:
        address = {"name": "igb0", "network": "203.0.113.0/24", "received-bytes": 1}
        link = {"name": "igb0", "network": "<Link#1>", "received-bytes": 2}

        assert interfaces({"a": address, "b": link}) == {"igb0": link}
        assert interfaces({"a": link, "b": address}) == {"igb0": link}

    def test_an_interface_with_only_addresses_is_taken_from_the_first(self) -> None:
        first = {"name": "igb0", "network": "203.0.113.0/24"}
        second = {"name": "igb0", "network": "198.51.100.0/24"}

        assert interfaces({"a": first, "b": second}) == {"igb0": first}

    def test_two_link_rows_are_not_a_reason_to_change_the_choice(self) -> None:
        first = {"name": "igb0", "network": "<Link#1>"}
        second = {"name": "igb0", "network": "<Link#2>"}

        assert interfaces({"a": first, "b": second}) == {"igb0": first}

    @pytest.mark.parametrize("name", ["lo0", "pflog0", "pfsync0", "enc0", "lo", "enc"])
    def test_the_interfaces_the_firewall_keeps_for_itself_are_left_out(self, name: str) -> None:
        assert interfaces({"a": {"name": name, "network": "<Link#1>"}}) == {}

    @pytest.mark.parametrize("name", ["igc0", "vlan0.10", "lagg0", "ix1", "wg0", "ovpns1", "log0"])
    def test_the_ones_that_carry_traffic_are_kept(self, name: str) -> None:
        node = {"name": name, "network": "<Link#1>"}

        assert interfaces({"a": node}) == {name: node}

    def test_a_member_that_is_not_an_interface_is_skipped(self) -> None:
        good = {"name": "igb0", "network": "<Link#1>"}

        assert interfaces({"a": "text", "b": None, "c": [1], "d": {"network": "x"}, "e": good}) == {
            "igb0": good
        }


def routed(replies: Mapping[str, object]) -> Callable[[Seen], Answer]:
    """A firewall that answers the paths given and says 404 to the others."""

    def handle(seen: Seen) -> Answer:
        if seen.path in replies:
            return Answer(status=200, body=json.dumps(replies[seen.path]))
        return Answer(status=404, body=json.dumps({"status": 404}))

    return handle


def answering(reply: object, *, status: int = 200) -> Callable[[Seen], Answer]:
    return lambda seen: Answer(status=status, body=json.dumps(reply))


def connect(
    session: Session, settings: Settings, server_url: str, certificate: Certificate
) -> None:
    submission = Submission(
        url=server_url,
        tls_mode="pinned",
        tls_ca_pem=None,
        tls_fingerprint=certificate.fingerprint,
        options={},
        secrets={"api_key": KEY, "api_secret": SECRET},
    )
    service.save(
        session,
        settings,
        netguard.HOME_NETWORK_AND_LOOPBACK,
        registry.INTEGRATIONS["opnsense"],
        {"api": submission},
        utcnow(),
    )
    session.commit()


def collect(settings: Settings, engine: Engine, collector: Collector) -> None:
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    scheduler = Scheduler(
        settings,
        maker,
        ApiLogRecorder(maker),
        netguard.HOME_NETWORK_AND_LOOPBACK,
        collectors=(collector,),
    )
    asyncio.run(scheduler.run_once())


def health(session: Session) -> CollectorHealth:
    session.expire_all()
    return session.scalars(select(CollectorHealth)).one()


def measured(session: Session) -> dict[str, float]:
    """What was stored, as ``name{label=value}`` and its value."""
    session.expire_all()
    rows = session.execute(
        select(MetricSeries.name, MetricSeries.labels, MetricSample.value)
        .join(MetricSample, MetricSample.series_id == MetricSeries.id)
        .order_by(MetricSeries.name)
    )
    return {
        name + "".join(f"{{{label}={text}}}" for label, text in labels.items()): value
        for name, labels, value in rows
    }


def run(
    session: Session,
    settings: Settings,
    engine: Engine,
    serve: Serve,
    collector: Collector,
    handler: Callable[[Seen], Answer],
) -> None:
    certificate = make_certificate()
    connect(session, settings, serve(handler, certificate).url, certificate)
    collect(settings, engine, collector)


def times(**changes: Any) -> dict[str, Any]:
    return {**stand_ins.sample_system_time(), **changes}


class TestAsScheduledCollectors:
    @pytest.mark.parametrize("collector", [SystemHealth, CpuUsage, InterfaceTraffic, GatewayStatus])
    def test_each_reads_the_firewalls_api_unless_the_firewall_module_is_off(
        self, collector: type[Collector]
    ) -> None:
        assert collector.reads("opnsense", "api")
        assert not collector.reads("opnsense", "zenarmor")
        assert not collector.reads("ntopng", "api")
        assert collector.module == "firewall"
        assert collector.timeout >= collector.interval

    @pytest.mark.parametrize(
        "collector", [SystemHealth(), CpuUsage(), InterfaceTraffic(), GatewayStatus()]
    )
    def test_each_is_one_of_the_collectors_with_a_name_of_its_own(
        self, collector: Collector
    ) -> None:
        assert collectors.find(collector.key) is not None
        assert [item.key for item in collectors.COLLECTORS].count(collector.key) == 1


class TestSystemHealth:
    def test_it_stores_the_load_uptime_memory_and_disk(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, SystemHealth(), opnsense(KEY, SECRET, set()))

        assert measured(session) == {
            "system.uptime_seconds": 93784.0,
            "system.load_1m": 0.31,
            "system.load_5m": 0.3,
            "system.load_15m": 0.27,
            "system.memory_total_bytes": 8589934592.0,
            "system.memory_used_bytes": 805306368.0,
            "disk.used_percent{mount=/}": 15.0,
            "disk.used_bytes{mount=/}": 18_000_000_000.0,
            "disk.total_bytes{mount=/}": 120_000_000_000.0,
        }
        assert (health(session).consecutive_failures, health(session).last_items) == (0, 9)

    def test_the_samples_are_the_firewalls_and_as_of_the_run(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        before = utcnow()
        run(session, settings, engine, serve, SystemHealth(), opnsense(KEY, SECRET, set()))

        session.expire_all()
        samples = session.scalars(select(MetricSample)).all()
        assert {item.source for item in samples} == {"opnsense"}
        assert len({item.sampled_at for item in samples}) == 1
        assert before <= samples[0].sampled_at <= utcnow()
        connection = session.scalars(select(MetricSeries.connection).distinct()).all()
        assert connection == ["api"]

    def test_what_the_firewall_cant_tell_is_left_out(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        handler = routed(
            {
                TIME: times(loadavg="N/A", uptime="soon"),
                RESOURCES: {"memory": {"total": 4294967296, "used": "N/A"}},
                DISK: {"devices": []},
            }
        )
        run(session, settings, engine, serve, SystemHealth(), handler)

        assert measured(session) == {"system.memory_total_bytes": 4294967296.0}

    def test_an_older_firewall_gives_the_percentage_of_a_disk_but_not_its_bytes(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        disks = {
            "devices": [
                {"type": "ufs", "blocks": "230G", "used_pct": 1, "mountpoint": "/"},
                {"type": "zfs", "used_pct": "42", "mountpoint": "/var"},
                {"type": "devfs", "used_pct": 0, "mountpoint": "/dev"},
                {"type": "tmpfs", "used_pct": 3, "mountpoint": "/var/run"},
                {"type": "msdosfs", "used_pct": 9, "mountpoint": "/boot/efi"},
                {"type": "ufs", "used_pct": 7},
                {"used_pct": 8, "mountpoint": "/untyped"},
                "text",
            ]
        }
        handler = routed({TIME: times(), RESOURCES: {}, DISK: disks})
        run(session, settings, engine, serve, SystemHealth(), handler)

        found = measured(session)
        assert {key: value for key, value in found.items() if key.startswith("disk.")} == {
            "disk.used_percent{mount=/}": 1.0,
            "disk.used_percent{mount=/var}": 42.0,
        }

    def test_the_load_needs_all_three_averages(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        handler = routed({TIME: times(loadavg="0.5, 0.4"), RESOURCES: {}, DISK: {}})
        run(session, settings, engine, serve, SystemHealth(), handler)

        assert measured(session) == {"system.uptime_seconds": 93784.0}

    @pytest.mark.parametrize("reply", [[], "text", None, {}, {"memory": "lots"}, 7])
    def test_answers_with_nothing_it_reads_say_so_instead_of_looking_like_a_quiet_firewall(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve, reply: object
    ) -> None:
        run(session, settings, engine, serve, SystemHealth(), answering(reply))

        assert "doesn't look like OPNsense's" in (health(session).last_error or "")
        assert measured(session) == {}

    def test_a_user_who_may_not_see_the_dashboard_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, SystemHealth(), answering({}, status=403))

        assert "didn't accept the credentials" in (health(session).last_error or "")


class TestCpuUsageRun:
    def test_it_stores_how_busy_the_processors_are(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, CpuUsage(), opnsense(KEY, SECRET, set()))

        assert measured(session) == {"cpu.usage_percent": 4.0}
        assert (health(session).consecutive_failures, health(session).last_items) == (0, 1)

    def test_reading_again_adds_a_reading_of_the_moment(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, CpuUsage(), opnsense(KEY, SECRET, set()))
        collect(settings, engine, CpuUsage())

        session.expire_all()
        assert len(session.scalars(select(MetricSample)).all()) == 2
        assert len(session.scalars(select(MetricSeries)).all()) == 1

    def test_an_answer_without_the_line_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, CpuUsage(), answering({"headers": ["Mem: 1M"]}))

        assert "doesn't look like OPNsense's" in (health(session).last_error or "")

    def test_a_user_who_may_not_see_the_activity_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, CpuUsage(), answering({}, status=403))

        assert "didn't accept the credentials" in (health(session).last_error or "")


class TestInterfaceTrafficRun:
    def test_it_stores_the_counters_of_each_interface_but_not_the_loopback(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, InterfaceTraffic(), opnsense(KEY, SECRET, set()))

        found = measured(session)
        assert len(found) == 14
        assert found["interface.bytes_in{interface=igb0}"] == 900_000_000
        assert found["interface.bytes_out{interface=igb0}"] == 120_000_000
        assert found["interface.packets_in{interface=igb0}"] == 1_200_000
        assert found["interface.packets_out{interface=igb0}"] == 800_000
        assert found["interface.errors_out{interface=igb0}"] == 1
        assert found["interface.drops_in{interface=igb0}"] == 3
        assert found["interface.bytes_out{interface=igb1}"] == 880_000_000
        assert not any("lo0" in key for key in found)
        assert health(session).last_items == 14

    def test_counters_given_as_text_are_numbers_too_and_missing_ones_are_skipped(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        reply = {
            "statistics": {
                "a": {
                    "name": "igc0",
                    "network": "<Link#1>",
                    "received-bytes": "1234",
                    "sent-bytes": "n/a",
                    "received-packets": None,
                }
            }
        }
        run(session, settings, engine, serve, InterfaceTraffic(), answering(reply))

        assert measured(session) == {"interface.bytes_in{interface=igc0}": 1234.0}

    def test_a_firewall_with_no_interfaces_stores_nothing_and_that_is_not_a_failure(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, InterfaceTraffic(), answering({"statistics": {}}))

        record = health(session)
        assert (record.consecutive_failures, record.last_items) == (0, 0)

    @pytest.mark.parametrize("reply", [[], {}, {"statistics": []}, {"statistics": "x"}, "text"])
    def test_an_answer_that_is_not_statistics_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve, reply: object
    ) -> None:
        run(session, settings, engine, serve, InterfaceTraffic(), answering(reply))

        assert "doesn't look like OPNsense's" in (health(session).last_error or "")

    def test_a_user_who_may_not_use_netstat_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, InterfaceTraffic(), answering({}, status=403))

        assert "didn't accept the credentials" in (health(session).last_error or "")


class TestGatewayStatusRun:
    def test_it_stores_whether_a_gateway_is_up_and_how_its_link_is_doing(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, GatewayStatus(), opnsense(KEY, SECRET, set()))

        assert measured(session) == {
            "gateway.up{gateway=WAN_DHCP}": 1.0,
            "gateway.latency_ms{gateway=WAN_DHCP}": 4.2,
            "gateway.jitter_ms{gateway=WAN_DHCP}": 0.6,
            "gateway.loss_percent{gateway=WAN_DHCP}": 0.0,
        }
        assert health(session).last_items == 4

    def test_a_gateway_that_is_down_is_down_and_one_that_is_poor_is_still_up(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        reply = {
            "items": [
                {"name": "WAN_A", "status": "down", "loss": "100.0 %", "delay": "~"},
                {"name": "WAN_B", "status": "force_down"},
                {"name": "WAN_C", "status": "delay+loss", "loss": "12.5 %", "delay": "310 ms"},
                {"name": "WAN_D", "status": "DELAY", "delay": "1 ms"},
                {"name": "WAN_E"},
            ],
            "status": "ok",
        }
        run(session, settings, engine, serve, GatewayStatus(), answering(reply))

        found = measured(session)
        ups = {key: value for key, value in found.items() if key.startswith("gateway.up")}
        assert ups == {
            "gateway.up{gateway=WAN_A}": 0.0,
            "gateway.up{gateway=WAN_B}": 0.0,
            "gateway.up{gateway=WAN_C}": 1.0,
            "gateway.up{gateway=WAN_D}": 1.0,
            "gateway.up{gateway=WAN_E}": 1.0,
        }
        assert found["gateway.loss_percent{gateway=WAN_A}"] == 100.0
        assert "gateway.latency_ms{gateway=WAN_A}" not in found
        assert found["gateway.latency_ms{gateway=WAN_C}"] == 310.0
        assert found["gateway.loss_percent{gateway=WAN_C}"] == 12.5

    def test_a_gateway_that_is_not_monitored_has_no_readings_of_its_link(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        reply = {
            "items": [
                {
                    "name": "LTE",
                    "status": "none",
                    "loss": "~",
                    "delay": "~",
                    "stddev": "~",
                    "monitor": "~",
                }
            ]
        }
        run(session, settings, engine, serve, GatewayStatus(), answering(reply))

        assert measured(session) == {"gateway.up{gateway=LTE}": 1.0}

    def test_an_item_that_is_not_a_gateway_is_skipped(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        reply = {"items": ["text", None, {"status": "none"}, {"name": "", "status": "none"}]}
        run(session, settings, engine, serve, GatewayStatus(), answering(reply))

        assert measured(session) == {}
        assert health(session).consecutive_failures == 0

    def test_a_firewall_without_gateways_is_not_a_failure(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(
            session,
            settings,
            engine,
            serve,
            GatewayStatus(),
            answering({"items": [], "status": "failed"}),
        )

        record = health(session)
        assert (record.consecutive_failures, record.last_items) == (0, 0)

    @pytest.mark.parametrize("reply", [[], {}, {"items": "none"}, {"items": {}}, "text"])
    def test_an_answer_without_a_list_of_gateways_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve, reply: object
    ) -> None:
        run(session, settings, engine, serve, GatewayStatus(), answering(reply))

        assert "doesn't look like OPNsense's" in (health(session).last_error or "")

    def test_a_user_who_may_not_see_the_gateways_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, GatewayStatus(), answering({}, status=403))

        assert "didn't accept the credentials" in (health(session).last_error or "")
