"""The threat intelligence AresGate keeps that is not about an address, a domain or a web address:
what NVD says of the CVEs that incidents name, and what Fingerbank says each device is. Both are
asked about in the background, within the limits of their own services, so this only reads what
is kept: it asks nothing of NVD or Fingerbank and counts toward no limit. The Threat intelligence
page shows them as the tabs for vulnerabilities and for devices."""

from datetime import date, datetime
from typing import Annotated, Any, Final, Literal, get_args
from typing import cast as as_type

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import ColumnElement, String, Text, case, cast, func, or_, select

from app.api.deps import Db, signed_in
from app.models import Device, DeviceAddress, DeviceIdentity, NvdCve
from app.nvd import lookup as nvd

router = APIRouter(prefix="/threat-intel", tags=["threat-intel"], dependencies=[Depends(signed_in)])

MAX_PAGE: Final = 100
MAX_TEXT: Final = 200

type Rating = Literal["critical", "high", "medium", "low", "unrated"]
type State = Literal["identified", "unknown", "private"]
RATINGS: Final[tuple[str, ...]] = get_args(Rating.__value__)
STATES: Final[tuple[str, ...]] = get_args(State.__value__)


def _escaped(text: str) -> str:
    """The text as a pattern that matches it anywhere, with nothing in it read as a wildcard."""
    cleaned = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{cleaned.lower()}%"


def _like(column: Any, pattern: str) -> ColumnElement[bool]:
    return func.lower(func.coalesce(column, "")).like(pattern, escape="\\")


class CveOut(BaseModel):
    """What NVD said of one CVE, and when AresGate asked."""

    cve_id: str
    # ``unknown`` where NVD has no record of it yet (a CVE published a moment ago).
    state: Literal["found", "unknown"]
    checked_at: AwareDatetime
    status: str | None
    published_at: AwareDatetime | None
    modified_at: AwareDatetime | None
    cvss_version: str | None
    score: float | None
    # What the score comes to, or ``unrated`` while it has none.
    rating: Rating
    vector: str | None
    description: str | None
    weaknesses: list[str]
    # Whether CISA lists it as exploited in the wild, and what it says of that.
    exploited: bool
    exploited_on: date | None
    action_due: date | None
    required_action: str | None
    kev_name: str | None
    link: str


class CveCountsOut(BaseModel):
    critical: int
    high: int
    medium: int
    low: int
    unrated: int
    exploited: int


class CvesOut(BaseModel):
    # What NVD asks a service that shows its data to say.
    notice: str
    # How many match, of which ``items`` is one page.
    total: int
    # How many match the text of each rating, whichever rating was asked for.
    counts: CveCountsOut
    items: list[CveOut]


def _rated(severity: str | None) -> Rating:
    # The rating NVD gives is one of NONE to CRITICAL; NONE (a score of 0) says as little as none.
    lowered = (severity or "").lower()
    return as_type("Rating", lowered) if lowered in RATINGS[:4] else "unrated"


def _cve(row: NvdCve) -> CveOut:
    return CveOut(
        cve_id=row.cve_id,
        state=as_type("Literal['found', 'unknown']", row.state),
        checked_at=row.checked_at,
        status=row.status,
        published_at=row.published_at,
        modified_at=row.modified_at,
        cvss_version=row.cvss_version,
        score=row.score,
        rating=_rated(row.severity),
        vector=row.vector,
        description=row.description,
        weaknesses=list(row.weaknesses),
        exploited=row.exploited,
        exploited_on=row.exploited_on,
        action_due=row.action_due,
        required_action=row.required_action,
        kev_name=row.kev_name,
        link=nvd.link_of(row.cve_id),
    )


@router.get("/cves")
def list_cves(
    db: Db,
    q: Annotated[
        str,
        Query(max_length=MAX_TEXT, description="Part of an identifier, a description or a CWE."),
    ] = "",
    rating: Annotated[Rating | None, Query(description="Only this rating.")] = None,
    exploited: Annotated[bool, Query(description="Only those CISA lists as exploited.")] = False,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 25,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> CvesOut:
    """The CVEs NVD has answered about, the ones asked about most recently first."""
    matching: list[ColumnElement[bool]] = []
    if q.strip():
        pattern = _escaped(q.strip())
        matching.append(
            or_(
                _like(NvdCve.cve_id, pattern),
                _like(NvdCve.description, pattern),
                _like(NvdCve.kev_name, pattern),
                _like(cast(NvdCve.weaknesses, Text), pattern),
            )
        )
    named = case(
        (NvdCve.severity.in_(["CRITICAL", "HIGH", "MEDIUM", "LOW"]), func.lower(NvdCve.severity)),
        else_="unrated",
    )
    counted = {
        row[0]: row[1]
        for row in db.execute(select(named, func.count()).where(*matching).group_by(named))
    }
    flagged = (
        db.scalar(
            select(func.count()).select_from(NvdCve).where(*matching, NvdCve.exploited.is_(True))
        )
        or 0
    )
    counts = CveCountsOut(
        critical=counted.get("critical", 0),
        high=counted.get("high", 0),
        medium=counted.get("medium", 0),
        low=counted.get("low", 0),
        unrated=counted.get("unrated", 0),
        exploited=flagged,
    )
    if rating is not None:
        matching.append(named == rating)
    if exploited:
        matching.append(NvdCve.exploited.is_(True))
    total = db.scalar(select(func.count()).select_from(NvdCve).where(*matching)) or 0
    rows = db.scalars(
        select(NvdCve)
        .where(*matching)
        .order_by(NvdCve.checked_at.desc(), NvdCve.cve_id)
        .limit(limit)
        .offset(offset)
    ).all()
    return CvesOut(notice=nvd.NOTICE, total=total, counts=counts, items=[_cve(row) for row in rows])


class DeviceIntelOut(BaseModel):
    """What Fingerbank said a device is, with what AresGate knows of the device itself."""

    device_id: int
    mac: str
    hostname: str | None
    # Who made its network card, from its hardware address.
    vendor: str | None
    # The address it was last listed with.
    address: str | None
    state: State
    # Why it was looked up: it is one of the owner's assets, or is in an incident.
    reason: Literal["asset", "incident"]
    name: str | None
    path: str | None
    manufacturer: str | None
    operating_system: str | None
    score: int | None
    checked_at: AwareDatetime
    last_seen_at: AwareDatetime


class DeviceCountsOut(BaseModel):
    identified: int
    unknown: int
    private: int


class DevicesIntelOut(BaseModel):
    total: int
    counts: DeviceCountsOut
    items: list[DeviceIntelOut]


@router.get("/devices")
def list_device_intel(
    db: Db,
    q: Annotated[
        str,
        Query(max_length=MAX_TEXT, description="Part of what it is, its name, maker or address."),
    ] = "",
    state: Annotated[State | None, Query(description="Only this state.")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 25,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> DevicesIntelOut:
    """What Fingerbank made of each device it was asked about, the most recently asked first. A
    device whose hardware address is private is listed without having been asked."""
    last_address = (
        select(func.host(DeviceAddress.address))
        .where(DeviceAddress.device_id == Device.id)
        .order_by(DeviceAddress.last_seen_at.desc())
        .limit(1)
        .correlate(Device)
        .scalar_subquery()
    )
    matching: list[ColumnElement[bool]] = []
    if q.strip():
        pattern = _escaped(q.strip())
        matching.append(
            or_(
                _like(DeviceIdentity.name, pattern),
                _like(DeviceIdentity.path, pattern),
                _like(DeviceIdentity.manufacturer, pattern),
                _like(DeviceIdentity.operating_system, pattern),
                _like(Device.hostname, pattern),
                _like(Device.vendor, pattern),
                _like(cast(Device.mac, String), pattern),
                _like(last_address, pattern),
            )
        )
    counted = {
        row[0]: row[1]
        for row in db.execute(
            select(DeviceIdentity.state, func.count())
            .join(Device, Device.id == DeviceIdentity.device_id)
            .where(*matching)
            .group_by(DeviceIdentity.state)
        )
    }
    counts = DeviceCountsOut(
        identified=counted.get("identified", 0),
        unknown=counted.get("unknown", 0),
        private=counted.get("private", 0),
    )
    if state is not None:
        matching.append(DeviceIdentity.state == state)
    total = (
        db.scalar(
            select(func.count())
            .select_from(DeviceIdentity)
            .join(Device, Device.id == DeviceIdentity.device_id)
            .where(*matching)
        )
        or 0
    )
    rows = db.execute(
        select(DeviceIdentity, Device, last_address)
        .join(Device, Device.id == DeviceIdentity.device_id)
        .where(*matching)
        .order_by(DeviceIdentity.checked_at.desc(), Device.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return DevicesIntelOut(
        total=total,
        counts=counts,
        items=[_device(identity, device, address) for identity, device, address in rows],
    )


def _device(identity: DeviceIdentity, device: Device, address: str | None) -> DeviceIntelOut:
    checked: datetime = identity.checked_at
    return DeviceIntelOut(
        device_id=device.id,
        mac=str(device.mac),
        hostname=device.hostname,
        vendor=device.vendor,
        address=address,
        state=as_type("State", identity.state),
        reason=as_type("Literal['asset', 'incident']", identity.reason),
        name=identity.name,
        path=identity.path,
        manufacturer=identity.manufacturer,
        operating_system=identity.operating_system,
        score=identity.score,
        checked_at=checked,
        last_seen_at=device.last_seen_at,
    )
