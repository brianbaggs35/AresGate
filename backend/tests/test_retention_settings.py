import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import quota, retention, retention_policy
from app.audit import Action
from app.config import Settings
from app.events import retention as event_retention
from app.events.store import record
from app.models import AuditEvent, Event, User
from app.partitions import EVENTS, METRIC_SAMPLES, Partition
from app.retention_policy import GIGABYTE, Policy
from tests.helpers import OTHER_ORIGIN, new_event

BASE = "/api/retention-settings"
# A Friday, in the week that begins on Monday 19 October.
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def ask(**changes: object) -> dict[str, object]:
    body: dict[str, object] = {
        "managed": True,
        "keep_forever": False,
        "days": 30,
        "quota_gb": None,
    }
    return body | changes


@pytest.fixture
def new_session(engine: Engine) -> Callable[[], Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def store_event(session: Session, age: timedelta, source: str = "wazuh") -> None:
    event = new_event(
        source=source, connection="api", occurred_at=NOW - age, identity=(source, str(age))
    )
    EVENTS.lock(session)
    EVENTS.ensure(session, [EVENTS.containing(event.occurred_at)])
    session.add(Event(**event.row(NOW)))
    session.flush()


class TestThePolicy:
    def test_nothing_is_managed_until_the_owner_says_so(self, session: Session) -> None:
        assert retention_policy.load(session) == Policy()
        assert Policy().deletes_by_age
        assert Policy().quota_bytes is None
        assert retention_policy.updated_at(session) is None

    def test_choices_are_kept_and_saving_the_same_again_changes_nothing(
        self, session: Session
    ) -> None:
        chosen = Policy(managed=True, days=14, quota_gb=5)

        assert retention_policy.save(session, chosen)
        assert not retention_policy.save(session, chosen)
        assert retention_policy.save(session, Policy(managed=True, days=14, quota_gb=None))
        session.commit()

        assert retention_policy.load(session) == Policy(managed=True, days=14)
        assert retention_policy.updated_at(session) is not None

    def test_the_owners_days_replace_the_built_in_ones_only_while_it_is_managed(
        self, settings: Settings
    ) -> None:
        managed = Policy(managed=True, days=7).apply(settings)

        assert (managed.event_retention_days, managed.alert_log_retention_days) == (7, 7)
        assert managed.audit_retention_days == settings.audit_retention_days
        assert Policy(managed=False, days=7).apply(settings) is settings
        assert Policy(managed=True, keep_forever=True, days=7).apply(settings) is settings

    def test_forever_deletes_nothing_and_has_no_quota(self) -> None:
        forever = Policy(managed=True, keep_forever=True, quota_gb=3)

        assert not forever.deletes_by_age
        assert forever.quota_bytes is None
        assert Policy(managed=True, quota_gb=3).quota_bytes == 3 * GIGABYTE
        assert Policy(managed=False, quota_gb=3).quota_bytes is None


class TestWhatIsKept:
    def test_unmanaged_events_keep_to_their_own_period(
        self, session: Session, settings: Settings
    ) -> None:
        assert event_retention.load(session, settings).default == settings.event_retention_days

    def test_the_owners_days_are_the_default_and_a_source_with_its_own_keeps_it(
        self, session: Session, settings: Settings
    ) -> None:
        retention_policy.save(session, Policy(managed=True, days=9))
        event_retention.set_days(session, "wazuh", 3)
        session.commit()

        loaded = event_retention.load(session, settings)

        assert (loaded.default, loaded.days("wazuh"), loaded.days("opnsense")) == (9, 3, 9)

    def test_forever_keeps_every_source_for_ever_and_stores_old_events(
        self, session: Session, settings: Settings
    ) -> None:
        retention_policy.save(session, Policy(managed=True, keep_forever=True))
        event_retention.set_days(session, "wazuh", 3)
        session.commit()
        old = new_event(
            source="wazuh",
            connection="api",
            occurred_at=NOW - timedelta(days=400),
            identity=("old",),
        )

        stored = record(session, settings, [old], NOW)
        session.commit()

        assert stored == 1
        assert event_retention.load(session, settings).days("wazuh") > 36000


class TestThePurge:
    def test_forever_deletes_nothing_by_age(
        self, session: Session, settings: Settings, new_session: Callable[[], Session]
    ) -> None:
        store_event(session, timedelta(days=settings.event_retention_days + 20))
        retention_policy.save(session, Policy(managed=True, keep_forever=True))
        session.commit()

        assert retention.purge_once(settings, new_session) == 0

        session.expire_all()
        assert session.scalar(select(func.count()).select_from(Event)) == 1

    def test_the_owners_days_decide_what_is_past_its_period(
        self, session: Session, settings: Settings, new_session: Callable[[], Session]
    ) -> None:
        now = datetime.now(UTC)
        for age in (10, 2):
            event = new_event(
                source="wazuh",
                connection="api",
                occurred_at=now - timedelta(days=age),
                identity=("age", str(age)),
            )
            EVENTS.lock(session)
            EVENTS.ensure(session, [EVENTS.containing(event.occurred_at)])
            session.add(Event(**event.row(now)))
        retention_policy.save(session, Policy(managed=True, days=5))
        session.commit()

        retention.purge_once(settings, new_session)

        session.expire_all()
        assert session.scalar(select(func.count()).select_from(Event)) == 1


def week(start: datetime) -> Partition:
    return EVENTS.containing(start)


class TestTheQuota:
    def prepare(self, session: Session, weeks: int) -> None:
        """Weeks of events and of samples, the oldest first, the last being the one in progress."""
        for number in range(weeks):
            start = NOW - timedelta(weeks=weeks - 1 - number)
            for table in (EVENTS, METRIC_SAMPLES):
                table.lock(session)
                table.ensure(session, [table.containing(start)])
        session.commit()

    def existing(self, session: Session) -> list[Partition]:
        return EVENTS.existing(session)

    def test_without_a_quota_it_does_nothing(self, session: Session) -> None:
        assert quota.enforce(session, Policy(managed=True), NOW) is None
        assert quota.enforce(session, Policy(managed=False, quota_gb=1), NOW) is None
        assert (
            quota.enforce(session, Policy(managed=True, keep_forever=True, quota_gb=1), NOW) is None
        )

    def test_under_the_quota_nothing_goes(self, session: Session) -> None:
        self.prepare(session, 3)

        done = quota.enforce(session, Policy(managed=True, quota_gb=1000), NOW)

        assert done is not None
        assert (done.weeks_dropped, done.over) == (0, False)
        assert len(self.existing(session)) == 3

    def test_over_the_quota_the_oldest_weeks_go_until_it_is_under_but_not_the_one_in_progress(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.prepare(session, 4)
        sizes = iter([100 * GIGABYTE, 90 * GIGABYTE, 50 * GIGABYTE])

        def measured(db: Session) -> int:
            return next(sizes)

        monkeypatch.setattr(quota, "database_bytes", measured)

        done = quota.enforce(session, Policy(managed=True, quota_gb=60), NOW)

        assert done is not None
        assert done.weeks_dropped == 2
        assert (done.before, done.after, done.over) == (100 * GIGABYTE, 50 * GIGABYTE, False)
        # The oldest week of the events went, and then that same week of the samples, which is as
        # old: the weeks after it, and the one in progress, are left.
        expected = [week(NOW - timedelta(weeks=number)).start for number in (2, 1, 0)]
        assert [partition.start for partition in EVENTS.existing(session)] == expected
        assert [partition.start for partition in METRIC_SAMPLES.existing(session)] == expected

    def test_when_only_the_week_in_progress_is_left_it_says_it_is_still_over(
        self, session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        self.prepare(session, 1)

        def measured(db: Session) -> int:
            return 10 * GIGABYTE

        monkeypatch.setattr(quota, "database_bytes", measured)

        with caplog.at_level(logging.WARNING):
            done = quota.enforce(session, Policy(managed=True, quota_gb=1), NOW)

        assert done is not None
        assert (done.weeks_dropped, done.over) == (0, True)
        assert "only the week in progress is left" in caplog.text
        assert len(self.existing(session)) == 1

    def test_it_gives_up_after_a_number_of_weeks_and_carries_on_next_time(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.prepare(session, 4)
        monkeypatch.setattr(quota, "MAX_DROPS", 1)

        def measured(db: Session) -> int:
            return 10 * GIGABYTE

        monkeypatch.setattr(quota, "database_bytes", measured)

        done = quota.enforce(session, Policy(managed=True, quota_gb=1), NOW)

        assert done is not None
        assert done.weeks_dropped == 1

    def test_the_database_and_its_tables_have_a_size(self, session: Session) -> None:
        assert quota.database_bytes(session) > 0
        assert quota.table_bytes(session, EVENTS) >= 0


class TestTheLoop:
    def test_a_failed_quota_check_is_logged_and_does_not_stop_the_purge(
        self, settings: Settings, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = {"purge": 0, "quota": 0}

        def purge(settings: Settings, new_session: Callable[[], Session]) -> int:
            calls["purge"] += 1
            return 0

        def broken(new_session: Callable[[], Session]) -> None:
            calls["quota"] += 1
            raise ConnectionError("the database isn't up yet")

        monkeypatch.setattr(retention, "purge_once", purge)
        monkeypatch.setattr(retention, "enforce_quota", broken)

        async def go() -> None:
            task = asyncio.create_task(
                retention.run(
                    settings,
                    lambda: None,  # type: ignore[arg-type,return-value]
                    interval=timedelta(milliseconds=1),
                    quota_interval=timedelta(milliseconds=1),
                )
            )
            while calls["quota"] < 2 or calls["purge"] < 2:
                await asyncio.sleep(0.001)
            task.cancel()
            await asyncio.wait({task})

        with caplog.at_level(logging.ERROR):
            asyncio.run(go())

        assert "Couldn't keep the database within its quota" in caplog.text

    def test_the_purge_waits_for_its_interval_but_the_quota_is_checked_more_often(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = {"purge": 0, "quota": 0}

        def purge(settings: Settings, new_session: Callable[[], Session]) -> int:
            calls["purge"] += 1
            return 0

        def checked(new_session: Callable[[], Session]) -> None:
            calls["quota"] += 1

        monkeypatch.setattr(retention, "purge_once", purge)
        monkeypatch.setattr(retention, "enforce_quota", checked)

        async def go() -> None:
            task = asyncio.create_task(
                retention.run(
                    settings,
                    lambda: None,  # type: ignore[arg-type,return-value]
                    interval=timedelta(hours=1),
                    quota_interval=timedelta(milliseconds=1),
                )
            )
            while calls["quota"] < 3:
                await asyncio.sleep(0.001)
            task.cancel()
            await asyncio.wait({task})

        asyncio.run(go())

        assert calls["purge"] == 1

    def test_the_quota_is_checked_with_the_owners_choice(
        self, session: Session, new_session: Callable[[], Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        retention_policy.save(session, Policy(managed=True, quota_gb=7))
        session.commit()
        seen: list[Policy] = []

        def enforce(db: Session, policy: Policy, now: datetime) -> None:
            seen.append(policy)

        monkeypatch.setattr(quota, "enforce", enforce)

        assert retention.enforce_quota(new_session) is None
        assert seen == [Policy(managed=True, quota_gb=7)]


class TestTheApi:
    def test_it_is_only_for_someone_signed_in(self, client: TestClient, account: User) -> None:
        assert client.get(BASE).status_code == 401
        assert client.put(BASE, json=ask()).status_code == 401

    def test_a_change_needs_the_security_token_and_an_origin_from_the_app(
        self, client: TestClient, csrf_token: str
    ) -> None:
        without = client.put(BASE, json=ask())
        foreign = client.put(
            BASE, json=ask(), headers={**headers(csrf_token), "Origin": OTHER_ORIGIN}
        )

        assert without.status_code == 403
        assert foreign.status_code == 403

    def test_it_starts_off_with_what_is_kept_today_and_what_the_database_holds(
        self, client: TestClient, csrf_token: str, settings: Settings
    ) -> None:
        body = client.get(BASE).json()

        assert (body["managed"], body["keep_forever"], body["days"], body["quota_gb"]) == (
            False,
            False,
            30,
            None,
        )
        assert body["built_in"] == {
            "events": settings.event_retention_days,
            "metrics": settings.metric_retention_days,
            "api_log": settings.api_log_retention_days,
            "ai_log": settings.ai_log_retention_days,
            "alert_log": settings.alert_log_retention_days,
            "audit": settings.audit_retention_days,
        }
        assert body["usage"]["database_bytes"] > 0
        assert body["usage"]["quota_bytes"] is None
        assert body["usage"]["over_quota"] is False
        assert body["updated_at"] is None

    def test_a_change_is_kept_and_written_in_the_audit_log(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        response = client.put(BASE, json=ask(days=14, quota_gb=20), headers=headers(csrf_token))

        assert response.status_code == 200
        body = response.json()
        assert (body["managed"], body["days"], body["quota_gb"]) == (True, 14, 20)
        assert body["usage"]["quota_bytes"] == 20 * GIGABYTE
        assert body["updated_at"] is not None
        assert client.get(BASE).json()["days"] == 14
        [entry] = session.scalars(
            select(AuditEvent).where(AuditEvent.action == Action.RETENTION_SETTINGS_CHANGED)
        ).all()
        assert entry.detail == {
            "managed": True,
            "from_managed": False,
            "days": 14,
            "from_days": 30,
            "quota_gb": 20,
            "from_quota_gb": "none",
        }

    def test_saving_the_same_again_writes_nothing_to_the_audit_log(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        for _ in range(2):
            client.put(BASE, json=ask(), headers=headers(csrf_token))

        entries = session.scalars(
            select(AuditEvent).where(AuditEvent.action == Action.RETENTION_SETTINGS_CHANGED)
        ).all()
        assert len(entries) == 1

    def test_going_back_to_no_quota_says_so_in_the_audit_log(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        client.put(BASE, json=ask(quota_gb=5), headers=headers(csrf_token))
        client.put(BASE, json=ask(quota_gb=None), headers=headers(csrf_token))

        last = session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == Action.RETENTION_SETTINGS_CHANGED)
            .order_by(AuditEvent.id.desc())
        ).first()
        assert last is not None
        assert last.detail == {"quota_gb": "none", "from_quota_gb": 5}

    @pytest.mark.parametrize(
        "changes",
        [
            {"days": 0},
            {"days": 4000},
            {"quota_gb": 0},
            {"quota_gb": 200000},
            {"extra": 1},
        ],
    )
    def test_numbers_outside_what_is_sensible_are_refused(
        self, client: TestClient, csrf_token: str, changes: dict[str, object]
    ) -> None:
        response = client.put(BASE, json=ask(**changes), headers=headers(csrf_token))

        assert response.status_code == 422
