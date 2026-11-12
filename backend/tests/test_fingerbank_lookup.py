"""What Fingerbank's answer says a device is, and the request that asks for it."""

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from app.fingerbank import lookup
from app.fingerbank.lookup import Failed, Identified, Identity, Throttled, Unknown
from app.integrations import netguard
from app.integrations.client import ApiClient, Call, Reply, Target
from app.integrations.netguard import HOME_NETWORK_AND_LOOPBACK
from tests.stubs import Answer, Seen, Serve, StubServer

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
MAC = "00:11:22:0a:0b:0c"
AS_JSON = {"Content-Type": "application/json"}


def body(**changes: object) -> dict[str, object]:
    """An answer as Fingerbank gives it for a phone, with some of it changed."""
    found: dict[str, object] = {
        "device": {"id": 33453, "name": "Apple iPhone 16", "parent_id": 1, "parents": []},
        "device_name": "Phone, Tablet, or Wearable/Apple iOS/Apple iPhone/Apple iPhone 16",
        "manufacturer": {"id": 5, "name": "Apple, Inc."},
        "operating_system": {"id": 7, "name": "Apple iOS"},
        "score": 72,
        "version": "2",
        "request_id": "abc",
        "vulnerabilities": {"cve_devices": [], "cve_os": [], "message": ""},
    }
    found.update(changes)
    return found


def reply(status: int = 200, content: object = None) -> Reply:
    return Reply(status, json.dumps(body() if content is None else content))


class TestWhatAnAnswerSays:
    def test_a_device_is_named_with_its_path_maker_system_and_score(self) -> None:
        answer = lookup.answer_of(reply(), NOW)

        assert answer == Identified(
            Identity(
                name="Apple iPhone 16",
                path="Phone, Tablet, or Wearable/Apple iOS/Apple iPhone/Apple iPhone 16",
                manufacturer="Apple, Inc.",
                operating_system="Apple iOS",
                score=72,
                external_id=33453,
            )
        )

    def test_a_maker_and_a_system_that_are_null_are_left_out(self) -> None:
        answer = lookup.answer_of(
            reply(content=body(manufacturer=None, operating_system=None)), NOW
        )

        assert isinstance(answer, Identified)
        assert answer.identity.manufacturer is None
        assert answer.identity.operating_system is None

    @pytest.mark.parametrize("score", [-1, 101, True, "72", None])
    def test_a_score_outside_zero_to_a_hundred_or_not_a_number_is_left_out(
        self, score: object
    ) -> None:
        answer = lookup.answer_of(reply(content=body(score=score)), NOW)

        assert isinstance(answer, Identified)
        assert answer.identity.score is None

    def test_text_is_cleaned_and_cut_to_what_is_kept(self) -> None:
        long = "x" * 5000
        answer = lookup.answer_of(
            reply(content=body(device={"id": 1, "name": f"Phone\x00{long}"}, device_name=long)), NOW
        )

        assert isinstance(answer, Identified)
        assert answer.identity.name is not None
        assert "\x00" not in answer.identity.name
        assert len(answer.identity.name) == lookup.MAX_NAME
        assert answer.identity.path is not None
        assert len(answer.identity.path) == lookup.MAX_PATH

    def test_a_device_that_names_nothing_is_no_match(self) -> None:
        answer = lookup.answer_of(reply(content=body(device={"id": 3}, device_name="  ")), NOW)

        assert answer == Unknown()

    def test_a_device_id_too_big_to_keep_is_left_out(self) -> None:
        answer = lookup.answer_of(reply(content=body(device={"id": 2**64, "name": "Phone"})), NOW)

        assert isinstance(answer, Identified)
        assert answer.identity.external_id is None

    def test_a_404_is_no_match_and_not_an_error(self) -> None:
        assert lookup.answer_of(Reply(404, "{}"), NOW) == Unknown()

    def test_a_429_holds_lookups_for_five_minutes_and_is_not_an_error(self) -> None:
        assert lookup.answer_of(Reply(429, ""), NOW) == Throttled(until=NOW + timedelta(minutes=5))

    @pytest.mark.parametrize(
        ("status", "words"),
        [(401, "didn't accept the key"), (403, "has blocked this key")],
    )
    def test_a_key_that_is_turned_down_is_a_failure_a_person_has_to_put_right(
        self, status: int, words: str
    ) -> None:
        answer = lookup.answer_of(Reply(status, ""), NOW)

        assert isinstance(answer, Failed)
        assert answer.refused
        assert words in answer.message

    def test_a_server_error_is_a_failure_that_is_tried_again(self) -> None:
        answer = lookup.answer_of(Reply(502, ""), NOW)

        assert answer == Failed("Fingerbank answered HTTP 502.")

    @pytest.mark.parametrize("text", ["<html>", "[]", '{"errors": ["nope"]}'])
    def test_an_answer_that_holds_no_device_is_a_failure(self, text: str) -> None:
        assert lookup.answer_of(Reply(200, text), NOW) == Failed(
            "Fingerbank's answer didn't hold a device."
        )


def target_for(server: StubServer) -> Target:
    return Target(
        integration="fingerbank",
        connection="api",
        origin=netguard.parse_origin(server.url, allow_http=True),
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options={},
        secrets={"api_key": "fb-secret-key"},
    )


async def record(_call: Call) -> None:
    pass  # Keeps nothing: the test needs only that the call was made.


def ask(
    serve: Serve, handler: Callable[[Seen], Answer]
) -> tuple[lookup.Answer, StubServer, list[Call]]:
    server = serve(handler)
    where = target_for(server)
    calls: list[Call] = []

    async def log(call: Call) -> None:
        calls.append(call)

    async def go() -> lookup.Answer:
        return await lookup.ask(where, log, HOME_NETWORK_AND_LOOPBACK, MAC, NOW)

    return asyncio.run(go()), server, calls


def test_a_device_is_asked_about_by_its_hardware_address_alone_with_the_key_in_a_header(
    serve: Serve,
) -> None:
    answer, server, calls = ask(
        serve, lambda seen: Answer(body=json.dumps(body()), headers=AS_JSON)
    )

    assert isinstance(answer, Identified)
    [seen] = server.seen
    assert seen.method == "GET"
    assert seen.target == "/api/v2/combinations/interrogate"
    assert json.loads(seen.body) == {"mac": MAC}
    assert seen.headers["authorization"] == "Bearer fb-secret-key"
    # The key is in no address, so it is in no API log entry.
    assert "fb-secret-key" not in calls[0].path


def test_a_request_that_gets_no_answer_is_a_failure_with_the_reason(serve: Serve) -> None:
    server = serve(lambda seen: Answer())
    where = target_for(server)
    server.stop()

    async def go() -> lookup.Answer:
        return await lookup.ask(where, record, HOME_NETWORK_AND_LOOPBACK, MAC, NOW)

    answer = asyncio.run(go())

    assert isinstance(answer, Failed)
    assert not answer.refused


def test_a_client_can_be_used_to_look_up_directly(serve: Serve) -> None:
    server = serve(lambda seen: Answer(status=404))
    where = target_for(server)

    async def go() -> lookup.Answer:
        async with ApiClient(where, record, HOME_NETWORK_AND_LOOPBACK) as client:
            return await lookup.look_up(client, where, MAC, NOW)

    assert asyncio.run(go()) == Unknown()
