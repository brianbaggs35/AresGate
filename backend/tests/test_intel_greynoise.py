"""What GreyNoise's answer says of an internet address, and the lookup that asks for it."""

import asyncio
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import pytest

from app.integrations import netguard
from app.integrations.client import ApiClient, Call, Target
from app.integrations.netguard import HOME_NETWORK, HOME_NETWORK_AND_LOOPBACK
from app.intel import greynoise, subjects
from app.intel.answers import Failed, Report, Reported, Throttled, Unknown
from tests.stubs import Answer, Seen, Serve, StubServer

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
ADDRESS = ip_address("93.184.216.34")
SUBJECT = subjects.of_address(ADDRESS)
AS_JSON = {"Content-Type": "application/json"}

# What the Community API answers for an address seen scanning, as its documentation shows it.
SCANNER: dict[str, object] = {
    "ip": "93.184.216.34",
    "noise": True,
    "riot": False,
    "classification": "malicious",
    "name": "unknown",
    "link": "https://viz.greynoise.io/ip/93.184.216.34",
    "last_seen": "2021-03-18",
    "message": "Success",
}
# And for one that belongs to a business service.
SERVICE: dict[str, object] = {
    "ip": "1.1.1.1",
    "noise": False,
    "riot": True,
    "classification": "benign",
    "name": "Cloudflare",
    "link": "https://viz.greynoise.io/riot/1.1.1.1",
    "last_seen": "2020-01-01",
    "message": "Success",
}
NOT_SEEN: dict[str, object] = {"ip": "93.184.216.34", "noise": False, "riot": False}


def subscribed(**changes: object) -> dict[str, object]:
    """What the IP Lookup API answers for a scanner, with some of it changed."""
    scanner: dict[str, object] = {
        "found": True,
        "classification": "malicious",
        "first_seen": "2024-01-02",
        "last_seen": "2026-11-08",
        "last_seen_timestamp": "2026-11-08T12:30:00Z",
        "actor": "Group X",
        "cves": ["CVE-2024-0001", "CVE-2024-0002"],
        "tor": True,
        "vpn": True,
        "vpn_service": "EXAMPLE_VPN",
        "metadata": {
            "organization": "Example Hosting",
            "asn": "AS64500",
            "source_country_code": "NL",
            "rdns": "scan.example.net",
        },
        "tags": [{"name": "Mirai", "intention": "malicious"}, {"name": "SSH Bruteforcer"}],
    }
    scanner.update(changes)
    return {
        "ip": "93.184.216.34",
        "business_service_intelligence": {"found": False},
        "internet_scanner_intelligence": scanner,
        "request_metadata": {"restricted_fields": []},
    }


def parsed(body: object) -> Report:
    answer = greynoise.parse(body, NOW)
    assert isinstance(answer, Reported)
    return answer.report


def counts(report: Report) -> tuple[int, int, int]:
    return report.malicious, report.suspicious, report.harmless


def test_a_scanner_classified_malicious_is_one_source_that_says_malicious() -> None:
    found = parsed(SCANNER)

    assert counts(found) == (1, 0, 0)
    assert found.engines == 1
    # GreyNoise says "unknown" where it has no name for the owner.
    assert found.owner is None
    assert found.analysed_at == datetime(2021, 3, 18, tzinfo=UTC)
    assert found.details == (("Classification", "malicious"), ("Last seen", "2021-03-18"))


@pytest.mark.parametrize(
    ("classification", "expected"),
    [("benign", (0, 0, 1)), ("malicious", (1, 0, 0)), ("unknown", (0, 1, 0)), (None, (0, 1, 0))],
)
def test_a_scanner_counts_by_how_greynoise_classifies_it(
    classification: str | None, expected: tuple[int, int, int]
) -> None:
    body = {**SCANNER, "classification": classification}

    assert counts(parsed(body)) == expected


def test_an_address_in_a_business_service_dataset_is_harmless_and_named() -> None:
    found = parsed(SERVICE)

    assert counts(found) == (0, 0, 1)
    assert found.owner == "Cloudflare"
    assert found.details == (
        ("Classification", "benign"),
        ("Last seen", "2020-01-01"),
        ("Business service", "Cloudflare"),
    )


def test_a_business_service_that_also_scans_is_still_a_business_service() -> None:
    assert counts(parsed({**SERVICE, "noise": True, "classification": "malicious"})) == (0, 0, 1)


@pytest.mark.parametrize("body", [NOT_SEEN, {"noise": False, "riot": False, "message": "No"}])
def test_an_address_greynoise_has_not_seen_is_no_report(body: dict[str, object]) -> None:
    assert greynoise.parse(body, NOW) == Unknown()


def test_a_report_with_no_time_is_dated_when_it_was_asked_for() -> None:
    assert parsed({**SCANNER, "last_seen": "not a date"}).analysed_at == NOW
    assert parsed({**SCANNER, "last_seen": 20210318}).analysed_at == NOW


def test_a_subscriptions_answer_gives_the_tags_the_actor_and_the_network() -> None:
    found = parsed(subscribed())

    assert counts(found) == (1, 0, 0)
    assert (found.owner, found.asn, found.country) == ("Example Hosting", 64500, "NL")
    assert found.categories == ("Mirai", "SSH Bruteforcer")
    assert found.analysed_at == datetime(2026, 11, 8, 12, 30, tzinfo=UTC)
    assert found.details == (
        ("Classification", "malicious"),
        ("Last seen", "2026-11-08"),
        ("First seen", "2024-01-02"),
        ("Actor", "Group X"),
        ("Tags", "Mirai, SSH Bruteforcer"),
        ("CVEs", "CVE-2024-0001, CVE-2024-0002"),
        ("Tor exit node", "yes"),
        ("VPN", "EXAMPLE_VPN"),
        ("Reverse DNS", "scan.example.net"),
    )


def test_a_subscriptions_answer_without_a_vpn_name_or_a_stamp_says_what_it_has() -> None:
    body = subscribed(vpn_service=None, tor=False, last_seen_timestamp=None, actor="unknown")

    found = parsed(body)

    assert ("VPN", "yes") in found.details
    assert [label for label, _ in found.details if label in ("Tor exit node", "Actor")] == []
    # The date stands in for the timestamp.
    assert found.analysed_at == datetime(2026, 11, 8, tzinfo=UTC)


def test_a_business_service_in_a_subscriptions_answer_is_named_with_its_trust_level() -> None:
    body: dict[str, object] = {
        "ip": "8.8.8.8",
        "business_service_intelligence": {
            "found": True,
            "name": "Google Public DNS",
            "category": "public_dns",
            "trust_level": "1",
        },
        "internet_scanner_intelligence": {"found": False},
    }

    found = parsed(body)

    assert counts(found) == (0, 0, 1)
    assert found.details == (("Business service", "Google Public DNS (trust level 1)"),)
    assert found.analysed_at == NOW


@pytest.mark.parametrize(
    ("service", "said"),
    [
        ({"found": True, "category": "cdn"}, "cdn"),
        ({"found": True, "name": "Example", "trust_level": None}, "Example"),
        ({"found": True}, "yes"),
    ],
)
def test_a_business_service_is_named_by_what_greynoise_gives(
    service: dict[str, object], said: str
) -> None:
    body = {"business_service_intelligence": service, "internet_scanner_intelligence": {}}

    assert dict(parsed(body).details)["Business service"] == said


def test_a_plan_that_holds_fields_back_still_gives_a_report_of_what_it_has() -> None:
    body: dict[str, object] = {
        "ip": "93.184.216.34",
        "internet_scanner_intelligence": {"found": True},
        "request_metadata": {"restricted_fields": ["actor", "tags"]},
    }

    found = parsed(body)

    # Seen scanning, with no classification given: suspicious, as for one GreyNoise doesn't class.
    assert counts(found) == (0, 1, 0)
    assert found.details == ()


def test_a_subscriptions_answer_of_an_address_nothing_names_is_no_report() -> None:
    assert greynoise.parse(subscribed(found=False), NOW) == Unknown()
    assert greynoise.parse({"internet_scanner_intelligence": {"found": False}}, NOW) == Unknown()


@pytest.mark.parametrize(
    "asn", [None, 521, "", "521", "AS", "ASx", "AS99999999999", "as64500 trailing"]
)
def test_an_asn_that_is_not_a_number_is_left_out(asn: object) -> None:
    body = subscribed(metadata={"asn": asn})

    assert parsed(body).asn is None


def test_text_from_greynoise_is_cleaned_and_cut_to_fit() -> None:
    body = subscribed(actor="Group\nX" + "y" * 500, tags=[{"name": 1}, {"name": "ok"}, "text", {}])

    details = dict(parsed(body).details)

    assert details["Actor"].startswith("Group X")
    assert len(details["Actor"]) <= greynoise.MAX_NAME
    assert details["Tags"] == "ok"


@pytest.mark.parametrize("body", [None, [], "text", 3])
def test_an_answer_that_is_not_an_object_is_a_failure(body: object) -> None:
    assert greynoise.parse(body, NOW) == Failed("GreyNoise's answer wasn't an object.")


def test_an_object_that_holds_no_report_is_a_failure() -> None:
    assert greynoise.parse({"hello": 1}, NOW) == Failed(
        "GreyNoise's answer didn't hold an address's report."
    )


def report_with(*, malicious: int = 0, suspicious: int = 0, harmless: int = 0) -> Report:
    return Report(
        malicious=malicious,
        suspicious=suspicious,
        harmless=harmless,
        undetected=0,
        reputation=0,
        analysed_at=NOW,
    )


def test_a_report_comes_to_what_greynoise_classified() -> None:
    assert greynoise.judge(None) == "unknown"
    assert greynoise.judge(report_with()) == "unknown"
    assert greynoise.judge(report_with(harmless=1)) == "clean"
    assert greynoise.judge(report_with(suspicious=1)) == "suspicious"
    assert greynoise.judge(report_with(malicious=1)) == "malicious"


@pytest.mark.parametrize(
    ("options", "plan"),
    [
        ({}, "free"),
        ({"access": "key"}, "free"),
        ({"access": "key", "plan": "free"}, "free"),
        ({"access": "key", "plan": "subscription"}, "subscription"),
        ({"access": "none"}, "anonymous"),
        ({"access": "none", "plan": "subscription"}, "anonymous"),
        ({"access": "key", "plan": "enterprise"}, "free"),
    ],
)
def test_the_plan_is_what_the_settings_say_and_the_free_one_when_they_say_nothing_clear(
    options: Mapping[str, str | int], plan: str
) -> None:
    assert greynoise.plan_of(options) == plan


def test_the_visualizer_has_a_page_for_an_address_and_one_for_a_business_service() -> None:
    assert greynoise.link_of("1.2.3.4") == "https://viz.greynoise.io/ip/1.2.3.4"
    assert greynoise.link_of("1.2.3.4", business=True) == "https://viz.greynoise.io/riot/1.2.3.4"


def redacted(value: str, limit: int) -> str:
    return value[:limit].upper()


def test_what_the_report_says_is_put_in_a_sentence_for_the_ai() -> None:
    said = greynoise.said(parsed(subscribed()).details, "malicious", redacted)

    assert said == (
        "seen scanning the internet and classified malicious; actor GROUP X; "
        "tags MIRAI, SSH BRUTEFORCER; cves CVE-2024-0001, CVE-2024-0002; a tor exit node; "
        "behind a VPN (EXAMPLE_VPN); last seen 2026-11-08; GreyNoise makes it malicious"
    )


def test_a_business_service_is_said_to_be_one_and_an_unclassified_scanner_unknown() -> None:
    service = greynoise.said(parsed(SERVICE).details, "clean", redacted)
    bare = greynoise.said((), "suspicious", redacted)

    assert service == (
        "a common business service (CLOUDFLARE); last seen 2020-01-01; GreyNoise makes it clean"
    )
    assert (
        bare == "seen scanning the internet and classified unknown; GreyNoise makes it suspicious"
    )


# -- the lookup


def target_for(server: StubServer, options: Mapping[str, str | int] | None = None) -> Target:
    return Target(
        integration="greynoise",
        connection="api",
        origin=netguard.parse_origin(server.url, allow_http=True),
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options=options or {},
        secrets={"api_key": "gn-key"},
    )


async def record(_call: Call) -> None:
    pass  # Keeps nothing: the test needs only that the call was made.


def ask(
    serve: Serve,
    handler: Callable[[Seen], Answer],
    subject: subjects.Subject = SUBJECT,
    options: Mapping[str, str | int] | None = None,
) -> tuple[greynoise.Answer, StubServer]:
    server = serve(handler)
    where = target_for(server, options)

    async def go() -> greynoise.Answer:
        async with ApiClient(where, record, HOME_NETWORK_AND_LOOPBACK) as client:
            return await greynoise.look_up(client, where, subject, NOW)

    return asyncio.run(go()), server


def test_a_free_accounts_lookup_goes_to_the_community_api_with_the_key_in_its_header(
    serve: Serve,
) -> None:
    answer, server = ask(serve, lambda seen: Answer(body=json.dumps(SCANNER), headers=AS_JSON))

    assert isinstance(answer, Reported)
    assert answer.report.malicious == 1
    [seen] = server.seen
    assert seen.target == "/v3/community/93.184.216.34"
    assert seen.headers["key"] == "gn-key"


def test_a_lookup_with_no_account_sends_no_key(serve: Serve) -> None:
    answer, server = ask(
        serve,
        lambda seen: Answer(body=json.dumps(SERVICE), headers=AS_JSON),
        options={"access": "none"},
    )

    assert isinstance(answer, Reported)
    [seen] = server.seen
    assert seen.target == "/v3/community/93.184.216.34"
    assert "key" not in seen.headers


def test_a_subscriptions_lookup_goes_to_the_ip_lookup_api(serve: Serve) -> None:
    answer, server = ask(
        serve,
        lambda seen: Answer(body=json.dumps(subscribed()), headers=AS_JSON),
        options={"access": "key", "plan": "subscription"},
    )

    assert isinstance(answer, Reported)
    assert answer.report.categories == ("Mirai", "SSH Bruteforcer")
    [seen] = server.seen
    assert seen.target == "/v3/ip/93.184.216.34"
    assert seen.headers["key"] == "gn-key"


@pytest.mark.parametrize("text", ["2606:4700:4700::1111", "example.com", "https://example.com/x"])
def test_only_an_ipv4_address_is_ever_sent_to_greynoise(serve: Serve, text: str) -> None:
    answer, server = ask(serve, lambda seen: Answer(body="{}"), subjects.parse(text))

    assert answer == Failed("GreyNoise is only asked about IPv4 addresses.")
    assert server.seen == []


def test_an_address_greynoise_does_not_know_is_unknown(serve: Serve) -> None:
    # The Community API answers 404, with a body that says so, for an address it has not seen.
    answer, _ = ask(serve, lambda seen: Answer(status=404, body=json.dumps(NOT_SEEN)))

    assert answer == Unknown()


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (
            401,
            "GreyNoise didn't accept the key. Copy it again from your GreyNoise account.",
        ),
        (
            403,
            "GreyNoise refused this request. The plan the key belongs to may not include it.",
        ),
        (400, "GreyNoise answered HTTP 400."),
        (500, "GreyNoise answered HTTP 500."),
    ],
)
def test_an_answer_that_is_not_ok_is_a_failure(serve: Serve, status: int, message: str) -> None:
    answer, _ = ask(serve, lambda seen: Answer(status=status))

    assert answer == Failed(message)


def test_a_429_holds_lookups_for_an_hour(serve: Serve) -> None:
    answer, _ = ask(serve, lambda seen: Answer(status=429))

    assert answer == Throttled(until=NOW + timedelta(hours=1))


def test_an_answer_that_is_no_report_is_a_failure(serve: Serve) -> None:
    answer, _ = ask(serve, lambda seen: Answer(body="[]", headers=AS_JSON))

    assert answer == Failed("GreyNoise's answer wasn't an object.")


def test_a_request_the_policy_refuses_is_a_failure_and_is_never_sent(serve: Serve) -> None:
    server = serve(lambda seen: Answer(body="{}"))

    answer = asyncio.run(greynoise.ask(target_for(server), record, HOME_NETWORK, SUBJECT, NOW))

    assert isinstance(answer, Failed)
    assert server.seen == []


def test_a_request_over_a_logged_connection_is_answered(serve: Serve) -> None:
    server = serve(lambda seen: Answer(body=json.dumps(SCANNER), headers=AS_JSON))

    answer = asyncio.run(
        greynoise.ask(target_for(server), record, HOME_NETWORK_AND_LOOPBACK, SUBJECT, NOW)
    )

    assert isinstance(answer, Reported)
