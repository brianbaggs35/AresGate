"""The lists as files: the incidents, the alerts that were sent, the devices and the assets, as
CSV or JSON, of exactly what the page's filters and order show, not only the page that is loaded.
Each takes what its list takes, so the page can hand over its own query; this router is included
before the lists' own so that ``export`` is not read as an incident, address or asset."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import AwareDatetime, IPvAnyAddress

from app import exporting
from app.api import alerts, assets, devices, incidents
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.assets.search import Sort as AssetSort
from app.audit import Action, Outcome
from app.devices.seen import Direction, Scope
from app.devices.seen import Sort as DeviceSort
from app.exporting import Format, Row
from app.incidents import rules
from app.incidents.queries import Order
from app.models import utcnow

router = APIRouter(tags=["exports"], dependencies=[Depends(signed_in)])

# The lists that can be exported, as the audit trail names them.
ListName = Literal["incidents", "alerts", "devices", "assets"]

Zone = Annotated[
    str | None,
    Query(description="The time zone the times are written in, such as America/Halifax."),
]
Words = Annotated[str, Query(max_length=500)]
# The column names the lists share.
FIRST_SEEN = "First seen"
LAST_SEEN = "Last seen"


@dataclass(frozen=True)
class Asker:
    """Who is asking for a file, and the request it came in, which the audit trail records."""

    request: Request
    auth: SignedIn


def asker(request: Request, auth: Annotated[SignedIn, Depends(signed_in)]) -> Asker:
    return Asker(request, auth)


By = Annotated[Asker, Depends(asker)]


def _audit(
    db: Db,
    by: Asker,
    name: ListName,
    format: Format,
    detail: dict[str, Any],
) -> None:
    record_audit(
        db,
        by.request,
        Action.LIST_EXPORTED,
        Outcome.SUCCESS,
        user=by.auth.user,
        detail={"list": name, "format": format, **detail},
    )
    db.commit()


def _file(
    name: ListName, format: Format, columns: tuple[str, ...], rows: Iterator[Row], zone: str | None
) -> StreamingResponse:
    return exporting.download(
        name, format, columns, rows, zone=exporting.zone_of(zone), stamp=utcnow()
    )


# ---------------------------------------------------------------------------------------------
# Incidents

INCIDENT_COLUMNS = (
    "ID",
    "Title",
    "Subject",
    "Status",
    "Severity",
    "Confidence",
    "Confidence level",
    "Verdict",
    "Activity",
    FIRST_SEEN,
    LAST_SEEN,
    "Signals",
    "Programs",
    "Addresses",
    "Response",
)


def _incident_row(item: incidents.IncidentOut) -> Row:
    return {
        "ID": item.id,
        "Title": item.title,
        "Subject": item.subject,
        "Status": item.status,
        "Severity": item.severity,
        "Confidence": item.confidence,
        "Confidence level": item.confidence_level,
        "Verdict": item.verdict,
        "Activity": [str(kind) for kind in item.activities],
        FIRST_SEEN: item.first_seen_at,
        LAST_SEEN: item.last_seen_at,
        "Signals": item.signal_count,
        "Programs": [program.name for program in item.sources],
        "Addresses": item.addresses,
        "Response": item.response.label,
    }


@router.get("/incidents/export")
def export_incidents(
    db: Db,
    by: By,
    scope: Annotated[incidents.Narrowed, Depends(incidents.narrowed)],
    format: Annotated[Format, Query()] = "csv",
    state: Annotated[list[incidents.Status] | None, Query(alias="status")] = None,
    verdict: Annotated[list[incidents.VerdictFilter] | None, Query()] = None,
    min_severity: Annotated[incidents.SeverityName | None, Query()] = None,
    min_confidence: Annotated[int, Query(ge=0, le=rules.MAX_CONFIDENCE)] = 0,
    address: Annotated[IPvAnyAddress | None, Query()] = None,
    since: Annotated[AwareDatetime | None, Query()] = None,
    q: Words = "",
    tz: Zone = None,
    order: Annotated[Order, Query()] = "recent",
) -> StreamingResponse:
    """The incidents the filters and the order show, up to 10,000 of them."""
    _audit(db, by, "incidents", format, {"search": q[:200], "limit": exporting.MAX_ROWS})

    def fetch(offset: int, count: int) -> tuple[list[incidents.IncidentOut], int]:
        page = incidents.list_incidents(
            db,
            scope,
            state=state,
            verdict=verdict,
            min_severity=min_severity,
            min_confidence=min_confidence,
            address=address,
            since=since,
            q=q,
            tz=tz,
            limit=count,
            offset=offset,
            order=order,
        )
        return page.items, page.total

    rows = (_incident_row(item) for item in exporting.rows_of(fetch))
    return _file("incidents", format, INCIDENT_COLUMNS, rows, tz)


# ---------------------------------------------------------------------------------------------
# Devices

DEVICE_COLUMNS = (
    "Address",
    "Scope",
    "Name",
    "Asset",
    "Connections to it",
    "Connections it made",
    FIRST_SEEN,
    LAST_SEEN,
    "Ports",
    "Protocols",
    "Incidents this week",
    "Worst severity",
)


def _device_row(item: devices.DeviceOut) -> Row:
    return {
        "Address": item.address,
        "Scope": item.scope,
        "Name": item.name,
        "Asset": item.asset.name if item.asset else None,
        "Connections to it": item.incoming,
        "Connections it made": item.outgoing,
        FIRST_SEEN: item.first_seen_at,
        LAST_SEEN: item.last_seen_at,
        "Ports": [str(port.port) for port in item.ports],
        "Protocols": item.protocols,
        "Incidents this week": item.incidents.count if item.incidents else 0,
        "Worst severity": item.incidents.worst if item.incidents else None,
    }


@router.get("/devices/export")
def export_devices(
    db: Db,
    by: By,
    format: Annotated[Format, Query()] = "csv",
    q: Annotated[str, Query(max_length=devices.MAX_SEARCH)] = "",
    scope: Annotated[Scope | None, Query()] = None,
    direction: Annotated[Direction | None, Query()] = None,
    flagged: Annotated[bool, Query()] = False,
    sort: Annotated[DeviceSort, Query()] = "recent",
    tz: Zone = None,
) -> StreamingResponse:
    """The devices the filters and the order show, up to 10,000 of them."""
    _audit(db, by, "devices", format, {"search": q[:200], "limit": exporting.MAX_ROWS})

    def fetch(offset: int, count: int) -> tuple[list[devices.DeviceOut], int]:
        page = devices.list_devices(
            db,
            q=q,
            scope=scope,
            direction=direction,
            flagged=flagged,
            sort=sort,
            limit=count,
            offset=offset,
        )
        return page.items, page.total

    rows = (_device_row(item) for item in exporting.rows_of(fetch))
    return _file("devices", format, DEVICE_COLUMNS, rows, tz)


# ---------------------------------------------------------------------------------------------
# Assets

ASSET_COLUMNS = (
    "Name",
    "Kind",
    "Host name",
    "Maker",
    "Hardware address",
    "Addresses",
    "Status",
    FIRST_SEEN,
    LAST_SEEN,
    "New",
    "Listed by",
    "Kind you gave it",
)


def _asset_row(item: assets.AssetOut) -> Row:
    return {
        "Name": item.name,
        "Kind": item.kind,
        "Host name": item.hostname,
        "Maker": item.vendor,
        "Hardware address": item.mac,
        "Addresses": item.addresses,
        "Status": item.status,
        FIRST_SEEN: item.first_seen_at,
        LAST_SEEN: item.last_seen_at,
        "New": item.is_new,
        "Listed by": list(dict.fromkeys(listing.source_name for listing in item.listings)),
        "Kind you gave it": item.profile.kind_label if item.profile else None,
    }


@router.get("/assets/export")
def export_assets(
    db: Db,
    by: By,
    format: Annotated[Format, Query()] = "csv",
    q: Annotated[str, Query(max_length=assets.MAX_SEARCH)] = "",
    state: Annotated[assets.StatusName | None, Query(alias="status")] = None,
    source: Annotated[list[str] | None, Query(max_length=assets.MAX_SOURCES)] = None,
    interface: Annotated[int | None, Query(ge=1, le=2**63 - 1)] = None,
    new: Annotated[bool, Query()] = False,
    unidentified: Annotated[bool, Query()] = False,
    kind: Annotated[str | None, Query(pattern=assets.KIND_PATTERN)] = None,
    sort: Annotated[AssetSort, Query()] = "recent",
    tz: Zone = None,
) -> StreamingResponse:
    """The assets the filters and the order show, up to 10,000 of them."""
    _audit(db, by, "assets", format, {"search": q[:200], "limit": exporting.MAX_ROWS})

    def fetch(offset: int, count: int) -> tuple[list[assets.AssetOut], int]:
        page = assets.list_assets(
            db,
            q=q,
            state=state,
            source=source,
            interface=interface,
            new=new,
            unidentified=unidentified,
            kind=kind,
            sort=sort,
            limit=count,
            offset=offset,
        )
        return page.items, page.total

    rows = (_asset_row(item) for item in exporting.rows_of(fetch))
    return _file("assets", format, ASSET_COLUMNS, rows, tz)


# ---------------------------------------------------------------------------------------------
# Alerts: the messages that were sent

ALERT_COLUMNS = (
    "ID",
    "Destination",
    "Kind",
    "Reason",
    "State",
    "Title",
    "Severity",
    "Confidence",
    "Incidents covered",
    "Attempts",
    "Created",
    "Due",
    "Sent",
    "Note",
)


def _alert_row(item: alerts.DeliveryOut) -> Row:
    return {
        "ID": item.id,
        "Destination": item.destination,
        "Kind": item.kind,
        "Reason": item.reason,
        "State": item.state,
        "Title": item.title,
        "Severity": item.severity,
        "Confidence": item.confidence,
        "Incidents covered": item.covers,
        "Attempts": item.attempts,
        "Created": item.created_at,
        "Due": item.due_at,
        "Sent": item.sent_at,
        "Note": item.note,
    }


def _deliveries(
    db: Db, destination_id: int | None, state: alerts.DeliveryState | None
) -> Iterator[Row]:
    before: int | None = None
    sent = 0
    while sent < exporting.MAX_ROWS:
        page = alerts.list_deliveries(
            db,
            destination_id=destination_id,
            state=state,
            before=before,
            limit=min(exporting.PAGE, exporting.MAX_ROWS - sent),
        )
        for item in page.items:
            yield _alert_row(item)
        sent += len(page.items)
        before = page.next_before
        if before is None:
            return


@router.get("/alerts/deliveries/export")
def export_deliveries(
    db: Db,
    by: By,
    format: Annotated[Format, Query()] = "csv",
    destination_id: Annotated[int | None, Query(ge=1, le=2**63 - 1)] = None,
    state: alerts.DeliveryState | None = None,
    tz: Zone = None,
) -> StreamingResponse:
    """The messages the filters show, the newest first, up to 10,000 of them."""
    _audit(db, by, "alerts", format, {"limit": exporting.MAX_ROWS})
    return _file("alerts", format, ALERT_COLUMNS, _deliveries(db, destination_id, state), tz)
