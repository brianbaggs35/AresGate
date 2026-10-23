import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors import connection_check, store
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.connection_check import ConnectionCheck
from app.collectors.health import WORKER
from app.collectors.scheduler import Scheduler, Timing
from app.config import Settings
from app.integrations import netguard, registry, service
from app.integrations.apilog import ApiLogRecorder
from app.integrations.probes import Verdict
from app.integrations.service import Submission
from app.models import (
    ApiCall,
    CollectorHealth,
    Event,
    IntegrationConnection,
    WorkerBeat,
    utcnow,
)
from app.security import credential_store
from app.security.credential_store import Kind
from e2e.stand_ins import crowdsec
from tests.helpers import new_event
from tests.stubs import Serve

SECRET = "a-very-secret-api-key-for-tests"
# What a run reads is the same every time, so reading it again finds nothing new.
WHEN = utcnow()
FAST = Timing(
    tick=timedelta(milliseconds=20),
    retry=timedelta(milliseconds=10),
    spread=timedelta(0),
    slots=2,
)


class Counting(Collector):
    key = "counting"
    title = "Counting"
    summary = "Counts its runs."
    interval = timedelta(milliseconds=20)
    timeout = timedelta(seconds=5)

    def __init__(self) -> None:
        self.runs: int = 0

    async def collect(self, context: Context) -> Outcome:
        self.runs += 1
        return Outcome(items=7)


class Hourly(Counting):
    key = "hourly"
    interval = timedelta(hours=1)


class Declining(Hourly):
    key = "declining"

    async def collect(self, context: Context) -> Outcome:
        self.runs += 1
        raise CollectorFailed("It said no.")


class Broken(Hourly):
    key = "broken"

    async def collect(self, context: Context) -> Outcome:
        self.runs += 1
        raise RuntimeError("something nobody expected")


class Hanging(Hourly):
    key = "hanging"
    timeout = timedelta(milliseconds=50)

    async def collect(self, context: Context) -> Outcome:
        await asyncio.sleep(30)
        return Outcome()


class Unreachable(Hourly):
    key = "unreachable"

    async def collect(self, context: Context) -> Outcome:
        await context.client.request("GET", "/anything")
        return Outcome()


class Saving(Hourly):
    key = "saving"

    async def collect(self, context: Context) -> Outcome:
        found = await context.save(lambda db: len(list(db.scalars(select(IntegrationConnection)))))
        return Outcome(items=found)


class Reporting(Hourly):
    key = "reporting"

    async def collect(self, context: Context) -> Outcome:
        target = context.target
        found = [
            new_event(
                source=target.integration,
                connection=target.connection,
                occurred_at=WHEN,
                identity=(number,),
            )
            for number in range(2)
        ]
        return Outcome(items=await context.record(found))


class OnlyOpnsense(Hourly):
    key = "only-opnsense"
    integration = "opnsense"


class OnlyWazuhIndexer(Hourly):
    key = "only-wazuh-indexer"
    integration = "wazuh"
    connection = "indexer"


class NeedsSuricata(Hourly):
    key = "needs-suricata"
    module = "suricata"


def connect(session: Session, settings: Settings, url: str, key: str = SECRET) -> None:
    submission = Submission(
        url=url,
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options={},
        secrets={"api_key": key},
    )
    service.save(
        session,
        settings,
        netguard.HOME_NETWORK_AND_LOOPBACK,
        registry.INTEGRATIONS["crowdsec"],
        {"lapi": submission},
        utcnow(),
    )
    session.commit()


def saved_row(session: Session, integration: str, connection: str, **changes: object):
    row = IntegrationConnection(
        integration=integration,
        connection=connection,
        base_url="https://192.168.1.2",
        tls_mode="system",
        options={},
        disabled_modules=[],
    )
    for name, value in changes.items():
        setattr(row, name, value)
    session.add(row)
    session.commit()
    return row


def make(
    settings: Settings,
    engine: Engine,
    *collectors: Collector,
    new_session: Callable[[], Session] | None = None,
    **options: object,
) -> Scheduler:
    maker = new_session or sessionmaker(bind=engine, expire_on_commit=False)
    return Scheduler(
        settings,
        maker,
        ApiLogRecorder(maker),
        netguard.HOME_NETWORK_AND_LOOPBACK,
        collectors=collectors or (ConnectionCheck(),),
        **options,  # type: ignore[arg-type]
    )


def health_rows(session: Session) -> list[CollectorHealth]:
    session.expire_all()
    return list(session.scalars(select(CollectorHealth).order_by(CollectorHealth.collector)))


def the_health(session: Session) -> CollectorHealth:
    [record] = health_rows(session)
    return record


async def until(condition: Callable[[], bool], seconds: float = 5.0) -> None:
    async with asyncio.timeout(seconds):
        while not condition():
            await asyncio.sleep(0.01)


# ---- Running once ----------------------------------------------------------------------------


def test_a_check_that_works_is_kept_and_marks_the_connection_connected(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)

    asyncio.run(make(settings, engine).run_once())

    record = the_health(session)
    assert (record.collector, record.integration, record.connection) == (
        "connection-check",
        "crowdsec",
        "lapi",
    )
    assert record.consecutive_failures == 0
    assert record.last_error is None
    assert record.last_success_at == record.last_finished_at
    assert record.last_started_at is not None
    assert record.last_finished_at is not None
    assert record.last_duration_ms is not None
    assert record.next_run_at == record.last_finished_at + timedelta(minutes=5)
    row = service.rows_for(session, "crowdsec")["lapi"]
    session.refresh(row)
    assert row.last_success_at is not None
    assert row.last_error is None
    [call] = session.scalars(select(ApiCall)).all()
    assert (call.integration, call.connection, call.method, call.path, call.status_code) == (
        "crowdsec",
        "lapi",
        "GET",
        "/v1/decisions",
        200,
    )


def test_a_check_that_fails_says_why_and_is_tried_again_sooner_each_time(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    server = serve(crowdsec(SECRET))
    connect(session, settings, server.url, key="not-the-key-at-all")

    asyncio.run(make(settings, engine).run_once())

    first = the_health(session)
    assert first.consecutive_failures == 1
    assert first.last_error is not None
    assert "CrowdSec didn't accept the credentials" in first.last_error
    assert first.last_success_at is None
    assert first.last_finished_at is not None
    assert first.next_run_at == first.last_finished_at + timedelta(seconds=30)
    row = service.rows_for(session, "crowdsec")["lapi"]
    session.refresh(row)
    assert row.last_error == first.last_error
    asyncio.run(make(settings, engine).run_once())
    second = the_health(session)
    assert second.consecutive_failures == 2
    assert second.last_finished_at is not None
    assert second.next_run_at == second.last_finished_at + timedelta(seconds=60)
    # Putting the key right and saving it makes the next run work, and clears the failures.
    connect(session, settings, server.url)
    asyncio.run(make(settings, engine).run_once())
    fixed = the_health(session)
    assert (fixed.consecutive_failures, fixed.last_error) == (0, None)
    assert fixed.last_success_at is not None
    session.refresh(row)
    assert row.last_error is None


def test_a_secret_that_has_gone_is_reported_not_crashed_on(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)
    credential_store.remove(session, Kind.INTEGRATION, "crowdsec-lapi", "api_key")
    session.commit()

    asyncio.run(make(settings, engine).run_once())

    record = the_health(session)
    assert record.consecutive_failures == 1
    assert record.last_error is not None
    assert "missing or can't be opened" in record.last_error


def test_an_address_that_is_no_longer_acceptable_is_reported(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)
    row = service.rows_for(session, "crowdsec")["lapi"]
    row.base_url = "ftp://192.168.1.4"
    session.commit()

    asyncio.run(make(settings, engine).run_once())

    assert the_health(session).last_error == (
        "Start the address with https:// and the host, such as https://192.168.1.1."
    )


def test_a_run_says_how_many_things_it_found(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)
    saved_row(session, "ntopng", "api")

    asyncio.run(make(settings, engine, Counting(), Saving()).run_once())

    found = {record.collector: record.last_items for record in health_rows(session)}
    assert found == {"counting": 7, "saving": 2}


def test_a_collector_stores_the_events_it_read_and_reading_them_again_adds_none(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)
    scheduler = make(settings, engine, Reporting())

    asyncio.run(scheduler.run_once())
    first = the_health(session).last_items
    asyncio.run(scheduler.run_once())
    second = the_health(session).last_items

    assert (first, second) == (2, 0)
    session.expire_all()
    events = session.scalars(select(Event).order_by(Event.id)).all()
    assert [(item.source, item.connection) for item in events] == [("crowdsec", "lapi")] * 2


def test_a_collector_that_declines_gives_its_reason(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)

    asyncio.run(make(settings, engine, Declining()).run_once())

    record = the_health(session)
    assert (record.consecutive_failures, record.last_error) == (1, "It said no.")


def test_a_request_that_gets_no_answer_is_a_failure_with_its_reason(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    server = serve(crowdsec(SECRET))
    connect(session, settings, server.url)
    server.stop()

    asyncio.run(make(settings, engine, Unreachable()).run_once())

    record = the_health(session)
    assert record.last_error is not None
    assert f"Couldn't connect to 127.0.0.1:{server.port}" in record.last_error


def test_a_collector_that_breaks_is_logged_and_does_not_leak_why(
    session: Session,
    settings: Settings,
    engine: Engine,
    serve: Serve,
    caplog: pytest.LogCaptureFixture,
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)

    with caplog.at_level(logging.ERROR):
        asyncio.run(make(settings, engine, Broken()).run_once())

    assert the_health(session).last_error == "Ran into a problem. The log has the details."
    assert "broken failed on crowdsec/lapi" in caplog.text
    assert "something nobody expected" in caplog.text


def test_a_collector_that_takes_too_long_is_stopped(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)

    asyncio.run(make(settings, engine, Hanging()).run_once())

    assert the_health(session).last_error == "Didn't finish within 0.05 seconds."


def test_a_connection_removed_while_a_run_starts_is_reported(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    sessions = 0

    def new_session() -> Session:
        nonlocal sessions
        sessions += 1
        # The first is the look at what is wanted, and the second loads the connection to run.
        if sessions == 2:
            service.disconnect(session, registry.INTEGRATIONS["crowdsec"])
            session.commit()
        return maker()

    asyncio.run(make(settings, engine, Counting(), new_session=new_session).run_once())

    assert the_health(session).last_error == "The connection was removed."


def test_a_record_deleted_while_a_run_is_in_progress_is_made_again(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    sessions = 0

    def new_session() -> Session:
        nonlocal sessions
        sessions += 1
        if sessions == 2:
            for record in health_rows(session):
                session.delete(record)
            session.commit()
        return maker()

    asyncio.run(make(settings, engine, Counting(), new_session=new_session).run_once())

    record = the_health(session)
    assert (record.collector, record.last_items, record.interval_seconds) == ("counting", 7, 0)


# ---- What is wanted --------------------------------------------------------------------------


def test_each_collector_is_wanted_on_each_connection_it_applies_to(
    session: Session,
) -> None:
    saved_row(session, "opnsense", "api")
    saved_row(session, "wazuh", "manager")
    saved_row(session, "wazuh", "indexer")

    everywhere = store.wanted(session, [Counting()])
    only_opnsense = store.wanted(session, [OnlyOpnsense()])
    only_indexer = store.wanted(session, [OnlyWazuhIndexer()])

    assert [item.key for item in everywhere] == [
        ("counting", "opnsense", "api"),
        ("counting", "wazuh", "indexer"),
        ("counting", "wazuh", "manager"),
    ]
    assert [item.key for item in only_opnsense] == [("only-opnsense", "opnsense", "api")]
    assert [item.key for item in only_indexer] == [("only-wazuh-indexer", "wazuh", "indexer")]


def test_a_collector_is_not_wanted_where_its_module_is_switched_off(session: Session) -> None:
    saved_row(session, "opnsense", "api", disabled_modules=["suricata"])
    saved_row(session, "wazuh", "manager", disabled_modules=["something-else"])

    found = store.wanted(session, [NeedsSuricata()])

    assert [item.key for item in found] == [
        ("needs-suricata", "wazuh", "manager"),
    ]


def test_a_connection_that_is_no_longer_known_is_left_alone(session: Session) -> None:
    saved_row(session, "dropped-from-the-product", "api")
    saved_row(session, "opnsense", "no-such-connection")

    assert store.wanted(session, [Counting()]) == []


def test_sync_makes_a_record_for_each_wanted_collector_and_deletes_the_rest(
    session: Session,
) -> None:
    saved_row(session, "ntopng", "api")
    now = utcnow()
    session.add_all(
        [
            CollectorHealth(
                collector="counting",
                integration="ntopng",
                connection="api",
                interval_seconds=999,
                consecutive_failures=2,
                last_error="Earlier.",
                updated_at=now,
            ),
            CollectorHealth(
                collector="counting",
                integration="crowdsec",
                connection="lapi",
                interval_seconds=1,
                consecutive_failures=0,
                updated_at=now,
            ),
        ]
    )
    session.commit()

    store.sync(session, store.wanted(session, [Counting(), Hourly()]), now)
    session.commit()

    records = {(row.collector, row.integration): row for row in health_rows(session)}
    assert set(records) == {("counting", "ntopng"), ("hourly", "ntopng")}
    # What was there keeps its history and takes the interval the collector has now.
    assert records[("counting", "ntopng")].interval_seconds == 0
    assert records[("counting", "ntopng")].last_error == "Earlier."
    assert records[("hourly", "ntopng")].interval_seconds == 3600
    assert records[("hourly", "ntopng")].last_finished_at is None


def test_the_heartbeat_is_made_and_then_kept_up_to_date(session: Session) -> None:
    started = utcnow() - timedelta(hours=1)
    store.beat(session, started, started)
    session.commit()

    first = session.get(WorkerBeat, WORKER)
    assert first is not None
    assert (first.started_at, first.beat_at) == (started, started)

    now = utcnow()
    store.beat(session, now - timedelta(minutes=1), now)
    session.commit()

    session.refresh(first)
    assert (first.started_at, first.beat_at) == (now - timedelta(minutes=1), now)


def test_a_failure_note_is_cleaned_and_kept_short(session: Session) -> None:
    saved_row(session, "ntopng", "api")
    [item] = store.wanted(session, [Counting()])
    store.sync(session, [item], utcnow())
    now = utcnow()

    store.finish(
        session,
        item,
        now,
        now,
        "Line one\nline\ttwo " + "x" * 600,
        None,
        lambda n: timedelta(seconds=n),
    )
    session.commit()

    record = the_health(session)
    assert record.last_error is not None
    assert len(record.last_error) <= 500
    assert "\n" not in record.last_error
    assert record.next_run_at == now + timedelta(seconds=1)


# ---- What the check leaves on the connection ---------------------------------------------------


def test_what_a_check_found_is_not_kept_if_the_settings_changed_meanwhile(
    session: Session, settings: Settings, serve: Serve
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)
    row = service.rows_for(session, "crowdsec")["lapi"]
    target = service.load_target(
        session, settings, registry.INTEGRATIONS["crowdsec"], registry.CROWDSEC.connections[0], row
    )
    loaded = row.updated_at
    failed = Verdict(False, "It was refused.")

    connection_check.remember(session, target, failed, utcnow(), loaded - timedelta(seconds=1))
    assert row.last_attempt_at is None

    connection_check.remember(session, target, failed, utcnow(), loaded)
    assert row.last_error == "It was refused."


def test_what_a_check_found_of_a_connection_that_is_gone_is_dropped(
    session: Session, settings: Settings, serve: Serve
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)
    row = service.rows_for(session, "crowdsec")["lapi"]
    target = service.load_target(
        session, settings, registry.INTEGRATIONS["crowdsec"], registry.CROWDSEC.connections[0], row
    )
    service.disconnect(session, registry.INTEGRATIONS["crowdsec"])
    session.commit()

    connection_check.remember(session, target, Verdict(True, "Fine."), utcnow(), row.updated_at)

    assert service.rows_for(session, "crowdsec") == {}


def test_what_collectors_apply_to_follows_their_class(session: Session) -> None:
    assert Counting.reads("opnsense", "api")
    assert OnlyOpnsense.reads("opnsense", "api")
    assert not OnlyOpnsense.reads("ntopng", "api")
    assert OnlyWazuhIndexer.reads("wazuh", "indexer")
    assert not OnlyWazuhIndexer.reads("wazuh", "manager")


# ---- Running for as long as the worker does --------------------------------------------------


def test_it_keeps_collecting_until_it_is_stopped_and_says_it_is_alive(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)
    counting = Counting()

    async def scenario() -> int:
        scheduler = make(settings, engine, counting, timing=FAST)
        task = asyncio.create_task(scheduler.run())
        try:
            await until(lambda: counting.runs >= 3)
            assert session.get(WorkerBeat, WORKER) is not None
        finally:
            task.cancel()
            await asyncio.wait({task})
        runs = counting.runs
        await asyncio.sleep(0.1)
        return runs - counting.runs

    assert asyncio.run(scenario()) == 0
    assert the_health(session).last_items == 7


def test_disconnecting_an_integration_stops_what_collects_from_it(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)
    counting = Counting()

    async def scenario() -> int:
        task = asyncio.create_task(make(settings, engine, counting, timing=FAST).run())
        try:
            await until(lambda: counting.runs >= 2)
            service.disconnect(session, registry.INTEGRATIONS["crowdsec"])
            session.commit()
            await until(lambda: not health_rows(session))
            await asyncio.sleep(0.1)
            settled = counting.runs
            await asyncio.sleep(0.2)
            return counting.runs - settled
        finally:
            task.cancel()
            await asyncio.wait({task})

    assert asyncio.run(scenario()) == 0
    assert health_rows(session) == []


def test_saving_a_connection_again_runs_its_collectors_straight_away(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    server = serve(crowdsec(SECRET))
    connect(session, settings, server.url)
    hourly = Hourly()

    async def scenario() -> None:
        task = asyncio.create_task(make(settings, engine, hourly, timing=FAST).run())
        try:
            await until(lambda: hourly.runs == 1)
            await asyncio.sleep(0.15)
            assert hourly.runs == 1
            connect(session, settings, server.url)
            await until(lambda: hourly.runs == 2)
        finally:
            task.cancel()
            await asyncio.wait({task})

    asyncio.run(scenario())


def test_a_failing_collector_is_tried_again_after_the_retry_delay(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)
    declining = Declining()

    async def scenario() -> None:
        task = asyncio.create_task(make(settings, engine, declining, timing=FAST).run())
        try:
            await until(lambda: declining.runs >= 3)
            await until(lambda: the_health(session).consecutive_failures >= 3)
        finally:
            task.cancel()
            await asyncio.wait({task})

    asyncio.run(scenario())


def test_a_run_that_cannot_be_written_down_is_logged_and_tried_again(
    session: Session,
    settings: Settings,
    engine: Engine,
    serve: Serve,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)
    counting = Counting()

    def refuse(*args: object, **kwargs: object) -> int:
        raise RuntimeError("the database went away")

    monkeypatch.setattr(store, "finish", refuse)

    async def scenario() -> None:
        task = asyncio.create_task(make(settings, engine, counting, timing=FAST).run())
        try:
            await until(lambda: counting.runs >= 2)
        finally:
            task.cancel()
            await asyncio.wait({task})

    with caplog.at_level(logging.ERROR):
        asyncio.run(scenario())

    assert "Couldn't keep how counting went" in caplog.text


def test_a_database_that_is_not_there_does_not_stop_the_scheduler(
    settings: Settings, engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    def no_database() -> Session:
        raise RuntimeError("the database isn't up yet")

    scheduler = make(settings, engine, new_session=no_database)

    with caplog.at_level(logging.ERROR):
        asyncio.run(scheduler.tick())

    assert "couldn't reach the database" in caplog.text


def test_turned_off_it_says_it_is_alive_and_collects_nothing(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    connect(session, settings, serve(crowdsec(SECRET)).url)
    counting = Counting()

    async def scenario() -> None:
        scheduler = make(settings, engine, counting, enabled=False, timing=FAST)
        await scheduler.tick()
        await scheduler.tick()

    asyncio.run(scenario())

    assert session.get(WorkerBeat, WORKER) is not None
    assert counting.runs == 0
    assert health_rows(session) == []
