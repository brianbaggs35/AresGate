from datetime import UTC, datetime
from itertools import product

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.incidents import attention
from app.incidents.attention import Standing
from app.models import Incident

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def incident(**changes: object) -> Incident:
    return Incident(
        **{
            "subject": "203.0.113.9",
            "title": "x",
            "severity": 3,
            "confidence": 60,
            "status": "open",
            "verdict": None,
            "first_seen_at": NOW,
            "last_seen_at": NOW,
            "top_source": "wazuh",
            "top_summary": "x",
            **changes,
        }
    )


class TestStanding:
    @pytest.mark.parametrize(
        ("changes", "expected"),
        [
            ({}, Standing.NEEDS_YOU),
            ({"status": "investigating"}, Standing.NEEDS_YOU),
            ({"verdict": "threat", "confidence": 100}, Standing.NEEDS_YOU),
            ({"confidence": 35}, Standing.NEEDS_YOU),
            ({"confidence": 34}, Standing.UNSURE),
            ({"verdict": "not_suspicious"}, Standing.MUTED),
            ({"verdict": "low_priority", "confidence": 0}, Standing.MUTED),
            ({"status": "resolved"}, Standing.HANDLED),
            ({"status": "dismissed", "verdict": "low_priority", "confidence": 5}, Standing.HANDLED),
        ],
    )
    def test_is_the_first_reason_that_applies(
        self, changes: dict[str, object], expected: Standing
    ) -> None:
        assert attention.standing(incident(**changes)) is expected

    def test_goes_by_the_floor_it_is_given(self) -> None:
        sure_enough = incident(confidence=50)

        assert attention.standing(sure_enough, 50) is Standing.NEEDS_YOU
        assert attention.standing(sure_enough, 51) is Standing.UNSURE

    def test_says_whether_one_needs_the_owner_and_whether_it_is_urgent(self) -> None:
        assert attention.needs_you(incident(confidence=40))
        assert not attention.urgent(incident(confidence=64))
        assert attention.urgent(incident(confidence=65))
        assert not attention.needs_you(incident(confidence=90, verdict="low_priority"))
        assert not attention.urgent(incident(confidence=90, verdict="low_priority"))
        assert not attention.urgent(incident(confidence=90, status="resolved"))

    def test_has_a_name_for_what_the_ai_will_clear_that_nothing_has_yet(self) -> None:
        assert Standing.AI_CLEARED.value == "ai_cleared"
        assert {standing.value for standing in Standing} == {
            "handled",
            "ai_cleared",
            "muted",
            "unsure",
            "needs_you",
        }


class TestClauses:
    def test_give_the_same_standing_as_the_function_for_every_kind_of_incident(
        self, session: Session
    ) -> None:
        kinds = list(
            product(
                ("open", "investigating", "resolved", "dismissed"),
                (None, "not_suspicious", "low_priority", "threat"),
                (0, 34, 35, 64, 65, 100),
            )
        )
        session.add_all(
            incident(subject=f"s{number}", status=status, verdict=verdict, confidence=confidence)
            for number, (status, verdict, confidence) in enumerate(kinds)
        )
        session.commit()

        for floor in (0, 35, 65, 100):
            clauses = attention.clauses(floor)
            for standing, clause in clauses.items():
                found = set(session.scalars(select(Incident.subject).where(clause)))
                expected = {
                    row.subject
                    for row in session.scalars(select(Incident))
                    if attention.standing(row, floor) is standing
                }
                assert found == expected, (floor, standing)
            urgent = set(
                session.scalars(select(Incident.subject).where(attention.urgent_clause(floor)))
            )
            assert urgent == {
                row.subject
                for row in session.scalars(select(Incident))
                if attention.urgent(row, floor)
            }

    def test_leave_no_incident_without_a_standing_or_with_two(self, session: Session) -> None:
        session.add_all(
            incident(subject=f"s{confidence}", confidence=confidence)
            for confidence in range(0, 101, 5)
        )
        session.commit()
        total = len(list(session.scalars(select(Incident))))

        counted = sum(
            len(list(session.scalars(select(Incident).where(clause))))
            for clause in attention.clauses().values()
        )

        assert counted == total
