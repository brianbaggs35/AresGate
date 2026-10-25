"""The devices on the network, as the integrations that see them tell it: who they are by their
hardware address, what they are called and which addresses they have had."""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import INET, MACADDR
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime


class Device(Base):
    """One thing that has been on the network, told apart from the others by its hardware (MAC)
    address, which is the one thing that stays when its IP address changes. A device that
    switches its MAC address on purpose, as a phone does to keep from being followed from
    network to network, is a new device each time."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # In lowercase with colons: aa:bb:cc:00:11:22.
    mac: Mapped[str] = mapped_column(MACADDR, unique=True)
    # What the device calls itself to a DHCP server, or what its address resolves to. Whichever
    # was last told is kept until another is.
    hostname: Mapped[str | None] = mapped_column(String(253), default=None)
    # Who made its network card, from the first half of the MAC address.
    vendor: Mapped[str | None] = mapped_column(String(128), default=None)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # The last time an integration listed it: in the firewall's ARP table or among its DHCP
    # leases. A lease is listed until it runs out, so this is not always the moment it left.
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)


class DeviceAddress(Base):
    """An IP address a device has had. A device that has more than one, or that moved from one to
    another, has a row for each, and an address that passed from one device to another is in the
    rows of both: the device that was seen with it last has it now."""

    __tablename__ = "device_addresses"
    # Not on when it was seen, which changes on every read, so that reading is a cheap update.
    __table_args__ = (
        PrimaryKeyConstraint("device_id", "address"),
        Index("ix_device_addresses_address", "address"),
    )

    device_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("devices.id", ondelete="CASCADE"))
    address: Mapped[IPv4Address | IPv6Address] = mapped_column(INET)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
