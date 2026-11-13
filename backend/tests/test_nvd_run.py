"""The loop that asks NVD about the CVEs that incidents name."""

import asyncio
import logging
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.integrations import netguard, service
from app.integrations.client import Call, CallFailed, Target
from app.models import IntegrationConnection, NvdCve
from app.models.base import utcnow
from app.nvd import lookup, run
from app.nvd.lookup import Failed, Found, Throttled, Unknown
from tests.nvd_support import incident_naming
from tests.test_intel_lookups import new_session_for

LOG4SHELL = "CVE-2021-44228"
BLUEKEEP = "CVE-2019-0708"


async def keep(_call: Call) -> None:
    pass  # Keeps nothing: the test needs only that the call was made.


def connect(
    session: Session, options: dict[str, str] | None = None, *, tested: bool = True
) -> None:
    session.add(
        IntegrationConnection(
            integration="nvd",
            connection="api",
            base_url="https://services.nvd.nist.gov",
            tls_mode="system",
            options=options or {"access": "key"},
            last_success_at=utcnow() if tested else None,
        )
    )
    session.commit()


@pytest.fixture
def connected(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """A connected, tested NVD connection whose secret opens."""
    origin = netguard.parse_origin("https://services.nvd.nist.gov", allow_http=False)

    def load(*args: object, **kwargs: object) -> Target:
        del args, kwargs
        return Target(
            integration="nvd",
            connection="api",
            origin=origin,
            tls_mode="system",
            tls_ca_pem=None,
            tls_fingerprint=None,
            options={"access": "key"},
            secrets={"api_key": "nvd-key"},
        )

    monkeypatch.setattr(service, "load_target", load)
    connect(session)


def answering(monkeypatch: pytest.MonkeyPatch, answer: object) -> list[str]:
    """Makes NVD answer with the answer given, or raise it. Returns the CVEs asked about."""
    asked: list[str] = []

    async def ask(*args: Any) -> object:
        asked.append(args[3])
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(lookup, "ask", ask)
    return asked


def go(session: Session, settings: Settings, pace: run.Pace | None = None) -> bool:
    session.commit()  # The loop reads through sessions of its own.
    return asyncio.run(
        run.lookup_once(new_session_for(session), settings, keep, pace or run.Pace())
    )


def a_record(cve_id: str = LOG4SHELL) -> Found:
    return Found(lookup.Record(cve_id=cve_id, score=9.8, severity="CRITICAL", cvss_version="3.1"))


def test_nothing_is_asked_until_the_connection_has_been_tested(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(session, tested=False)
    incident_naming(session, LOG4SHELL, seen=timedelta(minutes=5))
    asked = answering(monkeypatch, Unknown())

    assert go(session, settings) is False
    assert asked == []


def test_nothing_is_asked_when_nvd_is_not_connected(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    incident_naming(session, LOG4SHELL, seen=timedelta(minutes=5))
    asked = answering(monkeypatch, Unknown())

    assert go(session, settings) is False
    assert asked == []


def test_a_cve_an_incident_names_is_asked_about_and_the_record_kept(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    incident_naming(session, f"Exploit of {LOG4SHELL}", seen=timedelta(minutes=5))
    asked = answering(monkeypatch, a_record())

    assert go(session, settings) is True

    assert asked == [LOG4SHELL]
    session.expire_all()
    [row] = session.scalars(select(NvdCve)).all()
    assert (row.cve_id, row.state, row.score, row.severity) == (LOG4SHELL, "found", 9.8, "CRITICAL")


def test_a_cve_nvd_has_no_record_of_is_kept_as_unknown(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    incident_naming(session, LOG4SHELL, seen=timedelta(minutes=5))
    answering(monkeypatch, Unknown())

    assert go(session, settings) is True

    session.expire_all()
    assert session.scalars(select(NvdCve.state)).all() == ["unknown"]


def test_nothing_is_asked_when_no_incident_names_a_cve_and_the_queue_is_not_read_again_for_a_while(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    incident_naming(session, "A port scan", seen=timedelta(minutes=5))
    asked = answering(monkeypatch, Unknown())
    pace = run.Pace()

    assert go(session, settings, pace) is False
    assert pace.not_before is not None
    assert pace.not_before - utcnow() > run.IDLE - timedelta(seconds=5)

    incident_naming(session, LOG4SHELL, seen=timedelta(minutes=5))
    assert go(session, settings, pace) is False
    assert asked == []


def test_a_second_lookup_waits_out_the_spacing(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    incident_naming(session, LOG4SHELL, BLUEKEEP, seen=timedelta(minutes=5))
    asked = answering(monkeypatch, Unknown())
    pace = run.Pace()

    assert go(session, settings, pace) is True
    assert go(session, settings, pace) is False
    assert len(asked) == 1

    pace.not_before = utcnow() - timedelta(seconds=1)
    assert go(session, settings, pace) is True
    assert len(asked) == 2


def test_a_key_is_asked_with_more_often_than_no_key() -> None:
    def target(options: dict[str, str | int]) -> Target:
        return Target(
            integration="nvd",
            connection="api",
            origin=netguard.parse_origin("https://services.nvd.nist.gov", allow_http=False),
            tls_mode="system",
            tls_ca_pem=None,
            tls_fingerprint=None,
            options=options,
            secrets={},
        )

    assert run.spacing_of(target({"access": "key"})) == run.SPACING_WITH_KEY
    assert run.spacing_of(target({"access": "none"})) == run.SPACING_WITHOUT_KEY
    # Without a key NVD allows 5 requests in 30 seconds, and the loop stays under that.
    assert timedelta(seconds=30) / run.SPACING_WITHOUT_KEY <= 3
    # With one it allows 50, and NVD suggests six seconds between requests.
    assert timedelta(seconds=30) / run.SPACING_WITH_KEY <= 50


def test_a_request_nvd_turns_away_holds_lookups_until_it_lifts(
    session: Session, settings: Settings, connected: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    incident_naming(session, LOG4SHELL, seen=timedelta(minutes=5))
    until = utcnow() + lookup.THROTTLE
    answering(monkeypatch, Throttled(until=until))
    pace = run.Pace()

    assert go(session, settings, pace) is True

    assert pace.not_before == until
    session.expire_all()
    assert session.scalars(select(NvdCve)).all() == []
    assert go(session, settings, pace) is False


def test_a_failed_lookup_leaves_that_cve_alone_for_a_while_and_is_logged(
    session: Session,
    settings: Settings,
    connected: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    incident_naming(session, LOG4SHELL, seen=timedelta(minutes=5))
    incident_naming(session, BLUEKEEP, seen=timedelta(hours=3))
    asked = answering(monkeypatch, Failed("NVD answered HTTP 500."))
    pace = run.Pace()

    with caplog.at_level(logging.INFO):
        assert go(session, settings, pace) is True

    assert "An NVD lookup didn't give a record: NVD answered HTTP 500." in caplog.text
    assert LOG4SHELL in pace.left_alone
    pace.not_before = None
    assert go(session, settings, pace) is True
    assert asked == [LOG4SHELL, BLUEKEEP]


def test_a_cve_left_alone_is_tried_again_after_the_retry_time() -> None:
    now = utcnow()
    pace = run.Pace(left_alone={"CVE-2021-0001": now + timedelta(minutes=1), "CVE-2021-0002": now})

    assert pace.skipping(now) == frozenset({"CVE-2021-0001"})
    assert pace.left_alone == {"CVE-2021-0001": now + timedelta(minutes=1)}


def test_the_loop_survives_a_failure_and_asks_nothing_when_collecting_is_off(
    session: Session,
    settings: Settings,
    connected: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    incident_naming(session, LOG4SHELL, seen=timedelta(minutes=5))
    asked = answering(monkeypatch, CallFailed("boom"))
    session.commit()

    async def loops(enabled: bool) -> None:
        task = asyncio.create_task(
            run.run(
                new_session_for(session),
                settings,
                keep,
                enabled=enabled,
                interval=timedelta(seconds=0.01),
            )
        )
        await asyncio.sleep(0.2)
        task.cancel()

    with caplog.at_level(logging.INFO):
        asyncio.run(loops(False))
        assert asked == []
        asyncio.run(loops(True))

    assert asked
    assert "Couldn't ask NVD about a CVE" in caplog.text


def test_a_connection_with_no_secret_asks_nothing(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(session)
    incident_naming(session, LOG4SHELL, seen=timedelta(minutes=5))
    asked = answering(monkeypatch, Unknown())

    def incomplete(*args: object, **kwargs: object) -> Target:
        del args, kwargs
        raise service.Incomplete

    monkeypatch.setattr(service, "load_target", incomplete)

    assert go(session, settings) is False
    assert asked == []
