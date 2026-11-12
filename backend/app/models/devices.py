"""The devices on the network, as the integrations that see them tell it: who they are by their
hardware address, what they are called and which addresses they have had."""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    UniqueConstraint,
)
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


class DeviceIdentity(Base):
    """What a device is, as a service that fingerprints devices says (Fingerbank): its make and
    model, its operating system and how sure the service is. It is kept by the device, so every
    later connection from the same hardware address carries it, and it is looked up again only
    when it has gone stale. A device that made up its own hardware address (a phone on Wi-Fi) is
    kept as ``private`` and never sent, since the address says nothing of what it is."""

    __tablename__ = "device_identities"
    __table_args__ = (
        CheckConstraint("state IN ('identified', 'unknown', 'private')", name="state"),
        CheckConstraint("reason IN ('asset', 'incident')", name="reason"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="score"),
    )

    device_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    # The integration that said so (``fingerbank``).
    source: Mapped[str] = mapped_column(String(32))
    # ``identified``: the service named it. ``unknown``: it asked and had no match. ``private``:
    # the hardware address is the device's own invention, so nobody was asked.
    state: Mapped[str] = mapped_column(String(10))
    # Why it was looked up: it is one of the owner's assets, or it is in an incident or threat.
    reason: Mapped[str] = mapped_column(String(10))
    # The most specific thing it is, in the service's words ("Apple iPhone 16"), and the whole
    # path to it ("Phone, Tablet, or Wearable/Apple iOS, macOS, and tvOS/Apple iPhone/Apple
    # iPhone 16"), which says what kind of device it is.
    name: Mapped[str | None] = mapped_column(String(200), default=None)
    path: Mapped[str | None] = mapped_column(String(600), default=None)
    manufacturer: Mapped[str | None] = mapped_column(String(128), default=None)
    operating_system: Mapped[str | None] = mapped_column(String(128), default=None)
    # How sure the service is, from 0 to 100.
    score: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    # The service's own number for what it is, for linking to its page about it.
    external_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime)


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


class DeviceSource(Base):
    """One way an integration lists a device: OPNsense's ARP table, its DHCP leases, an ntopng
    host. A device listed by more than one has a row for each, so a page can say who has seen it
    and how long ago, and tell a device that is on the network now (the ARP table, ntopng) from
    one that only has a lease."""

    __tablename__ = "device_sources"
    # Not on when it was seen, which changes on every read, so that reading is a cheap update.
    __table_args__ = (PrimaryKeyConstraint("device_id", "source", "via"),)

    device_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("devices.id", ondelete="CASCADE"))
    # The integration (opnsense) and how it listed the device: a key of ``app.devices.ways``.
    source: Mapped[str] = mapped_column(String(32))
    via: Mapped[str] = mapped_column(String(16))
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # Whether the integration listed it as one of its own addresses (the firewall's own interfaces,
    # which the ARP table marks as permanent). Once it has been, it stays so.
    own: Mapped[bool] = mapped_column(Boolean, default=False)


class HostListing(Base):
    """A machine an integration lists by name and address, with no hardware address to tell it
    apart by, such as a Wazuh agent. It is not a ``Device``, but the Assets page matches it to one
    by its address or its name, and lists it on its own when nothing matches."""

    __tablename__ = "host_listings"
    __table_args__ = (UniqueConstraint("source", "connection", "key", name="uq_host_listings_key"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    connection: Mapped[str] = mapped_column(String(32))
    # How it was listed: a key of ``app.devices.ways``.
    via: Mapped[str] = mapped_column(String(16))
    # What the integration calls it: the agent's number.
    key: Mapped[str] = mapped_column(String(128))
    hostname: Mapped[str | None] = mapped_column(String(253), default=None)
    address: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET, default=None)
    # The integration's word for how it is doing (``active``, ``disconnected``), and whether that
    # means it is in touch now.
    state: Mapped[str] = mapped_column(String(32))
    online: Mapped[bool] = mapped_column(Boolean)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # The last time the integration heard from it: the run's time for one in touch.
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)


class AssetProfile(Base):
    """What the owner says an asset is: what kind of thing it is and what it is for. It is kept by
    the asset's key (``device-12`` or ``host-3``), which is what the Assets pages link to, and is
    the owner's word: nothing a program lists changes it."""

    __tablename__ = "asset_profiles"

    key: Mapped[str] = mapped_column(String(24), primary_key=True)
    # A key of ``app.assets.profile.KINDS``.
    kind: Mapped[str] = mapped_column(String(24))
    # In the owner's words: "Dad's work laptop", "Streams the news in the kitchen".
    purpose: Mapped[str | None] = mapped_column(String(200), default=None)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
