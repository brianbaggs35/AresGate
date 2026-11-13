"""Which CVE is asked about next, and what is kept of NVD's answers."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NvdCve
from app.nvd import lookup, queue, store
from tests.nvd_support import NOW, incident_naming, kept

LOG4SHELL = "CVE-2021-44228"
BLUEKEEP = "CVE-2019-0708"
HEARTBLEED = "CVE-2014-0160"


# -- what is kept


def test_a_record_is_kept_by_its_cve(session: Session) -> None:
    row = kept(session)

    assert row.state == store.FOUND
    assert store.load(session, [LOG4SHELL, "CVE-2000-0001"]) == {LOG4SHELL: row}
    assert (row.score, row.severity, row.exploited_on) == (10.0, "CRITICAL", date(2021, 12, 10))
    assert row.weaknesses == ["CWE-917"]


def test_a_newer_answer_takes_the_place_of_the_older(session: Session) -> None:
    kept(session)

    kept(session, score=7.5, severity="HIGH", exploited=False, exploited_on=None, weaknesses=[])

    [row] = session.scalars(select(NvdCve)).all()
    assert (row.score, row.severity, row.exploited, row.exploited_on) == (7.5, "HIGH", False, None)
    assert row.weaknesses == []


def test_that_nvd_has_no_record_is_kept_and_clears_what_was_known(session: Session) -> None:
    kept(session)

    row = store.keep(session, LOG4SHELL, lookup.Unknown(), NOW)

    assert row is not None
    assert (row.state, row.score, row.exploited, row.description) == (
        store.UNKNOWN,
        None,
        False,
        None,
    )
    assert row.checked_at == NOW


def test_a_failure_or_a_request_to_wait_keeps_nothing(session: Session) -> None:
    assert store.keep(session, LOG4SHELL, lookup.Failed("no"), NOW) is None
    assert store.keep(session, LOG4SHELL, lookup.Throttled(NOW), NOW) is None
    assert session.scalars(select(NvdCve)).all() == []


def test_nothing_is_loaded_for_no_cves(session: Session) -> None:
    kept(session)

    assert store.load(session, []) == {}


# -- what is stale


def test_a_cve_never_asked_about_is_stale() -> None:
    assert queue.stale(None, NOW)


def test_a_cve_nvd_has_no_record_of_or_has_not_scored_is_asked_again_after_a_day(
    session: Session,
) -> None:
    unscored = kept(session, score=None, severity=None, cvss_version=None, exploited=False)
    unknown = store.keep(session, BLUEKEEP, lookup.Unknown(), NOW)
    assert unknown is not None

    for row in (unscored, unknown):
        assert not queue.stale(row, NOW + timedelta(hours=23))
        assert queue.stale(row, NOW + timedelta(days=1))


def test_a_scored_cve_is_asked_again_after_three_days_and_an_exploited_one_after_two_weeks(
    session: Session,
) -> None:
    scored = kept(session, exploited=False)
    exploited = kept(session, BLUEKEEP)

    assert not queue.stale(scored, NOW + timedelta(days=2, hours=23))
    assert queue.stale(scored, NOW + timedelta(days=3))
    assert not queue.stale(exploited, NOW + timedelta(days=13))
    assert queue.stale(exploited, NOW + timedelta(weeks=2))


# -- which CVEs incidents name


def test_the_cves_wanted_are_those_recent_incidents_name_the_most_recent_first(
    session: Session,
) -> None:
    incident_naming(session, f"Exploit of {BLUEKEEP}", seen=timedelta(hours=5))
    incident_naming(session, f"Exploit of {LOG4SHELL}", seen=timedelta(hours=1))

    assert queue.named(session, NOW) == [LOG4SHELL, BLUEKEEP]


def test_a_cve_in_the_evidence_a_signal_kept_is_wanted(session: Session) -> None:
    incident_naming(
        session, "A vulnerability", evidence={"indicators": [{"kind": "cve", "value": HEARTBLEED}]}
    )

    assert queue.named(session, NOW) == [HEARTBLEED]


def test_an_old_incident_names_nothing_wanted(session: Session) -> None:
    incident_naming(session, f"Exploit of {LOG4SHELL}", seen=queue.RECENT + timedelta(days=1))

    assert queue.named(session, NOW) == []


def test_a_cve_named_by_two_incidents_is_wanted_once(session: Session) -> None:
    incident_naming(session, LOG4SHELL, seen=timedelta(hours=2))
    incident_naming(session, LOG4SHELL, BLUEKEEP, seen=timedelta(hours=1))

    assert queue.named(session, NOW) == [LOG4SHELL, BLUEKEEP]


# -- which is next


def test_nothing_is_wanted_when_no_incident_names_a_cve(session: Session) -> None:
    incident_naming(session, "A port scan")

    assert queue.next_wanted(session, NOW) is None


def test_the_most_recent_incidents_cve_is_next(session: Session) -> None:
    incident_naming(session, BLUEKEEP, seen=timedelta(hours=5))
    incident_naming(session, LOG4SHELL, seen=timedelta(hours=1))

    assert queue.next_wanted(session, NOW) == LOG4SHELL


def test_one_never_asked_about_comes_before_one_gone_stale(session: Session) -> None:
    incident_naming(session, LOG4SHELL, seen=timedelta(hours=1))
    incident_naming(session, BLUEKEEP, seen=timedelta(hours=5))
    kept(session, LOG4SHELL, checked=timedelta(days=30))

    assert queue.next_wanted(session, NOW) == BLUEKEEP


def test_nothing_is_next_when_every_answer_is_fresh(session: Session) -> None:
    incident_naming(session, LOG4SHELL)
    kept(session)

    assert queue.next_wanted(session, NOW) is None


def test_a_cve_that_is_to_be_left_alone_is_passed_over(session: Session) -> None:
    incident_naming(session, LOG4SHELL, seen=timedelta(hours=1))
    incident_naming(session, BLUEKEEP, seen=timedelta(hours=5))

    assert queue.next_wanted(session, NOW, skip=frozenset({LOG4SHELL})) == BLUEKEEP
    assert queue.next_wanted(session, NOW, skip=frozenset({LOG4SHELL, BLUEKEEP})) is None
