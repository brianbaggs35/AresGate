"""Storing what ntopng knows of the hosts it watches."""

from datetime import timedelta
from ipaddress import ip_address

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.hostinfo import traits
from app.hostinfo.traits import NewTrait
from app.models import HostTrait
from tests.test_ai_service import NOW

WEB = ip_address("192.168.1.20")
LAPTOP = ip_address("192.168.1.41")


def put(session: Session, found: list[NewTrait], when: object = NOW) -> int:
    count = traits.record(session, found, when, source="ntopng", connection="api")  # type: ignore[arg-type]
    session.commit()
    return count


def kept(session: Session) -> dict[str, HostTrait]:
    session.expire_all()
    return {str(row.address): row for row in session.scalars(select(HostTrait))}


def test_a_host_is_kept_with_what_ntopng_says_of_it(session: Session) -> None:
    count = put(
        session,
        [
            NewTrait(
                WEB,
                hostname="web1",
                os_name="Linux",
                asn=64512,
                as_name="Example ISP",
                country="CA",
                fingerprints={"tcp": "2:128"},
            )
        ],
    )

    row = kept(session)["192.168.1.20"]

    assert count == 1
    assert (row.hostname, row.os_name, row.asn, row.as_name, row.country) == (
        "web1",
        "Linux",
        64512,
        "Example ISP",
        "CA",
    )
    assert row.fingerprints == {"tcp": "2:128"}
    assert row.read_at == NOW


def test_what_it_says_later_takes_the_place_of_what_it_said(session: Session) -> None:
    put(session, [NewTrait(WEB, hostname="web1", os_name="Linux")])

    put(session, [NewTrait(WEB, hostname="web2")], NOW + timedelta(minutes=30))

    row = kept(session)["192.168.1.20"]
    assert (row.hostname, row.os_name, row.read_at) == ("web2", None, NOW + timedelta(minutes=30))


def test_a_host_it_no_longer_lists_is_forgotten(session: Session) -> None:
    put(session, [NewTrait(WEB), NewTrait(LAPTOP)])

    put(session, [NewTrait(LAPTOP)])

    assert list(kept(session)) == ["192.168.1.41"]


def test_a_read_that_lists_nothing_forgets_every_host(session: Session) -> None:
    put(session, [NewTrait(WEB)])

    assert put(session, []) == 0
    assert kept(session) == {}


def test_a_host_listed_twice_keeps_the_description_that_says_more(session: Session) -> None:
    put(
        session,
        [
            NewTrait(WEB, hostname="web1"),
            NewTrait(WEB, hostname="web1", os_name="Linux", fingerprints={"tcp": "x"}),
            NewTrait(WEB, hostname="other"),
        ],
    )

    row = kept(session)["192.168.1.20"]

    assert (row.hostname, row.os_name) == ("web1", "Linux")


def test_a_host_described_with_all_it_can_be_is_still_one_host(session: Session) -> None:
    full = NewTrait(WEB, hostname="a", os_name="b", asn=1, as_name="c", country="d")

    assert put(session, [full, NewTrait(WEB, hostname="a", os_name="b", asn=1)]) == 1
