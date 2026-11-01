from datetime import timedelta

import pytest
from psycopg.errors import DivisionByZero
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import Settings
from app.events.store import record as record_events
from app.interfaces import discovery
from app.interfaces.discovery import Found
from app.metrics.store import record as record_samples
from app.models import Event, IntegrationConnection, InterfaceFeed, utcnow
from tests.helpers import new_event, new_sample

NOW = utcnow()


def came_in(
    session: Session, settings: Settings, *ports: tuple[str, str, str | None], ago: timedelta
) -> None:
    """Stores an event for each (source, connection, port), as long ago as asked."""
    record_events(
        session,
        settings,
        [
            new_event(
                source=source,
                connection=connection,
                iface=port,
                occurred_at=NOW - ago,
                identity=(f"{source}-{connection}-{port}-{number}",),
            )
            for number, (source, connection, port) in enumerate(ports)
        ],
        NOW,
    )
    session.commit()


class TestPortsOfEvents:
    def test_each_port_is_found_once_per_program_and_connection(
        self, session: Session, settings: Settings
    ) -> None:
        came_in(
            session,
            settings,
            ("opnsense", "api", "igc0"),
            ("opnsense", "api", "igc0"),
            ("opnsense", "api", "igc1"),
            ("ntopng", "api", "igc0"),
            ago=timedelta(minutes=5),
        )

        found, complete = discovery.from_events(session, NOW)

        assert complete is True
        assert sorted(found) == [
            Found("ntopng", "api", "igc0"),
            Found("opnsense", "api", "igc0"),
            Found("opnsense", "api", "igc1"),
        ]

    def test_an_event_that_names_no_port_finds_nothing(
        self, session: Session, settings: Settings
    ) -> None:
        came_in(session, settings, ("wazuh", "indexer", None), ago=timedelta(minutes=5))

        assert discovery.from_events(session, NOW) == ([], True)

    def test_a_port_quiet_for_longer_than_the_window_is_not_found(
        self, session: Session, settings: Settings
    ) -> None:
        came_in(
            session,
            settings,
            ("opnsense", "api", "igc0"),
            ago=discovery.WINDOW + timedelta(hours=1),
        )

        assert discovery.from_events(session, NOW) == ([], True)

    def test_a_search_that_takes_too_long_is_given_up_and_said_so(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        came_in(session, settings, ("opnsense", "api", "igc0"), ago=timedelta(minutes=5))

        class Slow:
            """The columns of an event, with a port that takes a second to read."""

            source = Event.source
            connection = Event.connection
            occurred_at = Event.occurred_at
            iface = Event.iface.concat(func.pg_sleep(1).cast(Event.iface.type))

        monkeypatch.setattr(discovery, "Event", Slow)
        monkeypatch.setattr(discovery, "EVENTS_TIMEOUT_MS", 50)

        assert discovery.from_events(session, NOW) == ([], False)
        # What follows is not timed, and the session still works.
        assert session.scalar(select(func.current_setting("statement_timeout"))) == "0"

    def test_a_failure_that_is_not_a_timeout_is_not_hidden(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        came_in(session, settings, ("opnsense", "api", "igc0"), ago=timedelta(minutes=5))

        class Slow:
            """The columns of an event, with a port that takes a second to read."""

            source = Event.source
            connection = Event.connection
            occurred_at = Event.occurred_at
            iface = Event.iface.concat(func.pg_sleep(1).cast(Event.iface.type))

        monkeypatch.setattr(discovery, "Event", Slow)
        monkeypatch.setattr(discovery, "EVENTS_TIMEOUT_MS", 50)
        # The search is stopped, but as another kind of failure than running out of time.
        monkeypatch.setattr(discovery, "QueryCanceled", DivisionByZero)

        with pytest.raises(OperationalError, match="canceling statement"):
            discovery.from_events(session, NOW)


class TestPortsOfMetrics:
    def test_each_port_a_series_is_kept_for_is_found(
        self, session: Session, settings: Settings
    ) -> None:
        record_samples(
            session,
            settings,
            [
                new_sample(name="interface.bytes_in", labels={"interface": "igc0"}),
                new_sample(name="interface.bytes_out", labels={"interface": "igc0"}),
                new_sample(name="interface.bytes_in", labels={"interface": "igc1"}),
                new_sample(name="system.load_1m"),
                new_sample(name="system.load_5m", labels={"zone": "x"}),
            ],
            NOW,
        )
        session.commit()

        assert sorted(discovery.from_metrics(session)) == [
            Found("opnsense", "api", "igc0"),
            Found("opnsense", "api", "igc1"),
        ]


class TestConnectionsThatAreOneFeed:
    def connect(self, session: Session, integration: str, connection: str) -> None:
        session.add(
            IntegrationConnection(
                integration=integration,
                connection=connection,
                base_url="https://192.0.2.1:8443",
            )
        )
        session.commit()

    def test_only_a_connection_that_is_set_up_is_one(self, session: Session) -> None:
        self.connect(session, "crowdsec", "lapi")
        self.connect(session, "opnsense", "api")

        assert discovery.whole_connections(session) == [Found("crowdsec", "lapi", "")]

    def test_wazuh_s_alerts_are_one_as_well(self, session: Session) -> None:
        self.connect(session, "wazuh", "indexer")
        self.connect(session, "wazuh", "manager")

        assert discovery.whole_connections(session) == [Found("wazuh", "indexer", "")]

    def test_none_connected_finds_none(self, session: Session) -> None:
        assert discovery.whole_connections(session) == []


class TestKeepingWhatWasFound:
    def feeds(self, session: Session) -> dict[tuple[str, str, str], InterfaceFeed]:
        return {
            (feed.integration, feed.connection, feed.native_name): feed
            for feed in session.scalars(select(InterfaceFeed))
        }

    def test_a_feed_seen_for_the_first_time_is_made_and_not_placed(self, session: Session) -> None:
        new = discovery.store(
            session,
            [Found("opnsense", "api", "igc0", "WAN", "the way out"), Found("crowdsec", "lapi", "")],
            NOW,
        )

        assert new == 2
        feeds = self.feeds(session)
        wan = feeds["opnsense", "api", "igc0"]
        assert (wan.label, wan.detail) == ("WAN", "the way out")
        assert (wan.interface_id, wan.ignored) == (None, False)
        assert wan.last_seen_at == NOW
        assert ("crowdsec", "lapi", "") in feeds

    def test_one_found_twice_in_a_list_is_made_once(self, session: Session) -> None:
        assert discovery.store(session, [Found("a", "b", "c"), Found("a", "b", "c")], NOW) == 1

    def test_a_feed_seen_again_is_noted_as_seen_and_learns_what_the_source_says_of_it(
        self, session: Session
    ) -> None:
        discovery.store(session, [Found("opnsense", "api", "igc0")], NOW - timedelta(days=1))

        new = discovery.store(session, [Found("opnsense", "api", "igc0", "WAN", "fibre")], NOW)

        feed = self.feeds(session)["opnsense", "api", "igc0"]
        assert new == 0
        assert (feed.label, feed.detail, feed.last_seen_at) == ("WAN", "fibre", NOW)

    def test_what_a_source_says_is_not_blanked_by_one_that_says_less(
        self, session: Session
    ) -> None:
        discovery.store(session, [Found("ntopng", "api", "eth0", "WAN", "live capture")], NOW)

        discovery.store(session, [Found("ntopng", "api", "eth0")], NOW)

        feed = self.feeds(session)["ntopng", "api", "eth0"]
        assert (feed.label, feed.detail) == ("WAN", "live capture")

    def test_nothing_found_changes_nothing(self, session: Session) -> None:
        assert discovery.store(session, [], NOW) == 0
        assert self.feeds(session) == {}
