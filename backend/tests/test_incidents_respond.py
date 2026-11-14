from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.events.event import NewEvent, Severity
from app.incidents import respond
from tests.test_incidents_engine import (
    ATTACKER,
    NEIGHBOUR,
    NOW,
    OTHER_ATTACKER,
    alert,
    run,
    store,
)
from tests.test_incidents_response import (
    HOUR,
    MINUTE,
    connect,
    decision,
    incident_of,
    stopped,
    turned_away,
)

SOON = NOW + HOUR


def only(session: Session, settings: Settings, *events: NewEvent, days: int = 7) -> respond.Item:
    """The one incident the attacker's alert makes, once the events have been stored."""
    store(session, settings, alert(NOW), *events)
    run(session)
    (item,) = respond.overview(session, days, SOON).items
    return item


class TestWhereAnIncidentGoes:
    def test_one_nothing_has_answered_needs_a_response(
        self, session: Session, settings: Settings
    ) -> None:
        item = only(session, settings)

        assert item.group == "needs_response"
        assert item.why == "Nothing has banned it or turned it away."
        assert (item.banned_now, item.ban_ends_at, item.attackers) == (0, None, 1)

    def test_one_that_is_resolved_with_nothing_done_is_closed(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(NOW))
        run(session)
        incident_of(session).status = "resolved"
        session.commit()

        (item,) = respond.overview(session, 7, SOON).items

        assert (item.group, item.why) == ("closed", None)

    def test_a_ban_that_holds_is_a_banned_one_that_says_when_it_ends(
        self, session: Session, settings: Settings
    ) -> None:
        item = only(session, settings, decision(duration="4h"))

        assert (item.group, item.why, item.banned_now) == ("banned", None, 1)
        assert item.ban_ends_at == NOW + 2 * MINUTE + timedelta(hours=4)

    def test_a_ban_that_does_not_say_how_long_it_lasts_gives_no_end(
        self, session: Session, settings: Settings
    ) -> None:
        item = only(session, settings, decision(duration=None))

        assert (item.group, item.banned_now, item.ban_ends_at) == ("banned", 1, None)

    def test_the_last_end_of_several_bans_is_the_one_given(
        self, session: Session, settings: Settings
    ) -> None:
        item = only(
            session,
            settings,
            alert(NOW + MINUTE, n=2, src_address=NEIGHBOUR),
            decision(n=1, duration="2h"),
            decision(n=2, address=NEIGHBOUR, duration="5h"),
        )

        assert (item.group, item.banned_now, item.attackers) == ("banned", 2, 2)
        assert item.ban_ends_at == NOW + 2 * MINUTE + timedelta(hours=5)

    def test_some_of_the_addresses_banned_still_needs_a_response_while_it_goes_on(
        self, session: Session, settings: Settings
    ) -> None:
        item = only(session, settings, alert(NOW + MINUTE, n=2, src_address=NEIGHBOUR), decision())

        assert item.group == "needs_response"
        assert item.why == "Only 1 of its 2 addresses are banned."
        assert (item.banned_now, item.attackers) == (1, 2)

    def test_some_of_the_addresses_banned_is_a_banned_one_once_it_is_over(
        self, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            alert(NOW),
            alert(NOW + MINUTE, n=2, src_address=NEIGHBOUR),
            decision(),
        )
        run(session)
        incident_of(session).status = "resolved"
        session.commit()

        (item,) = respond.overview(session, 7, SOON).items

        assert (item.group, item.why) == ("banned", None)

    def test_a_ban_that_ended_with_nothing_seen_since_is_just_ended(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(NOW), decision(duration="30m"))
        run(session)

        (item,) = respond.overview(session, 7, NOW + 6 * HOUR).items

        assert (item.group, item.why, item.banned_now, item.ban_ends_at) == (
            "ban_ended",
            None,
            0,
            None,
        )

    def test_one_that_came_back_after_its_ban_ended_needs_a_response(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(NOW), decision(duration="30m"))
        run(session)
        found = incident_of(session)
        found.last_seen_at = NOW + 3 * HOUR
        session.commit()

        (item,) = respond.overview(session, 7, NOW + 6 * HOUR).items

        assert item.group == "needs_response"
        assert item.why == "It came back after its ban ended."

    def test_one_that_came_back_but_is_resolved_is_only_a_ban_that_ended(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(NOW), decision(duration="30m"))
        run(session)
        found = incident_of(session)
        found.last_seen_at = NOW + 3 * HOUR
        found.status = "resolved"
        session.commit()

        (item,) = respond.overview(session, 7, NOW + 6 * HOUR).items

        assert item.group == "ban_ended"

    def test_an_address_the_firewall_turned_away_is_blocked(
        self, session: Session, settings: Settings
    ) -> None:
        item = only(session, settings, turned_away(NOW + MINUTE, 1), stopped(NOW + MINUTE, 9))

        assert item.group == "blocked"
        assert (item.done.tally.blocked, item.done.tally.dropped) == (1, 1)

    def test_one_that_names_no_address_has_nothing_to_block(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(NOW, src_address=None, dst_address=None))
        run(session)

        (item,) = respond.overview(session, 7, SOON).items

        assert (item.group, item.why, item.attackers) == ("no_address", None, 1)


class TestWhichIncidentsCount:
    def test_only_medium_severity_and_up_count(self, session: Session, settings: Settings) -> None:
        store(
            session,
            settings,
            alert(NOW, severity=Severity.LOW),
            alert(NOW, n=2, src_address=OTHER_ATTACKER, severity=Severity.HIGH),
        )
        run(session)

        found = respond.overview(session, 7, SOON)

        assert [item.incident.subject for item in found.items] == [OTHER_ATTACKER]
        assert found.total == 1

    @pytest.mark.parametrize("verdict", ["not_suspicious", "low_priority"])
    def test_what_the_owner_called_harmless_does_not(
        self, session: Session, settings: Settings, verdict: str
    ) -> None:
        store(session, settings, alert(NOW))
        run(session)
        incident_of(session).verdict = verdict
        session.commit()

        assert respond.overview(session, 7, SOON).items == []

    def test_what_the_owner_called_a_threat_does(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(NOW))
        run(session)
        incident_of(session).verdict = "threat"
        session.commit()

        assert len(respond.overview(session, 7, SOON).items) == 1

    def test_a_dismissed_one_does_not(self, session: Session, settings: Settings) -> None:
        store(session, settings, alert(NOW))
        run(session)
        incident_of(session).status = "dismissed"
        session.commit()

        assert respond.overview(session, 7, SOON).items == []

    def test_only_what_went_on_in_the_days_asked_for_counts(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(NOW))
        run(session)

        assert len(respond.overview(session, 7, NOW + timedelta(days=6)).items) == 1
        assert respond.overview(session, 7, NOW + timedelta(days=8)).items == []
        assert len(respond.overview(session, 30, NOW + timedelta(days=8)).items) == 1

    def test_when_not_asked_it_is_now_that_counts(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(NOW))
        run(session)

        # The alert is long gone by the real date.
        assert respond.overview(session, 1).items == []


class TestTheOverview:
    def test_the_groups_come_in_order_and_the_most_serious_first_in_each(
        self, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            alert(NOW, severity=Severity.MEDIUM),
            alert(NOW, n=2, src_address=OTHER_ATTACKER, severity=Severity.CRITICAL),
            alert(NOW, n=3, src_address="1.1.1.1", severity=Severity.HIGH),
            decision(address="1.1.1.1"),
        )
        run(session)

        found = respond.overview(session, 7, SOON)

        assert [(item.incident.subject, item.group) for item in found.items] == [
            (OTHER_ATTACKER, "needs_response"),
            (ATTACKER, "needs_response"),
            ("1.1.1.1", "banned"),
        ]
        assert (found.count("needs_response"), found.count("banned"), found.count("closed")) == (
            2,
            1,
            0,
        )

    def test_it_holds_no_more_than_the_limit_and_says_how_many_there_were(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(respond, "MAX_INCIDENTS", 1)
        store(
            session,
            settings,
            alert(NOW, severity=Severity.HIGH),
            alert(NOW, n=2, src_address=OTHER_ATTACKER),
        )
        run(session)

        found = respond.overview(session, 7, SOON)

        assert found.total == 2
        assert [item.incident.subject for item in found.items] == [ATTACKER]

    def test_with_no_incidents_it_is_empty(self, session: Session) -> None:
        found = respond.overview(session, 7, SOON)

        assert (found.total, found.items) == (0, [])

    def test_it_says_which_of_the_programs_are_connected(self, session: Session) -> None:
        assert not respond.overview(session, 7, SOON).crowdsec_connected
        assert not respond.overview(session, 7, SOON).opnsense_connected

        connect(session, "crowdsec")
        found = respond.overview(session, 7, SOON)

        assert (found.crowdsec_connected, found.opnsense_connected) == (True, False)
        connect(session, "opnsense")
        assert respond.overview(session, 7, SOON).opnsense_connected
