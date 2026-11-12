"""What AlienVault OTX's answer says of an internet address or a domain, and the lookup that asks
for it."""

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import pytest

from app.integrations import netguard
from app.integrations.client import ApiClient, Call, Target
from app.integrations.netguard import HOME_NETWORK, HOME_NETWORK_AND_LOOPBACK
from app.intel import otx, subjects
from app.intel.answers import Failed, Report, Reported, Throttled, Unknown
from tests.stubs import Answer, Seen, Serve, StubServer

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
ADDRESS = ip_address("93.184.216.34")
SUBJECT = subjects.of_address(ADDRESS)
AS_JSON = {"Content-Type": "application/json"}


def pulse(**changes: object) -> dict[str, object]:
    """A pulse as OTX lists it under an indicator, with some of it changed."""
    found: dict[str, object] = {
        "name": "Botnet command servers",
        "modified": "2026-03-01T10:20:30.123456",
        "tags": ["botnet"],
        "malware_families": [{"id": "Mirai", "display_name": "Mirai"}],
        "attack_ids": [{"id": "T1071", "name": "Application Layer Protocol"}],
        "adversary": "Group X",
    }
    found.update(changes)
    return found


BARE: dict[str, object] = {
    "name": "A list of scanners",
    "tags": ["scanner"],
    "created": "2026-02-01T00:00:00",
}


def answer_of(*pulses: object, count: int | None = None, **changes: object) -> dict[str, object]:
    body: dict[str, object] = {
        "indicator": "93.184.216.34",
        "reputation": 2,
        "asn": "AS64500 Example Hosting",
        "country_code": "NL",
        "pulse_info": {"count": len(pulses) if count is None else count, "pulses": list(pulses)},
        "validation": [],
    }
    body.update(changes)
    return body


def report_with(*, malicious: int = 0, suspicious: int = 0, safe: bool = False) -> Report:
    return Report(
        malicious=malicious,
        suspicious=suspicious,
        harmless=0,
        undetected=0,
        reputation=0,
        analysed_at=NOW,
        details=((("Listed as safe", "yes"),) if safe else ()),
    )


def test_a_pulse_that_names_malware_an_adversary_or_a_technique_counts_as_malicious() -> None:
    found = otx.parse(answer_of(pulse(), BARE), NOW)

    assert found is not None
    assert (found.malicious, found.suspicious) == (1, 1)
    assert (found.harmless, found.undetected) == (0, 0)
    assert found.engines == 2


def test_the_facts_about_the_address_are_read_with_the_owner_split_from_the_number() -> None:
    found = otx.parse(answer_of(pulse()), NOW)

    assert found is not None
    assert (found.asn, found.owner, found.country) == (64500, "Example Hosting", "NL")
    assert found.reputation == -2
    assert found.analysed_at == datetime(2026, 3, 1, 10, 20, 30, 123456, tzinfo=UTC)
    assert found.categories == ("Mirai", "Group X", "botnet")
    assert found.details == (
        ("Pulses", "1"),
        ("Newest pulse", "Botnet command servers"),
        ("Malware", "Mirai"),
        ("Adversary", "Group X"),
        ("Attack techniques", "T1071"),
    )


def test_an_address_no_pulse_names_is_a_report_of_none() -> None:
    found = otx.parse(answer_of(), NOW)

    assert found is not None
    assert (found.malicious, found.suspicious) == (0, 0)
    assert found.details == ()
    assert found.analysed_at == NOW


def test_pulses_beyond_the_listed_ones_count_as_the_plainer_kind() -> None:
    found = otx.parse(answer_of(pulse(), count=40), NOW)

    assert found is not None
    assert (found.malicious, found.suspicious) == (1, 39)


def test_the_strong_pulses_never_outnumber_the_count_the_answer_gives() -> None:
    found = otx.parse(answer_of(pulse(), pulse(), count=1), NOW)

    assert found is not None
    assert (found.malicious, found.suspicious) == (1, 0)


def test_a_value_that_is_not_what_it_should_be_is_left_out_rather_than_guessed() -> None:
    found = otx.parse(
        answer_of(
            "bad",
            pulse(modified="yesterday", malware_families="Mirai", adversary=7, attack_ids=[3]),
            count=True,
            asn="not a number",
            country_code=44,
            reputation="high",
        ),
        NOW,
    )

    assert found is not None
    assert (found.asn, found.owner, found.country, found.reputation) == (
        None,
        "not a number",
        None,
        0,
    )
    assert found.analysed_at == NOW
    assert (found.malicious, found.suspicious) == (0, 0)


def test_a_number_with_no_owner_leaves_the_owner_out() -> None:
    found = otx.parse(answer_of(asn="AS64500"), NOW)

    assert found is not None
    assert (found.asn, found.owner) == (64500, None)


def test_a_missing_asn_leaves_both_out_and_control_characters_are_taken_out_of_names() -> None:
    found = otx.parse(
        answer_of(pulse(name="Bad\x07 name\n", malware_families=["Mirai\x07"]), asn=None), NOW
    )

    assert found is not None
    assert (found.asn, found.owner) == (None, None)
    assert all("\x07" not in value for _, value in found.details)


def test_malware_named_by_several_pulses_is_listed_once_and_names_are_text_or_objects() -> None:
    found = otx.parse(
        answer_of(
            pulse(malware_families=["Mirai", {"display_name": "Mirai"}, {"nothing": 1}, ""]),
            pulse(malware_families=[{"id": "Gafgyt"}]),
        ),
        NOW,
    )

    assert found is not None
    assert dict(found.details)["Malware"] == "Mirai, Gafgyt"


def test_the_newest_of_the_pulses_gives_the_time_and_one_without_a_time_does_not_count() -> None:
    found = otx.parse(
        answer_of(
            pulse(modified="2026-01-01T00:00:00"),
            pulse(modified="2026-05-01T00:00:00+02:00"),
            pulse(modified=None, created=None),
        ),
        NOW,
    )

    assert found is not None
    assert found.analysed_at == datetime(2026, 4, 30, 22, 0, tzinfo=UTC)
    assert found.analysed_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("source", ["whitelist", "false_positive", "FalsePositive"])
def test_an_address_otx_lists_as_safe_says_why(source: str) -> None:
    found = otx.parse(
        answer_of(
            pulse(),
            validation=[
                "skip",
                {"source": "other", "message": "no"},
                {"source": source, "message": "Known resolver"},
            ],
        ),
        NOW,
    )

    assert found is not None
    assert dict(found.details)["Listed as safe"] == "Known resolver"
    assert otx.judge(found) == "clean"


def test_a_safe_listing_with_no_message_falls_back_to_its_name_and_then_to_yes() -> None:
    named = otx.parse(answer_of(validation=[{"source": "whitelist", "name": "Google DNS"}]), NOW)
    bare = otx.parse(answer_of(validation=[{"source": "whitelist"}]), NOW)

    assert named is not None
    assert bare is not None
    assert dict(named.details)["Listed as safe"] == "Google DNS"
    assert dict(bare.details)["Listed as safe"] == "yes"


def test_each_judgement_is_made_from_the_pulses_that_name_the_address() -> None:
    assert otx.judge(None) == "unknown"
    assert otx.judge(report_with()) == "unknown"
    assert otx.judge(report_with(suspicious=1)) == "suspicious"
    assert otx.judge(report_with(suspicious=4)) == "suspicious"
    assert otx.judge(report_with(suspicious=5)) == "malicious"
    assert otx.judge(report_with(malicious=1)) == "suspicious"
    assert otx.judge(report_with(malicious=2)) == "malicious"
    assert otx.judge(report_with(malicious=3, safe=True)) == "clean"


@pytest.mark.parametrize("body", [None, [], "text", {"hello": 1}])
def test_an_answer_that_is_not_an_indicators_is_not_a_report(body: object) -> None:
    assert otx.parse(body, NOW) is None


def test_an_indicator_with_no_pulse_info_is_a_report_of_none() -> None:
    found = otx.parse({"indicator": "93.184.216.34"}, NOW)

    assert found is not None
    assert found.engines == 0


def test_each_kind_of_subject_links_to_its_own_page_on_otx() -> None:
    assert otx.link_for(SUBJECT) == "https://otx.alienvault.com/indicator/ip/93.184.216.34"
    assert (
        otx.link_for(subjects.parse("example.com"))
        == "https://otx.alienvault.com/indicator/domain/example.com"
    )
    assert otx.link_for(subjects.parse("https://example.com/login")) is None
    assert otx.link_of("url", "x") is None


def target_for(server: StubServer) -> Target:
    return Target(
        integration="alienvault_otx",
        connection="api",
        origin=netguard.parse_origin(server.url, allow_http=True),
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options={},
        secrets={"api_key": "otx-key"},
    )


async def record(_call: Call) -> None:
    pass  # Keeps nothing: the test needs only that the call was made.


def ask(
    serve: Serve,
    handler: Callable[[Seen], Answer],
    subject: subjects.Subject = SUBJECT,
) -> tuple[otx.Answer, StubServer]:
    server = serve(handler)
    where = target_for(server)

    async def go() -> otx.Answer:
        async with ApiClient(where, record, HOME_NETWORK_AND_LOOPBACK) as client:
            return await otx.look_up(client, where, subject, NOW)

    return asyncio.run(go()), server


def test_the_report_on_an_address_is_asked_for_with_the_key_in_its_header(serve: Serve) -> None:
    answer, server = ask(
        serve, lambda seen: Answer(body=json.dumps(answer_of(pulse())), headers=AS_JSON)
    )

    assert isinstance(answer, Reported)
    assert answer.report.malicious == 1
    [seen] = server.seen
    assert seen.target == "/api/v1/indicators/IPv4/93.184.216.34/general"
    assert seen.headers["x-otx-api-key"] == "otx-key"


@pytest.mark.parametrize(
    ("text", "path"),
    [
        ("example.com", "/api/v1/indicators/domain/example.com/general"),
        ("2606:4700:4700::1111", "/api/v1/indicators/IPv6/2606:4700:4700::1111/general"),
    ],
)
def test_a_domain_and_an_ipv6_address_are_asked_for_at_their_own_paths(
    serve: Serve, text: str, path: str
) -> None:
    answer, server = ask(
        serve,
        lambda seen: Answer(body=json.dumps(answer_of(pulse())), headers=AS_JSON),
        subjects.parse(text),
    )

    assert isinstance(answer, Reported)
    [seen] = server.seen
    assert seen.target == path


def test_a_web_address_is_never_sent_to_otx(serve: Serve) -> None:
    answer, server = ask(
        serve, lambda seen: Answer(body="{}"), subjects.parse("https://example.com/login")
    )

    assert answer == Failed("OTX is only asked about addresses and domains.")
    assert server.seen == []


def test_an_address_with_no_report_is_unknown(serve: Serve) -> None:
    answer, _ = ask(serve, lambda seen: Answer(status=404))

    assert answer == Unknown()


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (
            401,
            "OTX didn't accept the key. Copy it again from your OTX account's settings.",
        ),
        (
            403,
            "OTX refused this request with the key. Check that the key is the one for your "
            "account.",
        ),
        (500, "OTX answered HTTP 500."),
    ],
)
def test_an_answer_that_is_not_ok_is_a_failure(serve: Serve, status: int, message: str) -> None:
    answer, _ = ask(serve, lambda seen: Answer(status=status))

    assert answer == Failed(message)


def test_a_429_holds_lookups_for_a_few_minutes(serve: Serve) -> None:
    answer, _ = ask(serve, lambda seen: Answer(status=429))

    assert answer == Throttled(until=NOW + otx.THROTTLE)


def test_an_answer_that_is_no_indicator_is_a_failure(serve: Serve) -> None:
    answer, _ = ask(serve, lambda seen: Answer(body="[]", headers=AS_JSON))

    assert answer == Failed("OTX's answer didn't hold an indicator.")


def test_a_request_the_policy_refuses_is_a_failure_and_is_never_sent(serve: Serve) -> None:
    server = serve(lambda seen: Answer(body="{}"))

    answer = asyncio.run(otx.ask(target_for(server), record, HOME_NETWORK, SUBJECT, NOW))

    assert isinstance(answer, Failed)
    assert server.seen == []


def test_a_request_over_a_logged_connection_is_answered(serve: Serve) -> None:
    server = serve(lambda seen: Answer(body=json.dumps(answer_of(pulse())), headers=AS_JSON))

    answer = asyncio.run(
        otx.ask(target_for(server), record, HOME_NETWORK_AND_LOOPBACK, SUBJECT, NOW)
    )

    assert isinstance(answer, Reported)
