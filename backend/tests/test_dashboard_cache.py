"""The dashboard is built once for the polls that come within a few seconds of each other, and a
poll that finds it unchanged gets no body. A change the owner makes, or the passing of the seconds,
makes the next one build it again, and nobody who isn't signed in is ever given a kept answer."""

import logging
import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session, sessionmaker

from app import answers
from app.answers import AnswerCache
from app.api import dashboard as dashboard_api
from app.config import Settings
from app.events.event import Severity
from app.events.store import record as record_events
from app.models import utcnow
from tests.helpers import new_event

BASE = "/api/dashboard"
NOISE = "/api/noise-filters"
EVERYTHING: dict[str, Any] = {"confidence_floor": 35, "quiet_inside": False, "source_floors": {}}


class Clock:
    """Time that moves when a test says."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(app: FastAPI) -> Clock:
    clock = Clock()
    app.state.answers = AnswerCache(clock=clock)
    return clock


@pytest.fixture
def builds(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The windows that were built, in order."""
    built: list[str] = []
    build = dashboard_api.build

    def counting(db: Session, key: str, now: Any) -> Any:
        built.append(key)
        return build(db, key, now)

    monkeypatch.setattr(dashboard_api, "build", counting)
    return built


@contextmanager
def counted(engine: Engine) -> Generator[list[str]]:
    """The statements the database was asked, while the block runs."""
    statements: list[str] = []

    def note(connection: Any, cursor: Any, statement: str, *rest: Any) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", note)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", note)


class TestKeptForAFewSeconds:
    def test_two_polls_in_the_seconds_build_it_once(
        self, client: TestClient, csrf_token: str, clock: Clock, builds: list[str]
    ) -> None:
        first = client.get(BASE)
        clock.now += 14
        second = client.get(BASE)

        assert builds == ["24h"]
        assert first.content == second.content
        assert first.headers["ETag"] == second.headers["ETag"]

    def test_the_second_poll_does_not_read_the_events(
        self, client: TestClient, csrf_token: str, clock: Clock, engine: Engine
    ) -> None:
        with counted(engine) as first:
            client.get(BASE)
        with counted(engine) as second:
            client.get(BASE)

        assert any("FROM events" in statement for statement in first)
        assert not any("events" in statement for statement in second)
        assert len(second) < len(first) / 4

    def test_each_window_is_kept_on_its_own(
        self, client: TestClient, csrf_token: str, clock: Clock, builds: list[str]
    ) -> None:
        client.get(BASE, params={"window": "24h"})
        client.get(BASE, params={"window": "7d"})
        client.get(BASE, params={"window": "24h"})
        client.get(BASE, params={"window": "7d"})

        assert builds == ["24h", "7d"]

    def test_it_is_built_again_once_the_seconds_have_passed(
        self, client: TestClient, csrf_token: str, clock: Clock, builds: list[str]
    ) -> None:
        client.get(BASE)
        clock.now += answers.SECONDS + 1
        client.get(BASE)

        assert builds == ["24h", "24h"]

    def test_what_arrived_from_the_network_shows_once_the_seconds_have_passed(
        self,
        client: TestClient,
        csrf_token: str,
        clock: Clock,
        session: Session,
        settings: Settings,
    ) -> None:
        before = client.get(BASE)
        now = utcnow()
        record_events(session, settings, [new_event(severity=Severity.HIGH, occurred_at=now)], now)
        session.commit()

        kept = client.get(BASE)
        clock.now += answers.SECONDS + 1
        after = client.get(BASE)

        assert kept.json()["alerts"]["total"] == 0
        assert after.json()["alerts"]["total"] == 1
        assert after.headers["ETag"] != before.headers["ETag"]


class TestWhatTheOwnerChanges:
    def test_the_next_poll_shows_a_change_that_was_made(
        self, client: TestClient, csrf_token: str, clock: Clock, builds: list[str]
    ) -> None:
        before = client.get(BASE).json()["attention"]["floor"]

        changed = client.put(
            NOISE, json={**EVERYTHING, "confidence_floor": 50}, headers={"X-CSRF-Token": csrf_token}
        )
        after = client.get(BASE)

        assert changed.status_code == 200
        assert (before, after.json()["attention"]["floor"]) == (35, 50)
        assert builds == ["24h", "24h"]

    def test_a_change_made_in_another_worker_is_seen_too(
        self, client: TestClient, csrf_token: str, clock: Clock, engine: Engine, builds: list[str]
    ) -> None:
        client.get(BASE)
        # What another worker does when it serves a change: it writes the stamp, and this one
        # has never heard of it except through the database.
        answers.stamp_change(sessionmaker(bind=engine, expire_on_commit=False))
        client.get(BASE)

        assert builds == ["24h", "24h"]

    def test_a_change_that_was_refused_changes_nothing(
        self, client: TestClient, csrf_token: str, clock: Clock, builds: list[str]
    ) -> None:
        client.get(BASE)

        refused = client.put(
            NOISE,
            json={**EVERYTHING, "confidence_floor": 0},
            headers={"X-CSRF-Token": csrf_token},
        )
        client.get(BASE)

        assert refused.status_code == 422
        assert builds == ["24h"]

    def test_only_changes_are_noted(
        self, client: TestClient, csrf_token: str, clock: Clock, session: Session
    ) -> None:
        before = answers.current_stamp(session)

        client.get(BASE)
        client.get("/api/noise-filters")
        session.rollback()

        assert answers.current_stamp(session) == before

    def test_a_change_that_cannot_be_noted_still_goes_through(
        self,
        client: TestClient,
        csrf_token: str,
        clock: Clock,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        def broken(sessions: Any) -> None:
            raise RuntimeError("no database")

        monkeypatch.setattr(answers, "stamp_change", broken)

        with caplog.at_level(logging.WARNING, logger="aresgate.request"):
            response = client.put(
                NOISE,
                json={**EVERYTHING, "confidence_floor": 50},
                headers={"X-CSRF-Token": csrf_token},
            )

        assert response.status_code == 200
        assert "could not be noted" in caplog.text


class TestAnAnswerThatHasNotChanged:
    def test_the_tag_it_was_sent_with_gets_nothing_back(
        self, client: TestClient, csrf_token: str, clock: Clock
    ) -> None:
        first = client.get(BASE)

        again = client.get(BASE, headers={"If-None-Match": first.headers["ETag"]})

        assert first.status_code == 200
        assert again.status_code == 304
        assert again.content == b""
        assert again.headers["ETag"] == first.headers["ETag"]
        assert again.headers["Cache-Control"] == "private, no-cache"

    def test_it_is_sent_to_be_kept_by_the_browser_alone(
        self, client: TestClient, csrf_token: str, clock: Clock
    ) -> None:
        response = client.get(BASE)

        assert response.headers["Cache-Control"] == "private, no-cache"
        assert response.headers["content-type"] == "application/json"
        assert response.headers["ETag"].startswith('"')

    @pytest.mark.parametrize(
        "sent", ["{etag}", "W/{etag}", '"other", {etag}', '"other",W/{etag}', "*"]
    )
    def test_the_ways_a_tag_is_named(
        self, client: TestClient, csrf_token: str, clock: Clock, sent: str
    ) -> None:
        etag = client.get(BASE).headers["ETag"]

        response = client.get(BASE, headers={"If-None-Match": sent.format(etag=etag)})

        assert response.status_code == 304

    def test_another_tag_gets_the_answer(
        self, client: TestClient, csrf_token: str, clock: Clock
    ) -> None:
        response = client.get(BASE, headers={"If-None-Match": '"not-this-one"'})

        assert response.status_code == 200
        assert response.json()["window"]["key"] == "24h"

    def test_an_answer_that_changed_is_sent_with_a_new_tag(
        self, client: TestClient, csrf_token: str, clock: Clock
    ) -> None:
        old = client.get(BASE).headers["ETag"]
        client.put(
            NOISE, json={**EVERYTHING, "confidence_floor": 50}, headers={"X-CSRF-Token": csrf_token}
        )

        response = client.get(BASE, headers={"If-None-Match": old})

        assert response.status_code == 200
        assert response.headers["ETag"] != old

    def test_the_other_window_is_not_the_same_answer(
        self, client: TestClient, csrf_token: str, clock: Clock
    ) -> None:
        day = client.get(BASE).headers["ETag"]

        week = client.get(BASE, params={"window": "7d"}, headers={"If-None-Match": day})

        assert week.status_code == 200


class TestWhoIsSignedIn:
    def test_a_kept_answer_is_not_given_to_someone_signed_out(
        self, client: TestClient, csrf_token: str, clock: Clock, builds: list[str]
    ) -> None:
        etag = client.get(BASE).headers["ETag"]
        client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})

        plain = client.get(BASE)
        conditional = client.get(BASE, headers={"If-None-Match": etag})

        assert plain.status_code == 401
        assert conditional.status_code == 401
        assert "ETag" not in conditional.headers
        assert builds == ["24h"]

    def test_someone_who_never_signed_in_is_refused_with_nothing_kept(
        self, client: TestClient, clock: Clock, builds: list[str]
    ) -> None:
        assert client.get(BASE, headers={"If-None-Match": "*"}).status_code == 401
        assert builds == []


class TestTheKeptAnswers:
    """The cache itself, in one worker or two."""

    def test_a_burst_of_polls_waits_for_one_build(self, session: Session, engine: Engine) -> None:
        cache = AnswerCache()
        started = threading.Event()
        release = threading.Event()
        built: list[int] = []

        def slow() -> bytes:
            built.append(1)
            started.set()
            release.wait(5)
            return b"{}"

        results: list[bytes] = []

        def poll() -> None:
            with sessionmaker(bind=engine)() as db:
                results.append(cache.fetch("day", db, slow).body)

        first = threading.Thread(target=poll)
        first.start()
        assert started.wait(5)
        second = threading.Thread(target=poll)
        second.start()
        release.set()
        first.join(5)
        second.join(5)

        assert built == [1]
        assert results == [b"{}", b"{}"]

    def test_a_change_during_the_build_leaves_the_stamp_behind(
        self, session: Session, engine: Engine
    ) -> None:
        cache = AnswerCache()
        sessions = sessionmaker(bind=engine, expire_on_commit=False)

        def change_while_building() -> bytes:
            answers.stamp_change(sessions)
            return b"old"

        cache.fetch("day", session, change_while_building)
        session.rollback()

        assert cache.fetch("day", session, lambda: b"new").body == b"new"

    def test_a_tag_follows_the_body(self) -> None:
        assert answers.etag_of(b"a") == answers.etag_of(b"a")
        assert answers.etag_of(b"a") != answers.etag_of(b"b")

    def test_each_change_moves_the_stamp_on(self, session: Session, engine: Engine) -> None:
        sessions = sessionmaker(bind=engine, expire_on_commit=False)

        answers.stamp_change(sessions)
        first = answers.current_stamp(session)
        session.rollback()
        answers.stamp_change(sessions)
        second = answers.current_stamp(session)

        assert first is not None and second == first + 1
