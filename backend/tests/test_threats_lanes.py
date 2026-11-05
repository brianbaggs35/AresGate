"""Where an incident goes: a threat, a suspect or background. The function and the SQL that count
and list many say the same, whatever the owner's settings."""

from datetime import UTC, datetime
from itertools import product
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.incidents import attention
from app.incidents.attention import Lane, Standing
from app.models import Incident
from app.threats.settings import Tuning

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)

TUNINGS = [
    Tuning(),
    Tuning(confirming=True),
    Tuning(ai_may_clear=False),
    Tuning(ai_may_clear=False, confirming=True),
    Tuning(threat_from=90, clear_from=95),
    Tuning(threat_from=40, clear_from=50, confirming=True),
]


def incident(**changes: Any) -> Incident:
    fields: dict[str, Any] = {
        "subject": "203.0.113.9",
        "title": "x",
        "severity": 3,
        "confidence": 60,
        "status": "open",
        "verdict": None,
        "stages": [],
        "first_seen_at": NOW,
        "last_seen_at": NOW,
        "top_source": "wazuh",
        "top_summary": "x",
    }
    fields.update(changes)
    return Incident(**fields)


class TestWhichLane:
    @pytest.mark.parametrize(
        ("changes", "lane"),
        [
            ({"confidence": 80}, Lane.THREAT),
            ({"confidence": 50}, Lane.SUSPECT),
            ({"confidence": 10}, Lane.BACKGROUND),
            ({"confidence": 10, "stages": ["recon", "access"]}, Lane.THREAT),
            ({"confidence": 50, "stages": ["foothold"]}, Lane.THREAT),
            ({"confidence": 50, "stages": ["recon"]}, Lane.SUSPECT),
            ({"confidence": 10, "verdict": "threat"}, Lane.BACKGROUND),
            ({"confidence": 50, "verdict": "threat"}, Lane.THREAT),
            ({"confidence": 80, "ai_class": "probe", "ai_confidence": 90}, Lane.BACKGROUND),
            ({"confidence": 80, "ai_class": "probe", "ai_confidence": 70}, Lane.THREAT),
            (
                {
                    "confidence": 80,
                    "ai_class": "probe",
                    "ai_confidence": 90,
                    "stages": ["foothold"],
                },
                Lane.THREAT,
            ),
            (
                {"confidence": 80, "ai_class": "probe", "ai_confidence": 90, "severity": 4},
                Lane.THREAT,
            ),
            ({"confidence": 50, "ai_class": "attack", "ai_confidence": 70}, Lane.THREAT),
            ({"confidence": 10, "ai_class": "compromise", "ai_confidence": 90}, Lane.THREAT),
            ({"confidence": 50, "ai_class": "attack", "ai_confidence": 40}, Lane.SUSPECT),
            ({"confidence": 80, "verdict": "low_priority"}, None),
            ({"confidence": 80, "status": "resolved"}, None),
            ({"confidence": 80, "status": "dismissed"}, None),
        ],
    )
    def test_it_is_told_by_the_rules_and_by_what_the_ai_made_of_it(
        self, changes: dict[str, Any], lane: Lane | None
    ) -> None:
        assert attention.lane_of(incident(**changes)) is lane

    def test_with_the_ai_watching_the_rules_alone_do_not_make_a_threat(self) -> None:
        sure = incident(confidence=80)
        critical = incident(confidence=80, severity=4)
        confirming = Tuning(confirming=True)

        assert attention.lane_of(sure) is Lane.THREAT
        assert attention.lane_of(sure, tuning=confirming) is Lane.SUSPECT
        assert attention.lane_of(critical, tuning=confirming) is Lane.THREAT

    def test_the_ai_agreeing_makes_a_threat_while_it_is_watching(self) -> None:
        agreed = incident(confidence=80, ai_class="attack", ai_confidence=80)

        assert attention.lane_of(agreed, tuning=Tuning(confirming=True)) is Lane.THREAT

    def test_the_ai_may_be_forbidden_to_set_things_aside(self) -> None:
        judged = incident(confidence=80, ai_class="noise", ai_confidence=99)

        assert attention.lane_of(judged) is Lane.BACKGROUND
        assert attention.lane_of(judged, tuning=Tuning(ai_may_clear=False)) is Lane.THREAT

    def test_a_threat_is_urgent_and_needs_the_owner(self) -> None:
        found = incident(confidence=90)

        assert attention.urgent(found) and attention.needs_you(found)
        assert not attention.urgent(incident(confidence=50))
        assert attention.needs_you(incident(confidence=50))


class TestTheSqlSaysTheSame:
    def grid(self) -> list[Incident]:
        found: list[Incident] = []
        calls = [(None, None), ("noise", 60), ("probe", 90), ("attack", 90), ("compromise", 70)]
        for number, (status, verdict, confidence, severity, stages, (kind, sure)) in enumerate(
            product(
                ("open", "resolved"),
                (None, "threat", "low_priority"),
                (10, 50, 80),
                (2, 4),
                ([], ["recon"], ["recon", "access"], ["foothold"]),
                calls,
            )
        ):
            found.append(
                incident(
                    subject=f"s{number}",
                    status=status,
                    verdict=verdict,
                    confidence=confidence,
                    severity=severity,
                    stages=stages,
                    ai_class=kind,
                    ai_confidence=sure,
                )
            )
        return found

    @pytest.mark.parametrize("tuning", TUNINGS)
    def test_every_kind_of_incident_is_where_the_function_puts_it(
        self, session: Session, tuning: Tuning
    ) -> None:
        session.add_all(self.grid())
        session.commit()
        everything = list(session.scalars(select(Incident)))

        for floor in (35, 65):
            for standing, clause in attention.clauses(floor, tuning).items():
                found = set(session.scalars(select(Incident.subject).where(clause)))
                expected = {
                    each.subject
                    for each in everything
                    if attention.standing(each, floor, tuning) is standing
                }
                assert found == expected, (floor, standing)
            for lane, clause in attention.lane_clauses(floor, tuning).items():
                found = set(session.scalars(select(Incident.subject).where(clause)))
                expected = {
                    each.subject
                    for each in everything
                    if attention.lane_of(each, floor, tuning) is lane
                }
                assert found == expected, (floor, lane)
            urgent = set(
                session.scalars(
                    select(Incident.subject).where(attention.urgent_clause(floor, tuning))
                )
            )
            assert urgent == {
                each.subject for each in everything if attention.urgent(each, floor, tuning)
            }

    @pytest.mark.parametrize("tuning", TUNINGS)
    def test_the_lanes_and_what_is_in_none_cover_every_incident_once(
        self, session: Session, tuning: Tuning
    ) -> None:
        session.add_all(self.grid())
        session.commit()
        total = len(list(session.scalars(select(Incident))))
        clauses = attention.lane_clauses(35, tuning)
        by = attention.clauses(35, tuning)

        counted = sum(
            len(list(session.scalars(select(Incident).where(clause))))
            for clause in clauses.values()
        )
        left = sum(
            len(list(session.scalars(select(Incident).where(by[standing]))))
            for standing in (Standing.HANDLED, Standing.MUTED)
        )

        assert counted + left == total

    @pytest.mark.parametrize("tuning", TUNINGS)
    def test_the_tally_counts_what_the_clauses_do(self, session: Session, tuning: Tuning) -> None:
        session.add_all(self.grid())
        session.commit()
        everything = list(session.scalars(select(Incident)))

        found = attention.tally(session, 35, tuning)

        by_standing = [attention.standing(each, 35, tuning) for each in everything]
        assert found.unsure == by_standing.count(Standing.UNSURE)
        assert found.cleared == by_standing.count(Standing.AI_CLEARED)
        assert found.needs_you == by_standing.count(Standing.NEEDS_YOU)
        assert found.muted == by_standing.count(Standing.MUTED)
        assert found.urgent == sum(attention.urgent(each, 35, tuning) for each in everything)
        assert found.suspects == found.needs_you - found.urgent
        assert found.active == found.muted + found.unsure + found.cleared + found.needs_you
