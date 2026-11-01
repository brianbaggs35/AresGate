"""The parts of the network the owner names, and which feeds of data belong to each."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow

# What a part of the network is for. Only the Internet is outside: what the others carry is
# traffic of the home, a guest or a device, whatever the name of the port it comes in on.
ROLES = ("internet", "dmz", "home", "guest", "iot", "vpn", "management", "other")


class Interface(Base):
    """A named part of the network, such as Internet or Guests, with what it is for. The sources
    each call their own port something else (OPNsense ``igc0``, ntopng ``eno1``), and the owner
    says which of those are this part, so the data of different programs can be read as one."""

    __tablename__ = "interfaces"
    __table_args__ = (
        CheckConstraint(
            "role IN ('internet', 'dmz', 'home', 'guest', 'iot', 'vpn', 'management', 'other')",
            name="role",
        ),
        UniqueConstraint("name", name="uq_interfaces_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(16))
    notes: Mapped[str] = mapped_column(String(300), default="")
    # The addresses that belong to it, as CIDR blocks such as 192.168.20.0/24.
    networks: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    # Where it comes in a list: lowest first.
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class InterfaceFeed(Base):
    """What one integration reports about one port: the connection and the name it uses for it
    (``igc0``), or no name for a source that has none, such as CrowdSec, whose bans are of the
    whole connection. A feed belongs to one interface, or has been set aside as not wanted, or
    is not placed yet. Feeds are found by looking at what the integrations have stored and what
    they list, so one is made when it is first seen."""

    __tablename__ = "interface_feeds"
    __table_args__ = (
        UniqueConstraint(
            "integration", "connection", "native_name", name="uq_interface_feeds_name"
        ),
        # A feed set aside is not on an interface.
        CheckConstraint("NOT (ignored AND interface_id IS NOT NULL)", name="placed_or_ignored"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    integration: Mapped[str] = mapped_column(String(32))
    connection: Mapped[str] = mapped_column(String(32))
    # The name the source uses, as it stores it; empty for the whole connection.
    native_name: Mapped[str] = mapped_column(String(64), default="")
    # What the source says it is (ntopng's name for it), and a few words about it, to tell ports
    # apart on a page.
    label: Mapped[str] = mapped_column(String(120), default="")
    detail: Mapped[str] = mapped_column(String(200), default="")
    interface_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("interfaces.id", ondelete="SET NULL"), default=None
    )
    ignored: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # When data under this name was last found, to tell a port that is gone from one that is quiet.
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
