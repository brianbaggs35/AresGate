"""What VirusTotal's answer says of an internet address, a domain or a web address, and the lookup
that asks for it."""

import asyncio
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from hashlib import sha256
from ipaddress import ip_address

import pytest

from app.integrations import netguard
from app.integrations.client import ApiClient, Call, Target
from app.integrations.netguard import HOME_NETWORK, HOME_NETWORK_AND_LOOPBACK
from app.intel import subjects, virustotal
from app.intel.virustotal import Failed, Report, Reported, Unknown
from tests.stubs import Answer, Seen, Serve, StubServer

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
ADDRESS = ip_address("93.184.216.34")
SUBJECT = subjects.of_address(ADDRESS)
ANALYSED = 1_762_689_600
AS_JSON = {"Content-Type": "application/json"}
DETAILS = (("Owner", "Example Hosting"), ("Country", "NL"), ("Network", "AS64500"))
EXPECTED = Report(
    malicious=3,
    suspicious=1,
    harmless=60,
    undetected=20,
    reputation=-12,
    analysed_at=datetime.fromtimestamp(ANALYSED, UTC),
    country="NL",
    owner="Example Hosting",
    asn=64500,
    details=DETAILS,
)


def attributes(**changes: object) -> dict[str, object]:
    """An address's attributes as VirusTotal's answer gives them, with some of them changed."""
    found: dict[str, object] = {
        "last_analysis_stats": {
            "malicious": 3,
            "suspicious": 1,
            "harmless": 60,
            "undetected": 20,
            "timeout": 0,
        },
        "reputation": -12,
        "country": "NL",
        "as_owner": "Example Hosting",
        "asn": 64500,
        "last_analysis_date": ANALYSED,
    }
    found.update(changes)
    return found


def answer_of(found: Mapping[str, object] | None) -> dict[str, object]:
    return {"data": {"id": str(ADDRESS), "type": "ip_address", "attributes": found}}


def report_with(
    *, malicious: int = 0, suspicious: int = 0, harmless: int = 0, undetected: int = 0
) -> Report:
    return Report(
        malicious=malicious,
        suspicious=suspicious,
        harmless=harmless,
        undetected=undetected,
        reputation=0,
        analysed_at=NOW,
    )


def test_a_report_is_read_from_the_counts_and_attributes_it_gives() -> None:
    found = virustotal.parse(answer_of(attributes()), NOW)

    assert found == EXPECTED
    assert found is not None
    assert found.engines == 84


def test_what_an_answer_leaves_out_is_left_out_of_the_report() -> None:
    found = virustotal.parse(
        answer_of(
            attributes(
                reputation=None,
                country=None,
                as_owner=None,
                asn=None,
                last_analysis_date=None,
            )
        ),
        NOW,
    )

    assert found is not None
    assert (found.reputation, found.country, found.owner, found.asn) == (0, None, None, None)
    assert found.analysed_at == NOW
    assert found.details == ()


def test_a_value_that_is_not_what_it_should_be_is_left_out_rather_than_guessed() -> None:
    found = virustotal.parse(
        answer_of(attributes(asn=-1, country=12, reputation="low", last_analysis_date="today")),
        NOW,
    )

    assert found is not None
    assert (found.asn, found.country, found.reputation, found.analysed_at) == (None, None, 0, NOW)


def test_control_characters_are_taken_out_of_the_owner_name() -> None:
    found = virustotal.parse(answer_of(attributes(as_owner="Example\x07 Hosting\n")), NOW)

    assert found is not None
    assert found.owner is not None
    assert "\x07" not in found.owner
    assert found.owner.startswith("Example")


def test_a_domain_is_read_with_its_registrar_and_only_the_details_of_a_domain() -> None:
    found = virustotal.parse(
        answer_of(attributes(registrar="Example Registrar")), NOW, kind="domain"
    )

    assert found is not None
    assert found.details == (("Registrar", "Example Registrar"),)


def test_a_web_address_is_read_with_its_title_final_address_and_submissions() -> None:
    found = virustotal.parse(
        answer_of(
            attributes(
                title="Sign in",
                last_final_url="https://example.com/login",
                times_submitted=7,
            )
        ),
        NOW,
        kind="url",
    )

    assert found is not None
    assert found.details == (
        ("Title", "Sign in"),
        ("Final address", "https://example.com/login"),
        ("Times submitted", "7"),
    )


def test_details_that_are_not_given_are_left_out_of_a_web_address() -> None:
    found = virustotal.parse(
        answer_of(attributes(title=None, last_final_url=None, times_submitted="many")),
        NOW,
        kind="url",
    )

    assert found is not None
    assert found.details == ()


def test_categories_are_kept_once_each_in_order_and_no_more_than_twelve() -> None:
    many = {f"engine {number}": f"category {number:02d}" for number in range(20)}
    found = virustotal.parse(answer_of(attributes(categories=many)), NOW)

    assert found is not None
    assert len(found.categories) == virustotal.MAX_CATEGORIES
    assert list(found.categories) == sorted(set(found.categories))


@pytest.mark.parametrize(
    "value",
    [None, ["malware"], {"engine": 3}, {"engine": ""}],
)
def test_categories_that_are_not_text_by_engine_are_left_out(value: object) -> None:
    found = virustotal.parse(answer_of(attributes(categories=value)), NOW)

    assert found is not None
    assert found.categories == ()


def test_each_judgement_is_made_from_the_counts_of_the_engines() -> None:
    assert virustotal.judge(None) == "unknown"
    assert virustotal.judge(report_with(malicious=1, harmless=9)) == "malicious"
    assert virustotal.judge(report_with(suspicious=1, harmless=9)) == "suspicious"
    assert virustotal.judge(report_with(harmless=3, undetected=2)) == "clean"


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {"data": None},
        {"data": {}},
        {"data": {"attributes": None}},
        answer_of(None),
        answer_of({"last_analysis_stats": None}),
        answer_of({"last_analysis_stats": "three"}),
        answer_of({"last_analysis_stats": {"malicious": 1}}),
        answer_of(
            attributes(
                last_analysis_stats={
                    "malicious": -1,
                    "suspicious": 0,
                    "harmless": 0,
                    "undetected": 0,
                }
            )
        ),
        answer_of(
            attributes(
                last_analysis_stats={
                    "malicious": True,
                    "suspicious": 0,
                    "harmless": 0,
                    "undetected": 0,
                }
            )
        ),
        answer_of(
            attributes(
                last_analysis_stats={
                    "malicious": 1.5,
                    "suspicious": 0,
                    "harmless": 0,
                    "undetected": 0,
                }
            )
        ),
    ],
)
def test_an_answer_without_the_counts_of_a_report_is_not_a_report(body: object) -> None:
    assert virustotal.parse(body, NOW) is None


def test_each_kind_of_subject_links_to_its_own_page_on_virustotal() -> None:
    digest = sha256(b"https://example.com/login?next=/home").hexdigest()

    assert virustotal.link_for(SUBJECT) == "https://www.virustotal.com/gui/ip-address/93.184.216.34"
    assert (
        virustotal.link_for(subjects.parse("example.com"))
        == "https://www.virustotal.com/gui/domain/example.com"
    )
    assert (
        virustotal.link_for(subjects.parse("https://example.com/login?next=/home"))
        == f"https://www.virustotal.com/gui/url/{digest}"
    )


def target_for(server: StubServer) -> Target:
    return Target(
        integration="virustotal",
        connection="api",
        origin=netguard.parse_origin(server.url, allow_http=True),
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options={"tier": "free"},
        secrets={"api_key": "vt-key"},
    )


async def record(_call: Call) -> None:
    pass  # Keeps nothing: the test needs only that the call was made.


def ask(
    serve: Serve,
    handler: Callable[[Seen], Answer],
    subject: subjects.Subject = SUBJECT,
) -> tuple[virustotal.Answer, StubServer]:
    server = serve(handler)
    where = target_for(server)

    async def go() -> virustotal.Answer:
        async with ApiClient(where, record, HOME_NETWORK_AND_LOOPBACK) as client:
            return await virustotal.look_up(client, where, subject, NOW)

    return asyncio.run(go()), server


def test_the_report_on_an_address_is_asked_for_with_the_key_in_its_header(serve: Serve) -> None:
    answer, server = ask(
        serve, lambda seen: Answer(body=json.dumps(answer_of(attributes())), headers=AS_JSON)
    )

    assert answer == Reported(report=EXPECTED)
    [seen] = server.seen
    assert seen.target == "/api/v3/ip_addresses/93.184.216.34"
    assert seen.headers["x-apikey"] == "vt-key"


@pytest.mark.parametrize(
    ("text", "path"),
    [
        ("example.com", "/api/v3/domains/example.com"),
        (
            "https://example.com/login",
            "/api/v3/urls/" + sha256(b"https://example.com/login").hexdigest(),
        ),
    ],
)
def test_a_domain_and_a_web_address_are_asked_for_at_their_own_paths(
    serve: Serve, text: str, path: str
) -> None:
    answer, server = ask(
        serve,
        lambda seen: Answer(body=json.dumps(answer_of(attributes())), headers=AS_JSON),
        subjects.parse(text),
    )

    assert isinstance(answer, Reported)
    [seen] = server.seen
    assert seen.target == path


def test_an_address_with_no_report_is_unknown(serve: Serve) -> None:
    answer, _ = ask(serve, lambda seen: Answer(status=404))

    assert answer == Unknown()


@pytest.mark.parametrize("status", [401, 403, 429])
def test_an_answer_that_is_not_ok_is_a_failure(serve: Serve, status: int) -> None:
    answer, _ = ask(serve, lambda seen: Answer(status=status))

    assert answer == Failed(f"VirusTotal answered HTTP {status}.")


def test_an_answer_without_the_counts_of_a_report_is_a_failure(serve: Serve) -> None:
    answer, _ = ask(serve, lambda seen: Answer(body="{}", headers=AS_JSON))

    assert answer == Failed("VirusTotal's answer didn't hold the counts of a report.")


def test_a_request_the_policy_refuses_is_a_failure_and_is_never_sent(serve: Serve) -> None:
    server = serve(lambda seen: Answer(body="{}"))

    answer = asyncio.run(virustotal.ask(target_for(server), record, HOME_NETWORK, SUBJECT, NOW))

    assert isinstance(answer, Failed)
    assert server.seen == []
