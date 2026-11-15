from app.agents import grounding
from app.agents.grounding import Claim


def test_it_finds_the_addresses_and_the_cves_in_a_text() -> None:
    text = "From 203.0.113.5 to 192.168.1.20:22, see cve-2024-3094 and CVE-2021-44228."

    assert grounding.names_in(text) == {
        "203.0.113.5",
        "192.168.1.20",
        "CVE-2024-3094",
        "CVE-2021-44228",
    }


def test_a_number_that_is_not_an_address_is_not_one() -> None:
    assert grounding.names_in("Version 1.2.3.4.5, 999.1.1.1, 10.0.0 and 4,000 packets") == set()


def test_a_claim_is_in_the_answer_only_for_what_is_not_in_what_was_seen() -> None:
    claims = [
        Claim("All seen", "From 203.0.113.5."),
        Claim("Nothing to check", "A scan got further than usual."),
        Claim("Some not seen", "From 203.0.113.5, 198.51.100.7 and CVE-2099-1234."),
    ]

    assert grounding.unseen(claims, ["Scan from 203.0.113.5", "and nothing else"]) == {
        "Some not seen": ["198.51.100.7", "CVE-2099-1234"]
    }
