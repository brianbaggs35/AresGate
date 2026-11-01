from sqlalchemy.orm import Session

from app.interfaces import service
from app.interfaces.scope import Resolver
from app.models import InterfaceFeed


def feed(session: Session, integration: str, connection: str, name: str) -> InterfaceFeed:
    made = InterfaceFeed(integration=integration, connection=connection, native_name=name)
    session.add(made)
    session.flush()
    return made


def test_data_belongs_to_the_interface_its_port_is_placed_on(session: Session) -> None:
    port = feed(session, "opnsense", "api", "igc0")
    internet = service.create(
        session, name="Internet", role="internet", notes="", networks=[], feeds=[port.id]
    )

    place = Resolver(session).of("opnsense", "api", "igc0")

    assert place is not None
    assert place.interface is not None
    assert place.interface.id == internet.id
    assert place.ignored is False


def test_the_same_name_from_another_program_is_another_feed(session: Session) -> None:
    port = feed(session, "opnsense", "api", "igc0")
    service.create(
        session, name="Internet", role="internet", notes="", networks=[], feeds=[port.id]
    )

    assert Resolver(session).of("ntopng", "api", "igc0") is None


def test_placing_a_feed_elsewhere_moves_all_its_data(session: Session) -> None:
    port = feed(session, "opnsense", "api", "igc0")
    service.create(
        session, name="Internet", role="internet", notes="", networks=[], feeds=[port.id]
    )
    second = service.create(session, name="Home", role="home", notes="", networks=[], feeds=[])

    service.place(session, port.id, second.id)

    place = Resolver(session).of("opnsense", "api", "igc0")
    assert place is not None
    assert place.interface is not None
    assert place.interface.id == second.id


def test_a_feed_set_aside_says_so(session: Session) -> None:
    port = feed(session, "opnsense", "api", "lo0")
    service.place(session, port.id, None, ignored=True)

    place = Resolver(session).of("opnsense", "api", "lo0")

    assert place is not None
    assert (place.interface, place.ignored) == (None, True)


def test_data_without_a_port_belongs_to_the_interface_of_the_whole_connection(
    session: Session,
) -> None:
    ban = feed(session, "crowdsec", "lapi", "")
    internet = service.create(
        session, name="Internet", role="internet", notes="", networks=[], feeds=[ban.id]
    )
    resolver = Resolver(session)

    for name in (None, "", "ignored-port-name"):
        place = resolver.of("crowdsec", "lapi", name)
        assert place is not None
        assert place.interface is not None
        assert place.interface.id == internet.id


def test_a_port_nobody_placed_falls_back_to_the_whole_connection(session: Session) -> None:
    feed(session, "wazuh", "indexer", "agent-1")
    whole = feed(session, "wazuh", "indexer", "")
    home = service.create(
        session, name="Home", role="home", notes="", networks=[], feeds=[whole.id]
    )

    place = Resolver(session).of("wazuh", "indexer", "agent-1")

    assert place is not None
    assert place.interface is not None
    assert place.interface.id == home.id


def test_a_port_set_aside_stays_aside_whatever_the_connection_as_a_whole_says(
    session: Session,
) -> None:
    aside = feed(session, "wazuh", "indexer", "agent-1")
    service.place(session, aside.id, None, ignored=True)
    whole = feed(session, "wazuh", "indexer", "")
    service.create(session, name="Home", role="home", notes="", networks=[], feeds=[whole.id])

    place = Resolver(session).of("wazuh", "indexer", "agent-1")

    assert place is not None
    assert (place.interface, place.ignored) == (None, True)


def test_what_nobody_has_seen_belongs_nowhere(session: Session) -> None:
    assert Resolver(session).of("opnsense", "api", "igc0") is None
    assert Resolver(session).of("opnsense", "api", None) is None
