"""Which interface a piece of data belongs to. Data keeps the name its source gave it, and the
interface is worked out when it is read, so placing a feed somewhere else relabels everything
that came in before as well."""

from typing import NamedTuple

from sqlalchemy import ColumnElement, and_, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models import Event, Interface, InterfaceFeed


class Place(NamedTuple):
    """Where a feed was placed: an interface, or nowhere (``interface`` is None), and whether it
    was set aside."""

    interface: Interface | None
    ignored: bool


class Resolver:
    """Looks up the interface of data from a program, its connection and a port name, reading the
    feeds once. A name nobody placed falls back to the whole connection's feed, which is how data
    that has no port (CrowdSec's bans) belongs to an interface."""

    def __init__(self, db: Session) -> None:
        interfaces = {item.id: item for item in db.scalars(select(Interface))}
        self._places: dict[tuple[str, str, str], Place] = {
            (feed.integration, feed.connection, feed.native_name): Place(
                interfaces.get(feed.interface_id) if feed.interface_id is not None else None,
                feed.ignored,
            )
            for feed in db.scalars(select(InterfaceFeed))
        }

    def of(self, integration: str, connection: str, name: str | None) -> Place | None:
        """The place of a feed, or None when nobody has seen it (or, for a name, the connection
        as a whole has no feed either)."""
        if name:
            found = self._places.get((integration, connection, name))
            if found is not None and (found.interface is not None or found.ignored):
                return found
        return self._places.get((integration, connection, ""))


def on_interface(name: str) -> ColumnElement[bool]:
    """Events that came in on the interface of this name (in any case), as a condition on
    ``Event``. It reads the placing the way ``Resolver`` does, in the database: a port that was
    placed or set aside belongs where it was put, and any other port belongs where its
    connection as a whole was placed. A name that is no interface matches nothing."""
    placed = aliased(InterfaceFeed)
    specific = aliased(InterfaceFeed)
    interface = select(Interface.id).where(func.lower(Interface.name) == name.casefold())
    port_decided = (
        select(specific.id)
        .where(
            specific.integration == Event.source,
            specific.connection == Event.connection,
            specific.native_name == Event.iface,
            or_(specific.interface_id.is_not(None), specific.ignored),
        )
        .correlate(Event)
        .exists()
    )
    return exists().where(
        placed.integration == Event.source,
        placed.connection == Event.connection,
        placed.interface_id.in_(interface),
        or_(placed.native_name == Event.iface, and_(placed.native_name == "", ~port_decided)),
    )
