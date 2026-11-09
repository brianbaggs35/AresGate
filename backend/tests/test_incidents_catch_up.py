"""The first alerts an interface sends from ntopng: one incident for the interface, which says how
many alerts it folded in. An alert after the first half hour files as any other does (see
``engine.py``)."""

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.events.event import NewEvent, Severity
from app.events.store import record as record_events
from app.incidents import engine as correlation
from app.incidents import episode
from app.models import Event, Incident, SystemInfo
from tests.helpers import new_event

NOW = datetime(2026, 10, 26, 6, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=12)
MINUTE = timedelta(minutes=1)
# Public addresses, which the documentation ranges are not.
ADDRESSES = ("93.184.216.34", "8.8.8.8", "1.1.1.1", "9.9.9.9")


def alert(
    at: datetime,
    address: str = ADDRESSES[0],
    *,
    n: int = 1,
    iface: str | None = "eth0",
    source: str = "ntopng",
) -> NewEvent:
    """An alert as the collector stores it: from a program, on an interface, about an address."""
    return new_event(
        source=source,
        connection="api",
        occurred_at=at,
        identity=(f"alert-{n}",),
        src_address=address,
        dst_address="192.168.1.20",
        severity=Severity.MEDIUM,
        iface=iface,
    )


def store(session: Session, settings: Settings, *events: NewEvent) -> None:
    """Stores events as a collector would have as they happened."""
    for event in events:
        record_events(session, settings, [event], event.occurred_at)
    session.commit()


def run(session: Session, now: datetime = LATER) -> None:
    correlation.correlate(session, now)
    session.commit()


def incidents(session: Session) -> list[Incident]:
    session.expire_all()
    return list(session.scalars(select(Incident).order_by(Incident.id)))


def test_the_first_alerts_of_an_interface_fold_into_one_incident(
    session: Session, settings: Settings
) -> None:
    store(
        session,
        settings,
        *(alert(NOW + n * MINUTE, address, n=n) for n, address in enumerate(ADDRESSES)),
    )

    run(session)

    [incident] = incidents(session)
    assert incident.subject == "catch-up:eth0"
    assert incident.signal_count == len(ADDRESSES)
    assert incident.title == "4 ntopng alerts folded in from the first half hour on eth0"


def test_an_alert_after_the_first_half_hour_opens_its_own_incident(
    session: Session, settings: Settings
) -> None:
    store(
        session,
        settings,
        alert(NOW, ADDRESSES[0]),
        alert(NOW + 31 * MINUTE, ADDRESSES[1], n=2),
    )

    run(session)

    assert {item.subject for item in incidents(session)} == {"catch-up:eth0", ADDRESSES[1]}


def test_each_interface_has_its_own_catch_up(session: Session, settings: Settings) -> None:
    store(
        session,
        settings,
        alert(NOW, ADDRESSES[0]),
        alert(NOW, ADDRESSES[1], n=2, iface="eth1"),
    )

    run(session)

    assert {item.subject for item in incidents(session)} == {"catch-up:eth0", "catch-up:eth1"}


def test_alerts_from_another_program_or_without_an_interface_file_as_before(
    session: Session, settings: Settings
) -> None:
    store(
        session,
        settings,
        alert(NOW, ADDRESSES[0], source="suricata"),
        alert(NOW, ADDRESSES[1], n=2, iface=None),
    )

    run(session)

    assert {item.subject for item in incidents(session)} == {ADDRESSES[0], ADDRESSES[1]}


def test_a_later_run_adds_to_the_same_catch_up_and_keeps_where_it_began(
    session: Session, settings: Settings
) -> None:
    store(session, settings, alert(NOW, ADDRESSES[0]), alert(NOW + MINUTE, ADDRESSES[1], n=2))
    run(session)
    store(session, settings, alert(NOW + 10 * MINUTE, ADDRESSES[2], n=3))

    run(session)

    [incident] = incidents(session)
    assert incident.subject == "catch-up:eth0"
    assert incident.signal_count == 3
    kept = session.get(SystemInfo, correlation.CATCH_UP_KEY)
    assert kept is not None
    assert json.loads(kept.value) == {"eth0": NOW.isoformat()}


def test_an_interface_the_engine_has_read_before_has_no_catch_up(
    session: Session, settings: Settings
) -> None:
    # The engine read eth0 before this was known, so its later alerts are live, not a catch-up.
    # eth1 has never been read, so its first alerts are one, even on a later run.
    store(session, settings, alert(NOW, ADDRESSES[0]))
    session.add(
        SystemInfo(key=correlation.CURSOR, value=str(session.scalar(select(func.max(Event.id)))))
    )
    session.commit()
    store(session, settings, alert(NOW + MINUTE, ADDRESSES[1], n=2))
    run(session)
    store(session, settings, alert(NOW + 2 * MINUTE, ADDRESSES[2], n=3, iface="eth1"))

    run(session)

    assert {item.subject for item in incidents(session)} == {ADDRESSES[1], "catch-up:eth1"}
    kept = session.get(SystemInfo, correlation.CATCH_UP_KEY)
    assert kept is not None
    assert json.loads(kept.value) == {"eth0": None, "eth1": (NOW + 2 * MINUTE).isoformat()}


def test_a_catch_up_is_never_one_episode_with_a_scan_of_an_address() -> None:
    catch_up = Incident(
        subject="catch-up:eth0", activities=[episode.SCAN], first_seen_at=NOW, last_seen_at=NOW
    )
    scan = Incident(
        subject=ADDRESSES[0], activities=[episode.SCAN], first_seen_at=NOW, last_seen_at=NOW
    )

    assert correlation.fits(catch_up, scan, episode.DEFAULT_GAPS) is False
    assert correlation.fits(scan, catch_up, episode.DEFAULT_GAPS) is False
