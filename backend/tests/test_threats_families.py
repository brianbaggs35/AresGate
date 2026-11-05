"""Families: incidents that say the same thing the same way, which an AI judges once."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incident, IncidentFamily
from app.threats import families

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def incident(session: Session, subject: str, **changes: Any) -> Incident:
    fields: dict[str, Any] = {
        "subject": subject,
        "title": f"About {subject}",
        "severity": 2,
        "confidence": 50,
        "first_seen_at": NOW,
        "last_seen_at": NOW,
        "top_source": "opnsense",
        "top_summary": f"ET SCAN Potential SSH Scan from {subject} to 192.168.1.20:22",
        "signal_count": 3,
        "sources": ["opnsense"],
        "addresses": [],
        "ports": [],
        "activities": [],
        "waves": 1,
    }
    fields.update(changes)
    found = Incident(**fields)
    session.add(found)
    session.flush()
    return found


class TestWhatAFamilyIsCalled:
    def test_the_parts_that_differ_from_one_incident_to_the_next_are_left_out(self) -> None:
        said = families.label_of("ET SCAN from 203.0.113.9 to 192.168.1.20:22, 41 times")

        assert said == "ET SCAN from <address> to <address>:# , # times".replace(" ,", ",")

    def test_an_ipv6_address_is_left_out_too(self) -> None:
        assert families.label_of("scan from 2001:db8::1 now") == "scan from <address> now"
        assert families.label_of("from fe80::1:2 and 2001:db8:0:0:0:0:0:1") == (
            "from <address> and <address>"
        )

    def test_a_time_or_a_count_that_looks_like_an_address_is_only_a_number(self) -> None:
        assert families.label_of("at 12:30:45 saw 3 of 4") == "at #:#:# saw # of #"

    def test_spaces_are_squeezed_and_it_is_not_too_long(self) -> None:
        assert families.label_of("  a \n  b  ") == "a b"
        assert len(families.label_of("x" * 500)) == families.MAX_LABEL


class TestWhereAnIncidentIsFrom:
    @pytest.mark.parametrize(
        ("subject", "reach"),
        [
            ("8.8.8.8", families.INTERNET),
            ("2606:4700:4700::1111", families.INTERNET),
            ("192.168.1.7", families.NETWORK),
            ("fe80::1", families.NETWORK),
            ("rule:wazuh:5710", families.RULE),
        ],
    )
    def test_the_internet_the_network_or_a_rule(self, subject: str, reach: str) -> None:
        assert families.reach_of(subject) == reach


class TestWhatMakesAFamily:
    def made(self, **changes: Any) -> Incident:
        fields: dict[str, Any] = {
            "subject": "8.8.8.8",
            "title": "x",
            "top_source": "opnsense",
            "top_summary": "ET SCAN from 8.8.8.8",
            "first_seen_at": NOW,
            "last_seen_at": NOW,
        }
        fields.update(changes)
        return Incident(**fields)

    def test_two_incidents_that_say_the_same_of_different_addresses_are_one_family(self) -> None:
        one = families.key_of(self.made())
        other = families.key_of(self.made(subject="1.1.1.1", top_summary="ET SCAN from 1.1.1.1"))

        assert one == other
        assert len(one) == 40

    def test_the_words_the_program_and_the_place_each_make_a_family_of_their_own(self) -> None:
        base = families.key_of(self.made())

        assert families.key_of(self.made(top_summary="ET EXPLOIT x")) != base
        assert families.key_of(self.made(top_source="wazuh")) != base
        assert families.key_of(self.made(subject="192.168.1.7")) != base

    def test_the_case_of_the_words_does_not_matter(self) -> None:
        assert families.key_of(self.made(top_summary="et scan from 8.8.8.8")) == families.key_of(
            self.made()
        )


class TestGivingIncidentsTheirFamily:
    def test_incidents_that_say_the_same_share_a_family(self, session: Session) -> None:
        a = incident(session, "8.8.8.8")
        b = incident(session, "1.1.1.1")
        c = incident(session, "9.9.9.9", top_summary="ET EXPLOIT something")

        assert families.assign(session) == 3
        session.commit()

        assert a.family_id == b.family_id
        assert c.family_id != a.family_id
        family = session.get(IncidentFamily, a.family_id)
        assert family is not None
        assert (family.source, family.reach) == ("opnsense", "internet")
        assert family.label == "ET SCAN Potential SSH Scan from <address> to <address>:#"
        assert a.family_key == family.key

    def test_an_incident_that_has_one_keeps_it_and_a_known_family_is_reused(
        self, session: Session
    ) -> None:
        first = incident(session, "8.8.8.8")
        families.assign(session)
        later = incident(session, "1.1.1.1")

        assert families.assign(session) == 1
        session.commit()

        assert later.family_id == first.family_id
        assert session.scalars(select(IncidentFamily)).all() != []
        assert len(session.scalars(select(IncidentFamily)).all()) == 1

    def test_with_nothing_waiting_nothing_is_done(self, session: Session) -> None:
        assert families.assign(session) == 0

    def test_a_new_incident_is_told_what_its_family_has_been_judged(self, session: Session) -> None:
        first = incident(session, "8.8.8.8")
        families.assign(session)
        family = session.get(IncidentFamily, first.family_id)
        assert family is not None
        family.ai_class = "probe"
        family.ai_confidence = 91
        session.flush()
        later = incident(session, "1.1.1.1")

        families.assign(session)
        session.expire_all()

        assert (later.ai_class, later.ai_confidence, later.ai_basis) == ("probe", 91, "family")

    def test_an_incident_without_words_is_named_for_its_program(self, session: Session) -> None:
        found = incident(session, "8.8.8.8", top_summary="12345")

        families.assign(session)

        family = session.get(IncidentFamily, found.family_id)
        assert family is not None
        assert family.label == "#"

    def test_a_pass_only_takes_so_many(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(families, "BATCH", 2)
        for number in range(1, 4):
            incident(session, f"8.8.8.{number}")

        assert families.assign(session) == 2
        assert families.assign(session) == 1
        assert families.assign(session) == 0
