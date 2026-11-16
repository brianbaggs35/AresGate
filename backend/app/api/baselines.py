"""What AresGate learned is normal on this network: the usual traffic of each interface by hour
of the day, and the places each device usually talks to. For someone signed in. The owner can
correct it: say a place is expected, or forget it. What is read is put together in
app/baselines/report.py."""

from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.baselines import destinations, report, traffic
from app.models import utcnow

router = APIRouter(prefix="/baselines", tags=["baselines"], dependencies=[Depends(signed_in)])


class HourOut(BaseModel):
    """What is usual for an hour of the day (UTC), in bytes."""

    hour: int
    median: float
    spread: float
    samples: int


class DeviationOut(BaseModel):
    at: AwareDatetime
    summary: str
    observed: float
    usual: float
    severity: int


class SeriesOut(BaseModel):
    interface: str | None
    # What the owner calls the interface, once they have placed it.
    name: str | None
    direction: str
    hours: list[HourOut]
    learned_at: AwareDatetime | None
    samples: int
    deviations: list[DeviationOut]


class InterfacesOut(BaseModel):
    series: list[SeriesOut]
    # Whether any interface counter is collected at all.
    counted: bool
    # What is needed before an hour is learned, so an empty page can say how long it takes.
    weeks: int
    min_hours: int


class TalkerOut(BaseModel):
    address: str
    name: str | None
    places: int
    expected: int
    hits: int
    learning_since: AwareDatetime
    last_seen_at: AwareDatetime
    judged: bool


class TalkersOut(BaseModel):
    items: list[TalkerOut]
    total: int
    # What a device needs before a new place of its is reported: days watched and places known.
    watched_days: int
    min_places: int
    # How long a place that is not expected is kept after the device was last there.
    forget_days: int


class PlaceOut(BaseModel):
    network: str
    port: int
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime
    hits: int
    expected: bool


class PlacesOut(BaseModel):
    address: str
    name: str | None
    places: list[PlaceOut]


class PlaceIn(BaseModel):
    """A place, and whether it is expected."""

    model_config = ConfigDict(extra="forbid")

    network: str = Field(max_length=64)
    port: int = Field(ge=0, le=65_535)
    expected: bool = True


class ForgetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    network: str = Field(max_length=64)
    port: int = Field(ge=0, le=65_535)


@router.get("/interfaces")
def get_interfaces(db: Db) -> InterfacesOut:
    """The usual traffic of each interface in each direction, by hour of the day, with the hours
    that were far above it."""
    found = report.interfaces(db, utcnow())
    return InterfacesOut(
        series=[
            SeriesOut(
                interface=item.interface,
                name=item.name,
                direction=item.direction,
                hours=[HourOut(**hour.__dict__) for hour in item.hours],
                learned_at=item.learned_at,
                samples=item.samples,
                deviations=[DeviationOut(**deviation.__dict__) for deviation in item.deviations],
            )
            for item in found.series
        ],
        counted=found.counted,
        weeks=int(traffic.WINDOW.days // 7),
        min_hours=traffic.MIN_HOURS,
    )


@router.get("/devices")
def get_devices(db: Db) -> TalkersOut:
    """The devices that places are known for."""
    found = report.talkers(db, utcnow())
    return TalkersOut(
        items=[
            TalkerOut(
                address=str(item.address),
                name=item.name,
                places=item.places,
                expected=item.expected,
                hits=item.hits,
                learning_since=item.learning_since,
                last_seen_at=item.last_seen_at,
                judged=item.judged,
            )
            for item in found.items
        ],
        total=found.total,
        watched_days=destinations.WATCHED_FOR.days,
        min_places=destinations.MIN_PLACES,
        forget_days=destinations.FORGET_AFTER.days,
    )


def _client(address: str) -> IPv4Address | IPv6Address:
    try:
        return ip_address(address)
    except ValueError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such device.") from error


def _place(network: str, port: int) -> tuple[destinations.Network, int]:
    try:
        return report.place_key(network, port)
    except report.BadPlace as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.get("/devices/{address}")
def get_places(address: str, db: Db) -> PlacesOut:
    """The places a device talks to, the expected ones first, then the most visited."""
    client = _client(address)
    found = report.places(db, client)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nothing is known of where it talks to.")
    return PlacesOut(
        address=str(client),
        name=report.name_of(db, client),
        places=[PlaceOut(**place.__dict__) for place in found],
    )


@router.put("/devices/{address}/places")
def set_place(
    address: str,
    body: PlaceIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> PlaceOut:
    """Says a place is expected for a device, or takes that off. A place never learned is made,
    so where a device is yet to go can be expected too."""
    client = _client(address)
    network, port = _place(body.network, body.port)
    made = report.mark(db, client, network, port, expected=body.expected, now=utcnow())
    if made is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That place is not known.")
    record_audit(
        db,
        request,
        Action.BASELINE_PLACE_EXPECTED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={
            "address": str(client),
            "network": str(network),
            "port": port,
            "expected": body.expected,
            "made": made,
        },
    )
    db.commit()
    return next(
        PlaceOut(**place.__dict__)
        for place in report.places(db, client)
        if (place.network, place.port) == (str(network), port)
    )


@router.post("/devices/{address}/forget", status_code=status.HTTP_204_NO_CONTENT)
def forget_place(
    address: str,
    body: ForgetIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> Response:
    """Forgets a place a device talked to, so the next time it goes there is new again."""
    client = _client(address)
    network, port = _place(body.network, body.port)
    if not report.forget(db, client, network, port):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That place is not known.")
    record_audit(
        db,
        request,
        Action.BASELINE_PLACE_FORGOTTEN,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"address": str(client), "network": str(network), "port": port},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
