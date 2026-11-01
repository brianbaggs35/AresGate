"""Interfaces: the parts of the network the owner names (Internet, Guests, Cameras), and which
feeds of data belong to each, so what different programs say can be read as one. For someone
signed in."""

from typing import Annotated, Literal, cast

import anyio.from_thread
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy.orm import Session

from app.api.deps import Db, SettingsDep, SignedIn, record_audit, signed_in
from app.api.integrations import PolicyDep, RecorderDep
from app.audit import Action, Outcome
from app.incidents import rules
from app.integrations import registry, service
from app.interfaces import discovery, scope, suggest
from app.interfaces import service as interfaces
from app.models import Interface, InterfaceFeed, utcnow

router = APIRouter(prefix="/interfaces", tags=["interfaces"], dependencies=[Depends(signed_in)])

Role = Literal["internet", "dmz", "home", "guest", "iot", "vpn", "management", "other"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
Network = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Id = Annotated[int, Path(ge=1, le=2**63 - 1)]
FeedId = Annotated[int, Field(ge=1, le=2**63 - 1)]
# The one integration whose list of interfaces can be asked for.
LISTS_INTERFACES = ("ntopng", "api")


class FeedOut(BaseModel):
    id: int
    integration: str
    # What the integration and the connection are called on a page.
    integration_name: str
    connection: str
    connection_label: str
    # The name the source uses; empty for the whole connection.
    native_name: str
    label: str
    detail: str
    interface_id: int | None
    ignored: bool
    last_seen_at: AwareDatetime


class InterfaceOut(BaseModel):
    id: int
    name: str
    role: Role
    notes: str
    networks: list[str]
    position: int
    feeds: list[FeedOut]


class SuggestionOut(BaseModel):
    name: str
    role: Role
    feed_ids: list[int]
    reason: str
    # The interface the feeds would join, when one has that name; otherwise one is made.
    interface_id: int | None


class InterfacesOut(BaseModel):
    interfaces: list[InterfaceOut]
    # Feeds that were found and are not placed yet, and the ones set aside.
    unplaced: list[FeedOut]
    ignored: list[FeedOut]
    suggestions: list[SuggestionOut]
    max_interfaces: int


class InterfaceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    role: Role
    notes: Notes = ""
    networks: list[Network] = Field(
        default_factory=lambda: list[str](), max_length=interfaces.MAX_NETWORKS
    )
    # Feeds to place on it as it is made.
    feeds: list[FeedId] = Field(default_factory=lambda: list[int](), max_length=200)


class InterfaceChange(BaseModel):
    """What can be changed; what is left out stays."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    role: Role | None = None
    notes: Notes | None = None
    networks: list[Network] | None = Field(default=None, max_length=interfaces.MAX_NETWORKS)
    position: int | None = Field(default=None, ge=0, le=1000)


class FeedPlacement(BaseModel):
    """Where a feed goes: on an interface, set aside (``ignored``), or back to not placed."""

    model_config = ConfigDict(extra="forbid")

    interface_id: FeedId | None = None
    ignored: bool = False

    @model_validator(mode="after")
    def _one_place(self) -> FeedPlacement:
        if self.interface_id is not None and self.ignored:
            raise ValueError("A feed is placed on an interface or set aside, not both.")
        return self


class DiscoverOut(BaseModel):
    # How many feeds were found that hadn't been seen before.
    new: int
    # False when looking through the events took too long and was left for next time.
    complete: bool
    # What could not be asked, such as ntopng not answering, in a sentence each.
    notes: list[str]


class PlaceOut(BaseModel):
    interface_id: int | None
    name: str | None
    role: Role | None
    ignored: bool


def _feed(feed: InterfaceFeed) -> FeedOut:
    definition = registry.INTEGRATIONS.get(feed.integration)
    connection = definition.connection(feed.connection) if definition else None
    return FeedOut(
        id=feed.id,
        integration=feed.integration,
        integration_name=rules.name_of(feed.integration),
        connection=feed.connection,
        connection_label=connection.label if connection else feed.connection,
        native_name=feed.native_name,
        label=feed.label,
        detail=feed.detail,
        interface_id=feed.interface_id,
        ignored=feed.ignored,
        last_seen_at=feed.last_seen_at,
    )


def _interface(item: Interface, feeds: list[InterfaceFeed]) -> InterfaceOut:
    return InterfaceOut(
        id=item.id,
        name=item.name,
        role=cast("Role", item.role),
        notes=item.notes,
        networks=[str(block) for block in item.networks],
        position=item.position,
        feeds=[_feed(feed) for feed in feeds],
    )


def _listing(db: Session) -> InterfacesOut:
    taken = interfaces.listing(db)
    return InterfacesOut(
        interfaces=[_interface(item, feeds) for item, feeds in taken.interfaces],
        unplaced=[_feed(feed) for feed in taken.unplaced],
        ignored=[_feed(feed) for feed in taken.ignored],
        suggestions=[
            SuggestionOut(
                name=item.name,
                role=cast("Role", item.role),
                feed_ids=list(item.feed_ids),
                reason=item.reason,
                interface_id=item.interface_id,
            )
            for item in suggest.suggestions(db)
        ],
        max_interfaces=interfaces.MAX_INTERFACES,
    )


def _refused(error: interfaces.InterfaceError) -> HTTPException:
    """What the owner is told when a change can't be made, with the status that fits why."""
    if error.missing:
        code = status.HTTP_404_NOT_FOUND
    elif error.conflict:
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(code, str(error))


def _facts(item: Interface) -> dict[str, str | int | bool]:
    return {"interface_id": item.id, "name": item.name, "role": item.role}


@router.get("")
def list_interfaces(db: Db) -> InterfacesOut:
    """Every interface with the feeds on it, the feeds not placed yet or set aside, and where the
    feeds that aren't placed could go."""
    return _listing(db)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_interface(
    body: InterfaceIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> InterfaceOut:
    """Makes an interface, and places the feeds named on it."""
    try:
        made = interfaces.create(
            db,
            name=body.name,
            role=body.role,
            notes=body.notes,
            networks=body.networks,
            feeds=body.feeds,
        )
    except interfaces.InterfaceError as error:
        db.rollback()
        raise _refused(error) from error
    record_audit(
        db,
        request,
        Action.INTERFACE_CREATED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={**_facts(made), "feeds": len(body.feeds)},
    )
    db.commit()
    return _interface(made, interfaces.feeds_of(db, made.id))


@router.patch("/{interface_id}")
def change_interface(
    interface_id: Id,
    body: InterfaceChange,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> InterfaceOut:
    """Changes the name, role, notes, networks or place in the list of an interface."""
    try:
        found, changed = interfaces.change(
            db,
            interface_id,
            name=body.name,
            role=body.role,
            notes=body.notes,
            networks=body.networks,
            position=body.position,
        )
    except interfaces.InterfaceError as error:
        db.rollback()
        raise _refused(error) from error
    if changed:
        record_audit(
            db,
            request,
            Action.INTERFACE_CHANGED,
            Outcome.SUCCESS,
            user=auth.user,
            detail={**_facts(found), "changed": ", ".join(changed)},
        )
        db.commit()
    return _interface(found, interfaces.feeds_of(db, found.id))


@router.delete("/{interface_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_interface(
    interface_id: Id,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> Response:
    """Removes an interface. Its feeds go back to not being placed; no data is lost."""
    try:
        removed = interfaces.remove(db, interface_id)
    except interfaces.InterfaceError as error:
        db.rollback()
        raise _refused(error) from error
    record_audit(
        db,
        request,
        Action.INTERFACE_REMOVED,
        Outcome.SUCCESS,
        user=auth.user,
        detail=_facts(removed),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/feeds/{feed_id}")
def place_feed(
    feed_id: Id,
    body: FeedPlacement,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> FeedOut:
    """Puts a feed on an interface, sets it aside as not wanted, or leaves it not placed."""
    try:
        feed = interfaces.place(db, feed_id, body.interface_id, ignored=body.ignored)
    except interfaces.InterfaceError as error:
        db.rollback()
        raise _refused(error) from error
    facts: dict[str, str | int | bool] = {
        "feed_id": feed.id,
        "integration": feed.integration,
        "connection": feed.connection,
        "native_name": feed.native_name,
        "ignored": feed.ignored,
    }
    if feed.interface_id is not None:
        facts["interface_id"] = feed.interface_id
    record_audit(
        db, request, Action.INTERFACE_FEED_PLACED, Outcome.SUCCESS, user=auth.user, detail=facts
    )
    db.commit()
    return _feed(feed)


@router.post("/discover")
def discover(
    db: Db, settings: SettingsDep, policy: PolicyDep, recorder: RecorderDep
) -> DiscoverOut:
    """Looks for feeds: the ports that stored events and metrics came in on, the whole connections
    that are one feed, and the interfaces ntopng lists. Finds only; nothing is placed. A program
    that can't be asked is said in the notes, and the rest is still found."""
    now = utcnow()
    from_events, complete = discovery.from_events(db, now)
    found = [*from_events, *discovery.from_metrics(db), *discovery.whole_connections(db)]
    notes: list[str] = []
    definition = registry.INTEGRATIONS[LISTS_INTERFACES[0]]
    connection = definition.connection(LISTS_INTERFACES[1])
    row = service.rows_for(db, definition.key).get(LISTS_INTERFACES[1])
    if row is not None and connection is not None:
        try:
            target = service.load_target(db, settings, definition, connection, row)
        except service.Incomplete as incomplete:
            notes.append(f"{definition.name}: {incomplete}")
        else:
            live = anyio.from_thread.run(discovery.ntopng_live, target, recorder, policy)
            if isinstance(live, str):
                notes.append(f"{definition.name} couldn't list its interfaces. {live}")
            else:
                found.extend(live)
    new = discovery.store(db, found, now)
    db.commit()
    return DiscoverOut(new=new, complete=complete, notes=notes)


@router.get("/resolve")
def resolve(
    db: Db,
    integration: Annotated[str, Query(min_length=1, max_length=32)],
    connection: Annotated[str, Query(min_length=1, max_length=32)],
    name: Annotated[str, Query(max_length=64)] = "",
) -> PlaceOut:
    """Which interface data from a program, its connection and a port name belongs to."""
    place = scope.Resolver(db).of(integration, connection, name)
    item = place.interface if place else None
    return PlaceOut(
        interface_id=item.id if item else None,
        name=item.name if item else None,
        role=cast("Role", item.role) if item else None,
        ignored=place.ignored if place else False,
    )
