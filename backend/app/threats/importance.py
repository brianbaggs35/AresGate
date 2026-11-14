"""Which devices matter, and what that does to a threat.

An attack on the NAS that holds the backups is not the same thing as one on a smart plug, and a
list that ranks only by how bad and how sure treats them alike. The owner says how much each asset
matters (``normal``, ``important`` or ``critical``, on the Assets page), and a guest or an IoT
device is known to be of less consequence by its kind. What an incident touched is the devices
that have one of its addresses, as ``app/incidents/through.py`` reads it; its importance is that
of the one that matters most, kept on the incident (``Incident.importance``) so that ranking and
counting are only columns:

- 2: it touched a device the owner called critical.
- 1: it touched one called important.
- 0: it touched nothing the owner has an opinion of.
- -1: everything it touched is a guest or an IoT device and the owner did not say it matters.

The engine files it as the incident changes, and saving what an asset is files it again for the
incidents that are going on. The owner's settings (``app/threats/settings.py``) say what it does:
an incident that touched an important device is asked about at a lower floor, and one that touched
only guests and IoT devices at a higher one (``app/incidents/attention.py``), and among incidents
of the same severity, each step of importance counts as ten points of certainty
(``RANK_STEP``).
"""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address
from typing import Final
from typing import cast as assume

from sqlalchemy import ColumnElement, String, any_, case, cast, func, literal, select, update
from sqlalchemy.orm import Session, aliased

from app.assets.profile import BY_KEY
from app.models import AssetProfile, Device, DeviceAddress, HostListing, Incident

IMPORTANCES: Final = ("normal", "important", "critical")
# What kinds of asset are of less consequence by what they are: someone else's, or a gadget.
LOW_KINDS: Final = ("guest", "smart_home")
# What the kinds that usually matter offer as the importance, for the owner to take or leave.
PRESETS: Final = {
    "router": "critical",
    "firewall": "critical",
    "nas": "critical",
    "server": "important",
    "camera": "important",
}
# How many points of certainty one step of importance is worth when ranking incidents of the same
# severity.
RANK_STEP: Final = 10
_ACTIVE: Final = ("open", "investigating")
_WORDS: Final = {2: "critical", 1: "important", -1: "low"}

Address = IPv4Address | IPv6Address


def weight(importance: str, kind: str) -> int:
    """What an asset counts for: 2 if the owner called it critical, 1 important, -1 if it is
    normal and a guest or IoT device, 0 otherwise."""
    if importance == "critical":
        return 2
    if importance == "important":
        return 1
    return -1 if kind in LOW_KINDS else 0


def word(value: int) -> str:
    """An incident's importance in a word: ``critical``, ``important``, ``low`` or ``normal``."""
    return _WORDS.get(value, "normal")


def _weight() -> ColumnElement[int]:
    """``weight`` as SQL, on a profile that may be missing."""
    return case(
        (AssetProfile.importance == "critical", 2),
        (AssetProfile.importance == "important", 1),
        (AssetProfile.kind.in_(LOW_KINDS), -1),
        else_=0,
    )


def _touched() -> ColumnElement[int]:
    """The importance of an incident row, as SQL: the greatest weight among the assets that have
    one of its addresses. A device counts by the address it has now, and a machine a program lists
    by address only counts if no device has that address."""
    newest = aliased(DeviceAddress)
    by_device = (
        select(func.max(_weight()))
        .select_from(DeviceAddress)
        .outerjoin(
            AssetProfile,
            AssetProfile.key == literal("device-") + cast(DeviceAddress.device_id, String),
        )
        .where(
            DeviceAddress.address == any_(Incident.addresses),
            DeviceAddress.last_seen_at
            == select(func.max(newest.last_seen_at))
            .where(newest.address == DeviceAddress.address)
            .scalar_subquery(),
        )
        .scalar_subquery()
    )
    by_listing = (
        select(func.max(_weight()))
        .select_from(HostListing)
        .outerjoin(
            AssetProfile, AssetProfile.key == literal("host-") + cast(HostListing.id, String)
        )
        .where(
            HostListing.address == any_(Incident.addresses),
            HostListing.address.not_in(select(DeviceAddress.address)),
        )
        .scalar_subquery()
    )
    return func.coalesce(func.greatest(by_device, by_listing), 0)


def refresh(db: Session, ids: Collection[int] | None = None) -> int:
    """Files the importance of the incidents that are going on again (of these, if some are
    named), and says how many changed. The caller commits."""
    found = _touched()
    changed = update(Incident).where(
        Incident.status.in_(_ACTIVE), Incident.importance.is_distinct_from(found)
    )
    if ids is not None:
        if not ids:
            return 0
        changed = changed.where(Incident.id.in_(ids))
    # Not a change an incident's own ``updated_at`` should show.
    db.flush()
    return (
        db.connection()
        .execute(changed.values(importance=found, updated_at=Incident.updated_at))
        .rowcount
    )


def rank() -> ColumnElement[int]:
    """What incidents of the same severity are ranked by, the most first: how sure it is, and
    ``RANK_STEP`` points for each step of importance."""
    return Incident.confidence + Incident.importance * RANK_STEP


@dataclass(frozen=True)
class Touch:
    """The asset that makes an incident matter more (or less), for a card to say so."""

    name: str
    # What kind of thing it is, in a word the owner chose from (``Storage (NAS)``).
    kind: str
    importance: str


def _name(hostname: str | None, vendor: str | None, address: Address | None, kind: str) -> str:
    return hostname or vendor or (str(address) if address is not None else kind)


def touches(db: Session, incidents: Sequence[Incident]) -> dict[int, Touch]:
    """For each of these incidents that matters more or less than the rest, the asset that makes it
    so: the one that matters most, and for a low one the first it touched."""
    wanted = {
        address for incident in incidents if incident.importance for address in incident.addresses
    }
    if not wanted:
        return {}
    owners = _owners(db, wanted)
    found: dict[int, Touch] = {}
    for incident in incidents:
        for address in incident.addresses:
            owner = owners.get(address)
            if owner is not None and owner[0] == incident.importance:
                found.setdefault(incident.id, owner[1])
    return found


def _owner(
    address: Address, said: AssetProfile | None, name: str | None, vendor: str | None
) -> tuple[int, Touch]:
    """What an address's asset counts for, and what to call it: its name, its maker's, or its
    address."""
    kind = said.kind if said else "other"
    value = weight(said.importance if said else "normal", kind)
    label = BY_KEY[kind].label
    return value, Touch(_name(name, vendor, address, label), label, word(value))


def _owners(db: Session, wanted: Iterable[Address]) -> dict[Address, tuple[int, Touch]]:
    """For each address, the weight of the asset that has it now, and what to call it. A machine a
    program lists by address counts only where no device has the address."""
    owners: dict[Address, tuple[int, Touch]] = {}
    rows = db.execute(
        select(DeviceAddress.address, Device, AssetProfile)
        .join(Device, Device.id == DeviceAddress.device_id)
        .outerjoin(
            AssetProfile,
            AssetProfile.key == literal("device-") + cast(DeviceAddress.device_id, String),
        )
        .where(DeviceAddress.address.in_(list(wanted)))
        .order_by(DeviceAddress.last_seen_at.desc(), Device.id)
    )
    for address, device, said in rows:
        owners.setdefault(address, _owner(address, said, device.hostname, device.vendor))
    listings = db.execute(
        select(HostListing, AssetProfile)
        .outerjoin(
            AssetProfile, AssetProfile.key == literal("host-") + cast(HostListing.id, String)
        )
        .where(HostListing.address.in_(list(wanted)))
        .order_by(HostListing.id)
    )
    for listing, said in listings:
        # Only those with an address were asked for.
        address = assume(Address, listing.address)
        owners.setdefault(address, _owner(address, said, listing.hostname, None))
    return owners


def sentence(touch: Touch) -> str:
    """Why an incident is where it is, from the asset that matters: ``It touched nas-1, a storage
    (nas) you marked critical.``"""
    if touch.importance == "low":
        return (
            f"It only touched {touch.name}, a {touch.kind.lower()}, which matters less, so it "
            "takes more proof."
        )
    return f"It touched {touch.name}, a {touch.kind.lower()} you marked {touch.importance}."
