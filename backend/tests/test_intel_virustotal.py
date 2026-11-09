"""What VirusTotal's answer says of an internet address, and the lookup that asks for it."""

import asyncio
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from ipaddress import ip_address

import pytest

from app.integrations import netguard
from app.integrations.client import ApiClient, Call, Target
from app.integrations.netguard import HOME_NETWORK_AND_LOOPBACK
from app.intel import virustotal
from app.intel.virustotal import Failed, Report, Reported, Unknown
from tests.stubs import Answer, Seen, Serve, StubServer

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
ADDRESS = ip_address("93.184.216.34")
ANALYSED = 1_762_689_600
AS_JSON = {"Content-Type": "application/json"}
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


def ask(serve: Serve, handler: Callable[[Seen], Answer]) -> tuple[virustotal.Answer, StubServer]:
    server = serve(handler)
    where = target_for(server)

    async def record(_call: Call) -> None:
        pass  # Keeps nothing: the test needs only that the call was made.

    async def go() -> virustotal.Answer:
        async with ApiClient(where, record, HOME_NETWORK_AND_LOOPBACK) as client:
            return await virustotal.look_up(client, where, ADDRESS, NOW)

    return asyncio.run(go()), server


def test_the_report_on_an_address_is_asked_for_with_the_key_in_its_header(serve: Serve) -> None:
    answer, server = ask(
        serve, lambda seen: Answer(body=json.dumps(answer_of(attributes())), headers=AS_JSON)
    )

    assert answer == Reported(report=EXPECTED)
    [seen] = server.seen
    assert seen.target == "/api/v3/ip_addresses/93.184.216.34"
    assert seen.headers["x-apikey"] == "vt-key"


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
