"""The lookups AresGate makes of VirusTotal: what the limits allow, what is kept of them, which
address is asked about next, and the loop that makes them."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address, ip_network
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.integrations import netguard, service
from app.integrations.client import Call, CallFailed, Target
from app.intel import budget, candidates, run, store, subjects, virustotal
from app.models import Incident, IntegrationConnection, IntelLookup, IntelSubject, Interface
from app.models.base import utcnow
from tests.test_incidents_search import incident as make_incident

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
PROVIDER = virustotal.PROVIDER
ADDRESS = ip_address("93.184.216.34")
OTHER = ip_address("1.1.1.1")
HOME = ip_address("192.168.1.20")
WAN = ip_address("8.8.4.4")
REPORT = virustotal.Report(
    malicious=3,
    suspicious=1,
    harmless=60,
    undetected=20,
    reputation=-12,
    analysed_at=NOW - timedelta(days=2),
    country="NL",
    owner="Example Hosting",
    asn=64500,
)


def lookup_at(
    session: Session,
    when: datetime,
    *,
    address: str = str(ADDRESS),
    outcome: str = store.REPORTED,
    provider: str = PROVIDER,
) -> IntelLookup:
    row = IntelLookup(
        provider=provider,
        address=ip_address(address),
        requested_at=when,
        outcome=outcome,
    )
    session.add(row)
    session.flush()
    return row


def incident(session: Session, addresses: list[str], last_seen: datetime) -> Incident:
    return make_incident(
        session,
        addresses[0],
        addresses=[ip_address(address) for address in addresses],
        first_seen_at=last_seen - timedelta(minutes=5),
        last_seen_at=last_seen,
    )


def interface(session: Session, role: str, networks: list[Any]) -> Interface:
    row = Interface(name=f"{role} side", role=role, networks=networks)
    session.add(row)
    session.flush()
    return row


# -- the limits


def test_lookups_are_spaced_by_the_spacing_of_the_access_level(session: Session) -> None:
    lookup_at(session, NOW - timedelta(seconds=10))

    assert not budget.may_look_up(session, PROVIDER, budget.FREE, NOW)
    assert budget.may_look_up(session, PROVIDER, budget.FREE, NOW + timedelta(seconds=5))


def test_premium_lookups_are_only_a_second_apart(session: Session) -> None:
    lookup_at(session, NOW - timedelta(seconds=2))

    assert budget.may_look_up(session, PROVIDER, budget.PREMIUM, NOW)


def test_the_lookups_of_another_provider_do_not_space_these(session: Session) -> None:
    lookup_at(session, NOW - timedelta(seconds=1), provider="another")

    assert budget.may_look_up(session, PROVIDER, budget.FREE, NOW)


def test_the_day_allowance_counts_the_lookups_of_the_last_day(session: Session) -> None:
    level = budget.Level(spacing=timedelta(0), per_day=2, per_month=None)
    lookup_at(session, NOW - timedelta(hours=1))
    assert budget.may_look_up(session, PROVIDER, level, NOW)

    lookup_at(session, NOW - timedelta(hours=2))

    assert not budget.may_look_up(session, PROVIDER, level, NOW)


def test_lookups_older_than_a_day_do_not_use_up_the_day(session: Session) -> None:
    level = budget.Level(spacing=timedelta(0), per_day=1, per_month=None)
    lookup_at(session, NOW - timedelta(days=2))

    assert budget.may_look_up(session, PROVIDER, level, NOW)


def test_the_month_allowance_counts_the_lookups_of_the_last_thirty_days(session: Session) -> None:
    level = budget.Level(spacing=timedelta(0), per_day=None, per_month=1)
    lookup_at(session, NOW - timedelta(days=31))
    assert budget.may_look_up(session, PROVIDER, level, NOW)

    lookup_at(session, NOW - timedelta(days=3))

    assert not budget.may_look_up(session, PROVIDER, level, NOW)


def test_the_access_level_chosen_sets_the_limits() -> None:
    assert budget.level_of({"tier": "premium"}) is budget.PREMIUM
    assert budget.level_of({"tier": "free"}) is budget.FREE
    assert budget.level_of({}) is budget.FREE
    assert budget.FREE.spacing == timedelta(seconds=15)
    assert budget.FREE.per_day == 500
    assert budget.FREE.per_month == 15_000
    assert budget.PREMIUM.per_day is None
    assert budget.PREMIUM.per_month is None


# -- what is kept


def test_a_request_is_kept_as_pending_before_it_is_made(session: Session) -> None:
    lookup_id = store.record(session, PROVIDER, ADDRESS, NOW)

    row = session.get(IntelLookup, lookup_id)
    assert row is not None
    assert (row.provider, row.address, row.requested_at, row.outcome) == (
        PROVIDER,
        ADDRESS,
        NOW,
        store.PENDING,
    )


@pytest.mark.parametrize(
    ("answer", "outcome", "kept"),
    [
        (virustotal.Unknown(), store.UNKNOWN, True),
        (virustotal.Failed("no answer"), store.FAILED, False),
    ],
)
def test_an_answer_without_a_report_is_kept_as_unknown_and_a_failure_is_not_kept(
    session: Session, answer: virustotal.Answer, outcome: str, kept: bool
) -> None:
    subject = subjects.of_address(ADDRESS)
    lookup_id = store.record(session, PROVIDER, ADDRESS, NOW)

    store.finish(session, lookup_id, subject, answer, NOW)

    row = session.get(IntelLookup, lookup_id)
    assert row is not None
    assert row.outcome == outcome
    assert store.report_for(session, PROVIDER, ADDRESS) is None
    assert (store.cached(session, PROVIDER, subject, NOW) is not None) == kept


@pytest.mark.parametrize(
    ("answer", "outcome"),
    [
        (virustotal.Limited(until=NOW + timedelta(hours=12)), store.LIMITED),
        (virustotal.Throttled(until=NOW + timedelta(minutes=1)), store.THROTTLED),
    ],
)
def test_a_limit_is_kept_on_its_lookup_and_keeps_no_answer_about_the_subject(
    session: Session, answer: virustotal.Answer, outcome: str
) -> None:
    subject = subjects.of_address(ADDRESS)
    lookup_id = store.record(session, PROVIDER, ADDRESS, NOW)

    store.finish(session, lookup_id, subject, answer, NOW)

    row = session.get(IntelLookup, lookup_id)
    assert row is not None
    assert row.outcome == outcome
    assert store.cached(session, PROVIDER, subject, NOW) is None


def test_a_report_is_kept_with_the_lookup_that_brought_it(session: Session) -> None:
    lookup_id = store.record(session, PROVIDER, ADDRESS, NOW)

    store.finish(
        session, lookup_id, subjects.of_address(ADDRESS), virustotal.Reported(report=REPORT), NOW
    )

    row = session.get(IntelLookup, lookup_id)
    assert row is not None
    assert row.outcome == store.REPORTED
    kept = store.report_for(session, PROVIDER, ADDRESS)
    assert kept is not None
    assert (kept.malicious, kept.owner, kept.asn) == (3, "Example Hosting", 64500)


def test_finishing_a_lookup_that_is_not_kept_changes_nothing(session: Session) -> None:
    store.finish(session, 999_999, subjects.of_address(ADDRESS), virustotal.Unknown(), NOW)

    assert session.get(IntelLookup, 999_999) is None
    assert session.scalars(select(IntelSubject)).all() == []


def test_a_newer_report_replaces_the_one_kept_for_the_address(session: Session) -> None:
    subject = subjects.of_address(ADDRESS)
    store.keep(session, PROVIDER, subject, virustotal.Reported(REPORT), NOW)
    store.keep(session, PROVIDER, subject, virustotal.Reported(replace(REPORT, malicious=9)), NOW)

    kept = session.scalars(select(IntelSubject)).all()
    assert [row.malicious for row in kept] == [9]


def test_reports_are_found_for_the_addresses_asked_about(session: Session) -> None:
    store.keep(session, PROVIDER, subjects.of_address(ADDRESS), virustotal.Reported(REPORT), NOW)
    store.keep(session, "another", subjects.of_address(ADDRESS), virustotal.Reported(REPORT), NOW)

    assert store.reports_for(session, PROVIDER, []) == []
    found = store.reports_for(session, PROVIDER, [ADDRESS, ip_address("198.51.100.10")])
    assert [row.subject for row in found] == [str(ADDRESS)]


def test_an_answer_with_no_report_is_not_a_report_for_the_address(session: Session) -> None:
    store.keep(session, PROVIDER, subjects.of_address(ADDRESS), virustotal.Unknown(), NOW)

    assert store.report_for(session, PROVIDER, ADDRESS) is None
    assert store.reports_for(session, PROVIDER, [ADDRESS]) == []


CLEAN = replace(REPORT, malicious=0, suspicious=0)


def test_an_answer_no_engine_flagged_is_fresh_for_a_week(session: Session) -> None:
    subject = subjects.of_address(ADDRESS)
    store.keep(session, PROVIDER, subject, virustotal.Reported(CLEAN), NOW)

    assert store.cached(session, PROVIDER, subject, NOW + store.FRESH - timedelta(hours=1))
    assert store.cached(session, PROVIDER, subject, NOW + store.FRESH) is None
    assert store.kept(session, PROVIDER, subject) is not None


@pytest.mark.parametrize(
    "answer",
    [
        virustotal.Reported(REPORT),
        virustotal.Reported(replace(REPORT, malicious=0)),
        virustotal.Unknown(),
    ],
)
def test_a_flagged_answer_or_one_with_no_report_is_asked_about_again_sooner(
    session: Session, answer: store.Answered
) -> None:
    subject = subjects.of_address(ADDRESS)
    store.keep(session, PROVIDER, subject, answer, NOW)

    [row] = session.scalars(select(IntelSubject)).all()
    assert store.fresh_until(row) == NOW + store.SOONER
    assert store.cached(session, PROVIDER, subject, NOW + store.SOONER - timedelta(hours=1))
    assert store.cached(session, PROVIDER, subject, NOW + store.SOONER) is None


def test_a_subject_with_nothing_kept_has_no_answer(session: Session) -> None:
    assert store.kept(session, PROVIDER, subjects.of_address(ADDRESS)) is None


def test_a_newer_answer_keeps_when_the_subject_was_first_asked_about_and_how_often(
    session: Session,
) -> None:
    subject = subjects.of_address(ADDRESS)
    store.keep(session, PROVIDER, subject, virustotal.Reported(REPORT), NOW)
    store.keep(session, PROVIDER, subject, virustotal.Reported(REPORT), NOW + timedelta(days=3))

    [row] = session.scalars(select(IntelSubject)).all()
    assert (row.first_checked_at, row.checked_at) == (NOW, NOW + timedelta(days=3))
    assert (row.checks, row.judgement, row.host) == (2, "malicious", str(ADDRESS))
    assert (row.changed_at, row.previous_judgement) == (None, None)


def test_a_newer_answer_that_changes_the_judgement_says_when_and_from_what(
    session: Session,
) -> None:
    subject = subjects.of_address(ADDRESS)
    later = NOW + timedelta(days=3)
    store.keep(session, PROVIDER, subject, virustotal.Reported(CLEAN), NOW)
    store.keep(session, PROVIDER, subject, virustotal.Reported(REPORT), later)
    store.keep(session, PROVIDER, subject, virustotal.Reported(REPORT), later + timedelta(days=3))

    [row] = session.scalars(select(IntelSubject)).all()
    assert (row.checks, row.judgement) == (3, "malicious")
    assert (row.changed_at, row.previous_judgement) == (later, "clean")


def test_a_web_address_kept_before_its_host_was_gets_its_host_from_a_newer_answer(
    session: Session,
) -> None:
    subject = subjects.parse("https://example.com/login")
    store.keep(session, PROVIDER, subject, virustotal.Unknown(), NOW)
    [row] = session.scalars(select(IntelSubject)).all()
    assert row.host == "example.com"
    row.host = None
    session.flush()

    store.keep(session, PROVIDER, subject, virustotal.Unknown(), NOW + timedelta(days=1))

    session.refresh(row)
    assert row.host == "example.com"


def test_a_kept_answer_is_given_back_as_it_was_given(session: Session) -> None:
    report = replace(
        REPORT,
        categories=("malware", "phishing"),
        details=(("Owner", "Example Hosting"), ("Network", "AS64500")),
    )
    subject = subjects.of_address(ADDRESS)
    store.keep(session, PROVIDER, subject, virustotal.Reported(report), NOW)

    kept = store.cached(session, PROVIDER, subject, NOW)
    assert kept is not None
    assert store.answer_of(kept) == virustotal.Reported(report=report)


def test_a_kept_answer_with_no_report_is_given_back_as_unknown(session: Session) -> None:
    subject = subjects.of_address(ADDRESS)
    store.keep(session, PROVIDER, subject, virustotal.Unknown(), NOW)

    kept = store.cached(session, PROVIDER, subject, NOW)
    assert kept is not None
    assert store.answer_of(kept) == virustotal.Unknown()


def test_a_web_address_is_kept_as_the_hash_of_its_text(session: Session) -> None:
    subject = subjects.parse("https://example.com/login?next=1")
    store.keep(session, PROVIDER, subject, virustotal.Unknown(), NOW)

    [kept] = session.scalars(select(IntelSubject)).all()
    assert (kept.kind, kept.subject) == ("url", subjects.url_key(subject.text))
    assert kept.subject != subject.text


def test_lookups_older_than_the_keep_period_are_forgotten(session: Session) -> None:
    old = lookup_at(session, NOW - store.KEEP - timedelta(days=1))
    recent = lookup_at(session, NOW - timedelta(days=1))
    other = lookup_at(session, NOW - store.KEEP - timedelta(days=1), provider="another")

    store.prune(session, PROVIDER, NOW)

    remaining = set(session.scalars(select(IntelLookup.id)).all())
    assert recent.id in remaining
    assert other.id in remaining
    assert old.id not in remaining


# -- which address is next


def test_the_own_networks_are_the_ones_on_the_internet_side(session: Session) -> None:
    interface(session, "internet", ["8.8.4.0/24", "not a network", 7])
    interface(session, "home", ["192.168.1.0/24"])

    assert candidates.own_networks(session) == (ip_network("8.8.4.0/24"),)


def test_the_first_public_address_of_the_most_recent_incident_is_next(session: Session) -> None:
    incident(session, [str(HOME), str(ADDRESS)], NOW - timedelta(hours=1))
    incident(session, [str(OTHER)], NOW - timedelta(hours=3))

    assert candidates.next_address(session, PROVIDER, NOW) == ADDRESS


def test_an_address_on_the_home_s_own_internet_side_is_never_next(session: Session) -> None:
    interface(session, "internet", ["8.8.4.0/24"])
    incident(session, [str(WAN)], NOW - timedelta(hours=1))

    assert candidates.next_address(session, PROVIDER, NOW) is None


def test_the_home_network_is_never_asked_about(session: Session) -> None:
    incident(session, [str(HOME)], NOW - timedelta(hours=1))

    assert candidates.next_address(session, PROVIDER, NOW) is None


def answer_at(
    session: Session,
    when: datetime,
    *,
    address: str = str(ADDRESS),
    answer: store.Answered | None = None,
    provider: str = PROVIDER,
) -> None:
    """Keeps an answer about an address as it was given at a time, a flagged report by default."""
    subject = subjects.of_address(ip_address(address))
    store.keep(session, provider, subject, answer or virustotal.Reported(REPORT), when)


@pytest.mark.parametrize(
    "answer", [virustotal.Reported(REPORT), virustotal.Reported(CLEAN), virustotal.Unknown()]
)
def test_an_address_whose_answer_is_fresh_is_not_asked_about_again(
    session: Session, answer: store.Answered
) -> None:
    incident(session, [str(ADDRESS)], NOW - timedelta(hours=1))
    answer_at(session, NOW - timedelta(days=1), answer=answer)

    assert candidates.next_address(session, PROVIDER, NOW) is None


def test_an_answer_that_is_no_longer_fresh_is_asked_about_again(session: Session) -> None:
    incident(session, [str(ADDRESS)], NOW - timedelta(hours=1))
    answer_at(session, NOW - timedelta(days=8), answer=virustotal.Reported(CLEAN))

    assert candidates.next_address(session, PROVIDER, NOW) == ADDRESS


def test_a_flagged_address_is_asked_about_again_sooner_than_a_clean_one(session: Session) -> None:
    incident(session, [str(ADDRESS), str(OTHER)], NOW - timedelta(hours=1))
    answer_at(session, NOW - timedelta(days=3))
    answer_at(
        session, NOW - timedelta(days=3), address=str(OTHER), answer=virustotal.Reported(CLEAN)
    )

    assert candidates.next_address(session, PROVIDER, NOW) == ADDRESS


def test_an_address_with_no_answer_comes_before_one_whose_answer_is_no_longer_fresh(
    session: Session,
) -> None:
    incident(session, [str(ADDRESS)], NOW - timedelta(hours=1))
    incident(session, [str(OTHER)], NOW - timedelta(hours=3))
    answer_at(session, NOW - timedelta(days=8))

    assert candidates.next_address(session, PROVIDER, NOW) == OTHER


def test_the_answer_that_stopped_being_fresh_longest_ago_is_asked_about_first(
    session: Session,
) -> None:
    incident(session, [str(ADDRESS)], NOW - timedelta(hours=1))
    incident(session, [str(OTHER)], NOW - timedelta(hours=3))
    answer_at(session, NOW - timedelta(days=4))
    answer_at(session, NOW - timedelta(days=6), address=str(OTHER))

    assert candidates.next_address(session, PROVIDER, NOW) == OTHER


def test_an_address_asked_about_within_the_hour_waits_even_if_its_answer_is_old(
    session: Session,
) -> None:
    incident(session, [str(ADDRESS)], NOW - timedelta(hours=1))
    answer_at(session, NOW - timedelta(days=8))
    lookup_at(session, NOW - timedelta(minutes=30), outcome=store.LIMITED)

    assert candidates.next_address(session, PROVIDER, NOW) is None


def test_a_failed_lookup_is_tried_again_after_an_hour(session: Session) -> None:
    incident(session, [str(ADDRESS)], NOW - timedelta(hours=1))
    lookup_at(session, NOW - timedelta(minutes=30), outcome=store.FAILED)
    assert candidates.next_address(session, PROVIDER, NOW) is None

    session.query(IntelLookup).delete()
    lookup_at(session, NOW - timedelta(hours=2), outcome=store.FAILED)

    assert candidates.next_address(session, PROVIDER, NOW) == ADDRESS


def test_the_lookups_of_another_provider_do_not_stop_an_address(session: Session) -> None:
    incident(session, [str(ADDRESS)], NOW - timedelta(hours=1))
    lookup_at(session, NOW - timedelta(minutes=5), provider="another")
    answer_at(session, NOW - timedelta(days=1), provider="another")

    assert candidates.next_address(session, PROVIDER, NOW) == ADDRESS


def test_incidents_not_seen_for_a_week_are_not_looked_through(session: Session) -> None:
    incident(session, [str(ADDRESS)], NOW - timedelta(days=8))

    assert candidates.next_address(session, PROVIDER, NOW) is None


def test_no_incidents_means_no_address_to_ask_about(session: Session) -> None:
    assert candidates.next_address(session, PROVIDER, NOW) is None


# -- the lookups themselves


def connect(session: Session, *, tested: bool = True, tier: str = "free") -> None:
    session.add(
        IntegrationConnection(
            integration="virustotal",
            connection="api",
            base_url="https://www.virustotal.com",
            tls_mode="system",
            options={"tier": tier},
            last_success_at=utcnow() if tested else None,
        )
    )
    session.commit()


def fresh_incident(session: Session, *addresses: str) -> None:
    incident(session, list(addresses), utcnow() - timedelta(minutes=5))
    session.commit()


def new_session_for(session: Session) -> Callable[[], Session]:
    return sessionmaker(bind=session.get_bind(), expire_on_commit=False)


@pytest.fixture
def connected(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """A connected, tested VirusTotal connection whose secret opens."""
    origin = netguard.parse_origin("https://www.virustotal.com", allow_http=False)

    def load(*args: object, **kwargs: object) -> Target:
        del args, kwargs
        return Target(
            integration="virustotal",
            connection="api",
            origin=origin,
            tls_mode="system",
            tls_ca_pem=None,
            tls_fingerprint=None,
            options={"tier": "free"},
            secrets={"api_key": "vt-key"},
        )

    monkeypatch.setattr(service, "load_target", load)
    connect(session)


def answering(monkeypatch: pytest.MonkeyPatch, answer: object) -> list[object]:
    """Makes VirusTotal answer with the answer given, or raise it. Returns the requests made."""
    asked: list[object] = []

    async def look_up(*args: object) -> object:
        asked.append(args)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(virustotal, "look_up", look_up)
    return asked


def test_nothing_is_asked_until_the_connection_has_been_tested(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(session, tested=False)
    fresh_incident(session, str(ADDRESS))
    answering(monkeypatch, virustotal.Unknown())

    asked = asyncio.run(run.lookup_once(new_session_for(session), settings, _record))

    assert asked is False


def test_nothing_is_asked_without_a_connection(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))

    assert asyncio.run(run.lookup_once(new_session_for(session), settings, _record)) is False


def test_nothing_is_asked_while_the_spacing_has_not_passed(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))
    lookup_at(session, utcnow() - timedelta(seconds=1))
    session.commit()

    assert asyncio.run(run.lookup_once(new_session_for(session), settings, _record)) is False


def test_the_loop_waits_four_minutes_between_its_lookups_on_the_free_key(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))
    lookup_at(session, utcnow() - timedelta(minutes=1), address=str(OTHER))
    session.commit()
    answering(monkeypatch, virustotal.Unknown())

    assert asyncio.run(run.lookup_once(new_session_for(session), settings, _record)) is False


def test_the_loop_asks_once_four_minutes_have_passed_on_the_free_key(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))
    lookup_at(session, utcnow() - timedelta(minutes=5), address=str(OTHER))
    session.commit()
    answering(monkeypatch, virustotal.Unknown())

    assert asyncio.run(run.lookup_once(new_session_for(session), settings, _record)) is True
    session.expire_all()
    kept = session.scalars(select(IntelSubject)).all()
    assert [(row.kind, row.subject, row.outcome) for row in kept] == [
        ("ip", str(ADDRESS), store.UNKNOWN)
    ]


def test_nothing_is_asked_when_no_address_may_be_sent(
    session: Session, settings: Settings, connected: None
) -> None:
    fresh_incident(session, str(HOME))

    assert asyncio.run(run.lookup_once(new_session_for(session), settings, _record)) is False


def test_nothing_is_asked_when_the_secret_cannot_be_opened(
    session: Session,
    settings: Settings,
    connected: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fresh_incident(session, str(ADDRESS))

    def gone(*args: object, **kwargs: object) -> Target:
        del args, kwargs
        raise service.Incomplete("The API key isn't kept any more.")

    monkeypatch.setattr(service, "load_target", gone)

    assert asyncio.run(run.lookup_once(new_session_for(session), settings, _record)) is False


def test_a_report_brought_back_is_kept_for_the_address(
    session: Session,
    settings: Settings,
    connected: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fresh_incident(session, str(ADDRESS))
    answering(monkeypatch, virustotal.Reported(report=REPORT))

    asked = asyncio.run(run.lookup_once(new_session_for(session), settings, _record))

    assert asked is True
    session.expire_all()
    kept = store.report_for(session, PROVIDER, ADDRESS)
    assert kept is not None
    assert kept.malicious == 3
    [row] = session.scalars(select(IntelLookup)).all()
    assert row.outcome == store.REPORTED


def test_a_lookup_that_gets_no_answer_is_kept_as_failed(
    session: Session,
    settings: Settings,
    connected: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fresh_incident(session, str(ADDRESS))
    answering(monkeypatch, CallFailed("VirusTotal didn't answer in time."))

    assert asyncio.run(run.lookup_once(new_session_for(session), settings, _record)) is True

    session.expire_all()
    [row] = session.scalars(select(IntelLookup)).all()
    assert row.outcome == store.FAILED
    assert store.report_for(session, PROVIDER, ADDRESS) is None


def test_the_loop_keeps_going_after_a_failure_and_says_what_happened(
    session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[int] = []

    async def failing(*args: object) -> bool:
        del args
        calls.append(1)
        raise RuntimeError("The database was restarted.")

    monkeypatch.setattr(run, "lookup_once", failing)

    async def go() -> None:
        await asyncio.wait_for(
            run.run(
                new_session_for(session),
                settings,
                _record,
                interval=timedelta(seconds=0),
            ),
            timeout=0.2,
        )

    looping = go()
    with caplog.at_level(logging.ERROR), pytest.raises(TimeoutError):
        asyncio.run(looping)
    assert len(calls) > 1
    assert "Couldn't ask VirusTotal about an address" in caplog.text


def test_the_loop_asks_nothing_when_collecting_is_off(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    async def counting(*args: object) -> bool:
        del args
        calls.append(1)
        return False

    monkeypatch.setattr(run, "lookup_once", counting)

    async def go() -> None:
        await asyncio.wait_for(
            run.run(
                new_session_for(session),
                settings,
                _record,
                enabled=False,
                interval=timedelta(seconds=0),
            ),
            timeout=0.1,
        )

    looping = go()
    with pytest.raises(TimeoutError):
        asyncio.run(looping)
    assert calls == []


async def _record(_call: Call) -> None:
    pass  # Keeps nothing: the test needs only that the call was made.


def test_nothing_is_asked_while_a_used_up_daily_quota_holds(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))
    lookup_at(session, utcnow(), outcome=store.LIMITED)
    session.commit()
    asked = answering(monkeypatch, virustotal.Unknown())

    assert asyncio.run(run.lookup_once(new_session_for(session), settings, _record)) is False
    assert asked == []


def test_a_limit_answer_is_kept_and_leaves_the_connection_connected(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))
    answering(monkeypatch, virustotal.Limited(until=virustotal.next_reset(utcnow())))

    assert asyncio.run(run.lookup_once(new_session_for(session), settings, _record)) is True

    session.expire_all()
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert lookup.outcome == store.LIMITED
    [row] = session.scalars(select(IntegrationConnection)).all()
    assert row.last_error is None
    assert row.last_attempt_at is not None


def test_a_throttled_answer_counts_as_the_key_being_accepted(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))
    answering(monkeypatch, virustotal.Throttled(until=utcnow() + timedelta(minutes=1)))
    [before] = session.scalars(select(IntegrationConnection)).all()
    tested_at = before.last_success_at

    asyncio.run(run.lookup_once(new_session_for(session), settings, _record))

    session.expire_all()
    [row] = session.scalars(select(IntegrationConnection)).all()
    assert row.last_success_at is not None
    assert tested_at is None or row.last_success_at > tested_at
    assert row.last_error is None


def test_a_failed_lookup_leaves_the_connection_as_it_was(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))
    answering(monkeypatch, virustotal.Failed("VirusTotal answered HTTP 500."))

    asyncio.run(run.lookup_once(new_session_for(session), settings, _record))

    session.expire_all()
    [row] = session.scalars(select(IntegrationConnection)).all()
    assert row.last_error is None
    assert row.last_attempt_at is None


def test_a_lookup_is_kept_even_if_its_connection_is_removed_while_it_is_asked(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_incident(session, str(ADDRESS))

    async def look_up(*args: object) -> object:
        # The connection is removed while VirusTotal is being asked about the address.
        for row in session.scalars(select(IntegrationConnection)).all():
            session.delete(row)
        session.commit()
        return virustotal.Unknown()

    monkeypatch.setattr(virustotal, "look_up", look_up)

    assert asyncio.run(run.lookup_once(new_session_for(session), settings, _record)) is True

    session.expire_all()
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert lookup.outcome == store.UNKNOWN
    assert session.scalars(select(IntegrationConnection)).all() == []
