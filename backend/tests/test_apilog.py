import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.integrations import apilog, calldetail
from app.integrations.apilog import ApiLogRecorder
from app.integrations.client import Call
from app.models import ApiCall

NOW = datetime(2099, 1, 1, 12, 0, tzinfo=UTC)


def add(
    db: Session,
    *,
    integration: str = "opnsense",
    connection: str = "api",
    method: str = "GET",
    status: int | None = 200,
    error: str | None = None,
    at: datetime = NOW,
) -> int:
    call = ApiCall(
        occurred_at=at,
        integration=integration,
        connection=connection,
        method=method,
        path="/x",
        status_code=status,
        duration_ms=3,
        error=error,
    )
    db.add(call)
    db.commit()
    return call.id


def ids(page: apilog.Page) -> list[int]:
    return [call.id for call in page.calls]


def test_a_call_is_written_in_a_session_of_its_own(session: Session) -> None:
    recorder = ApiLogRecorder(sessionmaker(bind=session.get_bind()))
    call = Call(
        NOW, "wazuh", "manager", "POST", "/security/user/authenticate", 401, 12, "Unauthorized"
    )

    asyncio.run(recorder(call))

    [saved] = apilog.list_calls(session, "wazuh").calls
    assert (saved.occurred_at, saved.connection, saved.method) == (NOW, "manager", "POST")
    assert (saved.path, saved.status_code, saved.duration_ms) == (call.path, 401, 12)
    assert saved.error == "Unauthorized"


def test_calls_come_newest_first_for_one_integration(session: Session) -> None:
    first = add(session)
    other = add(session, integration="ntopng")
    last = add(session)

    assert ids(apilog.list_calls(session, "opnsense")) == [last, first]
    assert ids(apilog.list_calls(session, "ntopng")) == [other]
    assert ids(apilog.list_calls(session, "wazuh")) == []


def test_the_list_can_be_narrowed(session: Session) -> None:
    ok = add(session, method="GET", at=NOW)
    broke = add(
        session, method="POST", status=500, error="Internal Server Error", at=NOW + timedelta(1)
    )
    refused = add(
        session, connection="zenarmor", status=None, error="refused", at=NOW + timedelta(2)
    )

    def listed(**filters: object) -> list[int]:
        return ids(apilog.list_calls(session, "opnsense", **filters))  # type: ignore[arg-type]

    assert listed(connection="zenarmor") == [refused]
    assert listed(method="post") == [broke]
    assert listed(failed=True) == [refused, broke]
    assert listed(failed=False) == [ok]
    assert listed(since=NOW + timedelta(1)) == [refused, broke]
    assert listed(until=NOW + timedelta(1)) == [ok]
    assert listed(before=refused) == [broke, ok]


def test_a_long_list_is_paged(session: Session) -> None:
    added = [add(session) for _ in range(5)]

    first = apilog.list_calls(session, "opnsense", limit=2)
    second = apilog.list_calls(session, "opnsense", limit=2, before=first.next_before)
    third = apilog.list_calls(session, "opnsense", limit=2, before=second.next_before)

    assert ids(first) == [added[4], added[3]]
    assert first.next_before == added[3]
    assert ids(second) == [added[2], added[1]]
    assert ids(third) == [added[0]]
    assert third.next_before is None


def test_the_calls_past_the_retention_period_are_deleted(
    session: Session, settings: Settings
) -> None:
    old = add(session, at=NOW - timedelta(days=settings.api_log_retention_days, seconds=1))
    kept = add(
        session, at=NOW - timedelta(days=settings.api_log_retention_days) + timedelta(seconds=1)
    )

    assert apilog.purge_expired(session, settings, NOW) == 1

    assert ids(apilog.list_calls(session, "opnsense")) == [kept]
    assert old not in ids(apilog.list_calls(session, "opnsense"))
    assert apilog.purge_expired(session, settings, NOW) == 0


# -- what is kept of a call to show it


def recorded(session: Session, **fields: object) -> ApiCall:
    """Writes a call as the client does, and returns the row."""
    recorder = ApiLogRecorder(sessionmaker(bind=session.get_bind()))
    base = Call(NOW, "wazuh", "manager", "GET", "/x", 200, 5, None)
    asyncio.run(recorder(replace(base, **fields)))
    session.expire_all()
    return session.scalars(select(ApiCall).order_by(ApiCall.id.desc())).first() or ApiCall()


def test_the_detail_and_the_start_of_the_answer_are_kept_with_the_call(session: Session) -> None:
    saved = recorded(session, detail={"host": "10.0.0.1"}, excerpt="fine")

    assert (saved.detail, saved.excerpt) == ({"host": "10.0.0.1"}, "fine")


def test_a_call_gets_its_detail_back_by_its_id_and_its_integration(session: Session) -> None:
    saved = recorded(session, detail={"host": "10.0.0.1"})

    assert apilog.get_call(session, "wazuh", saved.id) == saved
    assert apilog.get_call(session, "opnsense", saved.id) is None
    assert apilog.get_call(session, "wazuh", saved.id + 1) is None


def excerpts(session: Session, connection: str = "manager") -> list[bool]:
    """Whether each call of the connection, oldest first, still has the start of its answer."""
    session.expire_all()
    rows = session.scalars(
        select(ApiCall).where(ApiCall.connection == connection).order_by(ApiCall.id)
    )
    return [row.excerpt is not None for row in rows]


def test_the_answers_of_only_the_latest_calls_that_worked_are_kept(session: Session) -> None:
    for number in range(calldetail.KEPT_WHEN_WORKED + 3):
        recorded(session, excerpt=f"answer {number}")

    kept = excerpts(session)
    assert kept == [False] * 3 + [True] * calldetail.KEPT_WHEN_WORKED


def test_the_answers_of_calls_that_failed_are_all_kept(session: Session) -> None:
    for number in range(calldetail.KEPT_WHEN_WORKED + 3):
        recorded(
            session, excerpt=f"answer {number}", status_code=500, error="Internal Server Error"
        )
    recorded(session, excerpt="worked")

    assert all(excerpts(session))


def test_another_connections_answers_are_left_alone(session: Session) -> None:
    recorded(session, connection="indexer", excerpt="mine")
    for number in range(calldetail.KEPT_WHEN_WORKED + 3):
        recorded(session, excerpt=f"answer {number}")

    assert excerpts(session, "indexer") == [True]
