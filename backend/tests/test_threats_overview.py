"""The Threats page's numbers: from reports to threats, and the kinds of incident."""

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app import dashboard
from app.config import Settings
from app.incidents.attention import Lane
from app.models import Incident, IncidentFamily, utcnow
from app.threats import families, overview
from app.threats.settings import Tuning
from e2e import factories
from tests.test_threats_families import incident

NOW = utcnow()


def kind(session: Session, count: int, words: str, **more: Any) -> IncidentFamily:
    """``count`` incidents of one family."""
    last = None
    for number in range(count):
        address = f"45.33.{sum(words.encode()) % 200}.{number + 1}"
        last = incident(
            session,
            address,
            top_summary=f"{words} from {address}",
            first_seen_at=NOW - timedelta(hours=2),
            last_seen_at=NOW - timedelta(minutes=10),
            **more,
        )
    families.assign(session)
    session.commit()
    assert last is not None
    found = session.get(IncidentFamily, last.family_id)
    assert found is not None
    return found


def test_the_funnel_goes_from_reports_to_what_is_left(session: Session, settings: Settings) -> None:
    factories.incidents(
        session,
        settings,
        NOW,
        [factories.IncidentSpec(address="93.184.216.34", scan=True, signals=6, twin="opnsense")],
    )
    session.commit()

    found = overview.funnel(session, dashboard.window("24h", NOW), 35, Tuning())

    assert found.reports == 12
    assert found.duplicates == 6
    assert 1 <= found.alerts <= 6
    assert found.alerts + found.repeats == 6
    assert found.incidents == 1
    assert found.families == 1
    assert found.threats + found.suspects + found.background + found.muted + found.handled == 1


def test_a_quiet_network_has_an_empty_funnel(session: Session) -> None:
    found = overview.funnel(session, dashboard.window("24h", NOW), 35, Tuning())

    assert found == overview.Funnel(*([0] * 11))


def test_the_lanes_are_counted_by_where_incidents_stand(session: Session) -> None:
    kind(session, 1, "ET SCAN a", confidence=90)
    kind(session, 1, "ET SCAN b", confidence=50)
    kind(session, 1, "ET SCAN c", confidence=10)
    kind(session, 1, "ET SCAN d", confidence=90, verdict="low_priority")
    kind(session, 1, "ET SCAN e", confidence=90, status="resolved")

    found = overview.funnel(session, dashboard.window("24h", NOW), 35, Tuning())

    assert (found.threats, found.suspects, found.background) == (1, 1, 1)
    assert (found.muted, found.handled, found.incidents) == (1, 1, 5)


class TestHowMuchTheAiHasJudged:
    def test_kinds_are_judged_owned_or_waiting(self, session: Session) -> None:
        judged = kind(session, 2, "ET SCAN judged")
        judged.judged_at = NOW
        owned = kind(session, 2, "ET SCAN owned")
        owned.owner_call = "watch"
        kind(session, 2, "ET SCAN waiting")
        session.commit()

        found = overview.coverage(session)

        assert found == overview.Coverage(families=3, judged=1, owned=1, waiting=1)

    def test_a_kind_with_nothing_going_is_not_counted(self, session: Session) -> None:
        kind(session, 2, "ET SCAN gone", status="resolved")

        assert overview.coverage(session) == overview.Coverage(0, 0, 0, 0)


class TestTheKinds:
    def made(self, session: Session) -> dict[str, IncidentFamily]:
        return {
            "threat": kind(session, 1, "ET EXPLOIT threat", confidence=90),
            "big": kind(session, 4, "ET SCAN big", confidence=50),
            "small": kind(session, 2, "ET SCAN small", confidence=10),
        }

    def test_the_ones_with_threats_come_first_then_suspects_then_the_biggest(
        self, session: Session
    ) -> None:
        made = self.made(session)

        found = overview.kinds(session, 35, Tuning())

        assert found.total == 3
        assert [item.family.id for item in found.items] == [
            made["threat"].id,
            made["big"].id,
            made["small"].id,
        ]
        first = found.items[0]
        assert (first.incidents, first.alerts, first.actors) == (1, 3, 1)
        assert (first.threats, first.suspects, first.background) == (1, 0, 0)
        assert found.items[1].suspects == 4

    def test_they_can_be_asked_for_by_lane(self, session: Session) -> None:
        made = self.made(session)

        def ids(lane: Lane) -> list[int]:
            return [
                item.family.id for item in overview.kinds(session, 35, Tuning(), lane=lane).items
            ]

        assert ids(Lane.THREAT) == [made["threat"].id]
        assert ids(Lane.SUSPECT) == [made["big"].id]
        assert ids(Lane.BACKGROUND) == [made["small"].id]

    def test_they_can_be_asked_for_by_whether_they_have_been_judged(self, session: Session) -> None:
        made = self.made(session)
        made["big"].judged_at = NOW
        made["small"].owner_call = "background"
        session.commit()

        def ids(judged: str) -> list[int]:
            return [
                item.family.id
                for item in overview.kinds(session, 35, Tuning(), judged=judged).items
            ]

        assert ids("ai") == [made["big"].id]
        assert ids("owner") == [made["small"].id]
        assert ids("waiting") == [made["threat"].id]

    def test_they_can_be_asked_for_by_words_and_one_at_a_time(self, session: Session) -> None:
        made = self.made(session)

        by_words = overview.kinds(session, 35, Tuning(), text="exploit")
        one = overview.kinds(session, 35, Tuning(), family_id=made["small"].id)
        none = overview.kinds(session, 35, Tuning(), text="100%")

        assert [item.family.id for item in by_words.items] == [made["threat"].id]
        assert [item.family.id for item in one.items] == [made["small"].id]
        assert none.total == 0

    def test_they_come_in_pages(self, session: Session) -> None:
        self.made(session)

        page = overview.kinds(session, 35, Tuning(), limit=1, offset=1)

        assert page.total == 3
        assert len(page.items) == 1
        assert isinstance(page.items[0].family, IncidentFamily)

    def test_incidents_that_are_over_do_not_count(self, session: Session) -> None:
        kind(session, 2, "ET SCAN over", status="dismissed")

        assert overview.kinds(session, 35, Tuning()).total == 0
        assert session.query(Incident).count() == 2
