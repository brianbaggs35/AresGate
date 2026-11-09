"""What may be searched for by hand: an internet address, a domain or a web address, and the
refusals for everything else, so that nothing on the home's own network is sent to a service."""

from ipaddress import ip_address

import pytest

from app.intel import subjects
from app.intel.subjects import Refusal

ADDRESS = ip_address("93.184.216.34")


def refusal_of(text: str) -> str:
    with pytest.raises(Refusal) as refused:
        subjects.parse(text)
    return str(refused.value)


def test_an_internet_address_is_searched_as_an_address() -> None:
    found = subjects.parse(" 93.184.216.34 ")

    assert found == subjects.Subject(
        kind="ip", text="93.184.216.34", host="93.184.216.34", address=ADDRESS
    )
    assert found.recorded() == (ADDRESS, None)


def test_an_address_is_written_the_way_it_is_normalised() -> None:
    found = subjects.parse("2606:2800:220:1:248:1893:25C8:1946")

    assert found.kind == "ip"
    assert found.text == "2606:2800:220:1:248:1893:25c8:1946"


def test_a_domain_is_searched_in_lower_case_without_its_last_dot() -> None:
    found = subjects.parse(" Example.COM. ")

    assert found == subjects.Subject(
        kind="domain", text="example.com", host="example.com", address=None
    )
    assert found.recorded() == (None, "example.com")


def test_a_domain_with_letters_outside_ascii_is_searched_as_it_is_written_in_ascii() -> None:
    assert subjects.parse("bücher.de").host == "xn--bcher-kva.de"


def test_a_web_address_is_searched_without_its_fragment_and_keeps_only_its_host_on_record() -> None:
    found = subjects.parse("https://Example.com/Path?q=1#section")

    assert found.kind == "url"
    assert found.text == "https://Example.com/Path?q=1"
    assert found.host == "example.com"
    assert found.recorded() == (None, "example.com")


def test_a_web_address_of_an_internet_address_keeps_that_address() -> None:
    found = subjects.parse("http://93.184.216.34:8080/login")

    assert (found.kind, found.host, found.address) == ("url", "93.184.216.34", ADDRESS)
    assert found.recorded() == (None, "93.184.216.34")


def test_an_address_found_by_an_incident_is_searched_as_an_address() -> None:
    found = subjects.of_address(ADDRESS)

    assert found == subjects.parse("93.184.216.34")
    assert found.recorded() == (ADDRESS, None)


@pytest.mark.parametrize("text", ["", "   "])
def test_nothing_to_search_for_is_refused(text: str) -> None:
    assert refusal_of(text) == subjects.EMPTY


def test_a_search_longer_than_a_web_address_can_be_is_refused() -> None:
    assert refusal_of("a" * (subjects.MAX_LENGTH + 1)) == (
        f"Enter at most {subjects.MAX_LENGTH} characters."
    )


@pytest.mark.parametrize(
    "text",
    [
        "two words.com",
        "tab\there.com",
        "bell\x07.com",
        "example.com/path",
        "example.com:443",
        "ftp://example.com",
        "a..b.com",
        "-bad.com",
        "bad-.com",
        "exa_mple.com",
        "1.2.3",
        "...",
        "a" * 64 + ".com",
        ("a" * 60 + ".") * 5 + "com",
        "http://example.com:99999",
        "http://[::1",
        "https://",
    ],
)
def test_anything_else_is_refused_as_malformed(text: str) -> None:
    assert refusal_of(text) == subjects.MALFORMED


@pytest.mark.parametrize(
    "text",
    ["http://user:secret@example.com", "https://user@example.com/login"],
)
def test_a_web_address_with_a_username_or_password_is_refused_so_it_is_not_sent(text: str) -> None:
    assert refusal_of(text) == subjects.CREDENTIALS


@pytest.mark.parametrize(
    "text",
    [
        "10.0.0.1",
        "192.168.1.20",
        "172.16.4.4",
        "127.0.0.1",
        "169.254.1.1",
        "224.0.0.1",
        "::1",
        "fe80::1",
        "2001:db8::1",
        "https://192.168.1.1/admin",
    ],
)
def test_a_private_address_is_refused(text: str) -> None:
    assert refusal_of(text) == (
        f"{text.removeprefix('https://').split('/')[0]} isn't a public internet address, "
        "so it isn't sent to VirusTotal."
    )


@pytest.mark.parametrize(
    "text",
    [
        "router",
        "nas.local",
        "printer.lan",
        "host.internal",
        "wiki.intranet",
        "x.test",
        "app.example",
        "localhost",
        "https://server.home.arpa",
        "box.corp",
    ],
)
def test_a_name_on_a_network_of_its_own_is_refused_so_it_is_not_sent(text: str) -> None:
    host = text.removeprefix("https://").split("/")[0]
    assert refusal_of(text) == (
        f"{host} is a name on your own network, so it isn't sent to VirusTotal."
    )
