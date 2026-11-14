"""Storing what agents report about their machines: the collectors call ``record`` with the
machines they read."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import HostPackage, HostPort, HostSystem

Address = IPv4Address | IPv6Address
# What tells one port, and one package, from another on the same machine.
PORT_KEY = ("transport", "address", "port")
PACKAGE_KEY = ("name", "version", "architecture", "kind")


@dataclass(frozen=True)
class NewPort:
    """A port a machine listens on."""

    transport: str
    address: Address
    port: int
    process: str | None = None


@dataclass(frozen=True)
class NewPackage:
    """A piece of software installed on a machine. What the agent doesn't say is empty."""

    name: str
    version: str = ""
    architecture: str = ""
    kind: str = ""


@dataclass(frozen=True)
class NewSystem:
    """One machine as an agent reports it, with the ports it listens on and what is installed."""

    agent_id: str
    name: str | None = None
    hostname: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    os_platform: str | None = None
    architecture: str | None = None
    kernel: str | None = None
    macs: tuple[str, ...] = ()
    addresses: tuple[Address, ...] = ()
    ports: tuple[NewPort, ...] = ()
    packages: tuple[NewPackage, ...] = ()

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("A machine needs the key the integration knows it by.")


def record(
    db: Session,
    systems: Sequence[NewSystem],
    now: datetime,
    *,
    source: str,
    connection: str,
    complete: bool,
) -> int:
    """Remembers the machines an integration reported on, and returns how many. A machine
    known before has what it says now put in place of what it said, its ports and software
    included. When ``complete`` says the list is the whole of what the connection has, a machine
    it no longer lists is forgotten with its ports and software. The caller commits."""
    found = {system.agent_id: system for system in systems}
    if found:
        new = insert(HostSystem)
        db.execute(
            new.on_conflict_do_update(
                index_elements=["source", "connection", "agent_id"],
                set_={
                    column: getattr(new.excluded, column)
                    for column in (
                        "name",
                        "hostname",
                        "os_name",
                        "os_version",
                        "os_platform",
                        "architecture",
                        "kernel",
                        "macs",
                        "addresses",
                        "read_at",
                    )
                },
            ),
            [
                {
                    "source": source,
                    "connection": connection,
                    "agent_id": system.agent_id,
                    "name": system.name,
                    "hostname": system.hostname,
                    "os_name": system.os_name,
                    "os_version": system.os_version,
                    "os_platform": system.os_platform,
                    "architecture": system.architecture,
                    "kernel": system.kernel,
                    "macs": list(system.macs),
                    "addresses": list(system.addresses),
                    "read_at": now,
                }
                for system in found.values()
            ],
        )
    for system in found.values():
        _replace(db, HostPort, PORT_KEY, source, connection, system.agent_id, _port_rows(system))
        _replace(
            db, HostPackage, PACKAGE_KEY, source, connection, system.agent_id, _package_rows(system)
        )
    if complete:
        db.execute(
            delete(HostSystem).where(
                HostSystem.source == source,
                HostSystem.connection == connection,
                HostSystem.agent_id.not_in(list(found)),
            )
        )
    return len(found)


def _port_rows(system: NewSystem) -> dict[tuple[Any, ...], dict[str, Any]]:
    """The ports by what tells them apart: a program that shares a port is told once."""
    rows: dict[tuple[Any, ...], dict[str, Any]] = {}
    for port in system.ports:
        key = (port.transport, port.address, port.port)
        rows.setdefault(
            key,
            {
                "transport": port.transport,
                "address": port.address,
                "port": port.port,
                "process": port.process,
            },
        )
    return rows


def _package_rows(system: NewSystem) -> dict[tuple[Any, ...], dict[str, Any]]:
    rows: dict[tuple[Any, ...], dict[str, Any]] = {}
    for package in system.packages:
        key = (package.name, package.version, package.architecture, package.kind)
        rows.setdefault(
            key,
            {
                "name": package.name,
                "version": package.version,
                "architecture": package.architecture,
                "kind": package.kind,
            },
        )
    return rows


def _replace(
    db: Session,
    table: type[HostPort] | type[HostPackage],
    key: tuple[str, ...],
    source: str,
    connection: str,
    agent_id: str,
    wanted: dict[tuple[Any, ...], dict[str, Any]],
) -> None:
    """Makes what is kept for one machine what it reports now, and touches nothing when they
    are the same, which is nearly always."""
    kept = {
        tuple(row)
        for row in db.execute(
            select(*(getattr(table, column) for column in key)).where(
                table.source == source,
                table.connection == connection,
                table.agent_id == agent_id,
            )
        ).all()
    }
    if kept == set(wanted):
        return
    db.execute(
        delete(table).where(
            table.source == source, table.connection == connection, table.agent_id == agent_id
        )
    )
    if wanted:
        db.execute(
            insert(table),
            [
                {"source": source, "connection": connection, "agent_id": agent_id, **row}
                for row in wanted.values()
            ],
        )
