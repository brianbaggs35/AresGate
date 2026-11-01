import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.interfaces import service
from app.models import Interface, InterfaceFeed


def feed(session: Session, name: str = "igc0", **changes: object) -> InterfaceFeed:
    made = InterfaceFeed(integration="opnsense", connection="api", native_name=name, **changes)
    session.add(made)
    session.flush()
    return made


def make(session: Session, name: str = "Internet", **changes: object) -> Interface:
    fields: dict[str, object] = {"role": "internet", "notes": "", "networks": [], "feeds": []}
    return service.create(session, name=name, **(fields | changes))  # type: ignore[arg-type]


class TestTheNetworks:
    def test_a_block_is_kept_as_it_is_written_canonically(self) -> None:
        assert service.clean_networks([" 192.168.20.7/24 ", "fd00::1/64", "10.0.0.0/8"]) == [
            "192.168.20.0/24",
            "fd00::/64",
            "10.0.0.0/8",
        ]

    def test_one_written_twice_is_kept_once(self) -> None:
        assert service.clean_networks(["192.168.1.0/24", "192.168.1.9/24"]) == ["192.168.1.0/24"]

    def test_a_lone_address_is_a_network_of_one(self) -> None:
        assert service.clean_networks(["192.168.1.9"]) == ["192.168.1.9/32"]

    def test_what_is_not_a_network_is_refused_and_named(self) -> None:
        with pytest.raises(service.InterfaceError, match="isn't a network") as refused:
            service.clean_networks(["192.168.1.0/24", "my house"])

        assert "'my house'" in str(refused.value)
        assert not refused.value.missing
        assert not refused.value.conflict

    def test_there_is_a_limit(self) -> None:
        with pytest.raises(service.InterfaceError, match="up to 16 networks"):
            service.clean_networks([f"10.0.{number}.0/24" for number in range(17)])


class TestMakingOne:
    def test_it_goes_at_the_end_of_the_list(self, session: Session) -> None:
        first = make(session, "Internet")
        second = make(session, "Home", role="home")

        assert (first.position, second.position) == (0, 1)

    def test_feeds_are_placed_on_it_once_each(self, session: Session) -> None:
        one, two = feed(session, "igc0"), feed(session, "igc1")

        made = make(session, feeds=[one.id, two.id, one.id])

        assert [item.interface_id for item in (one, two)] == [made.id, made.id]

    def test_its_networks_are_cleaned(self, session: Session) -> None:
        assert make(session, networks=["192.168.1.9/24"]).networks == ["192.168.1.0/24"]

    def test_a_role_that_does_not_exist_is_refused(self, session: Session) -> None:
        with pytest.raises(service.InterfaceError, match="The role is one of"):
            make(session, role="spaceship")

    def test_a_name_is_taken_whatever_its_capitals(self, session: Session) -> None:
        make(session, "Guests", role="guest")

        with pytest.raises(service.InterfaceError, match="already an interface called guests") as e:
            make(session, "guests", role="guest")

        assert e.value.conflict

    def test_there_is_a_limit_on_how_many(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(service, "MAX_INTERFACES", 1)
        make(session, "Internet")

        with pytest.raises(service.InterfaceError, match="You can have 1 interfaces") as e:
            make(session, "Home", role="home")

        assert e.value.conflict

    def test_a_feed_that_does_not_exist_is_refused(self, session: Session) -> None:
        with pytest.raises(service.InterfaceError, match="no such feed") as e:
            make(session, feeds=[999_999])

        assert e.value.missing


class TestChangingOne:
    def test_what_is_given_changes_and_the_rest_stays(self, session: Session) -> None:
        made = make(session, notes="the way out")

        changed, which = service.change(
            session, made.id, name="WAN", role=None, notes=None, networks=None, position=None
        )

        assert (changed.name, changed.role, changed.notes) == ("WAN", "internet", "the way out")
        assert which == ["name"]

    def test_every_field_can_change(self, session: Session) -> None:
        made = make(session)

        changed, which = service.change(
            session,
            made.id,
            name="Cameras",
            role="iot",
            notes="the doorbell",
            networks=["192.168.30.0/24"],
            position=5,
        )

        assert (changed.name, changed.role, changed.notes) == ("Cameras", "iot", "the doorbell")
        assert (changed.networks, changed.position) == (["192.168.30.0/24"], 5)
        assert which == ["name", "role", "notes", "networks", "position"]

    def test_what_is_the_same_is_not_a_change(self, session: Session) -> None:
        made = make(session, networks=["10.0.0.0/8"])

        _, which = service.change(
            session,
            made.id,
            name="Internet",
            role="internet",
            notes="",
            networks=["10.1.1.1/8"],
            position=0,
        )

        assert which == []

    def test_a_name_that_another_has_is_refused(self, session: Session) -> None:
        make(session, "Internet")
        home = make(session, "Home", role="home")

        with pytest.raises(service.InterfaceError, match="already an interface") as e:
            service.change(
                session,
                home.id,
                name="INTERNET",
                role=None,
                notes=None,
                networks=None,
                position=None,
            )

        assert e.value.conflict

    def test_it_may_be_renamed_to_its_own_name_in_other_capitals(self, session: Session) -> None:
        made = make(session, "Internet")

        changed, which = service.change(
            session, made.id, name="INTERNET", role=None, notes=None, networks=None, position=None
        )

        assert (changed.name, which) == ("INTERNET", ["name"])

    def test_a_role_that_does_not_exist_is_refused(self, session: Session) -> None:
        made = make(session)

        with pytest.raises(service.InterfaceError, match="The role is one of"):
            service.change(
                session,
                made.id,
                name=None,
                role="spaceship",
                notes=None,
                networks=None,
                position=None,
            )

    def test_one_that_is_not_there_is_missing(self, session: Session) -> None:
        with pytest.raises(service.InterfaceError, match="no such interface") as e:
            service.change(
                session, 999_999, name="x", role=None, notes=None, networks=None, position=None
            )

        assert e.value.missing


class TestRemovingOne:
    def test_its_feeds_go_back_to_not_being_placed(self, session: Session) -> None:
        placed = feed(session)
        made = make(session, feeds=[placed.id])

        removed = service.remove(session, made.id)
        session.refresh(placed)

        assert removed.name == "Internet"
        assert (placed.interface_id, placed.ignored) == (None, False)
        assert session.scalars(select(Interface)).all() == []

    def test_one_that_is_not_there_is_missing(self, session: Session) -> None:
        with pytest.raises(service.InterfaceError, match="no such interface"):
            service.remove(session, 999_999)


class TestPlacingAFeed:
    def test_it_goes_on_an_interface_and_comes_off_again(self, session: Session) -> None:
        port = feed(session)
        made = make(session)

        service.place(session, port.id, made.id)
        assert port.interface_id == made.id

        service.place(session, port.id, None)
        assert (port.interface_id, port.ignored) == (None, False)

    def test_it_can_be_set_aside_and_moved_to_an_interface_from_there(
        self, session: Session
    ) -> None:
        port = feed(session)
        made = make(session)

        service.place(session, port.id, None, ignored=True)
        assert (port.interface_id, port.ignored) == (None, True)

        service.place(session, port.id, made.id)
        assert (port.interface_id, port.ignored) == (made.id, False)

    def test_it_is_placed_or_set_aside_not_both(self, session: Session) -> None:
        port = feed(session)
        made = make(session)

        with pytest.raises(service.InterfaceError, match="not both"):
            service.place(session, port.id, made.id, ignored=True)

    def test_the_database_refuses_both_too(self, session: Session) -> None:
        made = make(session)

        with pytest.raises(IntegrityError):
            feed(session, interface_id=made.id, ignored=True)

    def test_a_feed_that_is_not_there_is_missing(self, session: Session) -> None:
        with pytest.raises(service.InterfaceError, match="no such feed") as e:
            service.place(session, 999_999, None)

        assert e.value.missing

    def test_an_interface_that_is_not_there_is_missing(self, session: Session) -> None:
        port = feed(session)

        with pytest.raises(service.InterfaceError, match="no such interface") as e:
            service.place(session, port.id, 999_999)

        assert e.value.missing


class TestTheListing:
    def test_it_sorts_feeds_onto_interfaces_and_into_those_not_placed_and_set_aside(
        self, session: Session
    ) -> None:
        wan = feed(session, "igc0")
        lan = feed(session, "igc1")
        loose = feed(session, "igc2")
        aside = feed(session, "lo0")
        internet = make(session, "Internet", feeds=[wan.id])
        home = make(session, "Home", role="home", feeds=[lan.id])
        service.place(session, aside.id, None, ignored=True)

        listing = service.listing(session)

        assert [
            (item.name, [port.native_name for port in ports]) for item, ports in listing.interfaces
        ] == [
            ("Internet", ["igc0"]),
            ("Home", ["igc1"]),
        ]
        assert [port.native_name for port in listing.unplaced] == [loose.native_name]
        assert [port.native_name for port in listing.ignored] == ["lo0"]
        assert (internet.position, home.position) == (0, 1)

    def test_an_interface_without_feeds_is_listed_with_none(self, session: Session) -> None:
        make(session, "Guests", role="guest")

        [(item, ports)] = service.listing(session).interfaces

        assert (item.name, ports) == ("Guests", [])

    def test_the_feeds_are_in_the_order_of_program_connection_and_name(
        self, session: Session
    ) -> None:
        session.add_all(
            [
                InterfaceFeed(integration="ntopng", connection="api", native_name="b"),
                InterfaceFeed(integration="opnsense", connection="api", native_name="b"),
                InterfaceFeed(integration="opnsense", connection="api", native_name="a"),
                InterfaceFeed(integration="crowdsec", connection="lapi", native_name=""),
            ]
        )
        session.flush()

        order = [(port.integration, port.native_name) for port in service.listing(session).unplaced]

        assert order == [("crowdsec", ""), ("ntopng", "b"), ("opnsense", "a"), ("opnsense", "b")]

    def test_the_feeds_of_one_interface(self, session: Session) -> None:
        second, first = feed(session, "igc1"), feed(session, "igc0")
        made = make(session, feeds=[second.id, first.id])
        feed(session, "igc9")

        assert [port.native_name for port in service.feeds_of(session, made.id)] == ["igc0", "igc1"]
