import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.collectors import registry as collectors
from app.collectors.crowdsec.decisions import Decisions
from app.collectors.crowdsec.decisions import parse as parse_standalone
from app.collectors.opnsense.crowdsec import (
    LIMIT,
    PluginAlerts,
    PluginDecisions,
    parse_alerts,
    parse_decisions,
)
from app.config import Settings
from app.events.event import Severity
from app.integrations import netguard, registry, service
from app.integrations.service import Submission
from app.models import CollectorHealth, Event, utcnow
from e2e.stand_ins import (
    crowdsec,
    opnsense,
    sample_crowdsec_decisions,
    sample_crowdsec_plugin_alerts,
    sample_crowdsec_plugin_decisions,
)
from tests.opnsense import KEY, SECRET, answering, collect, connect, health
from tests.stubs import Handler, Serve, StubServer, make_certificate
from tests.test_crowdsec_decisions import active, decision
from tests.test_opnsense_suricata_alerts import rows_of

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def banned(**changes: Any) -> dict[str, Any]:
    """A decision as the plugin's table gives it: the same decision CrowdSec's local API
    reports, with the address and its scope in one member and where the address is beside it."""
    row: dict[str, Any] = {
        "id": "101",
        "source": "crowdsec",
        "scope_value": "Ip:198.51.100.7",
        "reason": "crowdsecurity/ssh-bf",
        "action": "ban",
        "country": "DE",
        "as": "Example Hosting GmbH",
        "events_count": 6,
        "expiration": "3h59m12s",
        "alert_id": "11",
    }
    row.update(changes)
    return row


def alert(**changes: Any) -> dict[str, Any]:
    """An alert as the plugin's table gives it."""
    row: dict[str, Any] = {
        "id": "11",
        "value": "Ip:198.51.100.7",
        "reason": "crowdsecurity/ssh-bf",
        "country": "DE",
        "as": "Example Hosting GmbH",
        "decisions": "ban:1",
        "created": "2026-10-26T11:57:02Z",
    }
    row.update(changes)
    return row


class TestReadingDecisions:
    def test_a_ban_becomes_an_event_dated_by_the_run_that_saw_it(self) -> None:
        [event] = parse_decisions([banned()], NOW)

        assert (event.source, event.connection, event.kind) == ("crowdsec", "opnsense", "decision")
        assert event.occurred_at == NOW
        assert event.severity == Severity.MEDIUM
        assert event.signature == "crowdsecurity/ssh-bf"
        assert event.src_address == "198.51.100.7"
        assert event.summary == "Ban 198.51.100.7 for 3h59m12s: crowdsecurity/ssh-bf"

    def test_where_the_address_is_is_kept_with_the_ban(self) -> None:
        [event] = parse_decisions([banned()], NOW)

        assert event.raw == {
            "id": "101",
            "origin": "crowdsec",
            "type": "ban",
            "scope": "Ip",
            "value": "198.51.100.7",
            "scenario": "crowdsecurity/ssh-bf",
            "duration": "3h59m12s",
            "country": "DE",
            "as_name": "Example Hosting GmbH",
            "alert_id": "11",
            "events_count": 6,
        }

    def test_where_it_is_is_left_out_when_the_plugin_doesnt_know(self) -> None:
        [event] = parse_decisions([banned(country="", **{"as": ""})], NOW)

        assert event.raw is not None
        assert "country" not in event.raw
        assert "as_name" not in event.raw

    def test_an_ipv6_address_keeps_its_colons(self) -> None:
        [event] = parse_decisions([banned(scope_value="Ip:2001:db8::7")], NOW)

        assert event.src_address == "2001:db8::7"
        assert event.summary.startswith("Ban 2001:db8::7 for ")

    def test_a_ban_of_a_range_has_no_address_to_the_event_but_says_it_in_the_summary(self) -> None:
        [event] = parse_decisions([banned(scope_value="Range:203.0.113.0/24", source="cscli")], NOW)

        assert event.src_address is None
        assert event.summary.startswith("Ban 203.0.113.0/24 for ")

    def test_a_remedy_that_is_not_a_ban_is_the_lesser_worry(self) -> None:
        [event] = parse_decisions([banned(action="captcha")], NOW)

        assert event.severity == Severity.LOW
        assert event.summary.startswith("Captcha 198.51.100.7")

    def test_a_decision_with_little_on_it_still_says_what_it_can(self) -> None:
        [event] = parse_decisions(
            [{"id": 7, "source": "cscli", "scope_value": "Ip:198.51.100.7"}], NOW
        )

        assert (event.kind, event.severity) == ("decision", Severity.MEDIUM)
        assert event.signature is None
        assert event.summary.startswith("Ban 198.51.100.7")

    @pytest.mark.parametrize("origin", ["crowdsec", "cscli", "cscli-import", "console"])
    def test_the_origins_about_this_network_are_kept(self, origin: str) -> None:
        assert len(parse_decisions([banned(source=origin)], NOW)) == 1

    @pytest.mark.parametrize("origin", ["CAPI", "lists:firehol_botscout", "remediation_sync", ""])
    def test_the_community_blocklist_and_what_isnt_known_to_be_about_this_network_are_left_out(
        self, origin: str
    ) -> None:
        assert parse_decisions([banned(source=origin)], NOW) == []

    def test_a_ban_that_has_run_out_is_left_out(self) -> None:
        assert parse_decisions([banned(expiration="-5m2s")], NOW) == []

    @pytest.mark.parametrize(
        "row",
        [
            "not an object",
            None,
            ["list"],
            {},
            banned(id=""),
            banned(id=None),
            banned(scope_value=""),
            banned(scope_value="Ip"),
            banned(scope_value="Ip:"),
        ],
    )
    def test_a_row_that_cant_be_read_is_left_out_and_the_rest_are_kept(self, row: object) -> None:
        events = parse_decisions([row, banned(id="2")], NOW)

        assert [event.raw["id"] for event in events if event.raw] == ["2"]

    def test_nothing_is_nothing(self) -> None:
        assert parse_decisions([], NOW) == []


class TestOneAttackerSeenTwoWays:
    def test_a_ban_is_the_same_event_whether_the_plugin_or_the_local_api_told_of_it(self) -> None:
        [through_the_plugin] = parse_decisions([banned()], NOW)
        [through_the_api] = parse_standalone([decision()], NOW)

        assert through_the_plugin.connection != through_the_api.connection
        assert through_the_plugin.fingerprint == through_the_api.fingerprint

    def test_a_ban_of_a_range_is_too(self) -> None:
        [through_the_plugin] = parse_decisions(
            [banned(id=102, scope_value="Range:203.0.113.0/24", source="cscli")], NOW
        )
        [through_the_api] = parse_standalone(
            [decision(id=102, scope="Range", value="203.0.113.0/24", origin="cscli")], NOW
        )

        assert through_the_plugin.fingerprint == through_the_api.fingerprint

    def test_another_ban_of_the_same_address_is_another_event(self) -> None:
        [first] = parse_decisions([banned()], NOW)
        [again] = parse_decisions([banned(id="140")], NOW)
        [other] = parse_decisions([banned(reason="crowdsecurity/http-probing")], NOW)

        assert len({first.fingerprint, again.fingerprint, other.fingerprint}) == 3


class TestReadingAlerts:
    def test_an_alert_becomes_an_event_dated_by_its_own_time(self) -> None:
        [event] = parse_alerts([alert()])

        assert (event.source, event.connection, event.kind) == ("crowdsec", "opnsense", "alert")
        assert event.occurred_at == datetime(2026, 10, 26, 11, 57, 2, tzinfo=UTC)
        assert event.severity == Severity.MEDIUM
        assert event.signature == "crowdsecurity/ssh-bf"
        assert event.src_address == "198.51.100.7"
        assert event.summary == "crowdsecurity/ssh-bf from 198.51.100.7 (ban:1)"

    def test_where_the_address_is_and_what_was_decided_are_kept(self) -> None:
        [event] = parse_alerts([alert()])

        assert event.raw == {
            "id": "11",
            "scope": "Ip",
            "value": "198.51.100.7",
            "scenario": "crowdsecurity/ssh-bf",
            "decisions": "ban:1",
            "created_at": "2026-10-26T11:57:02Z",
            "country": "DE",
            "as_name": "Example Hosting GmbH",
        }

    def test_an_alert_that_led_to_nothing_is_the_lesser_worry(self) -> None:
        [event] = parse_alerts([alert(decisions="")])

        assert event.severity == Severity.LOW
        assert event.summary == "crowdsecurity/ssh-bf from 198.51.100.7"

    def test_an_alert_with_little_on_it_still_says_what_it_can(self) -> None:
        [event] = parse_alerts([alert(reason="", country="", **{"as": ""})])

        assert event.signature is None
        assert event.summary == "Alert from 198.51.100.7 (ban:1)"
        assert event.raw is not None
        assert "country" not in event.raw

    def test_an_alert_about_a_range_has_no_address_to_the_event(self) -> None:
        [event] = parse_alerts([alert(value="Range:203.0.113.0/24")])

        assert event.src_address is None
        assert "203.0.113.0/24" in event.summary

    def test_an_ipv6_address_keeps_its_colons(self) -> None:
        [event] = parse_alerts([alert(value="Ip:2001:db8::7")])

        assert event.src_address == "2001:db8::7"

    @pytest.mark.parametrize(
        ("stamp", "expected"),
        [
            ("2026-10-26T11:57:02Z", datetime(2026, 10, 26, 11, 57, 2, tzinfo=UTC)),
            ("2026-10-26T13:57:02+02:00", datetime(2026, 10, 26, 11, 57, 2, tzinfo=UTC)),
            ("2026-10-26T11:57:02.123456+00:00", datetime(2026, 10, 26, 11, 57, 2, 123456, UTC)),
        ],
    )
    def test_the_time_is_taken_in_the_zone_it_was_written_in(
        self, stamp: str, expected: datetime
    ) -> None:
        [event] = parse_alerts([alert(created=stamp)])

        assert event.occurred_at == expected

    @pytest.mark.parametrize(
        "row",
        [
            "not an object",
            None,
            ["list"],
            {},
            alert(id=""),
            alert(value=""),
            alert(value="Ip"),
            alert(created=""),
            alert(created="yesterday"),
            # Its zone isn't said, so what it means isn't known.
            alert(created="2026-10-26T11:57:02"),
        ],
    )
    def test_a_row_that_cant_be_read_is_left_out_and_the_rest_are_kept(self, row: object) -> None:
        events = parse_alerts([row, alert(id="2")])

        assert [event.raw["id"] for event in events if event.raw] == ["2"]

    def test_nothing_is_nothing(self) -> None:
        assert parse_alerts([]) == []

    def test_an_alert_is_the_same_event_each_time_it_is_read_and_not_the_ban_it_led_to(
        self,
    ) -> None:
        [first] = parse_alerts([alert()])
        [again] = parse_alerts([alert(decisions="ban:1 captcha:1")])
        [other] = parse_alerts([alert(id="12")])
        [ban] = parse_decisions([banned(id="11")], NOW)

        assert first.fingerprint == again.fingerprint
        assert len({first.fingerprint, other.fingerprint, ban.fingerprint}) == 3


class TestAsScheduledCollectors:
    def test_they_read_from_the_firewalls_api_when_the_plugin_is_installed(self) -> None:
        for collector in (PluginDecisions, PluginAlerts):
            assert collector.reads("opnsense", "api")
            assert not collector.reads("opnsense", "zenarmor")
            assert not collector.reads("crowdsec", "lapi")
            assert collector.module == "crowdsec"
            assert collector.interval == timedelta(minutes=1)
            assert collector.timeout >= collector.interval

    def test_they_are_two_of_the_collectors_and_not_the_standalone_one(self) -> None:
        assert isinstance(collectors.find("opnsense-crowdsec-decisions"), PluginDecisions)
        assert isinstance(collectors.find("opnsense-crowdsec-alerts"), PluginAlerts)
        assert not Decisions.reads("opnsense", "api")

    def test_the_plugin_is_one_of_the_services_testing_the_connection_looks_for(self) -> None:
        modules = {module.key: module for module in registry.OPNSENSE_MODULES}

        assert modules["crowdsec"].path == "/api/crowdsec/service/status"


def stored(session: Session) -> list[Event]:
    session.expire_all()
    return list(session.scalars(select(Event).order_by(Event.summary)))


def health_of(session: Session, collector: str) -> CollectorHealth:
    session.expire_all()
    return session.scalars(
        select(CollectorHealth).where(CollectorHealth.collector == collector)
    ).one()


def firewall(session: Session, settings: Settings, serve: Serve, handler: Handler) -> StubServer:
    """Connects to a firewall that answers with the handler, and returns the server."""
    certificate = make_certificate()
    server = serve(handler, certificate)
    connect(session, settings, server.url, certificate)
    return server


class TestRunningBansAgainstTheFirewall:
    def test_it_stores_the_bans_made_here_and_reading_them_again_adds_nothing(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        handler = opnsense(
            KEY, SECRET, {"crowdsec"}, crowdsec_decisions=sample_crowdsec_plugin_decisions()
        )
        firewall(session, settings, serve, handler)

        collect(settings, engine, PluginDecisions())

        # The one from the community blocklist and the one that ran out are left out.
        assert health(session).last_items == 2
        assert [item.summary for item in stored(session)] == [
            "Ban 198.51.100.7 for 3h59m12s: crowdsecurity/ssh-bf",
            "Ban 203.0.113.0/24 for 23h58m1s: manual 'ban' from 'localhost'",
        ]
        assert active(session) == [2]

        collect(settings, engine, PluginDecisions())

        assert health(session).last_items == 0
        assert len(stored(session)) == 2
        assert active(session) == [2, 2]

    def test_it_asks_for_the_most_it_keeps_with_a_post(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        server = firewall(session, settings, serve, opnsense(KEY, SECRET, {"crowdsec"}))

        collect(settings, engine, PluginDecisions())

        [asked] = [item for item in server.seen if "crowdsec" in item.path]
        assert (asked.method, asked.target) == ("POST", "/api/crowdsec/decisions/search")
        assert json.loads(asked.body) == {"rowCount": LIMIT, "current": 1}
        assert asked.headers["authorization"].startswith("Basic ")
        assert asked.headers["content-type"].startswith("application/json")
        assert (health(session).consecutive_failures, health(session).last_items) == (0, 0)
        assert active(session) == [0]

    def test_the_plugin_saying_it_has_nothing_to_show_is_none_banned(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        # What it answers when cscli printed ``null``, which it does when no one is banned.
        reply = {"message": "unable to retrieve data"}
        firewall(session, settings, serve, answering(reply))

        collect(settings, engine, PluginDecisions())

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 0)
        assert stored(session) == []
        assert active(session) == [0]

    def test_an_empty_table_is_the_same(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        firewall(session, settings, serve, answering(rows_of()))

        collect(settings, engine, PluginDecisions())

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 0)
        assert active(session) == [0]

    def test_some_unreadable_rows_among_good_ones_are_just_skipped(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        firewall(session, settings, serve, answering(rows_of(banned(), "nonsense", {"id": 3})))

        collect(settings, engine, PluginDecisions())

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 1)
        assert active(session) == [1]

    def test_rows_that_are_all_unreadable_say_so_instead_of_looking_like_a_quiet_network(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        firewall(session, settings, serve, answering(rows_of("nonsense", {"id": 3})))

        collect(settings, engine, PluginDecisions())

        record = health(session)
        assert record.consecutive_failures == 1
        assert record.last_error == "It answered, but the bans aren't in a form AresGate reads."
        assert stored(session) == []
        assert active(session) == []

    @pytest.mark.parametrize("reply", [{"hello": "world"}, {}, [], "text", {"rows": "nope"}])
    def test_an_answer_that_isnt_a_table_is_not_the_plugin(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve, reply: object
    ) -> None:
        firewall(session, settings, serve, answering(reply))

        collect(settings, engine, PluginDecisions())

        record = health(session)
        assert record.consecutive_failures == 1
        assert record.last_error == "It answered, but the answer doesn't look like OPNsense's."

    def test_a_user_who_may_not_use_the_plugin_is_told_so(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        firewall(session, settings, serve, answering({"status": 403}, status=403))

        collect(settings, engine, PluginDecisions())

        record = health(session)
        assert record.consecutive_failures == 1
        assert record.last_error is not None
        assert "isn't allowed to read this (HTTP 403)" in record.last_error

    def test_a_plugin_that_isnt_installed_is_a_404(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        firewall(session, settings, serve, opnsense(KEY, SECRET, set()))

        collect(settings, engine, PluginDecisions())

        record = health(session)
        assert record.consecutive_failures == 1
        assert record.last_error is not None
        assert "answered 404" in record.last_error

    def test_it_keeps_no_more_than_a_thousand_a_run(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        many = [
            banned(id=str(number), scope_value=f"Ip:10.0.{number // 250}.{number % 250}")
            for number in range(LIMIT + 5)
        ]
        firewall(session, settings, serve, answering(rows_of(*many)))

        collect(settings, engine, PluginDecisions())

        assert health(session).last_items == LIMIT
        assert active(session) == [float(LIMIT)]


class TestRunningAlertsAgainstTheFirewall:
    def test_it_stores_the_alerts_and_reading_them_again_adds_nothing(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        handler = opnsense(
            KEY, SECRET, {"crowdsec"}, crowdsec_alerts=sample_crowdsec_plugin_alerts()
        )
        firewall(session, settings, serve, handler)

        collect(settings, engine, PluginAlerts())

        assert health(session).last_items == 2
        events = stored(session)
        assert [(item.kind, item.severity) for item in events] == [("alert", 1), ("alert", 2)]
        assert [str(item.src_address) for item in events] == ["192.0.2.77", "198.51.100.7"]
        # Dated by when they were made, a few minutes ago, and not by this run.
        assert all(timedelta(minutes=2) < utcnow() - item.occurred_at for item in events)

        collect(settings, engine, PluginAlerts())

        assert health(session).last_items == 0
        assert len(stored(session)) == 2

    def test_it_asks_for_the_most_it_keeps_with_a_post(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        server = firewall(session, settings, serve, opnsense(KEY, SECRET, {"crowdsec"}))

        collect(settings, engine, PluginAlerts())

        [asked] = [item for item in server.seen if "crowdsec" in item.path]
        assert (asked.method, asked.target) == ("POST", "/api/crowdsec/alerts/search")
        assert json.loads(asked.body) == {"rowCount": LIMIT, "current": 1}
        assert (health(session).consecutive_failures, health(session).last_items) == (0, 0)

    def test_the_plugin_saying_it_has_nothing_to_show_is_no_alerts(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        firewall(session, settings, serve, answering({"message": "unable to retrieve data"}))

        collect(settings, engine, PluginAlerts())

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 0)
        assert stored(session) == []

    def test_rows_that_are_all_unreadable_say_so_instead_of_looking_like_a_quiet_network(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        rows = rows_of("nonsense", alert(created="yesterday"))
        firewall(session, settings, serve, answering(rows))

        collect(settings, engine, PluginAlerts())

        record = health(session)
        assert record.consecutive_failures == 1
        assert record.last_error == "It answered, but the alerts aren't in a form AresGate reads."

    def test_some_unreadable_rows_among_good_ones_are_just_skipped(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        now = utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        firewall(session, settings, serve, answering(rows_of(alert(created=now), "nonsense")))

        collect(settings, engine, PluginAlerts())

        assert (health(session).consecutive_failures, health(session).last_items) == (0, 1)


class TestAttackerSeenBothWays:
    def test_a_ban_the_local_api_and_the_plugin_both_report_is_stored_once(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        standalone = Submission(
            url=serve(crowdsec(KEY, sample_crowdsec_decisions())).url,
            tls_mode="system",
            tls_ca_pem=None,
            tls_fingerprint=None,
            options={},
            secrets={"api_key": KEY},
        )
        service.save(
            session,
            settings,
            netguard.HOME_NETWORK_AND_LOOPBACK,
            registry.INTEGRATIONS["crowdsec"],
            {"lapi": standalone},
            utcnow(),
        )
        session.commit()
        plugin = [
            banned(id="101"),
            banned(
                id="102",
                source="cscli",
                scope_value="Range:203.0.113.0/24",
                reason="manual 'ban' from 'localhost'",
                expiration="23h58m1s",
            ),
            banned(id="190", scope_value="Ip:192.0.2.190", reason="crowdsecurity/ssh-bf"),
        ]
        firewall(session, settings, serve, answering(rows_of(*plugin)))

        collect(settings, engine, Decisions())

        # The local API told of four.
        assert health_of(session, "crowdsec-decisions").last_items == 4

        collect(settings, engine, PluginDecisions())

        # Two of them are what the plugin tells of too, so it adds the one that is new.
        assert health_of(session, "opnsense-crowdsec-decisions").last_items == 1
        assert session.scalar(select(func.count()).select_from(Event)) == 5
