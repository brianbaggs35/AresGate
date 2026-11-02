"""Alerts: the places AresGate sends word of what it finds. Their addresses only go in: no route
here returns one, and a failed request doesn't quote what was sent."""

from typing import Annotated, Literal

import anyio.from_thread
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, StringConstraints
from sqlalchemy.orm import Session

from app.alerts import destinations, discord
from app.alerts.destinations import NameTaken, Unusable
from app.alerts.discord import InvalidWebhook
from app.api.deps import Db, SettingsDep, SignedIn, record_audit, signed_in
from app.api.integrations import RecorderDep
from app.audit import Action, Outcome
from app.integrations.service import Status
from app.models import AlertDestination, utcnow

# Everything here is for someone who is signed in.
router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(signed_in)])

DestinationId = Annotated[int, Path(ge=1, le=2**63 - 1)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Address = Annotated[SecretStr, Field(min_length=1, max_length=discord.MAX_URL)]


class DestinationOut(BaseModel):
    id: int
    kind: Literal["discord"]
    name: str
    enabled: bool
    # Where it goes without the secret: the host, and the end of the webhook's number.
    host: str
    hint: str
    # Not tried, working, or failing; "not_connected" is a destination whose address is gone.
    status: Status
    last_attempt_at: AwareDatetime | None
    last_success_at: AwareDatetime | None
    last_error: str | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class DestinationsOut(BaseModel):
    items: list[DestinationOut]
    max_destinations: int
    # The addresses a webhook may be at, for the page to say.
    hosts: list[str]


class DestinationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    url: Address


class DestinationChange(BaseModel):
    """What can be changed of a destination. What is left out stays; an address is replaced, never
    shown."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    enabled: bool | None = None
    url: Address | None = None


class TestOut(BaseModel):
    ok: bool
    message: str
    destination: DestinationOut


def _invalid(*location: str, message: str) -> dict[str, object]:
    return {"type": "value_error", "loc": ["body", *location], "msg": message}


def _out(row: AlertDestination, *, has_address: bool) -> DestinationOut:
    return DestinationOut(
        id=row.id,
        kind="discord",
        name=row.name,
        enabled=row.enabled,
        host=discord.HOSTS[0],
        hint=row.hint,
        status=destinations.status_of(row, has_address=has_address),
        last_attempt_at=row.last_attempt_at,
        last_success_at=row.last_success_at,
        last_error=row.last_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _one(db: Session, row: AlertDestination) -> DestinationOut:
    return _out(row, has_address=row.id in destinations.with_address(db))


def _find(db: Session, destination_id: int) -> AlertDestination:
    row = db.get(AlertDestination, destination_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no such destination.")
    return row


@router.get("/destinations")
def list_destinations(db: Db) -> DestinationsOut:
    """The places alerts are sent, in the order they were added."""
    addressed = destinations.with_address(db)
    return DestinationsOut(
        items=[_out(row, has_address=row.id in addressed) for row in destinations.listing(db)],
        max_destinations=destinations.MAX_DESTINATIONS,
        hosts=list(discord.HOSTS),
    )


@router.post("/destinations", status_code=status.HTTP_201_CREATED)
def add_destination(
    body: DestinationIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
) -> DestinationOut:
    """Keeps a new destination, with its address sealed. It isn't tried yet: the test route does
    that."""
    if destinations.count(db) >= destinations.MAX_DESTINATIONS:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You can keep {destinations.MAX_DESTINATIONS} destinations. Remove one to add "
            "another.",
        )
    try:
        row = destinations.create(db, settings, body.name, body.url.get_secret_value(), utcnow())
    except InvalidWebhook as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, [_invalid("url", message=str(error))]
        ) from None
    except NameTaken as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, [_invalid("name", message=str(error))]
        ) from None
    record_audit(
        db,
        request,
        Action.ALERT_DESTINATION_ADDED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"destination": row.name, "kind": row.kind},
    )
    db.commit()
    return _out(row, has_address=True)


@router.patch("/destinations/{destination_id}")
def change_destination(
    destination_id: DestinationId,
    body: DestinationChange,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
) -> DestinationOut:
    """Renames a destination, turns it on or off, or replaces its address."""
    row = _find(db, destination_id)
    now = utcnow()
    changed: list[str] = []
    try:
        if body.name is not None and body.name != row.name:
            destinations.check_name(db, body.name, except_id=row.id)
            row.name = body.name
            changed.append("name")
    except NameTaken as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, [_invalid("name", message=str(error))]
        ) from None
    try:
        if body.url is not None:
            destinations.replace_address(db, settings, row, body.url.get_secret_value(), now)
            changed.append("address")
    except InvalidWebhook as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, [_invalid("url", message=str(error))]
        ) from None
    if body.enabled is not None and body.enabled != row.enabled:
        row.enabled = body.enabled
        changed.append("turned on" if body.enabled else "turned off")
    if changed:
        row.updated_at = now
        record_audit(
            db,
            request,
            Action.ALERT_DESTINATION_CHANGED,
            Outcome.SUCCESS,
            user=auth.user,
            detail={"destination": row.name, "changed": ", ".join(changed)},
        )
    db.commit()
    return _one(db, row)


@router.delete("/destinations/{destination_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_destination(
    destination_id: DestinationId,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> Response:
    """Forgets a destination and its address."""
    row = _find(db, destination_id)
    name = row.name
    destinations.forget(db, row)
    record_audit(
        db,
        request,
        Action.ALERT_DESTINATION_REMOVED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"destination": name},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/destinations/{destination_id}/test")
def test_destination(
    destination_id: DestinationId,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
    recorder: RecorderDep,
) -> TestOut:
    """Sends a real test message and keeps how it went. It goes even when the destination is turned
    off, because the owner asked for it."""
    row = _find(db, destination_id)
    now = utcnow()
    sent: discord.Sent | str
    try:
        webhook = destinations.open_webhook(db, settings, row)
        sent = anyio.from_thread.run(
            lambda: discord.send(
                webhook,
                discord.check_message(row.name, now),
                connection=f"destination-{row.id}",
                recorder=recorder,
                policy=request.app.state.alert_policy,
                origin=request.app.state.alert_origin,
            )
        )
    except Unusable as problem:
        sent = str(problem)
    destinations.record_attempt(row, sent, now)
    ok = not isinstance(sent, str) and sent.ok
    record_audit(
        db,
        request,
        Action.ALERT_DESTINATION_TESTED,
        Outcome.SUCCESS if ok else Outcome.FAILURE,
        user=auth.user,
        detail={"destination": row.name},
    )
    db.commit()
    message = "The test message was sent. Look for it in the channel."
    if not ok:
        problem = sent if isinstance(sent, str) else sent.problem
        message = problem or "The message didn't get through."
    return TestOut(ok=ok, message=message, destination=_one(db, row))
