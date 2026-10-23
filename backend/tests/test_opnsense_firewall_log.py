import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors import registry as collectors
from app.collectors.base import CollectorFailed
from app.collectors.opnsense import clock
from app.collectors.opnsense.firewall_log import FirewallLog, parse
from app.collectors.scheduler import Scheduler
from app.config import Settings
from app.events.event import Severity
from app.integrations import netguard, registry, service
from app.integrations.apilog import ApiLogRecorder
from app.integrations.service import Submission
from app.models import CollectorHealth, Event, utcnow
from e2e.stand_ins import opnsense
from tests.stubs import Answer, Certificate, Seen, Serve, make_certificate

# A Friday evening in UTC, which is mid-afternoon at a firewall three hours behind.
NOW = datetime(2026, 10, 23, 18, 0, 30, tzinfo=UTC)
HALIFAX = timedelta(hours=-3)
KEY, SECRET = "firewall-key", "firewall-secret"


def entry(at: datetime = NOW, offset: timedelta = HALIFAX, **changes: Any) -> dict[str, Any]:
    """A line of OPNsense's firewall log as it answers, with the time in the newer format."""
    local = at + offset
    line: dict[str, Any] = {
        "__timestamp__": f"{local:%Y-%m-%dT%H:%M:%S}",
        "__host__": "fw01",
        "__digest__": "9e107d9d372bb6826bd81d3542a419d6",
        "__spec__": ["rulenr", "subrulenr"],
        "rulenr": "5",
        "rid": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
        "interface": "igb0",
        "reason": "match",
        "action": "block",
        "dir": "in",
        "ipversion": "4",
        "protonum": "6",
        "protoname": "tcp",
        "src": "198.51.100.7",
        "dst": "192.0.2.10",
        "srcport": "51514",
        "dstport": "443",
        "label": "Block SSH from WAN",
    }
    line.update(changes)
    return line


def old_style(at: datetime = NOW, offset: timedelta = HALIFAX, **changes: Any) -> dict[str, Any]:
    """The same line in the older log format, whose time has no year."""
    local = at + offset
    stamp = f"{local:%b} {local.day:>2} {local:%H:%M:%S}"
    return entry(at, offset, __timestamp__=stamp, **changes)


class TestTheFirewallsTime:
    def test_the_time_is_read_without_the_name_of_its_zone(self) -> None:
        assert clock.parse_system_time("Fri Oct 23 15:01:02 ADT 2026") == datetime(
            2026, 10, 23, 15, 1, 2
        )
        assert clock.parse_system_time("Sat Jan 3 5:01:02 +03 2026") == datetime(
            2026, 1, 3, 5, 1, 2
        )

    @pytest.mark.parametrize(
        "shown",
        ["", "Fri Oct 23 15:01:02 2026", "Fri Oct 23 15:01:02 ADT 2026 extra", "x Foo 1 2:3:4 Z 5"],
    )
    def test_a_form_it_doesnt_know_is_not_a_time(self, shown: str) -> None:
        assert clock.parse_system_time(shown) is None

    @pytest.mark.parametrize(
        ("hours", "minutes"), [(0, 0), (-3, 0), (2, 0), (5, 45), (-9, -30), (-12, 0), (14, 0)]
    )
    def test_the_zone_is_the_difference_to_the_nearest_quarter_hour(
        self, hours: int, minutes: int
    ) -> None:
        zone = timedelta(hours=hours, minutes=minutes)
        local = (NOW + zone + timedelta(seconds=40)).replace(tzinfo=None)

        assert clock.offset_from(local, NOW) == zone

    def test_a_clock_a_few_minutes_off_still_gives_the_zone(self) -> None:
        local = (NOW + HALIFAX - timedelta(minutes=4)).replace(tzinfo=None)

        assert clock.offset_from(local, NOW) == HALIFAX

    @pytest.mark.parametrize(
        ("skew", "message"),
        [
            (timedelta(minutes=7), "7 minutes ahead of AresGate's"),
            (timedelta(minutes=-7), "7 minutes behind AresGate's"),
        ],
    )
    def test_clocks_further_apart_than_a_zone_can_explain_are_reported(
        self, skew: timedelta, message: str
    ) -> None:
        local = (NOW + HALIFAX + skew).replace(tzinfo=None)

        with pytest.raises(CollectorFailed, match=message):
            clock.offset_from(local, NOW)


class TestReadingLines:
    def test_a_line_becomes_a_firewall_event(self) -> None:
        [event] = parse([entry(NOW - timedelta(seconds=20))], HALIFAX, NOW)

        assert (event.source, event.connection, event.kind) == ("opnsense", "api", "firewall")
        assert event.severity == Severity.LOW
        assert event.occurred_at == NOW - timedelta(seconds=20)
        assert event.signature == "Block SSH from WAN"
        assert (event.src_address, event.src_port) == ("198.51.100.7", 51514)
        assert (event.dst_address, event.dst_port) == ("192.0.2.10", 443)
        assert event.protocol == "tcp"
        assert event.summary == (
            "block in on igb0: tcp 198.51.100.7:51514 to 192.0.2.10:443 (Block SSH from WAN)"
        )

    def test_the_whole_line_is_kept_as_it_came_without_the_list_of_field_names(self) -> None:
        [event] = parse([entry()], HALIFAX, NOW)

        assert event.raw is not None
        assert "__spec__" not in event.raw
        assert event.raw["rid"] == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        assert event.raw["__host__"] == "fw01"

    def test_a_block_is_low_and_anything_else_is_info(self) -> None:
        events = parse(
            [entry(action=action, rid=action) for action in ("block", "pass", "match", "rdr")],
            HALIFAX,
            NOW,
        )

        assert [event.severity for event in events] == [
            Severity.LOW,
            Severity.INFO,
            Severity.INFO,
            Severity.INFO,
        ]

    def test_the_time_in_the_newer_format_is_the_firewalls_local_time(self) -> None:
        [event] = parse([entry(NOW - timedelta(minutes=5))], HALIFAX, NOW)

        assert event.occurred_at == datetime(2026, 10, 23, 17, 55, 30, tzinfo=UTC)

    @pytest.mark.parametrize(
        ("stamp", "expected"),
        [
            ("2026-10-23T15:00:00Z", datetime(2026, 10, 23, 15, 0, tzinfo=UTC)),
            ("2026-10-23T15:00:00-03:00", datetime(2026, 10, 23, 18, 0, tzinfo=UTC)),
            ("2026-10-23T15:00:00.123456", datetime(2026, 10, 23, 18, 0, 0, 123456, tzinfo=UTC)),
        ],
    )
    def test_a_time_that_says_its_zone_is_taken_at_its_word(
        self, stamp: str, expected: datetime
    ) -> None:
        [event] = parse([entry(__timestamp__=stamp)], HALIFAX, NOW)

        # A time without a zone is the firewall's local time, so only the last one gets shifted.
        assert event.occurred_at == expected

    def test_the_time_in_the_older_format_gets_this_years_date(self) -> None:
        [event] = parse([old_style(NOW - timedelta(minutes=5))], HALIFAX, NOW)

        assert event.occurred_at == datetime(2026, 10, 23, 17, 55, 30, tzinfo=UTC)

    def test_the_older_format_pads_a_single_digit_day_with_a_space(self) -> None:
        early = datetime(2026, 10, 3, 18, 0, 30, tzinfo=UTC)

        [event] = parse([old_style(early)], HALIFAX, early + timedelta(minutes=1))

        assert event.raw is not None
        assert event.raw["__timestamp__"] == "Oct  3 15:00:30"
        assert event.occurred_at == early

    def test_a_line_from_december_read_in_january_is_from_last_year(self) -> None:
        january = datetime(2027, 1, 2, 3, 0, tzinfo=UTC)
        december = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)

        [event] = parse([old_style(december)], HALIFAX, january)

        assert event.occurred_at == december

    def test_the_29th_of_february_is_found_in_the_leap_year_it_belongs_to(self) -> None:
        march = datetime(2028, 3, 1, 3, 0, tzinfo=UTC)
        leap_day = datetime(2028, 2, 29, 12, 0, tzinfo=UTC)

        [event] = parse([old_style(leap_day, timedelta(0))], timedelta(0), march)

        assert event.occurred_at == leap_day

    def test_the_29th_of_february_in_a_year_without_one_is_not_a_time(self) -> None:
        assert parse([entry(__timestamp__="Feb 29 12:00:00")], timedelta(0), NOW) == []

    def test_a_line_that_cant_be_read_is_left_out_and_the_rest_are_kept(self) -> None:
        lines: list[object] = [
            "not an object",
            ["list"],
            None,
            entry(__timestamp__="yesterday"),
            entry(__timestamp__=""),
            {"action": "block"},
            entry(rid="the one that can be read"),
        ]

        events = parse(lines, HALIFAX, NOW)

        assert [event.raw and event.raw["rid"] for event in events] == ["the one that can be read"]

    def test_nothing_is_nothing(self) -> None:
        assert parse([], HALIFAX, NOW) == []

    def test_the_protocol_number_stands_in_for_a_name_that_isnt_given(self) -> None:
        [event] = parse([entry(protoname="", protonum="47")], HALIFAX, NOW)

        assert event.protocol == "47"

    def test_a_line_with_no_protocol_has_none(self) -> None:
        [event] = parse([entry(protoname="", protonum="")], HALIFAX, NOW)

        assert event.protocol is None
        assert event.summary.startswith("block in on igb0: 198.51.100.7:51514 to")

    def test_ports_that_arent_numbers_are_left_out(self) -> None:
        [event] = parse([entry(srcport="abc", dstport="", protoname="icmp")], HALIFAX, NOW)

        assert (event.src_port, event.dst_port) == (None, None)
        assert event.summary == (
            "block in on igb0: icmp 198.51.100.7 to 192.0.2.10 (Block SSH from WAN)"
        )

    def test_numbers_that_arrive_as_numbers_are_read_too(self) -> None:
        [event] = parse([entry(srcport=51514, dstport=443)], HALIFAX, NOW)

        assert (event.src_port, event.dst_port) == (51514, 443)

    def test_an_ipv6_address_is_in_brackets_before_its_port(self) -> None:
        [event] = parse([entry(src="2001:db8::7", dst="2001:db8::10", ipversion="6")], HALIFAX, NOW)

        assert event.src_address == "2001:db8::7"
        assert event.summary == (
            "block in on igb0: tcp [2001:db8::7]:51514 to [2001:db8::10]:443 (Block SSH from WAN)"
        )

    def test_a_line_with_only_one_end_says_which(self) -> None:
        [only_source] = parse([entry(dst="", dstport="")], HALIFAX, NOW)
        [only_destination] = parse([entry(src="", srcport="")], HALIFAX, NOW)

        assert only_source.summary.startswith("block in on igb0: tcp 198.51.100.7:51514 (")
        assert only_destination.summary.startswith("block in on igb0: tcp to 192.0.2.10:443 (")
        assert (only_source.dst_address, only_destination.src_address) == (None, None)

    def test_a_line_with_little_on_it_still_says_what_it_can(self) -> None:
        stamp = entry()["__timestamp__"]

        [direction] = parse([{"__timestamp__": stamp, "dir": "out", "label": ""}], HALIFAX, NOW)
        [bare] = parse([{"__timestamp__": stamp}], HALIFAX, NOW)

        assert direction.summary == "logged out"
        assert direction.signature is None
        assert direction.severity == Severity.INFO
        assert bare.summary == "logged"


class TestLinesThatLookAlike:
    def test_identical_lines_are_as_many_events_as_there_are_lines(self) -> None:
        events = parse([entry(), entry(), entry()], HALIFAX, NOW)

        assert len({event.fingerprint for event in events}) == 3

    def test_lines_that_differ_in_any_of_their_facts_are_different_events(self) -> None:
        events = parse(
            [entry(), entry(srcport="1"), entry(src="203.0.113.1"), entry(action="pass")],
            HALIFAX,
            NOW,
        )

        assert len({event.fingerprint for event in events}) == 4

    def test_reading_the_log_again_a_moment_later_finds_the_same_events(self) -> None:
        first = parse([entry(), entry(), entry()], HALIFAX, NOW)
        # Two more lines of the same kind arrived in the same second.
        second = parse([entry()] * 5, HALIFAX, NOW)

        assert {event.fingerprint for event in first} < {event.fingerprint for event in second}
        assert len({event.fingerprint for event in second}) == 5

    def test_a_window_that_has_moved_on_leaves_the_older_lines_as_they_were(self) -> None:
        older = entry(NOW - timedelta(minutes=2))
        newer = entry(NOW)
        first = parse([newer, older, older], HALIFAX, NOW)
        # A newer line pushed one of the older ones out of a window of the same size.
        second = parse([entry(NOW + timedelta(minutes=1)), newer, older], HALIFAX, NOW)

        stored = {event.fingerprint for event in first}
        assert {event.fingerprint for event in second[1:]} <= stored


class TestAsAScheduledCollector:
    def test_it_reads_from_the_firewalls_api_only(self) -> None:
        assert FirewallLog.reads("opnsense", "api")
        assert not FirewallLog.reads("opnsense", "zenarmor")
        assert not FirewallLog.reads("wazuh", "indexer")
        assert FirewallLog.module == "firewall"

    def test_it_is_one_of_the_collectors(self) -> None:
        assert collectors.find("opnsense-firewall-log") is not None
        assert FirewallLog.interval == timedelta(seconds=30)
        assert FirewallLog.timeout > FirewallLog.interval


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


def collect(settings: Settings, engine: Engine) -> None:
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    scheduler = Scheduler(
        settings,
        maker,
        ApiLogRecorder(maker),
        netguard.HOME_NETWORK_AND_LOOPBACK,
        collectors=(FirewallLog(),),
    )
    asyncio.run(scheduler.run_once())


def health(session: Session) -> CollectorHealth:
    session.expire_all()
    return session.scalars(select(CollectorHealth)).one()


def stored_events(session: Session) -> list[Event]:
    session.expire_all()
    return list(session.scalars(select(Event).order_by(Event.occurred_at, Event.id)))


def firewall(
    log: object, time: str | None = None, *, zone: timedelta = HALIFAX
) -> Callable[[Seen], Answer]:
    """OPNsense answering with this firewall log and this time, which is its clock in ``zone``
    unless one is given."""

    def handle(seen: Seen) -> Answer:
        if seen.path == "/api/diagnostics/system/system_time":
            local = utcnow() + zone
            shown = time or f"{local:%a %b} {local.day} {local.hour}:{local:%M:%S} ADT {local:%Y}"
            return Answer(body=json.dumps({"datetime": shown}))
        if seen.path == "/api/diagnostics/firewall/log":
            return Answer(body=json.dumps(log))
        return Answer(status=404)

    return handle


class TestRunningAgainstTheFirewall:
    def test_it_stores_what_the_log_says_in_utc_and_reading_it_again_adds_nothing(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        now = utcnow().replace(microsecond=0)
        log = [
            entry(now - timedelta(seconds=5), srcport="1"),
            entry(now - timedelta(seconds=10), action="pass", srcport="2"),
            entry(now - timedelta(seconds=15), srcport="3"),
        ]
        certificate = make_certificate()
        handler = opnsense(KEY, SECRET, {"firewall"}, firewall_log=log, zone=HALIFAX)
        connect(session, settings, serve(handler, certificate).url, certificate)

        collect(settings, engine)

        assert health(session).last_items == 3
        stored = stored_events(session)
        assert [item.occurred_at for item in stored] == [
            now - timedelta(seconds=15),
            now - timedelta(seconds=10),
            now - timedelta(seconds=5),
        ]
        assert {(item.source, item.connection, item.kind) for item in stored} == {
            ("opnsense", "api", "firewall")
        }
        assert [item.severity for item in stored] == [1, 0, 1]

        collect(settings, engine)

        assert health(session).last_items == 0
        assert len(stored_events(session)) == 3

    def test_an_empty_log_is_a_run_that_worked(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        handler = opnsense(KEY, SECRET, {"firewall"})
        connect(session, settings, serve(handler, certificate).url, certificate)

        collect(settings, engine)

        record = health(session)
        assert (record.consecutive_failures, record.last_error, record.last_items) == (0, None, 0)

    def test_it_asks_for_the_newest_thousand_lines_with_the_key_and_secret(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        server = serve(opnsense(KEY, SECRET, {"firewall"}), certificate)
        connect(session, settings, server.url, certificate)

        collect(settings, engine)

        asked = [item for item in server.seen if item.path.endswith("firewall/log")]
        assert [item.target for item in asked] == ["/api/diagnostics/firewall/log?limit=1000"]
        assert asked[0].headers["authorization"].startswith("Basic ")

    def test_a_firewall_in_another_zone_is_read_right(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        now = utcnow().replace(microsecond=0)
        zone = timedelta(hours=5, minutes=45)
        log = [entry(now - timedelta(seconds=30), zone)]
        certificate = make_certificate()
        handler = opnsense(KEY, SECRET, {"firewall"}, firewall_log=log, zone=zone)
        connect(session, settings, serve(handler, certificate).url, certificate)

        collect(settings, engine)

        [stored] = stored_events(session)
        assert stored.occurred_at == now - timedelta(seconds=30)

    def test_a_clock_that_is_wrong_says_so_and_stores_nothing(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        # 37 minutes ahead is a zone 30 minutes ahead with a clock 7 minutes fast.
        certificate = make_certificate()
        server = serve(firewall([entry()], zone=timedelta(minutes=37)), certificate)
        connect(session, settings, server.url, certificate)

        collect(settings, engine)

        record = health(session)
        assert record.consecutive_failures == 1
        assert record.last_error is not None
        assert "7 minutes ahead of AresGate's" in record.last_error
        assert stored_events(session) == []
        assert not [item for item in server.seen if item.path.endswith("firewall/log")]

    @pytest.mark.parametrize("shown", ["sometime after lunch", 1761242462])
    def test_a_time_it_cant_read_says_so(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve, shown: object
    ) -> None:
        certificate = make_certificate()

        def handle(seen: Seen) -> Answer:
            return Answer(body=json.dumps({"datetime": shown}))

        connect(session, settings, serve(handle, certificate).url, certificate)

        collect(settings, engine)

        assert "a form AresGate doesn't read" in (health(session).last_error or "")

    def test_a_log_that_isnt_a_list_is_not_the_firewall_log(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        server = serve(firewall({"status": "ok"}), certificate)
        connect(session, settings, server.url, certificate)

        collect(settings, engine)

        assert "doesn't look like OPNsense's" in (health(session).last_error or "")

    def test_an_answer_that_isnt_json_is_not_the_firewall_either(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        server = serve(lambda seen: Answer(body="<html>Please log in</html>"), certificate)
        connect(session, settings, server.url, certificate)

        collect(settings, engine)

        assert "doesn't look like OPNsense's" in (health(session).last_error or "")

    def test_lines_that_are_all_unreadable_say_so_instead_of_looking_like_a_quiet_network(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        server = serve(firewall([entry(__timestamp__="yesterday"), "nonsense"]), certificate)
        connect(session, settings, server.url, certificate)

        collect(settings, engine)

        assert "aren't in a form AresGate reads" in (health(session).last_error or "")

    def test_some_unreadable_lines_among_good_ones_are_just_skipped(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        log = [entry(utcnow()), entry(__timestamp__="yesterday")]
        certificate = make_certificate()
        connect(session, settings, serve(firewall(log), certificate).url, certificate)

        collect(settings, engine)

        record = health(session)
        assert (record.consecutive_failures, record.last_items) == (0, 1)

    def test_a_key_the_firewall_refuses_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        certificate = make_certificate()
        server = serve(lambda seen: Answer(status=403, body="{}"), certificate)
        connect(session, settings, server.url, certificate)

        collect(settings, engine)

        assert "didn't accept the credentials" in (health(session).last_error or "")
        assert stored_events(session) == []
