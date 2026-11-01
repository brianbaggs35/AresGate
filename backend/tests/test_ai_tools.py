"""What the assistant may look at: each lookup finds what it says, reads only, and writes what it
finds through the redactor, so a provider that must not see an address sees a stand-in."""

from datetime import timedelta
from ipaddress import ip_address

from sqlalchemy.orm import Session

from app.ai import tools
from app.ai.redaction import Level, Redactor
from app.ai.tools import Args
from app.config import Settings
from app.events.event import Severity
from app.events.store import record as record_events
from app.models import (
    CollectorHealth,
    Device,
    DeviceAddress,
    IntegrationConnection,
)
from tests.helpers import new_event
from tests.test_ai_service import NOW
from tests.test_ai_triage import ATTACKER, DEVICE, incident, kept, signals

HOUR = timedelta(hours=1)


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
        assert [tools.by_name(name) is not None for name in tools.NAMES] == [True] * len(
            tools.NAMES
        )
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
