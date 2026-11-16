"""A list as a file: what a page shows, row for row, as CSV or JSON, with the columns named in
words and the times in the owner's time zone. Everything written was sent by someone the program
heard from, so a cell a spreadsheet would read as a formula is quoted."""

import csv
import io
import json
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from datetime import datetime
from typing import Final, Literal
from zoneinfo import ZoneInfo

from fastapi.responses import StreamingResponse

Format = Literal["csv", "json"]
Value = str | int | float | bool | datetime | Sequence[str] | None
Row = Mapping[str, Value]

# The most rows a list file holds, and how many are fetched at a time to make it.
MAX_ROWS: Final = 10_000
PAGE: Final = 100

# A spreadsheet reads a cell that begins with one of these as a formula.
FORMULA: Final = ("=", "+", "-", "@", "\t", "\r")


def neutral(text: str) -> str:
    """The text as it is written in a cell: quoted if a spreadsheet would run it."""
    return f"'{text}" if text.startswith(FORMULA) else text


def zone_of(name: str | None) -> ZoneInfo:
    """The owner's time zone, or UTC where none was said or it is not one."""
    try:
        return ZoneInfo(name) if name else ZoneInfo("UTC")
    except KeyError, ValueError, OSError:
        return ZoneInfo("UTC")


def _plain(value: Value, zone: ZoneInfo) -> str | int | float | bool:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(zone).isoformat(timespec="seconds")
    if isinstance(value, str):
        return neutral(value)
    if isinstance(value, (int, float, bool)):
        return value
    return neutral("; ".join(value))


def rows_of[T](
    fetch: Callable[[int, int], tuple[Sequence[T], int]], limit: int | None = None
) -> Iterator[T]:
    """Every row a list holds, a page at a time, up to ``limit`` (the most a file holds if none is
    given). ``fetch`` takes the offset and how many to ask for, and gives those and how many there
    are in all. The first page is read now, so a filter that cannot be understood is refused
    before a file is begun."""
    most = MAX_ROWS if limit is None else limit
    first, total = fetch(0, min(PAGE, most))
    return _pages(fetch, first, total, most)


def _pages[T](
    fetch: Callable[[int, int], tuple[Sequence[T], int]], first: Sequence[T], total: int, most: int
) -> Iterator[T]:
    found = first
    offset = 0
    while True:
        yield from found
        offset += len(found)
        if not found or offset >= total or offset >= most:
            return
        found, total = fetch(offset, min(PAGE, most - offset))


def _as_csv(columns: Sequence[str], rows: Iterable[Row], zone: ZoneInfo) -> Iterator[str]:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(columns)
    yield out.getvalue()
    for row in rows:
        out.seek(0)
        out.truncate()
        writer.writerow([_plain(row.get(name), zone) for name in columns])
        yield out.getvalue()


def _as_json(columns: Sequence[str], rows: Iterable[Row], zone: ZoneInfo) -> Iterator[str]:
    yield "["
    first = True
    for row in rows:
        shown = {name: _plain(row.get(name), zone) for name in columns}
        yield ("\n" if first else ",\n") + json.dumps(shown, separators=(",", ":"))
        first = False
    yield "\n]\n"


def download(
    name: str,
    format: Format,
    columns: Sequence[str],
    rows: Iterable[Row],
    *,
    zone: ZoneInfo,
    stamp: datetime,
) -> StreamingResponse:
    """The rows as a file to save, sent as they are made."""
    body = _as_csv(columns, rows, zone) if format == "csv" else _as_json(columns, rows, zone)
    return StreamingResponse(
        body,
        media_type="text/csv; charset=utf-8" if format == "csv" else "application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="aresgate-{name}-{stamp:%Y%m%d-%H%M%S}.{format}"'
            ),
            "Cache-Control": "no-store",
        },
    )
