"""The logs: every event AresGate collected, as each integration delivered it. For someone signed
in. The events are read newest first a page at a time, found again by the cursor of the last
one on the page, and one is read whole with the program's own record of it."""

import csv
import io
import json
from collections.abc import Iterator
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import func, select

from app.api import asking
from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.api.incidents import SourceCount, Status, TermOut
from app.audit import Action, Outcome
from app.events import queries, search
from app.events.event import Severity
from app.incidents import rules
from app.models import Event, Incident, utcnow

router = APIRouter(prefix="/logs", tags=["logs"], dependencies=[Depends(signed_in)])

MAX_PAGE = 200
# The most events one export holds, which is a few minutes of reading for a person who opens it.
MAX_EXPORT = 50_000
# How long an export may read, a search having five seconds: it is not waited for on a page.
EXPORT_TIMEOUT_MS = 60_000
Cursor = Annotated[str, Query(pattern=queries.CURSOR_PATTERN)]


class LogOut(BaseModel):
    """An event as the list shows it."""

    # Where it is in the order of the logs, which finds it again.
    cursor: str
    id: int
    at: AwareDatetime
    received_at: AwareDatetime
    source: str
    source_name: str
    connection: str
    kind: str
    severity: SeverityName
    summary: str
    signature: str | None
    src_address: str | None
    src_port: int | None
    dst_address: str | None
    dst_port: int | None
    protocol: str | None
    # Whether the program's own record was kept, which the detail has.
    has_raw: bool


class IncidentLink(BaseModel):
    """The incident an event was filed into."""

    id: int
    title: str
    status: Status
    severity: SeverityName


class LogDetail(LogOut):
    raw: dict[str, Any] | None
    incident: IncidentLink | None


class KindCount(BaseModel):
    kind: str
    count: int


class LogFacets(BaseModel):
    severity: dict[SeverityName, int]
    sources: list[SourceCount]
    kinds: list[KindCount]


class VolumeOut(BaseModel):
    """How many events there were in each stretch of time: ``counts[bar]`` is a count for each
    severity from info to critical, and the first bar begins at ``start``."""

    start: AwareDatetime
    seconds: int
    counts: list[list[int]]


class SummaryOut(BaseModel):
    """How the newest events that match are spread, whichever page of them is shown."""

    matched: int
    # Whether there were more than it read, the oldest ones.
    capped: bool
    facets: LogFacets
    volume: VolumeOut | None


class LogPage(BaseModel):
    items: list[LogOut]
    # Whether there are more past the end of the page (older), or, when the page was asked for
    # ``after`` a cursor, newer than it.
    more: bool
    terms: list[TermOut]
    # Left out when it was not asked for, since it is the same for every page of a search.
    summary: SummaryOut | None


def _log(row: queries.Row) -> LogOut:
    event = row.event
    return LogOut(
        cursor=str(queries.Cursor.of(event)),
        id=event.id,
        at=event.occurred_at,
        received_at=event.received_at,
        source=event.source,
        source_name=rules.name_of(event.source),
        connection=event.connection,
        kind=event.kind,
        severity=SEVERITY_NAMES[Severity(event.severity)],
        summary=event.summary,
        signature=event.signature,
        src_address=str(event.src_address) if event.src_address else None,
        src_port=event.src_port,
        dst_address=str(event.dst_address) if event.dst_address else None,
        dst_port=event.dst_port,
        protocol=event.protocol,
        has_raw=row.has_raw,
    )


def _summary(found: queries.Summary) -> SummaryOut:
    volume = found.volume
    return SummaryOut(
        matched=found.matched,
        capped=found.capped,
        facets=LogFacets(
            severity={name: found.severity.get(level, 0) for level, name in SEVERITY_NAMES.items()},
            sources=[
                SourceCount(key=key, name=rules.name_of(key), count=count)
                for key, count in sorted(
                    found.sources.items(), key=lambda pair: (-pair[1], pair[0])
                )
            ],
            kinds=[
                KindCount(kind=kind, count=count)
                for kind, count in sorted(found.kinds.items(), key=lambda pair: (-pair[1], pair[0]))
            ],
        ),
        volume=VolumeOut(start=volume.start, seconds=volume.seconds, counts=volume.counts)
        if volume
        else None,
    )


def _terms(asked: search.Search) -> list[TermOut]:
    return [
        TermOut(
            field=term.field, label=term.label, negated=term.negated, start=term.start, end=term.end
        )
        for term in asked.terms
    ]


def _ask(db: Db, text: str, zone: str | None) -> search.Search:
    return asking.ask(db, text, zone, search.parse)


@router.get("")
def list_logs(
    db: Db,
    q: Annotated[
        str,
        Query(
            description="A search in words, such as: severity>=high source:opnsense -port:22 "
            "since:1h. Everything it says has to be true."
        ),
    ] = "",
    tz: Annotated[
        str | None, Query(description="The time zone the person is in, such as America/Halifax.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 100,
    before: Annotated[Cursor | None, Query(description="Only older than this event.")] = None,
    after: Annotated[
        Cursor | None,
        Query(description="Only newer than this event, the oldest first up to limit."),
    ] = None,
    summary: Annotated[
        bool, Query(description="Also say how the events found are spread. Once is enough.")
    ] = True,
) -> LogPage:
    """Events, the newest first."""
    if before is not None and after is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Ask for older events or newer ones, not both."
        )
    asked = _ask(db, q, tz)
    where = asked.conditions()
    with asking.in_time(db):
        found = queries.page(
            db,
            where=where,
            limit=limit,
            before=queries.Cursor.parse(before) if before else None,
            after=queries.Cursor.parse(after) if after else None,
        )
        spread = queries.summary(db, where=where) if summary else None
    return LogPage(
        items=[_log(row) for row in found.rows],
        more=found.more,
        terms=_terms(asked),
        summary=_summary(spread) if spread else None,
    )


Format = Literal["csv", "json"]
_COLUMNS = (
    "time",
    "received",
    "source",
    "connection",
    "kind",
    "severity",
    "summary",
    "signature",
    "src_address",
    "src_port",
    "dst_address",
    "dst_port",
    "protocol",
)
# A spreadsheet reads a cell that begins with one of these as a formula, and what is in the logs
# was written by whoever the program heard from.
_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: object) -> str | int:
    if value is None:
        return ""
    if isinstance(value, int):
        return value
    text = str(value)
    return f"'{text}" if text.startswith(_FORMULA) else text


def _row(event: Event) -> dict[str, Any]:
    return {
        "time": event.occurred_at.isoformat(),
        "received": event.received_at.isoformat(),
        "source": event.source,
        "connection": event.connection,
        "kind": event.kind,
        "severity": SEVERITY_NAMES[Severity(event.severity)],
        "summary": event.summary,
        "signature": event.signature,
        "src_address": str(event.src_address) if event.src_address else None,
        "src_port": event.src_port,
        "dst_address": str(event.dst_address) if event.dst_address else None,
        "dst_port": event.dst_port,
        "protocol": event.protocol,
    }


def _as_csv(chunks: Iterator[list[Event]]) -> Iterator[str]:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(_COLUMNS)
    yield out.getvalue()
    for chunk in chunks:
        out.seek(0)
        out.truncate()
        for event in chunk:
            row = _row(event)
            writer.writerow([_cell(row[name]) for name in _COLUMNS])
        yield out.getvalue()


def _as_json(chunks: Iterator[list[Event]], *, raw: bool) -> Iterator[str]:
    yield "["
    first = True
    for chunk in chunks:
        for event in chunk:
            row = _row(event)
            if raw:
                row["raw"] = event.raw
            yield ("\n" if first else ",\n") + json.dumps(row, separators=(",", ":"))
            first = False
    yield "\n]\n"


@router.get("/export")
def export_logs(
    db: Db,
    request: Request,
    auth: Annotated[SignedIn, Depends(signed_in)],
    format: Annotated[Format, Query()] = "csv",  # the name people use
    q: Annotated[str, Query(description="What to export, searched for as in the list.")] = "",
    tz: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_EXPORT)] = MAX_EXPORT,
    raw: Annotated[
        bool, Query(description="Include the program's own record. Only JSON holds it.")
    ] = True,
) -> StreamingResponse:
    """The events that a search finds, as a file: the newest first, up to ``limit`` of them."""
    asked = _ask(db, q, tz)
    where = asked.conditions()
    keep_raw = raw and format == "json"
    record_audit(
        db,
        request,
        Action.LOGS_EXPORTED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"format": format, "search": q[:200], "limit": limit},
    )
    db.commit()
    # What follows is read as it is sent, so it has its own, longer, time.
    db.execute(select(func.set_config("statement_timeout", str(EXPORT_TIMEOUT_MS), True)))
    chunks = queries.export(db, where=where, limit=limit, raw=keep_raw)
    stamp = utcnow().strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        _as_csv(chunks) if format == "csv" else _as_json(chunks, raw=keep_raw),
        media_type="text/csv; charset=utf-8" if format == "csv" else "application/json",
        headers={
            "Content-Disposition": f'attachment; filename="aresgate-logs-{stamp}.{format}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{cursor}")
def get_log(
    db: Db,
    cursor: Annotated[str, Path(pattern=queries.CURSOR_PATTERN)],
) -> LogDetail:
    """One event whole, with the program's own record of it and the incident it was filed into."""
    event = queries.get(db, queries.Cursor.parse(cursor))
    if event is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "That event isn't there. It may have passed the time events are kept for.",
        )
    incident_id = queries.incident_of(db, event)
    incident = db.get(Incident, incident_id) if incident_id else None
    head = _log(queries.Row(event, event.raw is not None))
    return LogDetail(
        **head.model_dump(),
        raw=event.raw,
        incident=IncidentLink(
            id=incident.id,
            title=incident.title,
            status=cast(Status, incident.status),
            severity=SEVERITY_NAMES[Severity(incident.severity)],
        )
        if incident
        else None,
    )
