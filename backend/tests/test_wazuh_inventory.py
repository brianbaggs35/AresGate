import json
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collectors import registry as collectors
from app.collectors.wazuh import indexer, inventory
from app.collectors.wazuh.inventory import Inventory, machines, sightings
from app.config import Settings
from app.models import Device, DeviceAddress, DeviceSource, HostPackage, HostPort, HostSystem
from e2e.stand_ins import sample_wazuh_states, wazuh
from tests.opnsense import collect, health
from tests.stubs import Answer, Seen, Serve, make_certificate
from tests.wazuh import PASSWORD, USER, connect

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
WEB = {"agent": {"id": "001", "name": "web1"}}


def machine(**changes: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        **WEB,
        "host": {
            "hostname": "web1.home.arpa",
            "architecture": "x86_64",
            "os": {
                "name": "Ubuntu",
                "version": "24.04",
                "platform": "ubuntu",
                "full": "Ubuntu 24.04.1 LTS",
                "kernel": {"release": "6.8.0-45-generic", "version": "#45-Ubuntu"},
            },
        },
    }
    document.update(changes)
    return document


def card(name: str = "eth0", mac: Any = "00:11:22:0a:0b:0c", state: str = "up") -> dict[str, Any]:
    return {**WEB, "host": {"mac": mac}, "interface": {"name": name, "state": state}}


def network(name: str = "eth0", address: str = "192.168.1.20") -> dict[str, Any]:
    return {**WEB, "interface": {"name": name}, "network": {"ip": address, "type": "ipv4"}}


def package(name: str = "nginx", **changes: Any) -> dict[str, Any]:
    return {
        **WEB,
        "package": {
            "name": name,
            "version": "1.24",
            "architecture": "amd64",
            "type": "deb",
            **changes,
        },
    }


def listening(port: Any = 22, address: str = "192.168.1.20", **changes: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        **WEB,
        "source": {"ip": address, "port": port},
        "network": {"transport": "TCP"},
        "process": {"name": "sshd"},
        "interface": {"state": "listening"},
    }
    document.update(changes)
    return document


class TestTheMachine:
    def test_it_has_what_the_system_document_says(self) -> None:
        [found] = machines([machine()], [], [], [], [])

        assert (found.agent_id, found.name, found.hostname) == ("001", "web1", "web1.home.arpa")
        assert (found.os_name, found.os_version, found.os_platform) == (
            "Ubuntu 24.04.1 LTS",
            "24.04",
            "ubuntu",
        )
        assert (found.architecture, found.kernel) == ("x86_64", "6.8.0-45-generic")

    def test_the_operating_system_is_its_name_and_version_when_nothing_gives_it_in_full(
        self,
    ) -> None:
        document = machine()
        del document["host"]["os"]["full"]

        [found] = machines([document], [], [], [], [])

        assert found.os_name == "Ubuntu 24.04"

    def test_it_has_no_operating_system_when_none_is_given(self) -> None:
        [found] = machines([{**WEB, "host": {}}], [], [], [], [])

        assert (found.os_name, found.os_version, found.kernel, found.hostname) == (
            None,
            None,
            None,
            None,
        )

    @pytest.mark.parametrize(
        ("kernel", "shown"),
        [
            ("6.8.0", "6.8.0"),
            ("", None),
            ({"version": "#45"}, "#45"),
            ({"name": "Linux"}, None),
            (3, None),
        ],
    )
    def test_the_kernel_is_given_as_text_or_as_an_object_with_its_release(
        self, kernel: object, shown: str | None
    ) -> None:
        document = machine()
        document["host"]["os"]["kernel"] = kernel

        [found] = machines([document], [], [], [], [])

        assert found.kernel == shown

    def test_a_machine_that_only_has_ports_is_still_known_by_its_agent(self) -> None:
        [found] = machines([], [], [], [], [listening()])

        assert (found.agent_id, found.name, found.os_name) == ("001", "web1", None)
        assert len(found.ports) == 1

    def test_the_name_is_the_first_one_any_document_gives(self) -> None:
        nameless = {"agent": {"id": "001"}, "host": {}}

        [found] = machines([nameless], [card()], [], [], [])

        assert found.name == "web1"

    def test_a_document_that_names_no_agent_is_left_out(self) -> None:
        assert machines([{"host": {}}], [], [], [package()][:0], [{"source": {}}]) == []

    def test_the_last_system_document_of_an_agent_is_the_one_that_is_kept(self) -> None:
        older, newer = machine(), machine()
        older["host"]["hostname"] = "old"

        [found] = machines([older, newer], [], [], [], [])

        assert found.hostname == "web1.home.arpa"

    def test_two_agents_are_two_machines_in_the_order_they_appear(self) -> None:
        other = {"agent": {"id": "004", "name": "nas"}}

        found = machines([machine()], [], [], [package(), {**other, "package": {"name": "x"}}], [])

        assert [item.agent_id for item in found] == ["001", "004"]
        assert [len(item.packages) for item in found] == [1, 1]


class TestTheNetworkCards:
    def test_a_card_with_a_hardware_address_and_its_addresses_are_the_machines(self) -> None:
        [found] = machines(
            [machine()],
            [card(), card("wlan0", mac="AA-BB-CC-00-11-22")],
            [network(), network(address="2001:db8::20"), network("wlan0", "192.168.1.21")],
            [],
            [],
        )

        assert found.macs == ("00:11:22:0a:0b:0c", "aa:bb:cc:00:11:22")
        assert [str(address) for address in found.addresses] == [
            "192.168.1.20",
            "2001:db8::20",
            "192.168.1.21",
        ]

    @pytest.mark.parametrize(
        "name", ["lo", "docker0", "br-3fa1", "veth12", "virbr0", "cni0", "tun0", "vboxnet0", ""]
    )
    def test_an_interface_that_is_not_the_machines_own_is_left_out(self, name: str) -> None:
        [found] = machines(
            [machine()],
            [card(name, mac="02:42:ac:11:00:01")],
            [network(name, "172.17.0.1")],
            [],
            [],
        )

        assert (found.macs, found.addresses) == ((), ())

    def test_a_card_that_is_down_is_left_out(self) -> None:
        [found] = machines([machine()], [card(state="DOWN")], [], [], [])

        assert found.macs == ()

    @pytest.mark.parametrize(
        "mac", ["00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff", "nonsense", "", 5, None]
    )
    def test_a_hardware_address_that_is_not_a_devices_is_left_out(self, mac: object) -> None:
        [found] = machines([machine()], [card(mac=mac)], [], [], [])

        assert found.macs == ()

    def test_a_card_may_have_more_than_one_hardware_address(self) -> None:
        [found] = machines(
            [machine()], [card(mac=["00:11:22:0a:0b:0c", "00:11:22:0a:0b:0d", 3])], [], [], []
        )

        assert found.macs == ("00:11:22:0a:0b:0c", "00:11:22:0a:0b:0d")

    @pytest.mark.parametrize("address", ["127.0.0.1", "::1", "fe80::1%eth0", "::", "nonsense", ""])
    def test_an_address_that_is_not_one_to_be_found_at_is_left_out(self, address: str) -> None:
        [found] = machines([machine()], [], [network(address=address)], [], [])

        assert found.addresses == ()

    def test_an_address_with_no_interface_or_agent_is_left_out(self) -> None:
        [found] = machines(
            [machine()],
            [],
            [network(name=""), {"interface": {"name": "eth0"}, "network": {"ip": "192.168.1.2"}}],
            [],
            [],
        )

        assert found.addresses == ()

    def test_an_address_listed_twice_is_one(self) -> None:
        [found] = machines([machine()], [], [network(), network()], [], [])

        assert len(found.addresses) == 1


class TestThePorts:
    def test_a_port_is_the_transport_the_local_address_and_the_program(self) -> None:
        [found] = machines([machine()], [], [], [], [listening()])

        [port] = found.ports
        assert (port.transport, str(port.address), port.port, port.process) == (
            "tcp",
            "192.168.1.20",
            22,
            "sshd",
        )

    def test_a_port_with_no_program_has_none(self) -> None:
        [found] = machines([machine()], [], [], [], [listening(process={})])

        assert found.ports[0].process is None

    @pytest.mark.parametrize(
        "document",
        [
            listening(port=0),
            listening(port=65536),
            listening(port="ssh"),
            listening(address="nonsense"),
            listening(address=""),
            {**WEB, "network": {"transport": "tcp"}},
        ],
    )
    def test_a_port_that_is_not_one_is_left_out(self, document: dict[str, Any]) -> None:
        [found] = machines([machine()], [], [], [], [document])

        assert found.ports == ()

    def test_the_ports_of_another_agent_are_not_this_ones(self) -> None:
        other = listening(agent={"id": "004", "name": "nas"})

        found = machines([machine()], [], [], [], [listening(), other])

        assert [len(item.ports) for item in found] == [1, 1]


class TestThePackages:
    def test_a_package_has_its_name_version_architecture_and_kind(self) -> None:
        [found] = machines([machine()], [], [], [package()], [])

        [item] = found.packages
        assert (item.name, item.version, item.architecture, item.kind) == (
            "nginx",
            "1.24",
            "amd64",
            "deb",
        )

    def test_what_a_package_does_not_say_is_empty(self) -> None:
        [found] = machines([machine()], [], [], [{**WEB, "package": {"name": "x"}}], [])

        assert found.packages[0].version == ""
        assert found.packages[0].kind == ""

    def test_one_with_no_name_is_left_out(self) -> None:
        [found] = machines([machine()], [], [], [package(name=""), package("curl")], [])

        assert [item.name for item in found.packages] == ["curl"]


class TestTheDevices:
    def listed(self, **changes: Any) -> dict[str, indexer.Listed]:
        return {"001": indexer.Listed("192.168.1.20", NOW)} | changes

    def test_each_address_of_a_card_is_a_sighting_of_its_device_named_for_the_machine(self) -> None:
        interfaces = [card()]
        networks = [network(), network(address="2001:db8::20")]
        found = machines([machine()], interfaces, networks, [], [])

        seen = sightings(found, interfaces, networks, self.listed(), NOW)

        assert [(item.mac, str(item.address), item.hostname, item.seen_at) for item in seen] == [
            ("00:11:22:0a:0b:0c", "192.168.1.20", "web1.home.arpa", NOW),
            ("00:11:22:0a:0b:0c", "2001:db8::20", "web1.home.arpa", NOW),
        ]

    def test_a_card_with_no_address_is_one_sighting_with_none(self) -> None:
        interfaces = [card()]
        found = machines([{**WEB, "host": {}}], interfaces, [], [], [])

        seen = sightings(found, interfaces, [], {}, NOW)

        assert [(item.address, item.hostname) for item in seen] == [(None, "web1")]

    def test_it_is_dated_by_when_the_manager_last_heard_from_the_agent(self) -> None:
        interfaces = [card()]
        heard = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)
        found = machines([machine()], interfaces, [], [], [])

        [item] = sightings(found, interfaces, [], {"001": indexer.Listed(None, heard)}, NOW)

        assert item.seen_at == heard

    def test_a_card_that_is_left_out_is_no_sighting(self) -> None:
        interfaces = [card("docker0"), card("eth1", mac="nonsense")]
        found = machines([machine()], interfaces, [], [], [])

        assert sightings(found, interfaces, [], {}, NOW) == []

    def test_a_card_has_one_sighting_for_each_of_its_hardware_addresses(self) -> None:
        interfaces = [card(mac=["00:11:22:0a:0b:0c", "00:11:22:0a:0b:0d"])]
        found = machines([machine()], interfaces, [network()], [], [])

        seen = sightings(found, interfaces, [network()], {}, NOW)

        assert [item.mac for item in seen] == ["00:11:22:0a:0b:0c", "00:11:22:0a:0b:0d"]


def server(serve: Serve, states: dict[str, list[dict[str, object]]] | None = None) -> Any:
    certificate = make_certificate()
    started = serve(
        wazuh(USER, PASSWORD, states=sample_wazuh_states() if states is None else states),
        certificate,
    )
    return started, certificate


class TestRunningAgainstWazuh:
    def test_it_keeps_the_machines_with_their_ports_and_software(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started, certificate = server(serve)
        connect(session, settings, started.url, certificate)

        collect(settings, engine, Inventory())

        session.expire_all()
        assert health(session).last_items == 2
        web, nas = session.scalars(select(HostSystem).order_by(HostSystem.agent_id)).all()
        assert (web.name, web.os_name, web.architecture) == (
            "web1",
            "Ubuntu 24.04.1 LTS (Noble Numbat)",
            "x86_64",
        )
        assert web.kernel == "6.8.0-45-generic"
        assert (web.macs, [str(address) for address in web.addresses]) == (
            ["00:11:22:0a:0b:0c"],
            ["192.168.1.20"],
        )
        assert (nas.name, nas.os_name) == ("nas", "Debian GNU/Linux 12")
        ports = session.execute(
            select(HostPort.agent_id, HostPort.transport, HostPort.port, HostPort.process).order_by(
                HostPort.agent_id, HostPort.port
            )
        ).all()
        # The connection that is only established is not listening.
        assert [tuple(row) for row in ports] == [
            ("001", "tcp", 22, "sshd"),
            ("001", "tcp", 443, "nginx"),
            ("004", "tcp6", 445, "smbd"),
        ]
        assert session.scalars(select(HostPackage.name).order_by(HostPackage.name)).all() == [
            "nginx",
            "openssl",
            "samba",
        ]

    def test_it_asks_for_the_ports_that_listen_and_the_rest_of_each_index(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        asked: list[Seen] = []

        def handle(seen: Seen) -> Answer:
            asked.append(seen)
            return Answer(body=json.dumps({"hits": {"total": {"value": 0}, "hits": []}}))

        certificate = make_certificate()
        connect(session, settings, serve(handle, certificate).url, certificate)

        collect(settings, engine, Inventory())

        assert [seen.path for seen in asked] == [
            f"/{index}/_search"
            for index in (
                inventory.SYSTEM,
                inventory.INTERFACES,
                inventory.NETWORKS,
                inventory.PACKAGES,
                inventory.PORTS,
            )
        ]
        bodies = [json.loads(seen.body) for seen in asked]
        assert bodies[0] == {
            "track_total_hits": True,
            "size": indexer.WINDOW,
            "query": {"match_all": {}},
        }
        assert bodies[4]["query"] == {
            "bool": {"filter": [{"terms": {"interface.state": ["listening", "LISTEN"]}}]}
        }
        assert (health(session).consecutive_failures, health(session).last_items) == (0, 0)

    def test_the_network_card_of_a_machine_is_a_device_that_is_not_on_the_network_now(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        started, certificate = server(serve)
        connect(session, settings, started.url, certificate)

        collect(settings, engine, Inventory())

        session.expire_all()
        [device] = session.scalars(select(Device)).all()
        assert (str(device.mac), device.hostname) == ("00:11:22:0a:0b:0c", "web1.home.arpa")
        assert [str(row.address) for row in session.scalars(select(DeviceAddress))] == [
            "192.168.1.20"
        ]
        [way] = session.scalars(select(DeviceSource)).all()
        assert (way.source, way.via) == ("wazuh", "inventory")

    def test_a_machine_the_indexer_no_longer_reports_is_forgotten(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        states = sample_wazuh_states()
        started, certificate = server(serve, states)
        connect(session, settings, started.url, certificate)
        collect(settings, engine, Inventory())
        for index in states.values():
            index[:] = [item for item in index if item["agent"]["id"] != "004"]  # type: ignore[index]

        collect(settings, engine, Inventory())

        session.expire_all()
        assert session.scalars(select(HostSystem.agent_id)).all() == ["001"]
        assert session.scalars(select(HostPort.agent_id).distinct()).all() == ["001"]

    def test_machines_are_not_forgotten_when_the_system_index_holds_more_than_was_read(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        states = sample_wazuh_states()
        started, certificate = server(serve, states)
        connect(session, settings, started.url, certificate)
        collect(settings, engine, Inventory())

        def more(seen: Seen) -> Answer:
            nobody: dict[str, Any] = {
                "hits": {"total": {"value": 20000, "relation": "gte"}, "hits": []}
            }
            return Answer(body=json.dumps(nobody))

        connect_to = make_certificate()
        connect(session, settings, serve(more, connect_to).url, connect_to)

        collect(settings, engine, Inventory())

        session.expire_all()
        assert len(session.scalars(select(HostSystem)).all()) == 2

    def test_a_user_who_may_not_read_the_inventory_is_told_what_to_allow(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        def refuse(seen: Seen) -> Answer:
            return Answer(status=403, body="{}")

        certificate = make_certificate()
        connect(session, settings, serve(refuse, certificate).url, certificate)

        collect(settings, engine, Inventory())

        assert "read on wazuh-states-*" in (health(session).last_error or "")


def test_it_reads_from_the_indexer_and_is_one_of_the_collectors() -> None:
    collector = Inventory()

    assert (collector.integration, collector.connection) == ("wazuh", "indexer")
    assert collectors.find("wazuh-inventory") is not None
