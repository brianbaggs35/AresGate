"""What the assistant may ask about the machines the agents watch: the ports that listen, the
software installed and the flaws Wazuh found in it, written through the redactor like every
lookup."""

from datetime import timedelta
from ipaddress import ip_address

from sqlalchemy.orm import Session

from app.ai import tools
from app.ai.redaction import Level
from app.ai.tools import Args
from app.config import Settings
from app.events.event import NewEvent, Severity
from app.events.store import record as record_events
from app.hostinfo import store
from app.hostinfo.store import NewPackage, NewPort, NewSystem
from app.models import Device
from tests.test_ai_service import NOW
from tests.test_ai_tools import HOUR, redactor, run

WEB = "192.168.1.20"
MAC = "00:11:22:0a:0b:0c"


def machines(session: Session) -> None:
    """A web server with three ports and two packages, and a NAS with a port and a package."""
    address = ip_address(WEB)
    store.record(
        session,
        [
            NewSystem(
                "001",
                name="web1",
                hostname="web1.home.arpa",
                os_name="Ubuntu 24.04",
                architecture="x86_64",
                kernel="6.8.0",
                macs=(MAC,),
                addresses=(address,),
                ports=(
                    NewPort("tcp", address, 22, "sshd"),
                    NewPort("tcp", ip_address("::"), 443, "nginx"),
                    NewPort("udp", address, 5353),
                ),
                packages=(
                    NewPackage("openssl", "3.0.13", "amd64", "deb"),
                    NewPackage("nginx", "1.24", "amd64", "deb"),
                ),
            ),
            NewSystem(
                "004",
                name="nas",
                ports=(NewPort("tcp", ip_address("::"), 445, "smbd"),),
                packages=(NewPackage("samba", "4.17"), NewPackage("openssl", "3.0.11", "", "deb")),
            ),
        ],
        NOW,
        source="wazuh",
        connection="indexer",
        complete=True,
    )
    session.commit()


def flaw(
    session: Session,
    settings: Settings,
    cve: str,
    severity: Severity,
    summary: str,
    address: str | None = None,
) -> None:
    record_events(
        session,
        settings,
        [
            NewEvent(
                source="wazuh",
                connection="indexer",
                kind="vulnerability",
                severity=severity,
                occurred_at=NOW,
                identity=("001", cve),
                summary=summary,
                signature=cve,
                dst_address=address,
            )
        ],
        NOW,
    )
    session.commit()


class TestOpenPorts:
    def test_each_machine_says_what_it_runs_and_what_listens(self, session: Session) -> None:
        machines(session)

        found = run(session, "open_ports")

        assert found.lines == [
            "nas: tcp ::445 (smbd)",
            "web1 (Ubuntu 24.04, x86_64, 6.8.0): tcp 192.168.1.20:22 (sshd), "
            "tcp ::443 (nginx), udp 192.168.1.20:5353",
        ]
        assert found.summary == "2 machines"

    def test_one_machine_is_found_by_part_of_its_name_its_address_or_its_hardware_address(
        self, session: Session
    ) -> None:
        machines(session)

        for name in ("WEB", "web1.home", WEB, "00-11-22-0A-0B-0C"):
            assert run(session, "open_ports", Args(name=name)).summary == "1 machine"

    def test_a_percent_sign_is_not_a_wildcard(self, session: Session) -> None:
        machines(session)

        assert run(session, "open_ports", Args(name="%")).summary == "no machine with ports"

    def test_nothing_matching_is_said(self, session: Session) -> None:
        machines(session)

        found = run(session, "open_ports", Args(name="fridge"))

        assert found.summary == "no machine with ports"
        assert found.lines == [
            "No agent has reported a machine that matches, or none reports its ports."
        ]

    def test_a_machine_that_listens_on_nothing_says_so(self, session: Session) -> None:
        store.record(
            session,
            [NewSystem("007", hostname="quiet")],
            NOW,
            source="wazuh",
            connection="indexer",
            complete=False,
        )
        session.commit()

        assert run(session, "open_ports").lines == ["quiet: none listening"]

    def test_a_machine_with_no_name_is_called_by_its_agent(self, session: Session) -> None:
        store.record(
            session, [NewSystem("009")], NOW, source="wazuh", connection="indexer", complete=False
        )
        session.commit()

        assert run(session, "open_ports").lines == ["agent 009: none listening"]

    def test_a_machine_with_more_ports_than_it_lists_says_how_many_are_left(
        self, session: Session
    ) -> None:
        address = ip_address(WEB)
        many = tuple(NewPort("tcp", address, 1000 + at) for at in range(tools.MAX_PORTS + 3))
        store.record(
            session,
            [NewSystem("001", name="busy", ports=many)],
            NOW,
            source="wazuh",
            connection="indexer",
            complete=False,
        )
        session.commit()

        line = run(session, "open_ports").lines[0]

        assert line.endswith(" and 3 more")
        assert line.count("tcp") == tools.MAX_PORTS

    def test_the_limit_is_how_many_machines_are_listed(self, session: Session) -> None:
        machines(session)

        assert run(session, "open_ports", Args(limit=1)).summary == "1 machine"

    def test_a_provider_that_must_not_see_addresses_sees_stand_ins_and_can_name_one_back(
        self, session: Session
    ) -> None:
        machines(session)
        shown = redactor(session, Level.BALANCED)
        stand_in = shown.address(WEB)

        found = run(session, "open_ports", Args(name=stand_in), shown=shown)

        assert found.summary == "1 machine"
        assert WEB not in " ".join(found.lines)
        assert stand_in in " ".join(found.lines)


class TestInstalledSoftware:
    def test_each_machine_that_has_it_says_which_version(self, session: Session) -> None:
        machines(session)

        found = run(session, "installed_software", Args(name="openssl"))

        assert found.lines == [
            "openssl 3.0.11 (deb) on nas",
            "openssl 3.0.13 (deb, amd64) on web1 (Ubuntu 24.04, x86_64, 6.8.0)",
        ]
        assert found.summary == "2 installations"

    def test_part_of_a_name_is_enough_and_the_case_does_not_matter(self, session: Session) -> None:
        machines(session)

        assert run(session, "installed_software", Args(name="SSL")).summary == "2 installations"
        assert run(session, "installed_software", Args(name="samba")).summary == "1 installation"

    def test_a_package_that_says_nothing_of_its_kind_is_said_to_(self, session: Session) -> None:
        machines(session)

        assert run(session, "installed_software", Args(name="samba")).lines == [
            "samba 4.17 (no kind) on nas"
        ]

    def test_no_name_or_no_match_is_said(self, session: Session) -> None:
        machines(session)

        assert run(session, "installed_software").summary == "no software named"
        assert run(session, "installed_software", Args(name="%_")).summary == "no software named"
        found = run(session, "installed_software", Args(name="telnet"))
        assert found.lines == ["No machine an agent reports on has software named telnet."]
        assert found.summary == "no such software"

    def test_the_limit_is_how_many_installations_are_listed(self, session: Session) -> None:
        machines(session)

        assert run(session, "installed_software", Args(name="openssl", limit=1)).summary == (
            "1 installation"
        )


class TestHostVulnerabilities:
    def flaws(self, session: Session, settings: Settings) -> None:
        flaw(
            session,
            settings,
            "CVE-2024-7347",
            Severity.MEDIUM,
            "CVE-2024-7347 in nginx on web1 (Medium)",
            WEB,
        )
        flaw(
            session,
            settings,
            "CVE-2025-0001",
            Severity.CRITICAL,
            "CVE-2025-0001 in samba on nas (Critical)",
        )
        flaw(
            session,
            settings,
            "CVE-2024-13176",
            Severity.HIGH,
            "CVE-2024-13176 in openssl on web1 (High)",
            WEB,
        )

    def test_the_most_serious_come_first(self, session: Session, settings: Settings) -> None:
        self.flaws(session, settings)

        found = run(session, "host_vulnerabilities")

        assert found.lines == [
            "critical: CVE-2025-0001 in samba on nas (Critical)",
            "high: CVE-2024-13176 in openssl on web1 (High)",
            "medium: CVE-2024-7347 in nginx on web1 (Medium)",
        ]
        assert found.summary == "3 vulnerabilities"

    def test_it_is_narrowed_to_a_cve_a_machine_or_an_address(
        self, session: Session, settings: Settings
    ) -> None:
        self.flaws(session, settings)

        assert run(session, "host_vulnerabilities", Args(name="cve-2025")).summary == (
            "1 vulnerability"
        )
        assert run(session, "host_vulnerabilities", Args(name="web1")).summary == (
            "2 vulnerabilities"
        )
        assert run(session, "host_vulnerabilities", Args(name=WEB)).summary == "2 vulnerabilities"

    def test_a_percent_sign_is_not_a_wildcard_and_the_limit_is_kept(
        self, session: Session, settings: Settings
    ) -> None:
        self.flaws(session, settings)

        assert run(session, "host_vulnerabilities", Args(name="%")).summary == "no vulnerabilities"
        assert run(session, "host_vulnerabilities", Args(limit=2)).summary == "2 vulnerabilities"

    def test_none_known_is_said(self, session: Session, settings: Settings) -> None:
        found = run(session, "host_vulnerabilities")

        assert found.lines == ["No vulnerability is known that matches."]
        assert found.summary == "no vulnerabilities"

    def test_events_of_other_kinds_are_not_flaws(
        self, session: Session, settings: Settings
    ) -> None:
        record_events(
            session,
            settings,
            [
                NewEvent(
                    source="wazuh",
                    connection="indexer",
                    kind="alert",
                    severity=Severity.HIGH,
                    occurred_at=NOW - timedelta(minutes=1),
                    identity=("x",),
                    summary="sshd: authentication failed",
                )
            ],
            NOW,
        )
        session.commit()

        assert run(session, "host_vulnerabilities").summary == "no vulnerabilities"

    def test_a_provider_that_must_not_see_addresses_can_name_a_stand_in_back(
        self, session: Session, settings: Settings
    ) -> None:
        self.flaws(session, settings)
        shown = redactor(session, Level.BALANCED)

        found = run(session, "host_vulnerabilities", Args(name=shown.address(WEB)), shown=shown)

        assert found.summary == "2 vulnerabilities"


class TestADevice:
    def test_the_device_says_what_its_agent_reports_it_runs(self, session: Session) -> None:
        machines(session)
        session.add(Device(mac=MAC, hostname="web1", first_seen_at=NOW - HOUR, last_seen_at=NOW))
        session.commit()

        found = run(session, "device", Args(name="web1"))

        assert "; runs web1 (Ubuntu 24.04, x86_64, 6.8.0); addresses:" in found.lines[0]

    def test_a_device_no_agent_reports_says_nothing_of_it(self, session: Session) -> None:
        session.add(
            Device(mac="aa:bb:cc:00:00:09", hostname="plug", first_seen_at=NOW, last_seen_at=NOW)
        )
        session.commit()

        assert "runs" not in run(session, "device", Args(name="plug")).lines[0]
