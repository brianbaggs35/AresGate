"""What can be tidied among the incidents: duplicates, old quiet ones and ones the AI is sure are
noise, and that nothing serious is ever offered."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.incidents import cleanup
from tests.test_ai_service import NOW
from tests.test_ai_triage import incident, kept

DAY = timedelta(days=1)


def scans(session: Session, count: int = 3, **changes: object) -> list[int]:
    return [
        incident(session, subject=f"198.51.100.{number}", title="Scan of ssh", **changes).id
        for number in range(1, count + 1)
    ]


class TestDuplicates:
    def test_open_incidents_that_say_the_same_thing_keep_the_most_serious_and_dismiss_the_rest(
        self, session: Session
    ) -> None:
        lone = incident(session, subject="198.51.100.9", title="Only one")
        first, second, third = scans(session)
        mild = incident(session, subject="198.51.100.5", title="Scan of ssh", severity=1)
        session.commit()
        assert lone.id

        [found] = cleanup.duplicates(session)

        assert found.kind == "duplicates"
        assert found.action == "dismiss"
        assert found.title == "4 open incidents say the same thing"
        assert found.keep == first
        assert found.incidents == (second, third, mild.id)
        assert f"Incident {first} is the most serious" in found.detail
        assert found.confidence == 70

    def test_the_same_severity_makes_it_surer(self, session: Session) -> None:
        scans(session, 2)
        session.commit()

        [found] = cleanup.duplicates(session)

        assert found.confidence == 85

    def test_what_is_serious_settled_or_quieted_is_left_alone(self, session: Session) -> None:
        scans(session, 2, severity=3)
        scans(session, 2, confidence=90).append(0)
        for number in (1, 2):
            incident(session, subject=f"203.0.113.{number}", title="Settled", status="resolved")
            incident(session, subject=f"192.0.2.{number}", title="Quieted", verdict="low_priority")
        session.commit()

        assert cleanup.duplicates(session) == []

    def test_the_same_group_has_the_same_key_and_a_bigger_one_does_not(
        self, session: Session
    ) -> None:
        scans(session, 2)
        session.commit()
        [before] = cleanup.duplicates(session)
        assert cleanup.duplicates(session)[0].key == before.key

        incident(session, subject="198.51.100.77", title="Scan of ssh")
        session.commit()

        assert cleanup.duplicates(session)[0].key != before.key


class TestStale:
    def test_quiet_incidents_nothing_has_touched_for_days_are_to_be_resolved(
        self, session: Session
    ) -> None:
        old = incident(session, subject="198.51.100.1", last_seen_at=NOW - 4 * DAY)
        incident(session, subject="198.51.100.2", last_seen_at=NOW - DAY)
        incident(session, subject="198.51.100.3", last_seen_at=NOW - 5 * DAY, severity=3)
        session.commit()

        [found] = cleanup.stale(session, NOW)

        assert found.action == "resolve"
        assert found.incidents == (old.id,)
        assert found.title == "1 old incident nothing has touched"
        assert found.confidence == 90
        assert "3 days" in found.detail

    def test_several_are_named_in_the_plural(self, session: Session) -> None:
        incident(session, subject="198.51.100.1", last_seen_at=NOW - 4 * DAY)
        incident(session, subject="198.51.100.2", last_seen_at=NOW - 5 * DAY)
        session.commit()

        [found] = cleanup.stale(session, NOW)

        assert found.title == "2 old incidents nothing has touched"

    def test_with_none_there_is_nothing(self, session: Session) -> None:
        incident(session)
        session.commit()

        assert cleanup.stale(session, NOW) == []


class TestBenign:
    def test_incidents_the_ai_is_sure_are_noise_would_get_a_verdict(self, session: Session) -> None:
        sure = incident(session, subject="198.51.100.1")
        kept(session, sure, classification="noise", confidence=95)
        also = incident(session, subject="198.51.100.2")
        kept(session, also, classification="noise", confidence=85)
        unsure = incident(session, subject="198.51.100.3")
        kept(session, unsure, classification="noise", confidence=60)
        probe = incident(session, subject="198.51.100.4")
        kept(session, probe, classification="probe", confidence=99)
        session.commit()

        [found] = cleanup.benign(session)

        assert found.action == "not_suspicious"
        assert found.incidents == (sure.id, also.id)
        assert found.confidence == 85
        assert "at least 85% sure" in found.detail
        assert found.title == "2 incidents the AI is sure are noise"

    def test_one_is_named_in_the_singular(self, session: Session) -> None:
        sure = incident(session, subject="198.51.100.1")
        kept(session, sure, classification="noise", confidence=95)
        session.commit()

        [found] = cleanup.benign(session)

        assert found.title == "1 incident the AI is sure is noise"

    def test_with_none_there_is_nothing(self, session: Session) -> None:
        incident(session)
        session.commit()

        assert cleanup.benign(session) == []


def test_everything_is_found_the_surest_first(session: Session) -> None:
    scans(session, 2)
    incident(session, subject="198.51.100.40", last_seen_at=NOW - 9 * DAY, title="Old")
    session.commit()

    kinds = [item.kind for item in cleanup.find(session, NOW)]

    assert kinds == ["stale", "duplicates"]
    assert cleanup.find(session, NOW + DAY)[0].kind == "stale"
