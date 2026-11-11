"""Names: what an address on the internet is called, asked once and kept."""

import socket
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.incidents import names
from app.models import AddressName

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
SCANNER = "93.184.216.34"
OTHER = "8.8.8.8"
HOME = "192.168.1.20"


class Resolver:
    """A resolver that answers from a table and remembers what it was asked."""

    def __init__(self, known: dict[str, str | None]) -> None:
        self.known = known
        self.asked: list[str] = []

    def __call__(self, address: str) -> str | None:
        self.asked.append(address)
        return self.known.get(address)


@pytest.fixture
def resolver(monkeypatch: pytest.MonkeyPatch) -> Resolver:
    found = Resolver({SCANNER: "scanner-17.example.net", OTHER: None})
    monkeypatch.setattr(names, "resolver", found)
    return found


@pytest.fixture(autouse=True)
def reverse_dns_is_on(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    monkeypatch.setattr(names, "get_settings", lambda: settings)


class TestLookingUp:
    def test_an_address_is_given_its_name_and_the_answer_is_kept(
        self, session: Session, resolver: Resolver
    ) -> None:
        assert names.lookup(session, [SCANNER], NOW) == {SCANNER: "scanner-17.example.net"}
        session.commit()

        assert names.lookup(session, [SCANNER], NOW + timedelta(days=1)) == {
            SCANNER: "scanner-17.example.net"
        }
        assert resolver.asked == [SCANNER]
        assert session.get_one(AddressName, SCANNER).looked_up_at == NOW

    def test_an_answer_is_asked_again_after_a_week(
        self, session: Session, resolver: Resolver
    ) -> None:
        names.lookup(session, [SCANNER], NOW)
        session.commit()

        names.lookup(session, [SCANNER], NOW + names.KEEP + timedelta(minutes=1))

        assert resolver.asked == [SCANNER, SCANNER]

    def test_an_address_with_no_name_is_asked_again_after_a_day_not_before(
        self, session: Session, resolver: Resolver
    ) -> None:
        assert names.lookup(session, [OTHER], NOW) == {}
        session.commit()

        names.lookup(session, [OTHER], NOW + timedelta(hours=23))
        assert resolver.asked == [OTHER]

        names.lookup(session, [OTHER], NOW + names.KEEP_NONE + timedelta(minutes=1))
        assert resolver.asked == [OTHER, OTHER]

    def test_an_address_on_the_home_network_is_never_asked_about(
        self, session: Session, resolver: Resolver
    ) -> None:
        assert names.lookup(session, [HOME, "not an address"], NOW) == {}
        assert resolver.asked == []

    def test_nothing_is_asked_when_it_is_turned_off(
        self,
        session: Session,
        resolver: Resolver,
        monkeypatch: pytest.MonkeyPatch,
        settings: Settings,
    ) -> None:
        off = settings.model_copy(update={"reverse_dns": False})
        monkeypatch.setattr(names, "get_settings", lambda: off)

        assert names.lookup(session, [SCANNER], NOW) == {}
        assert resolver.asked == []

    def test_one_page_asks_about_few_addresses(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        found = Resolver({})
        monkeypatch.setattr(names, "resolver", found)
        many = [f"93.184.216.{n}" for n in range(1, 20)]

        names.lookup(session, many, NOW)

        assert len(found.asked) == names.MAX_LOOKUPS

    def test_a_resolver_that_fails_is_not_remembered_as_having_no_name(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def down(address: str) -> str | None:
            raise OSError("no resolver")

        monkeypatch.setattr(names, "resolver", down)

        assert names.lookup(session, [SCANNER], NOW) == {}
        session.commit()

        assert session.get(AddressName, SCANNER) is None

    def test_a_resolver_that_is_slow_does_not_hold_the_page_up(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def slow(address: str) -> str | None:
            time.sleep(0.5)
            return "late.example.net"

        monkeypatch.setattr(names, "resolver", slow)
        monkeypatch.setattr(names, "WAIT", 0.05)

        started = time.monotonic()
        assert names.lookup(session, [SCANNER], NOW) == {}

        assert time.monotonic() - started < 0.4
        assert session.get(AddressName, SCANNER) is None


def answering(name: str) -> Callable[[str], tuple[str, list[str], list[str]]]:
    def gethostbyaddr(address: str) -> tuple[str, list[str], list[str]]:
        return name, [], []

    return gethostbyaddr


class TestTheSystemResolver:
    def test_it_gives_the_name_in_lower_case_without_the_trailing_dot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(socket, "gethostbyaddr", answering("Scanner-17.Example.NET."))

        assert names.system_resolver(SCANNER) == "scanner-17.example.net"

    def test_it_gives_nothing_where_there_is_no_record(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def missing(address: str) -> tuple[str, list[str], list[str]]:
            raise socket.herror(1, "Unknown host")

        monkeypatch.setattr(socket, "gethostbyaddr", missing)

        assert names.system_resolver(SCANNER) is None

    def test_it_gives_nothing_for_a_name_that_cannot_be_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(address: str) -> tuple[str, list[str], list[str]]:
            raise UnicodeError("bad name")

        monkeypatch.setattr(socket, "gethostbyaddr", broken)

        assert names.system_resolver(SCANNER) is None

    def test_a_name_that_is_only_a_dot_is_no_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(socket, "gethostbyaddr", answering("."))

        assert names.system_resolver(SCANNER) is None
