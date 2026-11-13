"""The loop that asks Fingerbank what each device is."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.fingerbank import lookup, run
from app.fingerbank.lookup import Failed, Identified, Identity, Throttled, Unknown
from app.integrations import netguard, service
from app.integrations.client import Call, Target
from app.models import Device, DeviceIdentity, IntegrationConnection
from app.models.base import utcnow
from e2e import factories
from e2e.factories import AssetSpec
from tests.test_intel_lookups import fresh_incident, new_session_for

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
IDENTITY = Identity("Apple iPhone 16", "Phone/Apple iPhone 16", "Apple, Inc.", "Apple iOS", 72, 5)


async def _record(_call: Call) -> None:
    pass  # Keeps nothing: the test needs only that the call was made.


def connect(session: Session, *, options: dict[str, str | int] | None = None) -> None:
    now = utcnow()
    session.add(
        IntegrationConnection(
            integration="fingerbank",
            connection="api",
            base_url="https://api.fingerbank.org",
            tls_mode="system",
            options=options if options is not None else {"incident_devices": "no"},
            last_attempt_at=now,
            last_success_at=now,
        )
    )
    session.commit()


@pytest.fixture
def connected(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """A connected, tested Fingerbank connection whose secret opens."""

    def load(
        _db: Session, _settings: Settings, _definition: object, _connection: object, row: object
    ) -> Target:
        assert isinstance(row, IntegrationConnection)
        return Target(
            integration="fingerbank",
            connection="api",
            origin=netguard.parse_origin("https://api.fingerbank.org", allow_http=False),
            tls_mode="system",
            tls_ca_pem=None,
            tls_fingerprint=None,
            options=row.options,
            secrets={"api_key": "fb-key"},
        )

    monkeypatch.setattr(service, "load_target", load)
    connect(session)


def devices(session: Session, *specs: AssetSpec) -> None:
    factories.assets(session, utcnow(), list(specs), [])
    session.commit()


def answering(monkeypatch: pytest.MonkeyPatch, answer: lookup.Answer) -> list[str]:
    """Makes Fingerbank answer with the answer given. Returns the hardware addresses asked about."""
    asked: list[str] = []

    async def ask(*args: object) -> lookup.Answer:
        asked.append(str(args[3]))
        return answer

    monkeypatch.setattr(lookup, "ask", ask)
    return asked


def go(session: Session, settings: Settings, pace: run.Pace | None = None) -> bool:
    return asyncio.run(run.lookup_once(new_session_for(session), settings, _record, pace))


def kept(session: Session) -> list[DeviceIdentity]:
    session.expire_all()
    return list(session.scalars(select(DeviceIdentity)))


def test_nothing_is_asked_until_the_connection_has_been_set_up_and_tested(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    devices(session, AssetSpec(addresses=("192.168.1.20",)))
    asked = answering(monkeypatch, Unknown())

    assert go(session, settings) is False
    connect(session)
    row = session.scalars(select(IntegrationConnection)).one()
    row.last_error = "Fingerbank didn't accept the key."
    session.commit()

    assert go(session, settings) is False
    assert asked == []


def test_a_device_is_asked_about_and_what_comes_back_is_kept(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    devices(session, AssetSpec(addresses=("192.168.1.20",)))
    asked = answering(monkeypatch, Identified(IDENTITY))

    assert go(session, settings) is True

    [mac] = session.scalars(select(Device.mac)).all()
    assert asked == [str(mac)]
    [row] = kept(session)
    assert (row.state, row.name, row.score, row.reason) == (
        "identified",
        IDENTITY.name,
        72,
        "asset",
    )


def test_a_device_with_no_match_is_kept_as_unknown(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    devices(session, AssetSpec(addresses=("192.168.1.20",)))
    answering(monkeypatch, Unknown())

    assert go(session, settings) is True

    assert [row.state for row in kept(session)] == ["unknown"]


def test_the_loop_waits_ten_seconds_between_its_requests(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    devices(
        session,
        AssetSpec(addresses=("192.168.1.20",)),
        AssetSpec(addresses=("192.168.1.21",)),
    )
    asked = answering(monkeypatch, Unknown())

    assert go(session, settings) is True
    assert go(session, settings) is False
    assert len(asked) == 1


def test_a_429_holds_lookups_and_keeps_nothing(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    devices(session, AssetSpec(addresses=("192.168.1.20",)))
    asked = answering(monkeypatch, Throttled(until=utcnow() + lookup.THROTTLE))
    pace = run.Pace()

    assert go(session, settings, pace) is True

    assert kept(session) == []
    assert pace.holding(utcnow())
    assert go(session, settings, pace) is False
    assert len(asked) == 1


def test_an_answer_that_could_not_be_had_is_logged_and_tried_again_in_a_minute(
    session: Session,
    settings: Settings,
    connected: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    devices(session, AssetSpec(addresses=("192.168.1.20",)))
    answering(monkeypatch, Failed("Fingerbank answered HTTP 502."))
    pace = run.Pace()

    with caplog.at_level(logging.INFO):
        assert go(session, settings, pace) is True

    assert "didn't give an answer: Fingerbank answered HTTP 502." in caplog.text
    assert kept(session) == []
    assert pace.until is not None
    assert pace.until - utcnow() <= lookup.RETRY
    row = session.scalars(select(IntegrationConnection)).one()
    assert row.last_error is None


def test_a_key_that_is_turned_down_is_shown_on_the_connection_and_stops_the_loop(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    devices(session, AssetSpec(addresses=("192.168.1.20",)))
    answering(monkeypatch, Failed("Fingerbank didn't accept the key.", refused=True))
    pace = run.Pace()

    assert go(session, settings, pace) is True

    session.expire_all()
    row = session.scalars(select(IntegrationConnection)).one()
    assert row.last_error == "Fingerbank didn't accept the key."
    assert go(session, settings, pace) is False
    assert go(session, settings) is False


def test_the_loop_rests_for_a_minute_when_every_device_has_an_answer(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    devices(session, AssetSpec(addresses=("192.168.1.20",)))
    asked = answering(monkeypatch, Unknown())
    pace = run.Pace()
    assert go(session, settings, pace) is True
    for row in session.scalars(select(DeviceIdentity)):
        row.checked_at = utcnow() - timedelta(minutes=1)
    session.commit()

    assert go(session, settings, pace) is False

    assert len(asked) == 1
    assert pace.holding(utcnow())
    assert not pace.holding(utcnow() + run.IDLE + timedelta(seconds=1))


def test_devices_in_incidents_are_asked_about_only_when_the_owner_allowed_it(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    devices(session, AssetSpec(addresses=("9.9.9.9",)))
    fresh_incident(session, "9.9.9.9")
    asked = answering(monkeypatch, Unknown())

    assert go(session, settings) is False
    assert asked == []

    row = session.scalars(select(IntegrationConnection)).one()
    row.options = {"incident_devices": "yes"}
    session.commit()

    assert go(session, settings) is True
    [kept_row] = kept(session)
    assert kept_row.reason == "incident"


def test_the_setting_is_read_from_the_connection() -> None:
    def target(options: dict[str, str | int]) -> Target:
        return Target(
            integration="fingerbank",
            connection="api",
            origin=netguard.parse_origin("https://api.fingerbank.org", allow_http=False),
            tls_mode="system",
            tls_ca_pem=None,
            tls_fingerprint=None,
            options=options,
            secrets={},
        )

    assert run.incident_devices(target({"incident_devices": "yes"}))
    assert not run.incident_devices(target({"incident_devices": "no"}))
    assert not run.incident_devices(target({}))


def test_the_loop_keeps_going_when_one_lookup_fails(
    session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls = 0

    async def once(*args: object) -> bool:
        nonlocal calls
        del args
        calls += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(run, "lookup_once", once)

    async def looping() -> None:
        await asyncio.wait_for(
            run.run(new_session_for(session), settings, _record, interval=timedelta(seconds=0)),
            timeout=0.1,
        )

    loop = looping()
    with caplog.at_level(logging.ERROR), pytest.raises(TimeoutError):
        asyncio.run(loop)

    assert calls > 1
    assert "Couldn't ask Fingerbank about a device" in caplog.text


def test_nothing_is_asked_while_collecting_is_off(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    async def once(*args: object) -> bool:
        nonlocal called
        del args
        called = True
        return False

    monkeypatch.setattr(run, "lookup_once", once)

    async def looping() -> None:
        await asyncio.wait_for(
            run.run(
                new_session_for(session),
                settings,
                _record,
                enabled=False,
                interval=timedelta(seconds=0),
            ),
            timeout=0.05,
        )

    loop = looping()
    with pytest.raises(TimeoutError):
        asyncio.run(loop)

    assert called is False


def test_nothing_is_asked_when_the_key_can_no_longer_be_opened(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def gone(*_: object) -> Target:
        raise service.Incomplete("The stored key can't be read.")

    monkeypatch.setattr(service, "load_target", gone)
    connect(session)
    devices(session, AssetSpec(addresses=("192.168.1.20",)))
    asked = answering(monkeypatch, Unknown())

    assert go(session, settings) is False
    assert asked == []
