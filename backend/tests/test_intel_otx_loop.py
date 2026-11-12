"""How AlienVault OTX is asked about the addresses of incidents: the pace its card chooses, the
limit it asks for, what is kept of its answers beside VirusTotal's, and the loop that asks."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.integrations import netguard, service
from app.integrations.client import Call, CallFailed, Target
from app.intel import budget, otx, run, store, virustotal
from app.intel.answers import Reported, Throttled, Unknown
from app.models import IntegrationConnection, IntelLookup, IntelSubject
from app.models.base import utcnow
from tests.test_intel_lookups import fresh_incident, new_session_for

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
ADDRESS = ip_address("93.184.216.34")
REPORT = otx.Report(
    malicious=2,
    suspicious=1,
    harmless=0,
    undetected=0,
    reputation=-3,
    analysed_at=NOW,
    details=(("Pulses", "3"),),
)


def test_each_pace_sets_how_often_the_loop_asks_and_how_many_lookups_a_day() -> None:
    gentle, balanced, fast = (budget.OTX_PACES[name] for name in ("gentle", "balanced", "fast"))

    assert gentle.background_spacing == timedelta(seconds=90)
    assert balanced.background_spacing == timedelta(seconds=30)
    assert fast.background_spacing == timedelta(seconds=10)
    assert (gentle.per_day, balanced.per_day, fast.per_day) == (1_500, 5_000, 10_000)
    assert all(level.per_month is None for level in budget.OTX_PACES.values())


def test_the_pace_chosen_sets_the_limits_and_anything_else_is_balanced() -> None:
    assert budget.otx_level_of({"pace": "gentle"}) is budget.OTX_PACES["gentle"]
    assert budget.otx_level_of({"pace": "fast"}) is budget.OTX_PACES["fast"]
    assert budget.otx_level_of({"pace": "reckless"}) is budget.OTX_PACES["balanced"]
    assert budget.otx_level_of({}) is budget.OTX_PACES[budget.OTX_DEFAULT_PACE]


def test_each_service_holds_lookups_for_its_own_time_after_a_request_to_send_fewer() -> None:
    assert budget.THROTTLES[virustotal.PROVIDER] == virustotal.THROTTLE
    assert budget.THROTTLES[otx.PROVIDER] == otx.THROTTLE == timedelta(minutes=5)


def test_a_429_from_otx_pauses_otx_for_five_minutes_and_leaves_virustotal_alone(
    session: Session,
) -> None:
    now = utcnow()
    session.add(
        IntelLookup(
            provider=otx.PROVIDER,
            address=ADDRESS,
            requested_at=now - timedelta(minutes=1),
            outcome=store.THROTTLED,
        )
    )
    session.flush()

    held = budget.paused(session, otx.PROVIDER, now)

    assert held is not None
    assert held.daily is False
    assert held.until == now - timedelta(minutes=1) + otx.THROTTLE
    assert budget.paused(session, virustotal.PROVIDER, now) is None


def test_the_judgement_of_a_report_is_the_services_own() -> None:
    assert store.judge_for(otx.PROVIDER, REPORT) == "malicious"
    assert store.judge_for(virustotal.PROVIDER, REPORT) == "malicious"
    assert store.judge_for(otx.PROVIDER, None) == "unknown"
    lone = otx.Report(
        malicious=0, suspicious=1, harmless=0, undetected=0, reputation=0, analysed_at=NOW
    )
    assert store.judge_for(otx.PROVIDER, lone) == "suspicious"


# -- the loop


async def _record(_call: Call) -> None:
    pass  # Keeps nothing: the test needs only that the call was made.


def connect(session: Session, pace: str = "balanced") -> None:
    session.add(
        IntegrationConnection(
            integration="otx",
            connection="api",
            base_url="https://otx.alienvault.com",
            tls_mode="system",
            options={"pace": pace},
            last_success_at=utcnow(),
        )
    )
    session.commit()


@pytest.fixture
def connected(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """A connected, tested OTX connection whose secret opens."""
    origin = netguard.parse_origin("https://otx.alienvault.com", allow_http=False)

    def load(*args: object, **kwargs: object) -> Target:
        del args, kwargs
        return Target(
            integration="otx",
            connection="api",
            origin=origin,
            tls_mode="system",
            tls_ca_pem=None,
            tls_fingerprint=None,
            options={"pace": "balanced"},
            secrets={"api_key": "otx-key"},
        )

    monkeypatch.setattr(service, "load_target", load)
    connect(session)


def answering(monkeypatch: pytest.MonkeyPatch, answer: object) -> list[object]:
    """Makes OTX answer with the answer given, or raise it. Returns the requests made."""
    asked: list[object] = []

    async def look_up(*args: object) -> object:
        asked.append(args)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(otx, "look_up", look_up)
    return asked


def go(session: Session, settings: Settings) -> bool:
    return asyncio.run(
        run.lookup_once(new_session_for(session), settings, _record, run.ALIENVAULT_OTX)
    )


def test_nothing_is_asked_of_otx_until_its_connection_has_been_tested(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(session)
    row = session.scalars(select(IntegrationConnection)).one()
    row.last_success_at = None
    session.commit()
    fresh_incident(session, str(ADDRESS))
    asked = answering(monkeypatch, Unknown())

    assert go(session, settings) is False
    assert asked == []


def test_a_report_from_otx_is_kept_under_otx_and_asks_nothing_of_virustotal(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))
    asked = answering(monkeypatch, Reported(report=REPORT))

    assert go(session, settings) is True

    assert len(asked) == 1
    session.expire_all()
    kept = store.report_for(session, otx.PROVIDER, ADDRESS)
    assert kept is not None
    assert (kept.malicious, kept.suspicious) == (2, 1)
    assert store.report_for(session, virustotal.PROVIDER, ADDRESS) is None
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert (lookup.provider, lookup.outcome) == (otx.PROVIDER, store.REPORTED)
    [row] = session.scalars(select(IntelSubject)).all()
    assert row.judgement == "malicious"


def test_otx_is_asked_even_when_virustotal_has_answered_about_the_address(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))
    session.add(
        IntelLookup(
            provider=virustotal.PROVIDER,
            address=ADDRESS,
            requested_at=utcnow() - timedelta(minutes=10),
            outcome=store.REPORTED,
        )
    )
    session.commit()
    answering(monkeypatch, Unknown())

    assert go(session, settings) is True


def test_the_loop_waits_for_the_pace_chosen_between_its_lookups(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))
    session.add(
        IntelLookup(
            provider=otx.PROVIDER,
            address=ip_address("1.1.1.1"),
            requested_at=utcnow() - timedelta(seconds=10),
            outcome=store.REPORTED,
        )
    )
    session.commit()
    answering(monkeypatch, Unknown())

    assert go(session, settings) is False


def test_a_429_is_kept_and_otx_is_left_alone_until_it_lifts(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))
    answering(monkeypatch, Throttled(until=utcnow() + otx.THROTTLE))

    assert go(session, settings) is True
    session.expire_all()
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert lookup.outcome == store.THROTTLED
    assert go(session, settings) is False


def test_a_lookup_that_gets_no_answer_from_otx_is_kept_as_failed_and_logged(
    session: Session,
    settings: Settings,
    connected: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fresh_incident(session, str(ADDRESS))
    answering(monkeypatch, CallFailed("OTX didn't answer in time."))

    with caplog.at_level(logging.INFO):
        assert go(session, settings) is True

    session.expire_all()
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert lookup.outcome == store.FAILED
    assert "A AlienVault OTX lookup didn't give a report" in caplog.text


def test_the_loop_asks_every_service_and_one_failing_does_not_stop_the_other(
    session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    asked: list[str] = []

    async def once(*args: object) -> bool:
        feed = args[3]
        assert isinstance(feed, run.Feed)
        asked.append(feed.name)
        if feed is run.VIRUSTOTAL:
            raise RuntimeError("boom")
        return False

    monkeypatch.setattr(run, "lookup_once", once)

    async def looping() -> None:
        await asyncio.wait_for(
            run.run(new_session_for(session), settings, _record, interval=timedelta(seconds=0)),
            timeout=0.1,
        )

    with caplog.at_level(logging.ERROR), pytest.raises(TimeoutError):
        asyncio.run(looping())

    assert "VirusTotal" in asked
    assert "AlienVault OTX" in asked
    assert "Couldn't ask VirusTotal about an address" in caplog.text
