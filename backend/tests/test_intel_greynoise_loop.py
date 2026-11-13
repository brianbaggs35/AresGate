"""How GreyNoise is asked about the addresses of incidents: the limits of the plan its card
chooses, what is kept of its answers beside VirusTotal's and OTX's, and the loop that asks."""

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
from app.intel import budget, candidates, greynoise, otx, run, store, virustotal
from app.intel.answers import Reported, Throttled, Unknown
from app.models import IntegrationConnection, IntelLookup, IntelSubject
from app.models.base import utcnow
from tests.test_intel_lookups import fresh_incident, new_session_for

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
ADDRESS = ip_address("93.184.216.34")
REPORT = greynoise.Report(
    malicious=1,
    suspicious=0,
    harmless=0,
    undetected=0,
    reputation=0,
    analysed_at=NOW,
    details=(("Classification", "malicious"),),
)
OPTIONS = {"access": "key", "plan": "free"}


def test_each_plan_has_the_limits_of_its_allowance() -> None:
    anonymous = budget.GREYNOISE_LEVELS["anonymous"]
    free = budget.GREYNOISE_LEVELS["free"]
    subscription = budget.GREYNOISE_LEVELS["subscription"]

    # 10 lookups a day with no account, of which two are left over.
    assert (anonymous.per_day, anonymous.per_week) == (8, None)
    assert anonymous.background_spacing == timedelta(hours=3)
    # 50 searches a week for a free account, which the Visualizer shares: ten are left over.
    assert (free.per_week, free.per_day, free.per_month) == (40, None, None)
    assert free.background_spacing == timedelta(hours=4, minutes=15)
    # What a subscription allows isn't published, so it is only kept gentle.
    assert (subscription.per_day, subscription.per_week) == (None, None)
    assert subscription.background_spacing == timedelta(seconds=10)


def test_the_loops_lookups_fit_the_allowance_with_room_to_spare() -> None:
    # Spaced evenly, the loop asks 8 times a day without an account and 39 times a week with one.
    assert timedelta(days=1) / budget.GREYNOISE_LEVELS["anonymous"].background_spacing == 8
    free = budget.GREYNOISE_LEVELS["free"]
    assert timedelta(days=7) / free.background_spacing < (free.per_week or 0)


@pytest.mark.parametrize(
    ("options", "plan"),
    [
        ({}, greynoise.FREE),
        ({"access": "none"}, greynoise.ANONYMOUS),
        ({"access": "key", "plan": "subscription"}, greynoise.SUBSCRIPTION),
    ],
)
def test_the_plan_chosen_sets_the_limits(options: dict[str, str], plan: greynoise.Plan) -> None:
    assert budget.greynoise_level_of(options) is budget.GREYNOISE_LEVELS[plan]


def test_greynoise_holds_lookups_for_its_own_time_after_it_says_the_limit_is_reached() -> None:
    assert budget.THROTTLES[greynoise.PROVIDER] == greynoise.THROTTLE


def test_a_429_from_greynoise_pauses_greynoise_and_leaves_the_others_alone(
    session: Session,
) -> None:
    now = utcnow()
    session.add(
        IntelLookup(
            provider=greynoise.PROVIDER,
            address=ADDRESS,
            requested_at=now - timedelta(minutes=1),
            outcome=store.THROTTLED,
        )
    )
    session.flush()

    held = budget.paused(session, greynoise.PROVIDER, now)

    assert held is not None
    assert held.daily is False
    assert held.until == now - timedelta(minutes=1) + greynoise.THROTTLE
    assert budget.paused(session, otx.PROVIDER, now) is None
    assert budget.paused(session, virustotal.PROVIDER, now) is None


def test_the_weeks_allowance_holds_lookups_until_the_oldest_leaves_the_week(
    session: Session,
) -> None:
    now = utcnow()
    level = budget.GREYNOISE_LEVELS["free"]
    for days_ago in range(40):
        session.add(
            IntelLookup(
                provider=greynoise.PROVIDER,
                address=ADDRESS,
                requested_at=now - timedelta(days=6, hours=20) + timedelta(hours=days_ago),
                outcome=store.REPORTED,
            )
        )
    session.flush()

    wait = budget.wait_for(session, greynoise.PROVIDER, level, now)

    # The oldest was asked 6 days and 20 hours ago, so it leaves the week in four hours.
    assert wait == timedelta(hours=4)
    assert budget.may_look_up(session, greynoise.PROVIDER, level, now) is False


def test_the_judgement_of_a_report_is_the_services_own() -> None:
    assert store.judge_for(greynoise.PROVIDER, REPORT) == "malicious"
    assert store.judge_for(greynoise.PROVIDER, None) == "unknown"
    harmless = greynoise.Report(
        malicious=0, suspicious=0, harmless=1, undetected=0, reputation=0, analysed_at=NOW
    )
    assert store.judge_for(greynoise.PROVIDER, harmless) == "clean"
    # The same counts, read by each service's own rules.
    assert store.judge_for(otx.PROVIDER, harmless) == "unknown"


# -- who is asked about


def test_an_ipv6_address_is_never_chosen_for_a_service_that_takes_only_ipv4(
    session: Session,
) -> None:
    v6 = "2606:4700:4700::1111"
    fresh_incident(session, v6)

    assert candidates.next_address(session, greynoise.PROVIDER, utcnow()) == ip_address(v6)
    assert candidates.next_address(session, greynoise.PROVIDER, utcnow(), ipv4_only=True) is None


def test_an_ipv4_address_is_chosen_after_an_ipv6_one_for_a_service_that_takes_only_ipv4(
    session: Session,
) -> None:
    fresh_incident(session, "2606:4700:4700::1111", str(ADDRESS))

    chosen = candidates.next_address(session, greynoise.PROVIDER, utcnow(), ipv4_only=True)

    assert chosen == ADDRESS


# -- the loop


async def _record(_call: Call) -> None:
    pass  # Keeps nothing: the test needs only that the call was made.


def connect(session: Session, options: dict[str, str] | None = None) -> None:
    session.add(
        IntegrationConnection(
            integration="greynoise",
            connection="api",
            base_url="https://api.greynoise.io",
            tls_mode="system",
            options=options or OPTIONS,
            last_success_at=utcnow(),
        )
    )
    session.commit()


@pytest.fixture
def connected(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """A connected, tested GreyNoise connection whose secret opens."""
    origin = netguard.parse_origin("https://api.greynoise.io", allow_http=False)

    def load(*args: object, **kwargs: object) -> Target:
        del args, kwargs
        return Target(
            integration="greynoise",
            connection="api",
            origin=origin,
            tls_mode="system",
            tls_ca_pem=None,
            tls_fingerprint=None,
            options=OPTIONS,
            secrets={"api_key": "gn-key"},
        )

    monkeypatch.setattr(service, "load_target", load)
    connect(session)


def answering(monkeypatch: pytest.MonkeyPatch, answer: object) -> list[object]:
    """Makes GreyNoise answer with the answer given, or raise it. Returns the requests made."""
    asked: list[object] = []

    async def look_up(*args: object) -> object:
        asked.append(args)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(greynoise, "look_up", look_up)
    return asked


def go(session: Session, settings: Settings) -> bool:
    return asyncio.run(run.lookup_once(new_session_for(session), settings, _record, run.GREYNOISE))


def test_greynoise_is_one_of_the_services_the_loop_asks_and_takes_only_ipv4() -> None:
    assert run.GREYNOISE in run.FEEDS
    assert run.GREYNOISE.ipv4_only is True
    assert run.VIRUSTOTAL.ipv4_only is False
    assert run.ALIENVAULT_OTX.ipv4_only is False


def test_nothing_is_asked_of_greynoise_until_its_connection_has_been_tested(
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


def test_a_report_from_greynoise_is_kept_under_greynoise_and_asks_nothing_of_the_others(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))
    asked = answering(monkeypatch, Reported(report=REPORT))

    assert go(session, settings) is True

    assert len(asked) == 1
    session.expire_all()
    kept = store.report_for(session, greynoise.PROVIDER, ADDRESS)
    assert kept is not None
    assert (kept.malicious, kept.suspicious) == (1, 0)
    assert store.report_for(session, virustotal.PROVIDER, ADDRESS) is None
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert (lookup.provider, lookup.outcome) == (greynoise.PROVIDER, store.REPORTED)
    [row] = session.scalars(select(IntelSubject)).all()
    assert row.judgement == "malicious"


def test_an_ipv6_address_is_never_sent_to_greynoise_by_the_loop(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, "2606:4700:4700::1111")
    asked = answering(monkeypatch, Unknown())

    assert go(session, settings) is False
    assert asked == []


def test_greynoise_is_asked_even_when_the_others_have_answered_about_the_address(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))
    for provider in (virustotal.PROVIDER, otx.PROVIDER):
        session.add(
            IntelLookup(
                provider=provider,
                address=ADDRESS,
                requested_at=utcnow() - timedelta(minutes=10),
                outcome=store.REPORTED,
            )
        )
    session.commit()
    answering(monkeypatch, Unknown())

    assert go(session, settings) is True


def test_the_loop_leaves_hours_between_its_lookups_on_a_free_account(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))
    session.add(
        IntelLookup(
            provider=greynoise.PROVIDER,
            address=ip_address("1.1.1.1"),
            requested_at=utcnow() - timedelta(hours=1),
            outcome=store.REPORTED,
        )
    )
    session.commit()
    answering(monkeypatch, Unknown())

    assert go(session, settings) is False


def test_a_429_is_kept_and_greynoise_is_left_alone_until_it_lifts(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))
    answering(monkeypatch, Throttled(until=utcnow() + greynoise.THROTTLE))

    assert go(session, settings) is True
    session.expire_all()
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert lookup.outcome == store.THROTTLED
    assert go(session, settings) is False


def test_a_lookup_that_gets_no_answer_from_greynoise_is_kept_as_failed_and_logged(
    session: Session,
    settings: Settings,
    connected: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fresh_incident(session, str(ADDRESS))
    answering(monkeypatch, CallFailed("GreyNoise didn't answer in time."))

    with caplog.at_level(logging.INFO):
        assert go(session, settings) is True

    session.expire_all()
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert lookup.outcome == store.FAILED
    assert "A GreyNoise lookup didn't give a report" in caplog.text
