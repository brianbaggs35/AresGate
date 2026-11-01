"""Making, changing and removing interfaces, and placing feeds on them."""

from dataclasses import dataclass
from ipaddress import ip_network

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import INTERFACE_ROLES, Interface, InterfaceFeed

# How many interfaces and networks one may have: a home has a handful, and every page that
# lists them has to stay one to read.
MAX_INTERFACES = 24
MAX_NETWORKS = 16


class InterfaceError(ValueError):
    """What is wrong with a change, in a sentence for the owner. ``missing`` is for what isn't
    there and ``conflict`` for what clashes with what is (a name taken, no room for another),
    which are told apart from what can't be said at all."""

    def __init__(self, message: str, *, missing: bool = False, conflict: bool = False) -> None:
        super().__init__(message)
        self.missing = missing
        self.conflict = conflict


@dataclass(frozen=True)
class Listing:
    """Everything on the Interfaces page: each interface with the feeds on it, the feeds not
    placed yet, and the ones set aside."""

    interfaces: list[tuple[Interface, list[InterfaceFeed]]]
    unplaced: list[InterfaceFeed]
    ignored: list[InterfaceFeed]


def _feed_order(feed: InterfaceFeed) -> tuple[str, str, str]:
    return (feed.integration, feed.connection, feed.native_name)


def listing(db: Session) -> Listing:
    interfaces = db.scalars(select(Interface).order_by(Interface.position, Interface.id)).all()
    feeds = sorted(db.scalars(select(InterfaceFeed)).all(), key=_feed_order)
    placed: dict[int, list[InterfaceFeed]] = {item.id: [] for item in interfaces}
    unplaced: list[InterfaceFeed] = []
    ignored: list[InterfaceFeed] = []
    for feed in feeds:
        if feed.interface_id is not None:
            placed[feed.interface_id].append(feed)
        elif feed.ignored:
            ignored.append(feed)
        else:
            unplaced.append(feed)
    return Listing([(item, placed[item.id]) for item in interfaces], unplaced, ignored)


def clean_networks(networks: list[str]) -> list[str]:
    """The networks as CIDR blocks, each once, with the host bits cleared (192.168.20.7/24 is
    192.168.20.0/24). Raises ``InterfaceError`` for one that isn't a network."""
    if len(networks) > MAX_NETWORKS:
        raise InterfaceError(f"An interface can have up to {MAX_NETWORKS} networks.")
    found: list[str] = []
    for text in networks:
        try:
            block = str(ip_network(text.strip(), strict=False))
        except ValueError:
            raise InterfaceError(
                f"{text.strip()[:60]!r} isn't a network. Write it like 192.168.20.0/24."
            ) from None
        if block not in found:
            found.append(block)
    return found


def _check_role(role: str) -> None:
    if role not in INTERFACE_ROLES:
        raise InterfaceError(f"The role is one of {', '.join(INTERFACE_ROLES)}.")


def _check_name(db: Session, name: str, *, own: int | None = None) -> None:
    """A name is taken whatever its capitals, so Guests and guests can't both exist."""
    query = select(Interface.id).where(func.lower(Interface.name) == name.lower())
    if own is not None:
        query = query.where(Interface.id != own)
    if db.scalar(query) is not None:
        raise InterfaceError(f"There is already an interface called {name}.", conflict=True)


def feeds_of(db: Session, interface_id: int) -> list[InterfaceFeed]:
    """The feeds on an interface, in the order the page lists them."""
    feeds = db.scalars(select(InterfaceFeed).where(InterfaceFeed.interface_id == interface_id))
    return sorted(feeds, key=_feed_order)


def get(db: Session, interface_id: int) -> Interface:
    found = db.get(Interface, interface_id)
    if found is None:
        raise InterfaceError("There is no such interface.", missing=True)
    return found


def create(
    db: Session,
    *,
    name: str,
    role: str,
    notes: str,
    networks: list[str],
    feeds: list[int],
) -> Interface:
    """Makes an interface, at the end of the list, with some feeds placed on it. The caller
    commits."""
    _check_role(role)
    _check_name(db, name)
    blocks = clean_networks(networks)
    kept = db.scalar(select(func.count()).select_from(Interface)) or 0
    if kept >= MAX_INTERFACES:
        raise InterfaceError(
            f"You can have {MAX_INTERFACES} interfaces. Remove one to add another.",
            conflict=True,
        )
    last = db.scalar(select(func.max(Interface.position)))
    made = Interface(
        name=name,
        role=role,
        notes=notes,
        networks=blocks,
        position=0 if last is None else last + 1,
    )
    db.add(made)
    db.flush()
    for feed_id in dict.fromkeys(feeds):
        place(db, feed_id, made.id)
    return made


def change(
    db: Session,
    interface_id: int,
    *,
    name: str | None,
    role: str | None,
    notes: str | None,
    networks: list[str] | None,
    position: int | None,
) -> tuple[Interface, list[str]]:
    """Changes what is given, and says which of name, role, notes, networks and position changed.
    The caller commits."""
    found = get(db, interface_id)
    changed: list[str] = []
    if name is not None and name != found.name:
        _check_name(db, name, own=found.id)
        found.name = name
        changed.append("name")
    if role is not None and role != found.role:
        _check_role(role)
        found.role = role
        changed.append("role")
    if notes is not None and notes != found.notes:
        found.notes = notes
        changed.append("notes")
    if networks is not None:
        blocks = clean_networks(networks)
        if blocks != found.networks:
            found.networks = blocks
            changed.append("networks")
    if position is not None and position != found.position:
        found.position = position
        changed.append("position")
    db.flush()
    return found, changed


def remove(db: Session, interface_id: int) -> Interface:
    """Removes an interface; its feeds go back to being not placed. The caller commits."""
    found = get(db, interface_id)
    db.delete(found)
    db.flush()
    return found


def place(
    db: Session, feed_id: int, interface_id: int | None, *, ignored: bool = False
) -> InterfaceFeed:
    """Puts a feed on an interface, sets it aside (``ignored``), or leaves it not placed (neither).
    The caller commits."""
    feed = db.get(InterfaceFeed, feed_id)
    if feed is None:
        raise InterfaceError("There is no such feed.", missing=True)
    if interface_id is not None and ignored:
        raise InterfaceError("A feed is placed on an interface or set aside, not both.")
    if interface_id is not None:
        get(db, interface_id)
    feed.interface_id = interface_id
    feed.ignored = ignored
    db.flush()
    return feed
