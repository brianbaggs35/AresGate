import pytest
from sqlalchemy.orm import Session

from app.interfaces import service, suggest
from app.interfaces.suggest import Suggestion
from app.models import Interface, InterfaceFeed


def feed(
    session: Session, name: str, integration: str = "opnsense", **changes: object
) -> InterfaceFeed:
    made = InterfaceFeed(
        integration=integration,
        connection="lapi" if integration == "crowdsec" else "api",
        native_name=name,
        **changes,
    )
    session.add(made)
    session.flush()
    return made


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("Guest_WiFi2", {"guest", "wifi"}),
        ("ovpns1", {"ovpns"}),
        ("igc0.20", {"igc"}),
        ("WAN", {"wan"}),
        ("", set[str]()),
        ("12", set[str]()),
    ],
)
def test_the_words_of_a_name(text: str, words: set[str]) -> None:
    assert suggest.words_of(text) == words


class TestHints:
    @pytest.mark.parametrize(
        ("name", "role", "hinted"),
        [
            ("wan", "internet", "Internet"),
            ("WAN2", "internet", "Internet"),
            ("pppoe0", "internet", "Internet"),
            ("lan", "home", "Home"),
            ("guest", "guest", "Guests"),
            ("iot_net", "iot", "IoT"),
            ("cctv", "iot", "IoT"),
            ("dmz", "dmz", "DMZ"),
            ("wg0", "vpn", "VPN"),
            ("ovpns1", "vpn", "VPN"),
            ("mgmt", "management", "Management"),
            # The first that fits wins: a guest VPN is for guests.
            ("guest_vpn", "guest", "Guests"),
        ],
    )
    def test_a_name_that_says_what_it_is_for(self, name: str, role: str, hinted: str) -> None:
        found = suggest.hint_for(name)

        assert found is not None
        assert (found.role, found.name) == (role, hinted)

    def test_a_name_that_says_nothing_has_none(self) -> None:
        assert suggest.hint_for("igc0", "") is None

    def test_any_of_the_texts_may_say_it(self) -> None:
        found = suggest.hint_for("igc1", "Guest wifi")

        assert found is not None
        assert found.role == "guest"

    def test_every_hint_is_a_role_there_is(self) -> None:
        from app.models import INTERFACE_ROLES

        assert {hint.role for hint in suggest.HINTS} <= set(INTERFACE_ROLES)


class TestSuggestions:
    def test_a_name_that_says_what_it_is_for_is_suggested_with_its_role(
        self, session: Session
    ) -> None:
        wan = feed(session, "wan")

        assert suggest.suggestions(session) == [
            Suggestion(
                name="Internet",
                role="internet",
                feed_ids=(wan.id,),
                reason="“wan” says what it is for: wan in OPNsense.",
                interface_id=None,
            )
        ]

    def test_ports_of_different_programs_that_say_the_same_thing_go_together(
        self, session: Session
    ) -> None:
        one = feed(session, "wan")
        other = feed(session, "WAN", integration="ntopng")
        third = feed(session, "wan2")

        [found] = suggest.suggestions(session)

        assert (found.name, found.role) == ("Internet", "internet")
        assert found.feed_ids == (one.id, other.id, third.id)
        assert found.reason.endswith(": WAN in ntopng, wan in OPNsense and wan2 in OPNsense.")

    def test_a_name_in_several_programs_is_one_port_even_when_it_says_nothing(
        self, session: Session
    ) -> None:
        one = feed(session, "igc3")
        other = feed(session, "igc3", integration="ntopng")

        assert suggest.suggestions(session) == [
            Suggestion(
                name="igc3",
                role="other",
                feed_ids=(one.id, other.id),
                reason="Several programs name it: igc3 in ntopng and igc3 in OPNsense.",
                interface_id=None,
            )
        ]

    def test_a_name_in_one_program_that_says_nothing_is_left_alone(self, session: Session) -> None:
        feed(session, "igc3")

        assert suggest.suggestions(session) == []

    def test_the_only_interface_with_the_role_a_name_says_is_joined(self, session: Session) -> None:
        fibre = service.create(
            session, name="Fibre", role="internet", notes="", networks=[], feeds=[]
        )
        port = feed(session, "wan2")

        [found] = suggest.suggestions(session)

        assert found.feed_ids == (port.id,)
        assert (found.interface_id, found.name, found.role) == (fibre.id, "Fibre", "internet")

    def test_with_two_interfaces_of_the_role_it_is_not_guessed_which(
        self, session: Session
    ) -> None:
        for name in ("Fibre", "Backup"):
            service.create(session, name=name, role="internet", notes="", networks=[], feeds=[])
        feed(session, "wan2")

        [found] = suggest.suggestions(session)

        assert (found.interface_id, found.name) == (None, "Internet")

    def test_a_hint_that_an_interface_already_has_the_name_of_joins_it(
        self, session: Session
    ) -> None:
        internet = service.create(
            session, name="internet", role="internet", notes="", networks=[], feeds=[]
        )
        port = feed(session, "wan")

        [found] = suggest.suggestions(session)

        assert found.feed_ids == (port.id,)
        assert (found.interface_id, found.name, found.role) == (internet.id, "internet", "internet")

    def test_the_exact_name_of_an_interface_joins_it_when_nothing_else_says_what_it_is(
        self, session: Session
    ) -> None:
        netz = Interface(name="Lab", role="other", notes="", networks=[], position=0)
        session.add(netz)
        session.flush()
        port = feed(session, "lab")

        [found] = suggest.suggestions(session)

        assert found.feed_ids == (port.id,)
        assert (found.interface_id, found.name, found.role) == (netz.id, "Lab", "other")
        assert found.reason == "It has the name of an interface: lab in OPNsense."

    def test_feeds_already_placed_or_set_aside_are_not_suggested(self, session: Session) -> None:
        placed = feed(session, "wan")
        feed(session, "guest", ignored=True)
        service.create(
            session, name="Internet", role="internet", notes="", networks=[], feeds=[placed.id]
        )

        assert suggest.suggestions(session) == []

    def test_a_whole_connection_has_no_name_to_go_by(self, session: Session) -> None:
        feed(session, "", integration="crowdsec")

        assert suggest.suggestions(session) == []

    def test_they_are_listed_by_name(self, session: Session) -> None:
        guest = feed(session, "guest")
        wan = feed(session, "wan")

        assert [found.name for found in suggest.suggestions(session)] == ["Guests", "Internet"]
        assert guest.id != wan.id
