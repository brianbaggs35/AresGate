"""Which interface a piece of data belongs to. Data keeps the name its source gave it, and the
interface is worked out when it is read, so placing a feed somewhere else relabels everything
that came in before as well."""

from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Interface, InterfaceFeed


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
