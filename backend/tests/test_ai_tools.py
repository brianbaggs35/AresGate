"""What the assistant may look at: each lookup finds what it says, reads only, and writes what it
finds through the redactor, so a provider that must not see an address sees a stand-in."""

from dataclasses import replace
from datetime import timedelta
from ipaddress import IPv4Address, IPv6Address, ip_address

import pytest
from sqlalchemy.orm import Session

from app.ai import tools
from app.ai.redaction import Level, Redactor
from app.ai.tools import Args
from app.config import Settings
from app.events.event import NewEvent, Severity
from app.events.store import record as record_events
from app.intel import store as intel_store
from app.intel import subjects, virustotal
from app.intel.virustotal import Report
from app.models import (
    Agent,
    AgentRun,
    CollectorHealth,
    Device,
    DeviceAddress,
    IntegrationConnection,
)
from tests.helpers import new_event
from tests.test_ai_service import NOW
from tests.test_ai_triage import ATTACKER, DEVICE, incident, kept, signals

HOUR = timedelta(hours=1)
PUBLIC = ip_address("93.184.216.34")
HOME = ip_address(DEVICE)


def save_report(session: Session, address: IPv4Address | IPv6Address, report: Report) -> None:
    """Keeps what VirusTotal reported of an address, as the address's answer."""
    intel_store.keep(
        session,
        virustotal.PROVIDER,
        subjects.of_address(address),
        virustotal.Reported(report),
        report.analysed_at,
    )


REPORT = Report(
    malicious=3,
    suspicious=1,
    harmless=60,
    undetected=20,
    reputation=-12,
    analysed_at=NOW - timedelta(days=2),
    country="NL",
    owner="Example Hosting",
    asn=64500,
)


def redactor(session: Session, level: Level = Level.LOCAL) -> Redactor:
    return Redactor(session, level, NOW)


def run(
    session: Session,
    name: str,
    args: Args | None = None,
    level: Level = Level.LOCAL,
    shown: Redactor | None = None,
) -> tools.Found:
    tool = tools.by_name(name)
    assert tool is not None
    return tool.run(session, shown or redactor(session, level), args or Args(), NOW)


class TestTheList:
    def test_every_tool_is_found_by_its_name_and_nothing_else_is(self) -> None:
        assert tools.names() == (
            "open_incidents",
            "incident",
            "alerts",
            "blocked_sources",
            "device",
            "integrations",
            "reputation",
            "new_devices",
            "noisy_alerts",
            "targeted_ports",
            "repeated_incidents",
            "agent_findings",
            "cleanup_candidates",
        )
        assert all(tools.by_name(name) is not None for name in tools.names())
        assert tools.by_name("delete_everything") is None

    def test_every_tool_says_what_it_gives(self) -> None:
        assert all(tool.description.endswith(".") for tool in tools.TOOLS)


class TestOpenIncidents:
    def test_the_most_serious_come_first_with_what_the_ai_made_of_them(
        self, session: Session
    ) -> None:
        low = incident(session, subject="198.51.100.9", severity=1, confidence=90)
        high = incident(session, severity=3, confidence=60, title="Guessing at ssh")
        kept(session, high, headline="Someone guessed passwords")
        session.commit()

        found = run(session, "open_incidents")

        assert [line.split("]")[0] for line in found.lines] == [
            f"[incident {high.id}",
            f"[incident {low.id}",
        ]
        assert "high, AresGate's confidence 60 of 100, open: Guessing at ssh" in found.lines[0]
        assert "the AI's reading: probe, Someone guessed passwords" in found.lines[0]
        assert "the AI's reading" not in found.lines[1]
        assert [(ref.kind, ref.key) for ref in found.refs] == [
            ("incident", str(high.id)),
            ("incident", str(low.id)),
        ]
        assert found.summary == "2 open incidents"

    def test_settled_incidents_and_the_ones_the_owner_quieted_are_left_out(
        self, session: Session
    ) -> None:
        incident(session, status="resolved")
        incident(session, subject="198.51.100.9", verdict="not_suspicious")
        mine = incident(session, subject="198.51.100.10", verdict="threat", status="investigating")
        session.commit()

        found = run(session, "open_incidents")

        assert [ref.key for ref in found.refs] == [str(mine.id)]
        assert found.summary == "1 open incident"

    def test_how_many_is_kept_within_the_limits(self, session: Session) -> None:
        for number in range(12):
            incident(session, subject=f"198.51.100.{number}")
        session.commit()

        assert len(run(session, "open_incidents", Args(limit=500)).lines) == tools.MAX_ITEMS
        assert len(run(session, "open_incidents", Args(limit=-3)).lines) == 1
        assert len(run(session, "open_incidents").lines) == 5

    def test_with_none_it_says_so(self, session: Session) -> None:
        found = run(session, "open_incidents")

        assert found.lines == ["There are no open incidents."]
        assert (found.refs, found.summary) == ([], "no open incidents")

    def test_a_provider_that_may_not_see_addresses_is_not_shown_them(
        self, session: Session
    ) -> None:
        incident(session)
        session.commit()

        found = run(session, "open_incidents", level=Level.STRICT)

        assert ATTACKER not in " ".join(found.lines)
        assert "EXT_" in " ".join(found.lines)


class TestIncident:
    def test_it_gives_everything_known_about_one(self, session: Session) -> None:
        found = incident(session)
        signals(session, found)
        session.commit()

        result = run(session, "incident", Args(id=found.id))

        assert result.lines[0] == f"[incident {found.id}]"
        assert any("ET SCAN 0" in line for line in result.lines)
        assert [(ref.kind, ref.key, ref.label) for ref in result.refs] == [
            ("incident", str(found.id), f"Incident {found.id}")
        ]
        assert result.summary == f"incident {found.id}"

    def test_one_that_is_not_there_is_said_not_to_be(self, session: Session) -> None:
        for args in (Args(id=4040), Args()):
            result = run(session, "incident", args)

            assert result.refs == []
            assert result.summary == "no such incident"
            assert result.lines == [f"There is no incident {args.id}."]


class TestAlerts:
    def test_they_are_the_latest_first_with_who_to_whom(
        self, session: Session, settings: Settings
    ) -> None:
        record_events(
            session,
            settings,
            [
                new_event(
                    severity=Severity.HIGH,
                    occurred_at=NOW - HOUR,
                    identity=("a",),
                    signature="ET EXPLOIT attempt",
                    src_address=ATTACKER,
                    src_port=4444,
                    dst_address=DEVICE,
                    dst_port=22,
                ),
                new_event(occurred_at=NOW - 2 * HOUR, identity=("b",), summary="Login failed"),
            ],
            NOW,
        )
        session.commit()

        found = run(session, "alerts")

        assert len(found.lines) == 2
        assert found.lines[0].endswith(f"ET EXPLOIT attempt {ATTACKER}:4444 -> {DEVICE}:22")
        assert " wazuh high: " in found.lines[0]
        assert found.lines[1].endswith("Login failed ? -> ?")
        assert found.summary == "2 alerts in 24 hours"

    def test_only_the_hours_asked_for_count(self, session: Session, settings: Settings) -> None:
        record_events(
            session, settings, [new_event(occurred_at=NOW - 3 * HOUR, identity=("a",))], NOW
        )
        session.commit()

        assert run(session, "alerts", Args(hours=2)).summary == "no alerts in 2 hours"
        assert run(session, "alerts", Args(hours=0)).summary == "no alerts in 1 hour"
        assert run(session, "alerts", Args(hours=9999)).summary == "1 alert in 168 hours"
        assert run(session, "alerts", Args(hours=4)).summary == "1 alert in 4 hours"

    def test_with_none_it_says_so(self, session: Session) -> None:
        found = run(session, "alerts")

        assert found.lines == ["There were no alerts in the last 24 hours."]

    def test_addresses_are_stand_ins_for_a_provider_that_may_not_see_them(
        self, session: Session, settings: Settings
    ) -> None:
        record_events(
            session,
            settings,
            [new_event(occurred_at=NOW - HOUR, identity=("a",), src_address=ATTACKER)],
            NOW,
        )
        session.commit()

        found = run(session, "alerts", level=Level.STRICT)

        assert ATTACKER not in found.lines[0]
        assert "EXT_" in found.lines[0]


class TestBlockedSources:
    def test_the_address_blocked_most_comes_first(
        self, session: Session, settings: Settings
    ) -> None:
        record_events(
            session,
            settings,
            [
                new_event(
                    source="opnsense",
                    kind="firewall",
                    severity=Severity.LOW,
                    src_address=address,
                    occurred_at=NOW - HOUR,
                    identity=(f"{address}-{number}",),
                )
                for address, count in ((ATTACKER, 3), ("198.51.100.9", 1))
                for number in range(count)
            ],
            NOW,
        )
        session.commit()

        found = run(session, "blocked_sources", Args(limit=1))

        assert found.lines == [f"{ATTACKER}: 3 connections blocked"]
        assert found.summary == "1 blocked address"
        assert run(session, "blocked_sources").summary == "2 blocked addresses"

    def test_with_none_it_says_so(self, session: Session) -> None:
        found = run(session, "blocked_sources", Args(hours=6))

        assert found.lines == ["The firewall blocked nothing in the last 6 hours."]
        assert found.summary == "nothing blocked in 6 hours"


class TestDevice:
    def devices(self, session: Session) -> None:
        nas = Device(
            mac="aa:bb:cc:00:00:01",
            hostname="nas",
            vendor="Synology",
            first_seen_at=NOW - 30 * HOUR,
            last_seen_at=NOW - HOUR,
        )
        printer = Device(
            mac="aa:bb:cc:00:00:02",
            hostname=None,
            vendor="Brother",
            first_seen_at=NOW - 40 * HOUR,
            last_seen_at=NOW - 2 * HOUR,
        )
        session.add_all([nas, printer])
        session.flush()
        session.add_all(
            [
                DeviceAddress(
                    device_id=nas.id,
                    address=ip_address(DEVICE),
                    first_seen_at=NOW - HOUR,
                    last_seen_at=NOW - HOUR,
                ),
                DeviceAddress(
                    device_id=printer.id,
                    address=ip_address("192.168.1.30"),
                    first_seen_at=NOW - HOUR,
                    last_seen_at=NOW - HOUR,
                ),
            ]
        )
        session.commit()

    def test_it_is_found_by_part_of_a_name_or_a_maker(self, session: Session) -> None:
        self.devices(session)

        by_name = run(session, "device", Args(name="NA"))
        by_maker = run(session, "device", Args(name="brother"))

        assert by_name.lines == [
            f"nas (aa:bb:cc:00:00:01), made by Synology; addresses: {DEVICE}; first seen "
            f"{NOW - 30 * HOUR:%Y-%m-%d %H:%M} UTC, last seen {NOW - HOUR:%Y-%m-%d %H:%M} UTC"
        ]
        assert by_name.summary == "1 device"
        assert by_maker.lines[0].startswith("unnamed (aa:bb:cc:00:00:02), made by Brother;")

    def test_it_is_found_by_an_address_or_a_hardware_address(self, session: Session) -> None:
        self.devices(session)

        assert run(session, "device", Args(name=DEVICE)).lines[0].startswith("nas ")
        assert (
            run(session, "device", Args(name="AA-BB-CC-00-00-02")).lines[0].startswith("unnamed ")
        )

    def test_a_percent_sign_is_not_a_wildcard(self, session: Session) -> None:
        self.devices(session)

        assert run(session, "device", Args(name="%")).summary == "no such device"

    def test_the_stand_in_a_provider_was_shown_means_the_device_it_stood_for(
        self, session: Session
    ) -> None:
        self.devices(session)
        shown = redactor(session, Level.BALANCED)
        stand_in = shown.address(DEVICE)

        found = run(session, "device", Args(name=stand_in), shown=shown)

        assert found.summary == "1 device"
        assert DEVICE not in found.lines[0]
        assert stand_in in found.lines[0]

    def test_no_name_or_no_match_is_said(self, session: Session) -> None:
        self.devices(session)

        assert run(session, "device").summary == "no device named"
        assert run(session, "device", Args(name="   ")).summary == "no device named"
        assert run(session, "device", Args(name="fridge")).lines == [
            "No device on the home network matches that."
        ]

    def test_a_device_with_no_address_known_says_so(self, session: Session) -> None:
        session.add(
            Device(
                mac="aa:bb:cc:00:00:09",
                hostname="lamp",
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
        )
        session.commit()

        line = run(session, "device", Args(name="lamp")).lines[0]

        assert "addresses: none known" in line
        assert "made by" not in line


class TestIntegrations:
    def test_each_is_listed_with_how_it_is_doing_and_the_collectors_that_fail(
        self, session: Session
    ) -> None:
        session.add_all(
            [
                IntegrationConnection(
                    integration="opnsense",
                    connection="api",
                    base_url="https://fw.test",
                    last_success_at=NOW - HOUR,
                ),
                IntegrationConnection(
                    integration="ntopng",
                    connection="api",
                    base_url="https://top.test",
                    last_error=f"Could not reach {ATTACKER}",
                ),
                IntegrationConnection(
                    integration="mystery", connection="api", base_url="https://x.test"
                ),
            ]
        )
        session.add_all(
            [
                CollectorHealth(
                    collector="alerts",
                    integration="ntopng",
                    connection="api",
                    interval_seconds=60,
                    consecutive_failures=4,
                    last_error="The key was refused",
                    updated_at=NOW,
                ),
                CollectorHealth(
                    collector="hosts",
                    integration="ntopng",
                    connection="api",
                    interval_seconds=60,
                    consecutive_failures=0,
                    updated_at=NOW,
                ),
                CollectorHealth(
                    collector="logs",
                    integration="opnsense",
                    connection="api",
                    interval_seconds=60,
                    consecutive_failures=1,
                    updated_at=NOW,
                ),
            ]
        )
        session.commit()

        found = run(session, "integrations", level=Level.STRICT)

        text = "\n".join(found.lines)
        assert "[integration mystery] mystery (api): last worked never" in text
        assert f"last worked {NOW - HOUR:%Y-%m-%d %H:%M} UTC" in text
        assert "failing: Could not reach EXT_" in text
        assert ATTACKER not in text
        assert "collector alerts of ntopng: failed 4 times in a row: The key was refused" in text
        assert "collector logs of opnsense: failed 1 times in a row: no reason given" in text
        assert "hosts" not in text
        assert [(ref.kind, ref.key) for ref in found.refs] == [
            ("integration", "mystery"),
            ("integration", "ntopng"),
            ("integration", "opnsense"),
        ]
        assert found.summary == "3 integrations, 2 collectors failing"

    def test_with_none_connected_it_says_so(self, session: Session) -> None:
        found = run(session, "integrations")

        assert found.lines == ["No integration is connected yet."]
        assert found.summary == "no integrations"


def test_nothing_in_the_list_writes() -> None:
    # A lookup is given the session to read with. This is the cheap guard that a tool added
    # later doesn't quietly change something: none of these functions may add, delete or commit.
    import inspect

    for tool in tools.TOOLS:
        source = inspect.getsource(tool.run)
        assert not any(
            word in source for word in (".add(", ".delete(", ".commit(", ".flush(", "insert(")
        ), tool.name


class TestReputation:
    """What VirusTotal has said of one address on the internet, read by the assistant."""

    def test_an_address_on_the_internet_is_described_by_the_engines_and_its_owner(
        self, session: Session
    ) -> None:
        save_report(session, PUBLIC, REPORT)
        session.commit()

        found = run(session, "reputation", Args(name=str(PUBLIC)))

        assert found.lines == [
            f"{PUBLIC}: 3 of 84 engines flag it as malicious, 1 as suspicious, 60 as harmless "
            "and 20 found nothing.",
            "Owner Example Hosting, country NL, community score -12, "
            f"analysed {REPORT.analysed_at:%Y-%m-%d %H:%M} UTC.",
        ]
        assert found.summary == f"VirusTotal's report on {PUBLIC}"

    def test_a_report_without_an_owner_or_country_says_so(self, session: Session) -> None:
        save_report(session, PUBLIC, replace(REPORT, owner=None, country=None))
        session.commit()

        found = run(session, "reputation", Args(name=str(PUBLIC)))

        assert "Owner unknown owner, country unknown, community score -12" in found.lines[1]

    def test_an_address_nobody_has_reported_on_says_so(self, session: Session) -> None:
        found = run(session, "reputation", Args(name=str(PUBLIC)))

        assert found.lines == [
            f"VirusTotal hasn't reported on {PUBLIC}: it hasn't been asked, or it has no report."
        ]
        assert found.summary == f"no VirusTotal report on {PUBLIC}"

    def test_an_address_on_the_home_network_is_not_looked_for(self, session: Session) -> None:
        found = run(session, "reputation", Args(name=str(HOME)))

        assert found.lines == [f"{HOME} isn't on the internet, so VirusTotal isn't asked about it."]
        assert found.summary == f"{HOME} isn't on the internet"

    @pytest.mark.parametrize("name", [None, "", "the nas", "10.0.0.999"])
    def test_something_that_is_not_an_address_is_refused(
        self, session: Session, name: str | None
    ) -> None:
        found = run(session, "reputation", Args(name=name))

        assert found.lines == ["Give the address to look up, such as 203.0.113.7."]
        assert found.summary == "no address given"

    def test_at_the_strictest_level_the_address_is_a_stand_in(self, session: Session) -> None:
        save_report(session, PUBLIC, REPORT)
        session.commit()

        found = run(session, "reputation", Args(name=str(PUBLIC)), level=Level.STRICT)

        text = "\n".join(found.lines)
        assert str(PUBLIC) not in text
        assert "EXT_" in text


class TestNewDevices:
    def seen(self, session: Session, mac: str, first: object, **changes: object) -> Device:
        fields: dict[str, object] = {
            "mac": mac,
            "hostname": None,
            "first_seen_at": first,
            "last_seen_at": NOW,
            **changes,
        }
        found = Device(**fields)
        session.add(found)
        session.flush()
        return found

    def test_devices_first_seen_within_the_hours_are_listed_newest_first(
        self, session: Session
    ) -> None:
        old = self.seen(session, "aa:bb:cc:00:00:01", NOW - 30 * HOUR, hostname="nas")
        fresh = self.seen(
            session, "aa:bb:cc:00:00:02", NOW - 2 * HOUR, hostname="camera", vendor="Acme"
        )
        bare = self.seen(session, "aa:bb:cc:00:00:03", NOW - HOUR)
        session.add(
            DeviceAddress(
                device_id=fresh.id, address=HOME, first_seen_at=NOW - HOUR, last_seen_at=NOW
            )
        )
        assert old.id
        assert bare.id
        session.commit()

        found = run(session, "new_devices")

        assert found.summary == "2 new devices"
        assert found.lines == [
            f"unnamed (aa:bb:cc:00:00:03); addresses: none known; first seen "
            f"{NOW - HOUR:%Y-%m-%d %H:%M} UTC",
            f"camera (aa:bb:cc:00:00:02), made by Acme; addresses: {HOME}; first seen "
            f"{NOW - 2 * HOUR:%Y-%m-%d %H:%M} UTC",
        ]
        assert run(session, "new_devices", Args(hours=48, limit=1)).summary == "1 new device"

    def test_with_none_it_says_so(self, session: Session) -> None:
        found = run(session, "new_devices", Args(hours=6))

        assert found.lines == ["No new device appeared in the last 6 hours."]
        assert found.summary == "no new devices in 6 hours"

    def test_a_provider_that_may_not_see_addresses_is_shown_stand_ins(
        self, session: Session
    ) -> None:
        fresh = self.seen(session, "aa:bb:cc:00:00:02", NOW - HOUR, hostname="camera")
        session.add(
            DeviceAddress(
                device_id=fresh.id, address=HOME, first_seen_at=NOW - HOUR, last_seen_at=NOW
            )
        )
        session.commit()

        [line] = run(session, "new_devices", level=Level.STRICT).lines

        assert str(HOME) not in line
        assert "camera" not in line


class TestNoisyAlerts:
    def test_the_alert_reported_most_comes_first_with_how_widely_it_spread(
        self, session: Session, settings: Settings
    ) -> None:
        record_events(
            session,
            settings,
            [
                new_event(
                    severity=Severity.HIGH,
                    occurred_at=NOW - HOUR,
                    identity=(f"a{number}",),
                    signature="ET SCAN ssh",
                    src_address=f"198.51.100.{number}",
                    dst_address=DEVICE,
                )
                for number in range(1, 4)
            ]
            + [new_event(occurred_at=NOW - HOUR, identity=("b",), signature=None)],
            NOW,
        )
        session.commit()

        found = run(session, "noisy_alerts")

        assert found.summary == "2 repeated alerts"
        assert found.lines[0] == "wazuh high: ET SCAN ssh, 3 times from 3 addresses to 1 address"
        assert found.lines[1].startswith("wazuh medium: an alert with no name, 1 time from")

    def test_with_none_it_says_so(self, session: Session) -> None:
        found = run(session, "noisy_alerts", Args(hours=3))

        assert found.lines == ["There were no alerts in the last 3 hours."]
        assert found.summary == "no alerts in 3 hours"


class TestTargetedPorts:
    def test_the_port_refused_most_comes_first_with_how_many_addresses_tried_it(
        self, session: Session, settings: Settings
    ) -> None:
        def blocked(number: int, port: int | None, protocol: str | None, who: str) -> NewEvent:
            return new_event(
                source="opnsense",
                kind="firewall",
                severity=Severity.LOW,
                src_address=who,
                dst_port=port,
                protocol=protocol,
                occurred_at=NOW - HOUR,
                identity=(f"f{number}",),
            )

        record_events(
            session,
            settings,
            [
                blocked(1, 22, "tcp", "198.51.100.1"),
                blocked(2, 22, "tcp", "198.51.100.2"),
                blocked(3, 22, "tcp", "198.51.100.2"),
                blocked(4, 3389, None, "198.51.100.3"),
                blocked(5, None, "udp", "198.51.100.4"),
            ],
            NOW,
        )
        session.commit()

        found = run(session, "targeted_ports")

        assert found.lines == [
            "port 22/tcp: 3 connections refused from 2 addresses",
            "port 3389/any: 1 connection refused from 1 address",
        ]
        assert found.summary == "2 targeted ports"

    def test_with_none_it_says_so(self, session: Session) -> None:
        found = run(session, "targeted_ports", Args(hours=2))

        assert found.lines == ["The firewall refused nothing aimed at a port in the last 2 hours."]
        assert found.summary == "no ports targeted in 2 hours"


class TestRepeatedIncidents:
    def test_open_incidents_that_say_the_same_thing_are_grouped(self, session: Session) -> None:
        first = incident(session, subject="198.51.100.1", title="Scanning ssh")
        second = incident(session, subject="198.51.100.2", title="Scanning ssh", severity=3)
        incident(session, subject="198.51.100.3", title="Something else")
        incident(session, subject="198.51.100.4", title="Scanning ssh", status="resolved")
        session.commit()

        found = run(session, "repeated_incidents")

        assert found.lines == [
            f'2 open incidents say "Scanning ssh" (up to high): '
            f"[incident {first.id}], [incident {second.id}]"
        ]
        assert [ref.key for ref in found.refs] == [str(first.id), str(second.id)]
        assert found.summary == "1 repeated incident"

    def test_with_none_it_says_so(self, session: Session) -> None:
        incident(session, title="Only one")
        session.commit()

        found = run(session, "repeated_incidents")

        assert found.lines == ["No open incidents repeat each other."]
        assert found.summary == "no repeated incidents"


class TestAgentFindings:
    def test_each_agent_is_listed_by_what_its_last_finished_run_reported(
        self, session: Session
    ) -> None:
        hunter = Agent(name="Night watch", template="threat_hunter")
        scanner = Agent(name="Scanner", template="exposure_scanner")
        session.add_all([hunter, scanner])
        session.flush()
        session.add_all(
            [
                AgentRun(
                    agent_id=hunter.id,
                    trigger="manual",
                    status="succeeded",
                    finished_at=NOW - timedelta(days=1),
                    summary="Old news.",
                    findings=[{"severity": "low", "title": "Settled"}],
                ),
                AgentRun(
                    agent_id=hunter.id,
                    trigger="manual",
                    status="succeeded",
                    finished_at=NOW - timedelta(hours=2),
                    summary="Something is going on.",
                    findings=[{"severity": "high", "title": "Brute force on the NAS"}],
                ),
                AgentRun(
                    agent_id=hunter.id,
                    trigger="manual",
                    status="failed",
                    finished_at=NOW,
                    summary="Broke.",
                ),
                AgentRun(
                    agent_id=scanner.id,
                    trigger="manual",
                    status="succeeded",
                    finished_at=NOW - timedelta(hours=1),
                    summary="",
                ),
            ]
        )
        session.commit()

        found = run(session, "agent_findings")

        assert found.lines == [
            f"Scanner, {NOW - timedelta(hours=1):%Y-%m-%d %H:%M} UTC: nothing",
            f"Night watch, {NOW - timedelta(hours=2):%Y-%m-%d %H:%M} UTC: Something is going on.",
            "- high: Brute force on the NAS",
        ]
        assert found.summary == "2 agent reports"

    def test_with_no_finished_run_it_says_so(self, session: Session) -> None:
        found = run(session, "agent_findings", Args(limit=2))

        assert found.lines == ["No agent has finished a run yet."]
        assert found.summary == "no agent findings"


class TestCleanupCandidates:
    def test_what_could_be_tidied_is_listed_with_a_key_to_name_it_by(
        self, session: Session
    ) -> None:
        first = incident(session, subject="198.51.100.1", title="Scanning ssh")
        second = incident(session, subject="198.51.100.2", title="Scanning ssh")
        session.commit()

        found = run(session, "cleanup_candidates")

        [line] = found.lines
        assert line.startswith("[candidate duplicates-")
        assert f"would dismiss [incident {second.id}]; [incident {first.id}] stays open" in line
        assert "85 of 100 sure" in line
        assert {ref.key for ref in found.refs} == {str(first.id), str(second.id)}
        assert found.summary == "1 thing to tidy"

    def test_with_nothing_to_tidy_it_says_so(self, session: Session) -> None:
        found = run(session, "cleanup_candidates", Args(limit=3))

        assert found.lines == ["There is nothing to tidy."]
        assert found.summary == "nothing to tidy"

    def test_a_stale_group_has_no_incident_that_stays(self, session: Session) -> None:
        incident(session, last_seen_at=NOW - 9 * HOUR * 24)
        session.commit()

        [line] = run(session, "cleanup_candidates").lines

        assert "stays open" not in line
        assert "would resolve" in line
