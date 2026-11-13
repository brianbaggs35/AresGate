"""What NVD's CVE API says of one CVE, and how it is asked."""

import asyncio
import dataclasses
import json
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from app.integrations import netguard
from app.integrations.client import ApiClient, Call, CallFailed, Reply, Target
from app.integrations.netguard import HOME_NETWORK_AND_LOOPBACK
from app.nvd import lookup
from app.nvd.lookup import Failed, Found, Throttled, Unknown
from tests.nvd_body import LOG4SHELL, body, cve, metric_v2, metric_v31
from tests.stubs import Answer, Seen, Serve, StubServer

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def record_of(*entries: dict[str, Any], cve_id: str = LOG4SHELL) -> lookup.Record:
    answer = lookup.parse(json.loads(body(*entries)), cve_id)
    assert isinstance(answer, Found)
    return answer.record


# -- reading an answer


def test_a_record_holds_what_nvd_and_cisa_say_of_the_cve() -> None:
    found = record_of(cve())

    assert found.cve_id == LOG4SHELL
    assert found.status == "Analyzed"
    assert found.published_at == datetime(2021, 12, 10, 10, 15, 9, 143000, tzinfo=UTC)
    assert found.modified_at == datetime(2025, 10, 27, 16, 15, 38, 223000, tzinfo=UTC)
    assert (found.cvss_version, found.score, found.severity) == ("3.1", 10.0, "CRITICAL")
    assert found.vector == "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H"
    assert found.description == "Apache Log4j2 JNDI features do not protect against LDAP."
    assert found.weaknesses == ("CWE-917", "CWE-20")
    assert found.exploited is True
    assert found.exploited_on == date(2021, 12, 10)
    assert found.action_due == date(2021, 12, 24)
    assert found.required_action == (
        "For all affected software assets, apply updates per vendor instructions."
    )
    assert found.kev_name == "Apache Log4j2 Remote Code Execution Vulnerability"


def test_a_cve_cisa_does_not_list_is_not_marked_exploited() -> None:
    found = record_of(
        cve(
            cisaExploitAdd=None,
            cisaActionDue=None,
            cisaRequiredAction=None,
            cisaVulnerabilityName=None,
        )
    )

    assert found.exploited is False
    assert (found.exploited_on, found.action_due, found.required_action) == (None, None, None)


def test_the_newest_cvss_version_is_the_score() -> None:
    v40 = {
        "type": "Secondary",
        "cvssData": {
            "version": "4.0",
            "vectorString": "CVSS:4.0/AV:N",
            "baseScore": 9.3,
            "baseSeverity": "CRITICAL",
        },
    }
    found = record_of(
        cve(metrics={"cvssMetricV40": [v40], "cvssMetricV31": [metric_v31(5.0, "MEDIUM")]})
    )

    assert (found.cvss_version, found.score, found.severity) == ("4.0", 9.3, "CRITICAL")


def test_among_scores_of_one_version_the_primary_one_is_the_score() -> None:
    found = record_of(
        cve(
            metrics={
                "cvssMetricV31": [
                    metric_v31(9.8, "CRITICAL", source="security@apache.org", primary=False),
                    metric_v31(7.5, "HIGH"),
                ]
            }
        )
    )

    assert (found.score, found.severity) == (7.5, "HIGH")


def test_a_cve_with_only_cvss_2_takes_its_rating_from_beside_the_data() -> None:
    found = record_of(cve(metrics={"cvssMetricV2": [metric_v2(5.0, "MEDIUM")]}))

    assert (found.cvss_version, found.score, found.severity) == ("2.0", 5.0, "MEDIUM")
    assert found.vector == "AV:N/AC:M/Au:N/C:C/I:C/A:C"


@pytest.mark.parametrize(
    ("score", "version", "rating"),
    [
        (0.0, "3.1", "NONE"),
        (3.9, "3.1", "LOW"),
        (4.0, "3.1", "MEDIUM"),
        (6.9, "2.0", "MEDIUM"),
        (7.0, "3.1", "HIGH"),
        (8.9, "3.1", "HIGH"),
        (9.0, "3.1", "CRITICAL"),
        (10.0, "2.0", "HIGH"),
    ],
)
def test_a_score_given_without_its_rating_is_rated_by_cvss(
    score: float, version: str, rating: str
) -> None:
    metric = {"cvssData": {"version": version, "baseScore": score}}

    found = record_of(cve(metrics={"cvssMetricV31": [metric]}))

    assert found.severity == rating


def test_a_rating_nvd_gives_that_cvss_has_no_word_for_is_rated_by_its_score() -> None:
    metric = metric_v31(9.8, "SEVERE")

    assert record_of(cve(metrics={"cvssMetricV31": [metric]})).severity == "CRITICAL"


@pytest.mark.parametrize(
    "metrics",
    [
        None,
        {},
        {"cvssMetricV31": []},
        {"cvssMetricV31": ["x"]},
        {"cvssMetricV31": [{"cvssData": "x"}]},
        {"cvssMetricV31": [{"cvssData": {"version": "3.1", "baseScore": 11}}]},
        {"cvssMetricV31": [{"cvssData": {"version": "3.1", "baseScore": True}}]},
        {"cvssMetricV31": [{"cvssData": {"version": "3.1"}}]},
        {"cvssMetricV31": [{"cvssData": {"version": "abc", "baseScore": 5}}]},
        {"epss": [metric_v31()]},
    ],
)
def test_a_cve_without_a_usable_score_has_none(metrics: Any) -> None:
    found = record_of(cve(metrics=metrics))

    assert (found.cvss_version, found.score, found.severity, found.vector) == (None,) * 4


def test_a_cve_not_yet_analysed_has_a_record_and_no_score() -> None:
    found = record_of(cve(vulnStatus="Awaiting Analysis", metrics=None, weaknesses=None))

    assert found.status == "Awaiting Analysis"
    assert found.score is None
    assert found.weaknesses == ()


def test_the_description_is_the_english_one() -> None:
    entries = [{"lang": "es", "value": "uno"}, {"lang": "en", "value": "one"}]

    assert record_of(cve(descriptions=entries)).description == "one"
    assert record_of(cve(descriptions=[{"lang": "es", "value": "uno"}])).description is None
    assert record_of(cve(descriptions=["x"])).description is None


def test_text_nvd_gives_is_cut_and_cleaned() -> None:
    entries = [{"lang": "en", "value": "a\x00b" + "c" * 5000}]

    found = record_of(cve(descriptions=entries))

    assert found.description is not None
    assert len(found.description) == lookup.MAX_DESCRIPTION
    assert "\x00" not in found.description


def test_weaknesses_are_each_listed_once_and_only_when_they_are_weaknesses() -> None:
    entries = [
        {"description": [{"lang": "en", "value": "CWE-79"}, {"lang": "en", "value": "CWE-79"}]},
        {"description": [{"lang": "en", "value": "NVD-CWE-Other"}, {"value": "something"}, "x"]},
        {"description": "x"},
        "x",
    ]

    assert record_of(cve(weaknesses=entries)).weaknesses == ("CWE-79", "NVD-CWE-Other")


@pytest.mark.parametrize(
    "value", ["2021-12-10", "2021-12-10T10:15:09.143", "2021-12-10T10:15:09+02:00"]
)
def test_times_nvd_gives_are_utc_unless_they_say_otherwise(value: str) -> None:
    found = record_of(cve(published=value))

    assert found.published_at is not None
    assert found.published_at.tzinfo is not None
    assert found.published_at.date() == date(2021, 12, 10)


@pytest.mark.parametrize("value", [None, 5, "soon", ""])
def test_a_time_that_is_not_one_is_left_out(value: object) -> None:
    found = record_of(cve(published=value, lastModified=value, cisaExploitAdd=value))

    assert (found.published_at, found.modified_at, found.exploited) == (None, None, False)


def test_an_answer_that_lists_no_cve_says_nvd_has_none() -> None:
    assert lookup.parse({"vulnerabilities": []}, LOG4SHELL) == Unknown()


def test_an_answer_for_another_cve_than_the_one_asked_is_not_taken_for_it() -> None:
    other = cve("CVE-2019-0708")

    assert lookup.parse({"vulnerabilities": [other, "x", {"cve": "x"}]}, LOG4SHELL) == Unknown()


@pytest.mark.parametrize("answer", [None, [], "x", {}, {"vulnerabilities": "x"}])
def test_an_answer_that_lists_no_cves_at_all_is_a_failure(answer: object) -> None:
    assert lookup.parse(answer, LOG4SHELL) == Failed("NVD's answer didn't hold a list of CVEs.")


def test_the_page_about_a_cve_is_on_nvds_site() -> None:
    assert lookup.link_of(LOG4SHELL) == "https://nvd.nist.gov/vuln/detail/CVE-2021-44228"


def test_a_key_is_sent_unless_the_settings_say_none() -> None:
    assert lookup.access_of({}) == lookup.KEY
    assert lookup.access_of({"access": "key"}) == lookup.KEY
    assert lookup.access_of({"access": "none"}) == lookup.NONE


# -- what a reply says


def reply(status: int = 200, text: str = "", **headers: str) -> Reply:
    return Reply(status=status, text=text, headers=headers)


def test_a_good_reply_is_read_for_the_cve() -> None:
    answer = lookup.answer_of(reply(text=body(cve())), LOG4SHELL, NOW)

    assert isinstance(answer, Found)


@pytest.mark.parametrize("status", [403, 429, 503])
def test_a_refusal_that_may_be_the_limit_holds_lookups_for_a_while(status: int) -> None:
    assert lookup.answer_of(reply(status), LOG4SHELL, NOW) == Throttled(NOW + lookup.THROTTLE)


def test_a_404_says_nvd_has_no_record() -> None:
    assert lookup.answer_of(reply(404), LOG4SHELL, NOW) == Unknown()
    assert lookup.answer_of(reply(404, message="CVE not found"), LOG4SHELL, NOW) == Unknown()


def test_a_404_that_blames_the_key_is_a_failure_not_an_unknown_cve() -> None:
    answer = lookup.answer_of(reply(404, message="Invalid apiKey."), LOG4SHELL, NOW)

    assert answer == Failed("NVD answered HTTP 404: Invalid apiKey.")


def test_a_400_says_why_in_the_words_nvd_gives() -> None:
    answer = lookup.answer_of(reply(400, message="Invalid cveId\x00 given"), LOG4SHELL, NOW)

    assert answer == Failed("NVD answered HTTP 400: Invalid cveId  given")


def test_an_error_that_says_nothing_is_a_failure_with_its_status() -> None:
    assert lookup.answer_of(reply(500), LOG4SHELL, NOW) == Failed("NVD answered HTTP 500.")


def test_a_message_too_long_is_cut() -> None:
    answer = lookup.answer_of(reply(400, message="x" * 500), LOG4SHELL, NOW)

    assert isinstance(answer, Failed)
    assert len(answer.message) < 160


def test_a_reply_that_is_not_json_is_a_failure() -> None:
    assert isinstance(lookup.answer_of(reply(text="<html>"), LOG4SHELL, NOW), Failed)


# -- asking


def target_for(server: StubServer, options: Mapping[str, str | int] | None = None) -> Target:
    return Target(
        integration="nvd",
        connection="api",
        origin=netguard.parse_origin(server.url, allow_http=True),
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options=options or {},
        secrets={"api_key": "nvd-key"},
    )


async def keep(_call: Call) -> None:
    pass  # Keeps nothing: the test needs only that the call was made.


def ask(
    serve: Serve,
    handler: Callable[[Seen], Answer],
    options: Mapping[str, str | int] | None = None,
) -> tuple[lookup.Answer, StubServer]:
    server = serve(handler)
    where = target_for(server, options)

    async def go() -> lookup.Answer:
        async with ApiClient(where, keep, HOME_NETWORK_AND_LOOPBACK) as client:
            return await lookup.look_up(client, where, LOG4SHELL, NOW)

    return asyncio.run(go()), server


def test_the_cve_is_asked_for_by_id_with_the_key_in_its_header(serve: Serve) -> None:
    answer, server = ask(serve, lambda seen: Answer(body=body(cve())))

    assert isinstance(answer, Found)
    [seen] = server.seen
    assert seen.method == "GET"
    assert seen.target == "/rest/json/cves/2.0?cveIds=CVE-2021-44228"
    assert seen.headers["apikey"] == "nvd-key"


def test_a_connection_that_asks_without_a_key_sends_none(serve: Serve) -> None:
    answer, server = ask(serve, lambda seen: Answer(body=body()), options={"access": "none"})

    assert answer == Unknown()
    [seen] = server.seen
    assert "apikey" not in seen.headers


def test_a_connection_that_asks_with_a_key_it_does_not_hold_sends_none(serve: Serve) -> None:
    server = serve(lambda seen: Answer(body=body()))
    where = target_for(server)
    where = dataclasses.replace(where, secrets={})

    async def go() -> lookup.Answer:
        async with ApiClient(where, keep, HOME_NETWORK_AND_LOOPBACK) as client:
            return await lookup.look_up(client, where, LOG4SHELL, NOW)

    assert asyncio.run(go()) == Unknown()
    assert "apikey" not in server.seen[0].headers


def test_a_lookup_nvd_does_not_answer_is_a_failure_with_the_reason(serve: Serve) -> None:
    server = serve(lambda seen: Answer(drop=True))
    where = target_for(server)

    answer = asyncio.run(lookup.ask(where, keep, HOME_NETWORK_AND_LOOPBACK, LOG4SHELL, NOW))

    assert isinstance(answer, Failed)
    assert answer.message


def test_ask_gives_what_the_lookup_gives(serve: Serve) -> None:
    server = serve(lambda seen: Answer(body=body(cve())))
    where = target_for(server)

    answer = asyncio.run(lookup.ask(where, keep, HOME_NETWORK_AND_LOOPBACK, LOG4SHELL, NOW))

    assert isinstance(answer, Found)


def test_the_throttle_is_a_pause_of_minutes() -> None:
    assert timedelta(minutes=1) <= lookup.THROTTLE <= timedelta(minutes=10)


def test_the_notice_is_the_one_nvd_asks_for() -> None:
    assert lookup.NOTICE == (
        "This product uses data from the NVD API but is not endorsed or certified by the NVD."
    )


def test_call_failed_is_what_a_dropped_connection_raises(serve: Serve) -> None:
    server = serve(lambda seen: Answer(drop=True))
    where = target_for(server)

    async def go() -> None:
        async with ApiClient(where, keep, HOME_NETWORK_AND_LOOPBACK) as client:
            await lookup.look_up(client, where, LOG4SHELL, NOW)

    with pytest.raises(CallFailed):
        asyncio.run(go())
