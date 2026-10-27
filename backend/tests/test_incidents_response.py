from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import Settings
from app.events.event import NewEvent, Severity
from app.incidents import response
from app.models import Event, Incident, IntegrationConnection
from tests.helpers import new_event
from tests.test_incidents_engine import (
    ATTACKER,
    NEIGHBOUR,
    NOW,
    OTHER_ATTACKER,
    alert,
    incidents,
    run,
    store,
)

MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)
SCENARIO = "crowdsecurity/ssh-bf"


def decision(
    at: datetime = NOW + 2 * MINUTE,
    n: int = 1,
    address: str = ATTACKER,
    duration: str | None = "4h",
    **raw: Any,
) -> NewEvent:
    """A ban as the CrowdSec collector keeps it: dated by the minute it was first read."""
    record: dict[str, Any] = {
        "id": n,
        "origin": "crowdsec",
        "type": "ban",
        "scope": "Ip",
        "value": address,
        "scenario": SCENARIO,
        **({"duration": duration} if duration else {}),
        **raw,
    }
    return new_event(
        source="crowdsec",
        connection="lapi",
        kind="decision",
        severity=Severity.MEDIUM,
        occurred_at=at,
        identity=(f"ban-{n}",),
        summary=f"Ban {address}",
        signature=SCENARIO,
        src_address=address,
        raw=record,
    )


def turned_away(at: datetime, n: int, address: str = ATTACKER) -> NewEvent:
    """A packet the firewall blocked."""
    return new_event(
        source="opnsense",
        connection="api",
        kind="firewall",
        severity=Severity.LOW,
        occurred_at=at,
        identity=(f"block-{n}",),
        summary="Blocked",
        src_address=address,
    )


def stopped(at: datetime, n: int) -> NewEvent:
    """An alert Suricata stopped."""
    return alert(
        at,
        n=n,
        source="opnsense",
        connection="api",
        severity=Severity.LOW,
        raw={"alert_action": "blocked"},
    )


def connect(session: Session, *integrations: str) -> None:
    session.add_all(
        IntegrationConnection(integration=key, connection="api", base_url="https://host.test")
        for key in integrations
    )
    session.commit()


def incident_of(session: Session, address: str = ATTACKER) -> Incident:
    return next(found for found in incidents(session) if found.subject == address)


def judged(
    session: Session, settings: Settings, *events: NewEvent, now: datetime = NOW + HOUR
) -> response.Response:
    """What was done about the attacker's incident, once the events have been stored."""
    store(session, settings, alert(NOW), *events)
    run(session)
    return response.of(session, [incident_of(session)], now)[incident_of(session).id]


class TestTheTimeLeftOfABan:
    @pytest.mark.parametrize(
        ("text", "left"),
        [
            ("3h59m12s", timedelta(hours=3, minutes=59, seconds=12)),
            ("23h59m59.5s", timedelta(hours=23, minutes=59, seconds=59.5)),
            ("1m30s", timedelta(seconds=90)),
            ("0s", timedelta(0)),
            ("-5m", timedelta(minutes=-5)),
            ("1.5h", timedelta(minutes=90)),
            ("500ms", timedelta(milliseconds=500)),
            ("250µs", timedelta(microseconds=250)),
            ("250μs", timedelta(microseconds=250)),
            ("10ns", timedelta(0)),
        ],
    )
    def test_a_go_duration_is_read(self, text: str, left: timedelta) -> None:
        assert response.time_left(text) == left

    @pytest.mark.parametrize("text", ["", "3 hours", "5", "h", "1d", "1.h", "m5", "1h 2m", "--1h"])
    def test_text_that_is_not_one_is_not_guessed_at(self, text: str) -> None:
        assert response.time_left(text) is None

    def test_a_time_too_long_to_be_one_is_not_read(self) -> None:
        assert response.time_left("9" * 40 + "h") is None

    def test_a_ban_that_runs_past_the_end_of_time_has_no_end_that_is_known(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(session, settings, decision(duration="2000000000h"))

        assert done.bans[0].ends_at is None
        assert done.state == "banned"


class TestWhatWasDone:
    def test_a_ban_that_is_still_in_force_is_a_banned_address(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(session, settings, decision(duration="3h59m12s"), now=NOW + HOUR)

        assert done.state == "banned"
        assert done.label == "Banned"
        (ban,) = done.bans
        assert (ban.address, ban.kind, ban.scenario) == (ATTACKER, "ban", SCENARIO)
        assert ban.origin == "CrowdSec's own detection"
        assert ban.seen_at == NOW + 2 * MINUTE
        assert ban.ends_at == NOW + 2 * MINUTE + timedelta(hours=3, minutes=59, seconds=12)
        assert ban.in_force(NOW + HOUR)

    def test_a_ban_that_has_run_out_is_one_that_ended(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(session, settings, decision(duration="1h"), now=NOW + 6 * HOUR)

        assert done.state == "ban_ended"
        assert done.label == "Ban ended"
        assert not done.bans[0].in_force(NOW + 6 * HOUR)

    def test_a_ban_whose_length_is_not_known_is_taken_to_hold(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(session, settings, decision(duration=None), now=NOW + 30 * HOUR)

        assert done.state == "banned"
        assert done.bans[0].ends_at is None

    def test_an_origin_it_does_not_know_is_shown_as_it_is(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(session, settings, decision(origin="somewhere-new"))

        assert done.bans[0].origin == "somewhere-new"

    def test_a_ban_that_says_nothing_of_where_it_came_from_has_no_origin(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(session, settings, decision(origin=7, type=None))

        assert done.bans[0].origin is None
        assert done.bans[0].kind == "ban"

    def test_a_simulated_ban_is_listed_but_is_no_response(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(session, settings, decision(simulated=True))

        assert done.state == "none"
        assert [ban.simulated for ban in done.bans] == [True]
        assert not done.bans[0].in_force(NOW)

    def test_another_remedy_is_listed_but_is_no_ban(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(session, settings, decision(type="Captcha"))

        assert done.state == "none"
        assert done.bans[0].kind == "captcha"

    def test_a_ban_whose_decision_is_gone_still_counts_as_one(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(NOW), decision())
        run(session)
        session.execute(delete(Event).where(Event.kind == "decision"))
        session.commit()
        connect(session, "crowdsec", "opnsense")

        found = incident_of(session)
        done = response.of(session, [found], NOW + HOUR)[found.id]

        assert done.state == "banned"
        assert done.bans == ()
        assert done.unknown == ("The ban was made too long ago for its details to be kept.",)

    def test_turned_away_by_the_firewall_is_blocked(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(
            session, settings, turned_away(NOW + 5 * MINUTE, 1), turned_away(NOW + 9 * MINUTE, 2)
        )

        assert done.state == "blocked"
        assert done.label == "Blocked"
        assert done.tally.blocked == 2
        assert done.tally.last_blocked_at == NOW + 9 * MINUTE
        assert done.tally.dropped == 0

    def test_an_alert_that_suricata_stopped_is_blocked(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(session, settings, stopped(NOW + MINUTE, 2))

        assert done.state == "blocked"
        assert done.tally.dropped == 1
        assert done.tally.blocked == 0

    def test_a_blocked_packet_of_no_importance_or_of_another_address_is_not_counted(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(
            session,
            settings,
            replace(turned_away(NOW + MINUTE, 1), severity=Severity.INFO),
            turned_away(NOW + MINUTE, 2, address=OTHER_ATTACKER),
            turned_away(NOW - 2 * HOUR, 3),
        )

        assert done.state == "none"
        assert done.tally.blocked == 0

    def test_nothing_done_is_no_response_yet(self, session: Session, settings: Settings) -> None:
        done = judged(session, settings)

        assert done.state == "none"
        assert done.label == "No response yet"
        assert done.bans == ()

    def test_an_incident_about_a_rule_has_no_address_to_act_on(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(NOW, src_address=None, dst_address=None))
        run(session)
        (found,) = incidents(session)

        done = response.of(session, [found], NOW + HOUR)[found.id]

        assert done.state == "no_address"
        assert done.label == "Nothing to block"
        assert (done.bans, done.unknown, done.tally) == ((), (), response.Tally())


class TestABlockOfAddresses:
    def test_a_ban_of_some_of_the_addresses_is_a_partial_one(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(
            session, settings, alert(NOW + MINUTE, n=2, src_address=NEIGHBOUR), decision()
        )

        assert done.state == "partly"
        assert done.label == "Partly banned"

    def test_a_ban_of_all_of_them_is_a_ban(self, session: Session, settings: Settings) -> None:
        done = judged(
            session,
            settings,
            alert(NOW + MINUTE, n=2, src_address=NEIGHBOUR),
            decision(),
            decision(n=2, address=NEIGHBOUR),
        )

        assert done.state == "banned"
        assert {ban.address for ban in done.bans} == {ATTACKER, NEIGHBOUR}

    def test_the_subject_is_listed_first_and_then_the_newest(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(response, "MAX_BANS", 3)
        done = judged(
            session,
            settings,
            alert(NOW + MINUTE, n=2, src_address=NEIGHBOUR),
            decision(NOW + 2 * MINUTE, n=1, address=NEIGHBOUR),
            decision(NOW + 3 * MINUTE, n=2),
            decision(NOW + 4 * MINUTE, n=3),
            decision(NOW + 5 * MINUTE, n=4, address=NEIGHBOUR),
        )

        assert [(ban.address, ban.seen_at) for ban in done.bans] == [
            (ATTACKER, NOW + 4 * MINUTE),
            (ATTACKER, NOW + 3 * MINUTE),
            (NEIGHBOUR, NOW + 5 * MINUTE),
        ]


class TestHowOftenItWasTurnedAway:
    def test_blocks_are_counted_from_the_first_ban_on(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(
            session,
            settings,
            turned_away(NOW + MINUTE, 1),
            decision(NOW + 2 * MINUTE),
            turned_away(NOW + 3 * MINUTE, 2),
            turned_away(NOW + 4 * MINUTE, 3),
        )

        assert done.tally.blocked == 3
        assert done.tally.after_ban == 2

    def test_the_blocks_of_a_whole_ban_count_though_the_incident_was_long_over(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(
            session,
            settings,
            decision(NOW + 2 * MINUTE, duration="4h"),
            turned_away(NOW + 3 * HOUR, 1),
            turned_away(NOW + 5 * HOUR, 2),
            now=NOW + 12 * HOUR,
        )

        # The first is during the ban, the second after it ended.
        assert done.tally.blocked == 1

    def test_a_ban_that_is_still_going_counts_blocks_up_to_now(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(
            session,
            settings,
            decision(NOW + 2 * MINUTE, duration="4h"),
            turned_away(NOW + 3 * HOUR, 1),
            turned_away(NOW + 3 * HOUR + 30 * MINUTE, 2),
            now=NOW + 3 * HOUR + 10 * MINUTE,
        )

        assert done.tally.blocked == 1

    def test_a_ban_that_was_not_one_does_not_lengthen_the_time_that_counts(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(
            session,
            settings,
            decision(NOW + 2 * MINUTE, duration="4h", simulated=True),
            turned_away(NOW + 3 * HOUR, 1),
            now=NOW + 12 * HOUR,
        )

        assert done.tally.blocked == 0
        assert done.tally.after_ban == 0


class TestWhatCannotBeTold:
    def test_a_program_that_is_not_connected_is_named(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(session, settings)

        assert done.unknown == (
            "CrowdSec isn't connected, so AresGate can't see whether it banned it.",
            "OPNsense isn't connected, so AresGate can't see whether its firewall or Suricata "
            "turned it away.",
        )

    def test_nothing_is_missing_when_both_are_connected(
        self, session: Session, settings: Settings
    ) -> None:
        connect(session, "crowdsec", "opnsense")

        assert judged(session, settings).unknown == ()

    def test_a_ban_says_that_it_is_dated_by_when_it_was_read(
        self, session: Session, settings: Settings
    ) -> None:
        connect(session, "crowdsec", "opnsense")

        done = judged(session, settings, decision())

        assert done.unknown == (
            "A ban is dated by when AresGate first read it, which may be a little later.",
        )

    def test_blocks_that_were_seen_mean_the_firewall_is_connected(
        self, session: Session, settings: Settings
    ) -> None:
        connect(session, "crowdsec")

        assert judged(session, settings, turned_away(NOW + MINUTE, 1)).unknown == ()


class TestManyIncidents:
    def test_each_is_answered_by_its_id(self, session: Session, settings: Settings) -> None:
        store(
            session,
            settings,
            alert(NOW),
            alert(NOW + MINUTE, n=2, src_address=OTHER_ATTACKER),
            decision(NOW + 2 * MINUTE),
            turned_away(NOW + 3 * MINUTE, 1, address=OTHER_ATTACKER),
        )
        run(session)
        found = incidents(session)

        done = response.of(session, found, NOW + HOUR)

        assert {incident.subject: done[incident.id].state for incident in found} == {
            ATTACKER: "banned",
            OTHER_ATTACKER: "blocked",
        }

    def test_none_is_answered_with_none(self, session: Session) -> None:
        assert response.of(session, []) == {}

    def test_a_ban_made_outside_the_time_of_an_incident_is_not_one_of_its_bans(
        self, session: Session, settings: Settings
    ) -> None:
        done = judged(session, settings, decision(NOW + 30 * HOUR))

        assert done.bans == ()
        assert done.state == "none"
