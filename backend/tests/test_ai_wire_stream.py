import asyncio
import json
from contextlib import aclosing
from typing import Any

import pytest

from app.ai import catalog, wire
from app.ai.catalog import ProviderDef
from app.ai.wire import AiFailed, Completion
from app.integrations import netguard
from app.integrations.client import ApiClient, Call, Target
from app.integrations.netguard import HOME_NETWORK_AND_LOOPBACK
from tests.stubs import Answer, Seen, Serve

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}}


def sse(*events: dict[str, object] | str) -> str:
    """Server-sent events, as Anthropic and OpenAI write them: a named event, its data, a blank
    line."""
    out: list[str] = []
    for event in events:
        if isinstance(event, str):
            out.append(event)
            continue
        out.append(f"event: {event['type']}\ndata: {json.dumps(event)}\n")
    return "\n".join(out) + "\n"


def lines(*objects: object) -> str:
    return "\n".join(json.dumps(item) for item in objects) + "\n"


class Log:
    def __init__(self) -> None:
        self.calls: list[Call] = []

    async def __call__(self, call: Call) -> None:
        self.calls.append(call)


def stream(
    serve: Serve,
    definition: ProviderDef,
    answer: Answer,
    *,
    seen: list[Seen] | None = None,
    **options: Any,
) -> tuple[list[str], Completion | None, Log]:
    def handler(request: Seen) -> Answer:
        if seen is not None:
            seen.append(request)
        return answer

    server = serve(handler)
    target = Target(
        integration="ai",
        connection=definition.key,
        origin=netguard.parse_origin(server.url, allow_http=True),
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options={},
        secrets={"api_key": "sk-a-key"},
    )
    log = Log()

    async def go() -> tuple[list[str], Completion | None]:
        pieces: list[str] = []
        done: Completion | None = None
        async with ApiClient(target, log, HOME_NETWORK_AND_LOOPBACK) as client:
            async for item in wire.stream(
                client,
                definition,
                "a-model",
                "sk-a-key",
                system="Be brief.",
                prompt="Hi",
                **options,
            ):
                if isinstance(item, Completion):
                    done = item
                else:
                    pieces.append(item)
        return pieces, done

    pieces, done = asyncio.run(go())
    return pieces, done, log


def fails(serve: Serve, definition: ProviderDef, answer: Answer, message: str) -> AiFailed:
    with pytest.raises(AiFailed, match=message) as raised:
        stream(serve, definition, answer)
    return raised.value


ANTHROPIC_ANSWER = sse(
    {
        "type": "message_start",
        "message": {
            "usage": {
                "input_tokens": 10,
                "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": 5,
                "output_tokens": 1,
            }
        },
    },
    {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    {"type": "ping"},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hel"}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "lo"}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": ""}},
    {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "thinking_delta", "thinking": "x"},
    },
    ": a comment",
    "data: not json",
    "data: [1, 2]",
    {"type": "something_new"},
    {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 7}},
    {"type": "message_stop"},
)


class TestAnthropic:
    def test_the_text_comes_in_pieces_and_then_what_it_counted(self, serve: Serve) -> None:
        seen: list[Seen] = []

        pieces, done, log = stream(
            serve,
            catalog.ANTHROPIC,
            Answer(body=ANTHROPIC_ANSWER),
            seen=seen,
            schema=SCHEMA,
            max_tokens=300,
        )

        assert pieces == ["Hel", "lo"]
        assert done == Completion(
            text="Hello",
            input_tokens=115,
            output_tokens=7,
            cached_tokens=100,
            cache_write_tokens=5,
        )
        body = json.loads(seen[0].body)
        assert body["stream"] is True
        assert body["max_tokens"] == 300
        assert body["output_config"]["format"]["schema"] == SCHEMA
        assert seen[0].headers["x-api-key"] == "sk-a-key"
        assert seen[0].headers["accept"] == "text/event-stream"
        assert [(call.path, call.status_code) for call in log.calls] == [("/v1/messages", 200)]

    def test_an_answer_that_ran_out_of_room_says_so(self, serve: Serve) -> None:
        body = sse(
            {"type": "message_delta", "delta": {"stop_reason": "max_tokens"}, "usage": {}},
            {"type": "message_stop"},
        )

        _, done, _ = stream(serve, catalog.ANTHROPIC, Answer(body=body))

        assert done is not None
        assert done.truncated is True

    def test_a_refusal_is_not_an_answer(self, serve: Serve) -> None:
        body = sse(
            {"type": "message_delta", "delta": {"stop_reason": "refusal"}},
            {"type": "message_stop"},
        )

        fails(serve, catalog.ANTHROPIC, Answer(body=body), "declined")

    def test_an_error_in_the_middle_of_it_ends_it(self, serve: Serve) -> None:
        body = sse(
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hel"}},
            {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}},
        )

        error = fails(serve, catalog.ANTHROPIC, Answer(body=body), "part of the way")

        assert "Overloaded" not in str(error)

    def test_a_stream_that_stops_before_its_end_is_not_an_answer(self, serve: Serve) -> None:
        body = sse({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hel"}})

        fails(serve, catalog.ANTHROPIC, Answer(body=body), "stopped before the answer")

    def test_a_status_that_is_not_a_success_is_explained(self, serve: Serve) -> None:
        error = fails(serve, catalog.ANTHROPIC, Answer(status=401, body="no"), "didn't accept")

        assert error.status == 401


def completed(response: dict[str, object], kind: str = "response.completed") -> str:
    return sse({"type": kind, "response": response})


def delta(text: str) -> dict[str, object]:
    return {"type": "response.output_text.delta", "delta": text, "item_id": "i"}


class TestOpenAi:
    def test_the_text_comes_in_pieces_and_the_whole_says_what_it_counted(
        self, serve: Serve
    ) -> None:
        seen: list[Seen] = []
        body = sse(
            {"type": "response.created", "response": {}},
            delta("Hel"),
            delta("lo"),
            completed(
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "Hello"}],
                        }
                    ],
                    "usage": {
                        "input_tokens": 20,
                        "output_tokens": 9,
                        "input_tokens_details": {"cached_tokens": 12},
                        "output_tokens_details": {"reasoning_tokens": 4},
                    },
                }
            ),
        )

        pieces, done, _ = stream(serve, catalog.OPENAI, Answer(body=body), seen=seen, schema=SCHEMA)

        assert pieces == ["Hel", "lo"]
        assert done == Completion(
            text="Hello", input_tokens=20, output_tokens=9, cached_tokens=12, reasoning_tokens=4
        )
        sent = json.loads(seen[0].body)
        assert sent["stream"] is True
        assert sent["text"]["format"]["schema"] == SCHEMA
        assert seen[0].headers["authorization"] == "Bearer sk-a-key"
        assert seen[0].headers["accept"] == "text/event-stream"

    def test_what_was_written_is_kept_when_the_end_does_not_repeat_it(self, serve: Serve) -> None:
        body = sse(delta("Hel"), delta("lo"), completed({"usage": {"output_tokens": 2}}))

        _, done, _ = stream(serve, catalog.OPENAI, Answer(body=body))

        assert done is not None
        assert (done.text, done.output_tokens) == ("Hello", 2)

    def test_an_answer_that_ran_out_of_room_is_incomplete(self, serve: Serve) -> None:
        body = sse(
            delta("Hel"),
            completed(
                {"incomplete_details": {"reason": "max_output_tokens"}}, "response.incomplete"
            ),
        )

        _, done, _ = stream(serve, catalog.OPENAI, Answer(body=body))

        assert done is not None
        assert done.truncated is True

    @pytest.mark.parametrize(
        ("event", "message"),
        [
            ({"type": "response.refusal.delta", "delta": "No"}, "declined"),
            ({"type": "response.failed", "response": {}}, "couldn't answer"),
            ({"type": "error", "message": "no", "code": "x"}, "couldn't answer"),
        ],
    )
    def test_an_answer_that_is_refused_or_fails_is_not_one(
        self, serve: Serve, event: dict[str, object], message: str
    ) -> None:
        fails(serve, catalog.OPENAI, Answer(body=sse(delta("Hel"), event)), message)

    def test_a_stream_that_stops_before_its_end_is_not_an_answer(self, serve: Serve) -> None:
        fails(serve, catalog.OPENAI, Answer(body=sse(delta("Hel"))), "stopped before the answer")

    def test_events_that_are_not_for_it_are_left_alone(self, serve: Serve) -> None:
        body = sse(
            "event: x",
            "data: [DONE]",
            "data: 3",
            {"type": "response.in_progress"},
            completed({}),
        )

        pieces, done, _ = stream(serve, catalog.OPENAI, Answer(body=body))

        assert (pieces, done) == ([], Completion(text="", input_tokens=0, output_tokens=0))


class TestOllama:
    def test_the_text_comes_in_pieces_and_the_last_line_says_what_it_counted(
        self, serve: Serve
    ) -> None:
        seen: list[Seen] = []
        body = lines(
            {"message": {"role": "assistant", "content": "Hel"}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": False},
            {"message": {"role": "assistant", "content": "lo"}, "done": False},
            {
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "done_reason": "length",
                "prompt_eval_count": 11,
                "eval_count": 3,
            },
        )

        pieces, done, _ = stream(
            serve,
            catalog.OLLAMA,
            Answer(body=body),
            seen=seen,
            schema=SCHEMA,
            max_tokens=200,
            keep_alive="10m",
        )

        assert pieces == ["Hel", "lo"]
        assert done == Completion(text="Hello", input_tokens=11, output_tokens=3, truncated=True)
        sent = json.loads(seen[0].body)
        assert sent["stream"] is True
        assert sent["keep_alive"] == "10m"
        assert sent["format"] == SCHEMA
        assert seen[0].headers["accept"] == "application/json"

    def test_lines_that_are_not_objects_are_left_alone(self, serve: Serve) -> None:
        body = "not json\n[1]\n" + lines({"message": {"content": "Hi"}, "done": True})

        pieces, done, _ = stream(serve, catalog.OLLAMA, Answer(body=body))

        assert (pieces, done) == (["Hi"], Completion(text="Hi", input_tokens=0, output_tokens=0))

    def test_an_error_line_ends_it(self, serve: Serve) -> None:
        body = lines({"message": {"content": "Hi"}, "done": False}, {"error": "out of memory"})

        error = fails(serve, catalog.OLLAMA, Answer(body=body), "part of the way")

        assert "memory" not in str(error)

    def test_a_stream_that_stops_before_its_end_is_not_an_answer(self, serve: Serve) -> None:
        body = lines({"message": {"content": "Hi"}, "done": False})

        fails(serve, catalog.OLLAMA, Answer(body=body), "stopped before the answer")

    def test_a_model_it_does_not_have_is_explained(self, serve: Serve) -> None:
        error = fails(
            serve, catalog.OLLAMA, Answer(status=404, body="{}"), "doesn't have that model"
        )

        assert error.status == 404


def test_it_closes_the_connection_when_the_reader_stops_early(serve: Serve) -> None:
    server = serve(lambda seen: Answer(body=ANTHROPIC_ANSWER))
    target = Target(
        integration="ai",
        connection="anthropic",
        origin=netguard.parse_origin(server.url, allow_http=True),
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options={},
        secrets={},
    )
    log = Log()

    async def go() -> str:
        async with (
            ApiClient(target, log, HOME_NETWORK_AND_LOOPBACK) as client,
            aclosing(
                wire.stream(client, catalog.ANTHROPIC, "m", "k", system="s", prompt="p")
            ) as pieces,
        ):
            async for piece in pieces:
                return str(piece)
        return ""

    assert asyncio.run(go()) == "Hel"
    assert [call.status_code for call in log.calls] == [200]
