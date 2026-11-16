"""A list as a file: the columns in words, the times in the owner's zone, formulas quoted."""

import asyncio
import csv
import io
import json
from datetime import UTC, datetime
from typing import Any

from app import exporting


def body(response: Any) -> str:
    async def read() -> str:
        return "".join([chunk async for chunk in response.body_iterator])

    return asyncio.run(read())


def stamp() -> datetime:
    return datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


class TestACell:
    def test_text_a_spreadsheet_would_run_is_quoted(self) -> None:
        assert [exporting.neutral(text) for text in ("=1+1", "+1", "-1", "@SUM", "\tx", "\rx")] == [
            "'=1+1",
            "'+1",
            "'-1",
            "'@SUM",
            "'\tx",
            "'\rx",
        ]

    def test_other_text_is_left_alone(self) -> None:
        assert exporting.neutral("A scan") == "A scan"


class TestTheZone:
    def test_a_known_zone_is_used(self) -> None:
        assert exporting.zone_of("America/Halifax").key == "America/Halifax"

    def test_none_or_something_that_is_not_a_zone_is_utc(self) -> None:
        assert [exporting.zone_of(name).key for name in (None, "", "Nowhere/Land", "../x")] == [
            "UTC"
        ] * 4


class TestPaging:
    def test_every_row_is_fetched_a_page_at_a_time(self) -> None:
        asked: list[tuple[int, int]] = []

        def fetch(offset: int, count: int) -> tuple[list[int], int]:
            asked.append((offset, count))
            return list(range(offset, min(offset + count, 250))), 250

        assert list(exporting.rows_of(fetch)) == list(range(250))
        assert asked == [(0, 100), (100, 100), (200, 100)]

    def test_it_stops_at_the_limit(self) -> None:
        def fetch(offset: int, count: int) -> tuple[list[int], int]:
            return list(range(offset, offset + count)), 1000

        assert len(list(exporting.rows_of(fetch, limit=150))) == 150

    def test_it_stops_when_a_page_comes_back_empty(self) -> None:
        def fetch(offset: int, count: int) -> tuple[list[int], int]:
            return [], 5

        assert list(exporting.rows_of(fetch)) == []


COLUMNS = ("Name", "Seen", "Ports", "Count", "Nothing")
ROWS = [
    {
        "Name": "=cmd()",
        "Seen": datetime(2026, 11, 16, 15, 0, tzinfo=UTC),
        "Ports": ["22", "=80"],
        "Count": 3,
        "Nothing": None,
    }
]


class TestTheFile:
    def test_csv_has_the_names_in_words_and_the_times_in_the_zone(self) -> None:
        response = exporting.download(
            "things",
            "csv",
            COLUMNS,
            ROWS,
            zone=exporting.zone_of("America/Halifax"),
            stamp=stamp(),
        )

        assert response.media_type == "text/csv; charset=utf-8"
        assert response.headers["content-disposition"] == (
            'attachment; filename="aresgate-things-20261116-120000.csv"'
        )
        assert response.headers["cache-control"] == "no-store"
        table = list(csv.reader(io.StringIO(body(response))))
        assert table == [
            list(COLUMNS),
            ["'=cmd()", "2026-11-16T11:00:00-04:00", "22; =80", "3", ""],
        ]

    def test_json_has_the_same_columns(self) -> None:
        response = exporting.download(
            "things", "json", COLUMNS, ROWS, zone=exporting.zone_of(None), stamp=stamp()
        )

        assert response.media_type == "application/json"
        [row] = json.loads(body(response))
        assert row == {
            "Name": "'=cmd()",
            "Seen": "2026-11-16T15:00:00+00:00",
            "Ports": "22; =80",
            "Count": 3,
            "Nothing": "",
        }

    def test_a_list_with_nothing_in_it_is_an_empty_array(self) -> None:
        response = exporting.download(
            "things", "json", COLUMNS, [], zone=exporting.zone_of(None), stamp=stamp()
        )

        assert json.loads(body(response)) == []
