"""What an agent on a machine reports about it: its system, the ports it listens on and the
software installed. Wazuh keeps these in its indexer; AresGate reads them so the analyst can be
asked about them. They say what a machine is, so a row is replaced when the agent says something
else, and forgotten with the machine."""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import BigInteger, ForeignKeyConstraint, PrimaryKeyConstraint, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, INET
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime

SYSTEM_KEY = ("source", "connection", "agent_id")
SYSTEM_REFERENCE = ["host_systems.source", "host_systems.connection", "host_systems.agent_id"]


class HostSystem(Base):
    """One machine an integration's agent reports on: what it is called, what it runs, and the
    hardware and IP addresses of its network interfaces."""

    __tablename__ = "host_systems"
    __table_args__ = (PrimaryKeyConstraint(*SYSTEM_KEY),)

    source: Mapped[str] = mapped_column(String(32))
    connection: Mapped[str] = mapped_column(String(32))
    # What the integration calls it: the agent's number.
    agent_id: Mapped[str] = mapped_column(String(128))
    # The agent's name, and the host name its operating system reports.
    name: Mapped[str | None] = mapped_column(String(253), default=None)
    hostname: Mapped[str | None] = mapped_column(String(253), default=None)
    # The operating system as a person reads it ("Ubuntu 24.04.1 LTS"), and its parts.
    os_name: Mapped[str | None] = mapped_column(String(128), default=None)
    os_version: Mapped[str | None] = mapped_column(String(64), default=None)
    os_platform: Mapped[str | None] = mapped_column(String(32), default=None)
    architecture: Mapped[str | None] = mapped_column(String(32), default=None)
    kernel: Mapped[str | None] = mapped_column(String(128), default=None)
    # In lowercase with colons, as ``devices`` keeps them.
    macs: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    addresses: Mapped[list[IPv4Address | IPv6Address]] = mapped_column(ARRAY(INET), default=list)
    # When the agent last had its inventory read, which is not when it reported it.
    read_at: Mapped[datetime] = mapped_column(UTCDateTime)


class HostPort(Base):
    """A port a machine listens on, and the program that does."""

    __tablename__ = "host_ports"
    __table_args__ = (
        PrimaryKeyConstraint(*SYSTEM_KEY, "transport", "address", "port"),
        ForeignKeyConstraint([*SYSTEM_KEY], SYSTEM_REFERENCE, ondelete="CASCADE"),
    )

    source: Mapped[str] = mapped_column(String(32))
    connection: Mapped[str] = mapped_column(String(32))
    agent_id: Mapped[str] = mapped_column(String(128))
    # ``tcp`` or ``udp``, as the agent says (``tcp6`` is TCP over IPv6).
    transport: Mapped[str] = mapped_column(String(8))
    # What it listens on: 0.0.0.0 and :: for every address of the machine.
    address: Mapped[IPv4Address | IPv6Address] = mapped_column(INET)
    port: Mapped[int] = mapped_column(BigInteger)
    process: Mapped[str | None] = mapped_column(String(128), default=None)


class HostPackage(Base):
    """A piece of software installed on a machine. A name, version, architecture and kind
    (``deb``, ``rpm``, ``pypi``) tell one from another, and what the agent doesn't say is empty."""

    __tablename__ = "host_packages"
    __table_args__ = (
        PrimaryKeyConstraint(*SYSTEM_KEY, "name", "version", "architecture", "kind"),
        ForeignKeyConstraint([*SYSTEM_KEY], SYSTEM_REFERENCE, ondelete="CASCADE"),
    )

    source: Mapped[str] = mapped_column(String(32))
    connection: Mapped[str] = mapped_column(String(32))
    agent_id: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(256))
    version: Mapped[str] = mapped_column(String(128), default="")
    architecture: Mapped[str] = mapped_column(String(32), default="")
    kind: Mapped[str] = mapped_column(String(16), default="")
