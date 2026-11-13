"""A kind of incident that has changed since it was judged: what it was like then and is like now,
what counts as a change, how it is marked and shown to the AI, and when the AI asks again."""

import json
from datetime import timedelta
from ipaddress import ip_address

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import families
from app.ai.gateway import Answer
from app.ai.redaction import Level, Redactor
from app.config import Settings
from app.incidents import run as incident_run
from app.models import Incident, IncidentFamily
from app.review import settings as review_settings
from app.threats import drift
from tests.test_ai_families import asked_about_families, judgement, kind
from tests.test_ai_service import NOW
from tests.test_ai_triage import ready, with_level

MINUTE = timedelta(minutes=1)


def judged(session: Session, family: IncidentFamily, **changes: object) -> IncidentFamily:
    """A kind the AI judged a while ago, with what its incidents were like then."""
    family.judged_at = NOW - 3 * 60 * MINUTE
    family.judged_incidents = 3
    family.ai_class = "probe"
    family.ai_confidence = 93
    for name, value in changes.items():
        setattr(family, name, value)
    session.commit()
    return family


def members(session: Session, family: IncidentFamily) -> list[Incident]:
    return list(session.scalars(select(Incident).where(Incident.family_id == family.id)))


class TestWhatAKindIsLike:
    def test_it_is_what_its_incidents_that_are_going_on_say(self, session: Session) -> None:
        family = kind(session, 3, ports=[22, 80], stages=["recon"])
        first = members(session, family)[0]
        first.stages = ["access", "recon"]
        first.ports = [22, 3389]
        first.addresses = [
            ip_address("203.0.113.5"),
            ip_address("192.168.1.7"),
            ip_address("10.0.0.2"),
        ]
        session.commit()

        like = drift.profiles(session, [family.id])[family.id]

        assert like.stages == ("recon", "access")
        assert like.ports == (22, 80, 3389)
        assert like.devices == ("10.0.0.2", "192.168.1.20", "192.168.1.7")
        assert like.actors == 3

    def test_only_the_owners_own_devices_are_devices(self, session: Session) -> None:
        family = kind(session, 1)
        only = members(session, family)[0]
        only.addresses = [
            ip_address("203.0.113.5"),
            ip_address("8.8.8.8"),
            ip_address("172.16.5.5"),
            ip_address("172.32.0.1"),
            ip_address("fd12::1"),
        ]
        session.commit()

        like = drift.profiles(session, [family.id])[family.id]

        assert like.devices == ("172.16.5.5", "fd12::1")

    def test_incidents_that_are_over_are_not_what_it_is_like(self, session: Session) -> None:
        family = kind(session, 2, ports=[22])
        going, over = sorted(members(session, family), key=lambda each: each.id)
        going.ports = [80]
        over.ports = [9999]
        over.status = "resolved"
        session.commit()

        like = drift.profiles(session, [family.id])[family.id]

        assert like.ports == (80,)
        assert like.actors == 1

    def test_a_kind_with_nothing_going_is_left_out(self, session: Session) -> None:
        family = kind(session, 1)
        members(session, family)[0].status = "dismissed"
        session.commit()

        assert drift.profiles(session, [family.id]) == {}
        assert drift.profiles(session, []) == {}

    def test_no_more_than_so_many_ports_and_devices_are_kept(self, session: Session) -> None:
        family = kind(session, 1)
        only = members(session, family)[0]
        only.ports = list(range(1, 80))
        only.addresses = [ip_address(f"10.0.0.{number}") for number in range(1, 49)] + [
            ip_address(f"10.0.1.{number}") for number in range(1, 9)
        ]
        session.commit()

        like = drift.profiles(session, [family.id])[family.id]

        assert like.ports == tuple(range(1, drift.KEPT + 1))
        assert len(like.devices) == drift.KEPT

    def test_it_is_kept_as_json_and_read_back(self) -> None:
        like = drift.Profile(("recon",), (22,), ("10.0.0.1",), 4)

        assert drift.Profile.of(like.as_json()) == like
        assert drift.Profile.of({}) == drift.Profile()


class TestWhatCountsAsAChange:
    before = drift.Profile(("recon",), (22, 80), ("192.168.1.20",), 10)

    def test_a_kind_as_it_was_has_not_changed(self) -> None:
        assert drift.compare(self.before, self.before) == {}

    def test_what_went_away_is_not_a_change(self) -> None:
        assert drift.compare(self.before, drift.Profile((), (22,), (), 2)) == {}

    def test_a_new_stage_is_one(self) -> None:
        now = drift.Profile(("recon", "access", "foothold"), (22, 80), ("192.168.1.20",), 10)

        assert drift.compare(self.before, now) == {drift.STAGES: ["access", "foothold"]}

    def test_a_new_port_is_one_for_a_kind_that_touched_few(self) -> None:
        now = drift.Profile(("recon",), (22, 80, 3389, 445), ("192.168.1.20",), 10)

        assert drift.compare(self.before, now) == {drift.PORTS: [445, 3389]}

    def test_a_new_port_is_not_news_for_a_kind_that_touched_many(self) -> None:
        wide = drift.Profile((), tuple(range(1, 30)), (), 1)

        assert drift.compare(wide, drift.Profile((), (*wide.ports, 3389), (), 1)) == {}

    def test_no_more_ports_are_named_than_a_line_can_hold(self) -> None:
        now = drift.Profile(("recon",), tuple(range(1000, 1030)), (), 10)

        changed = drift.compare(self.before, now)

        assert changed[drift.PORTS] == list(range(1000, 1000 + drift.SHOWN))

    def test_a_new_device_is_one_for_a_kind_that_touched_few(self) -> None:
        now = drift.Profile(("recon",), (22, 80), ("192.168.1.20", "192.168.1.8"), 10)

        assert drift.compare(self.before, now) == {drift.DEVICES: ["192.168.1.8"]}

    def test_a_new_device_is_not_news_for_a_kind_that_touched_many(self) -> None:
        wide = drift.Profile((), (), tuple(f"10.0.0.{number}" for number in range(1, 30)), 1)

        assert drift.compare(wide, drift.Profile((), (), (*wide.devices, "10.0.1.1"), 1)) == {}

    @pytest.mark.parametrize(
        ("actors", "changed"),
        [(29, False), (30, True), (500, True)],
    )
    def test_many_more_addresses_is_one_but_a_few_more_is_not(
        self, actors: int, changed: bool
    ) -> None:
        now = drift.Profile(("recon",), (22, 80), ("192.168.1.20",), actors)

        assert (drift.compare(self.before, now) != {}) is changed

    def test_a_rise_has_to_be_big_in_numbers_too(self) -> None:
        small = drift.Profile((), (), (), 1)

        assert drift.compare(small, drift.Profile((), (), (), 5)) == {}
        assert drift.compare(small, drift.Profile((), (), (), 25)) == {drift.ACTORS: [1, 25]}


class TestInWords:
    def test_each_change_is_a_line(self) -> None:
        lines = drift.describe(
            {
                drift.STAGES: ["access"],
                drift.PORTS: [3389, 445],
                drift.DEVICES: ["192.168.1.8"],
                drift.ACTORS: [4, 40],
            }
        )

        assert lines == [
            "It has a stage of an attack it did not have before: trying to get in.",
            "It now reaches destination ports it did not before: 3389, 445.",
            "It now targets devices it did not before: 192.168.1.8.",
            "It comes from many more addresses: 4 when it was judged, 40 now.",
        ]

    def test_an_address_is_said_the_way_it_is_asked_to(self) -> None:
        lines = drift.describe({drift.DEVICES: ["192.168.1.8", "10.0.0.1"]}, lambda _: "<device>")

        assert lines == ["It now targets devices it did not before: <device>, <device>."]

    def test_a_stage_without_a_name_is_said_as_it_is(self) -> None:
        assert drift.describe({drift.STAGES: ["odd"]}) == [
            "It has a stage of an attack it did not have before: odd."
        ]

    def test_a_kind_as_it_was_says_nothing(self, session: Session) -> None:
        family = kind(session, 1)

        assert drift.lines_of(family) == []

        family.changes = {drift.ACTORS: [1, 30]}

        assert drift.lines_of(family) == [
            "It comes from many more addresses: 1 when it was judged, 30 now."
        ]


class TestNoticing:
    def test_a_kind_judged_before_this_was_kept_takes_what_it_is_like_now(
        self, session: Session
    ) -> None:
        family = judged(session, kind(session, 3, ports=[22]))

        assert drift.detect(session, NOW) == 0

        assert family.judged_profile == drift.profiles(session, [family.id])[family.id].as_json()
        assert family.changes is None
        assert family.drift_checked_at == NOW

    def test_a_kind_that_has_changed_is_marked_when_it_is_noticed(self, session: Session) -> None:
        family = judged(session, kind(session, 3, ports=[22]))
        drift.detect(session, NOW)
        members(session, family)[0].ports = [22, 3389]
        members(session, family)[0].stages = ["foothold"]
        session.commit()

        marked = drift.detect(session, NOW + 10 * MINUTE)

        assert marked == 1
        assert family.changes == {drift.STAGES: ["foothold"], drift.PORTS: [3389]}
        assert family.changed_at == NOW + 10 * MINUTE

    def test_it_stays_marked_from_when_it_was_first_noticed(self, session: Session) -> None:
        family = judged(session, kind(session, 3, ports=[22]))
        drift.detect(session, NOW)
        members(session, family)[0].ports = [22, 3389]
        session.commit()
        drift.detect(session, NOW + 10 * MINUTE)
        members(session, family)[0].stages = ["access"]
        session.commit()

        drift.detect(session, NOW + 20 * MINUTE)

        assert family.changes == {drift.STAGES: ["access"], drift.PORTS: [3389]}
        assert family.changed_at == NOW + 10 * MINUTE

    def test_it_is_cleared_when_it_is_as_it_was_again(self, session: Session) -> None:
        family = judged(session, kind(session, 3, ports=[22]))
        drift.detect(session, NOW)
        extra = members(session, family)[0]
        extra.ports = [22, 3389]
        session.commit()
        drift.detect(session, NOW + 10 * MINUTE)
        extra.ports = [22]
        session.commit()

        assert drift.detect(session, NOW + 20 * MINUTE) == 0

        assert family.changes is None
        assert family.changed_at is None

    def test_a_kind_the_owner_called_is_marked_too(self, session: Session) -> None:
        family = kind(session, 3, ports=[22])
        family.owner_call = "background"
        session.commit()
        drift.detect(session, NOW)
        members(session, family)[0].stages = ["foothold"]
        session.commit()

        assert drift.detect(session, NOW + 10 * MINUTE) == 1
        assert family.owner_call == "background"
        assert family.changes == {drift.STAGES: ["foothold"]}

    def test_a_kind_nobody_has_judged_or_called_is_not_looked_at(self, session: Session) -> None:
        family = kind(session, 3)

        assert drift.detect(session, NOW) == 0
        assert family.judged_profile is None
        assert family.drift_checked_at is None

    def test_a_kind_is_not_looked_at_again_within_minutes(self, session: Session) -> None:
        family = judged(session, kind(session, 3, ports=[22]))
        drift.detect(session, NOW)
        members(session, family)[0].stages = ["foothold"]
        session.commit()

        assert drift.detect(session, NOW + MINUTE) == 0
        assert family.changes is None

    def test_a_kind_that_has_not_moved_is_not_looked_at_again(self, session: Session) -> None:
        family = judged(session, kind(session, 3, ports=[22]))
        for each in members(session, family):
            each.updated_at = NOW - 60 * MINUTE
            each.last_seen_at = NOW - 60 * MINUTE
        drift.detect(session, NOW)

        assert drift.due(session, NOW + 10 * MINUTE) == []

    def test_a_kind_whose_incidents_are_over_is_not_looked_at(self, session: Session) -> None:
        family = judged(session, kind(session, 2))
        for each in members(session, family):
            each.status = "resolved"
        session.commit()

        assert drift.due(session, NOW) == []

    def test_a_kind_looked_at_once_with_no_incident_left_takes_what_there_is(
        self, session: Session
    ) -> None:
        family = judged(session, kind(session, 2), judged_profile={drift.STAGES: ["recon"]})
        for each in members(session, family):
            each.status = "resolved"
        session.commit()

        assert drift.detect(session, NOW) == 0
        assert family.changes is None

    def test_the_longest_ago_is_looked_at_first_and_no_more_than_a_run_can_hold(
        self, session: Session
    ) -> None:
        for number in range(drift.BATCH + 2):
            judged(session, kind(session, 1, f"ET SCAN number {chr(97 + number)}"))

        assert len(drift.due(session, NOW)) == drift.BATCH

    def test_the_worker_notices_while_it_files_incidents(self, session: Session) -> None:
        family = judged(session, kind(session, 3, ports=[22]))

        incident_run.correlate_once(lambda: session)

        session.expire_all()
        assert session.get(IncidentFamily, family.id).judged_profile is not None  # type: ignore[union-attr]


class TestKeeping:
    def test_what_a_kind_is_like_when_judged_is_kept_and_what_changed_is_forgotten(
        self, session: Session
    ) -> None:
        family = kind(session, 3, ports=[22])
        family.changes = {drift.STAGES: ["access"]}
        family.changed_at = NOW - 60 * MINUTE
        like = drift.Profile(("recon",), (22,), (), 3)

        drift.keep(family, like, NOW)

        assert family.judged_profile == like.as_json()
        assert family.changes is None
        assert family.changed_at is None
        assert family.drift_checked_at == NOW


class TestAskingAgain:
    def at_level(self, session: Session, settings: Settings, level: str) -> None:
        ready(session, settings)
        with_level(session, level)

    def test_a_kind_that_has_changed_is_judged_again_before_it_has_grown(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "medium")
        family = judged(session, kind(session, 5), judged_incidents=5, changed_at=NOW - 5 * MINUTE)
        family.judged_at = NOW - 20 * MINUTE
        session.commit()

        assert families.plan(session, NOW) == [family.id]

    def test_at_the_lowest_level_that_judges_a_changed_kind_is_judged_again_too(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "low")
        family = judged(session, kind(session, 20), changed_at=NOW - 5 * MINUTE)

        assert families.plan(session, NOW) == [family.id]

    def test_the_lowest_level_judges_none_changed_or_not(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "very_low")
        judged(session, kind(session, 20), changed_at=NOW - 5 * MINUTE)

        assert families.plan(session, NOW) == []

    def test_it_is_not_asked_about_again_within_a_while(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "medium")
        family = judged(session, kind(session, 5), judged_incidents=5, changed_at=NOW)
        family.judged_at = NOW - 5 * MINUTE
        session.commit()

        assert families.plan(session, NOW) == []

    def test_a_kind_that_has_not_changed_is_left_alone(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "medium")
        judged(session, kind(session, 5), judged_incidents=5)

        assert families.plan(session, NOW) == []

    def test_a_kind_the_owner_called_is_left_alone_though_it_changed(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "medium")
        judged(
            session,
            kind(session, 5),
            owner_call="watch",
            changed_at=NOW - 5 * MINUTE,
        )

        assert families.plan(session, NOW) == []

    def test_the_changed_come_before_the_bigger(self, session: Session, settings: Settings) -> None:
        self.at_level(session, settings, "maximum")
        big = kind(session, 6, "ET SCAN big")
        small = judged(session, kind(session, 2, "ET SCAN small"), changed_at=NOW - 5 * MINUTE)

        assert families.plan(session, NOW) == [small.id, big.id]

    def test_the_ai_is_told_what_changed_and_what_it_said_before(self, session: Session) -> None:
        family = judged(
            session,
            kind(session, 3),
            changes={drift.STAGES: ["access"], drift.DEVICES: ["192.168.1.8"]},
            changed_at=NOW,
        )
        _, found = families.question_for(session, [family.id])
        redactor = Redactor(session, Level.BALANCED, NOW)

        said = redactor.finish(families.prompt_for(found, redactor))

        assert "CHANGED since you judged it probe (93% sure):" in said
        assert "- It has a stage of an attack it did not have before: trying to get in." in said
        assert "192.168.1.8" not in said

    def test_a_kind_changed_that_was_not_judged_is_said_to_have_been_before(
        self, session: Session
    ) -> None:
        family = kind(session, 3)
        family.owner_call = "watch"
        family.changes = {drift.ACTORS: [1, 40]}
        session.commit()
        _, found = families.question_for(session, [family.id])
        redactor = Redactor(session, Level.BALANCED, NOW)

        said = redactor.finish(families.prompt_for(found, redactor))

        assert "CHANGED since it was judged before:" in said

    def test_a_kind_that_has_not_changed_says_nothing_of_it(self, session: Session) -> None:
        family = kind(session, 3)
        _, found = families.question_for(session, [family.id])
        redactor = Redactor(session, Level.BALANCED, NOW)

        assert "CHANGED" not in redactor.finish(families.prompt_for(found, redactor))

    def test_judging_it_again_makes_it_as_it_is_now(self, session: Session) -> None:
        review_settings.save(session, review_settings.Policy("auto"))
        call = asked_about_families(session)
        family = judged(
            session,
            kind(session, 3, ports=[22, 3389]),
            changes={drift.PORTS: [3389]},
            changed_at=NOW,
        )
        _, found = families.question_for(session, [family.id])
        answer = Answer(
            ok=True,
            text=json.dumps(judgement(1)),
            reason=None,
            call_id=call,
            truncated=False,
            provider="anthropic",
            model="claude-haiku-5-5",
        )

        families.keep(session, found, answer, NOW)
        session.commit()

        assert family.changes is None
        assert family.changed_at is None
        assert family.judged_profile is not None
        assert family.judged_profile[drift.PORTS] == [22, 3389]
        assert family.drift_checked_at == NOW
