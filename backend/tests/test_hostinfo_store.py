from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.hostinfo import store
from app.hostinfo.store import NewPackage, NewPort, NewSystem
from app.models import HostPackage, HostPort, HostSystem

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def system(agent: str = "001", **changes: object) -> NewSystem:
    fields: dict[str, object] = {
        "agent_id": agent,
        "name": "web1",
        "hostname": "web1.home.arpa",
        "os_name": "Ubuntu 24.04",
        "os_version": "24.04",
        "os_platform": "ubuntu",
        "architecture": "x86_64",
        "kernel": "6.8.0",
        "macs": ("00:11:22:0a:0b:0c",),
        "addresses": (ip_address("192.168.1.20"),),
        "ports": (NewPort("tcp", ip_address("192.168.1.20"), 22, "sshd"),),
        "packages": (NewPackage("nginx", "1.24", "amd64", "deb"),),
    }
    fields.update(changes)
    return NewSystem(**fields)  # type: ignore[arg-type]


def record(
    session: Session, *systems: NewSystem, now: datetime = NOW, complete: bool = False
) -> int:
    count = store.record(
        session, systems, now, source="wazuh", connection="indexer", complete=complete
    )
    session.commit()
    session.expire_all()
    return count


def ports(session: Session) -> list[tuple[str, int, str | None]]:
    return [
        (row.transport, row.port, row.process)
        for row in session.scalars(select(HostPort).order_by(HostPort.port))
    ]


def packages(session: Session) -> list[tuple[str, str]]:
    return [
        (row.name, row.version)
        for row in session.scalars(select(HostPackage).order_by(HostPackage.name))
    ]


class TestRemembering:
    def test_a_machine_is_kept_with_its_ports_and_software(self, session: Session) -> None:
        assert record(session, system()) == 1

        found = session.scalars(select(HostSystem)).one()
        assert (found.source, found.connection, found.agent_id) == ("wazuh", "indexer", "001")
        assert (found.name, found.os_name, found.kernel) == ("web1", "Ubuntu 24.04", "6.8.0")
        assert found.macs == ["00:11:22:0a:0b:0c"]
        assert [str(address) for address in found.addresses] == ["192.168.1.20"]
        assert found.read_at == NOW
        assert ports(session) == [("tcp", 22, "sshd")]
        assert packages(session) == [("nginx", "1.24")]

    def test_reading_the_same_machine_again_changes_only_when_it_was_read(
        self, session: Session
    ) -> None:
        record(session, system())

        record(session, system(), now=NOW + timedelta(hours=1))

        assert session.scalars(select(HostSystem)).one().read_at == NOW + timedelta(hours=1)
        assert ports(session) == [("tcp", 22, "sshd")]
        assert packages(session) == [("nginx", "1.24")]

    def test_what_the_agent_says_now_replaces_what_it_said(self, session: Session) -> None:
        record(session, system())

        record(
            session,
            system(
                os_name="Ubuntu 26.04",
                macs=(),
                ports=(NewPort("udp", ip_address("::"), 5353),),
                packages=(NewPackage("nginx", "1.26"), NewPackage("curl")),
            ),
        )

        found = session.scalars(select(HostSystem)).one()
        assert (found.os_name, found.macs) == ("Ubuntu 26.04", [])
        assert ports(session) == [("udp", 5353, None)]
        assert packages(session) == [("curl", ""), ("nginx", "1.26")]

    def test_a_machine_that_now_has_no_ports_or_software_has_none_kept(
        self, session: Session
    ) -> None:
        record(session, system())

        record(session, system(ports=(), packages=()))

        assert (ports(session), packages(session)) == ([], [])

    def test_a_program_that_shares_a_port_and_a_package_listed_twice_are_kept_once(
        self, session: Session
    ) -> None:
        address = ip_address("0.0.0.0")  # noqa: S104
        record(
            session,
            system(
                ports=(NewPort("tcp", address, 80, "nginx"), NewPort("tcp", address, 80, "apache")),
                packages=(NewPackage("curl", "8"), NewPackage("curl", "8")),
            ),
        )

        assert ports(session) == [("tcp", 80, "nginx")]
        assert packages(session) == [("curl", "8")]

    def test_the_same_package_of_another_kind_is_another(self, session: Session) -> None:
        record(
            session,
            system(
                packages=(
                    NewPackage("requests", "2.32", "", "pypi"),
                    NewPackage("requests", "2.32", "", "deb"),
                )
            ),
        )

        assert len(session.scalars(select(HostPackage)).all()) == 2

    def test_two_machines_keep_their_own_ports(self, session: Session) -> None:
        other = system(
            "004", name="nas", ports=(NewPort("tcp", ip_address("::"), 445, "smbd"),), packages=()
        )

        assert record(session, system(), other) == 2

        assert ports(session) == [("tcp", 22, "sshd"), ("tcp", 445, "smbd")]

    def test_no_machines_is_none_remembered(self, session: Session) -> None:
        assert record(session) == 0
        assert session.scalars(select(HostSystem)).all() == []


class TestForgetting:
    def test_a_machine_not_listed_is_forgotten_with_its_ports_and_software_if_the_list_is_complete(
        self, session: Session
    ) -> None:
        record(session, system(), system("004", name="nas"))

        record(session, system(), complete=True)

        assert session.scalars(select(HostSystem.agent_id)).all() == ["001"]
        assert session.scalars(select(HostPort.agent_id).distinct()).all() == ["001"]
        assert session.scalars(select(HostPackage.agent_id).distinct()).all() == ["001"]

    def test_it_is_kept_when_the_list_may_not_be_the_whole_of_it(self, session: Session) -> None:
        record(session, system(), system("004", name="nas"))

        record(session, system())

        assert len(session.scalars(select(HostSystem)).all()) == 2

    def test_an_empty_complete_list_forgets_every_machine(self, session: Session) -> None:
        record(session, system())

        record(session, complete=True)

        assert session.scalars(select(HostSystem)).all() == []

    def test_what_another_connection_reported_is_not_touched(self, session: Session) -> None:
        record(session, system())
        store.record(session, [], NOW, source="wazuh", connection="other", complete=True)
        session.commit()

        assert len(session.scalars(select(HostSystem)).all()) == 1


def test_a_machine_needs_the_number_the_integration_knows_it_by() -> None:
    with pytest.raises(ValueError, match="needs the key"):
        NewSystem(agent_id="")
