import asyncio
import json
from collections.abc import Callable
from typing import Any

import pytest

from app.ai import catalog, wire
from app.ai.catalog import ProviderDef
from app.ai.wire import AiFailed, Completion
from app.integrations import netguard
from app.integrations.client import ApiClient, Call, Reply, Target
from app.integrations.netguard import HOME_NETWORK_AND_LOOPBACK
from e2e import stand_ins
from tests.stubs import Answer, Seen, Serve

SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string"}}}
# About 1,250 tokens by the rule of thumb: long enough for either provider to cache.
LONG_SYSTEM = "Be brief. " * 500


def ok(body: object) -> Reply:
    return Reply(200, json.dumps(body))


class Log:
    def __init__(self) -> None:
        self.calls: list[Call] = []

    async def __call__(self, call: Call) -> None:
        self.calls.append(call)


def ask(
    serve: Serve,
    definition: ProviderDef,
    handler: Callable[[Seen], Answer],
    action: Callable[[ApiClient], Any],
    key: str | None = "sk-a-key",
) -> tuple[Any, Log]:
    server = serve(handler)
    target = Target(
        integration="ai",
        connection=definition.key,
        origin=netguard.parse_origin(server.url, allow_http=True),
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options={},
        secrets={"api_key": key} if key else {},
    )
    log = Log()

    async def go() -> Any:
        async with ApiClient(target, log, HOME_NETWORK_AND_LOOPBACK) as client:
            return await action(client)

    return asyncio.run(go()), log


class TestAsking:
    def test_anthropic_gets_its_key_and_version_and_the_schema_in_its_own_place(
        self, serve: Serve
    ) -> None:
        stand_in = stand_ins.anthropic("sk-a-key", {"claude-haiku-5-5"})
        seen: list[Seen] = []

        def handler(request: Seen) -> Answer:
            seen.append(request)
            return stand_in(request)

        answer, log = ask(
            serve,
            catalog.ANTHROPIC,
            handler,
            lambda client: wire.complete(
                client,
                catalog.ANTHROPIC,
                "claude-haiku-5-5",
                "sk-a-key",
                system="Be brief.",
                prompt="Hello",
                schema=SCHEMA,
                max_tokens=50,
            ),
        )

        assert answer == Completion("OK", 14, 1, 0, truncated=True)
        (request,) = seen
        assert request.path == "/v1/messages"
        assert request.headers["x-api-key"] == "sk-a-key"
        assert request.headers["anthropic-version"] == wire.ANTHROPIC_VERSION
        assert json.loads(request.body) == {
            "model": "claude-haiku-5-5",
            "max_tokens": 50,
            "system": "Be brief.",
            "messages": [{"role": "user", "content": "Hello"}],
            "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
        }
        assert "sk-a-key" not in json.dumps([call.__dict__ for call in log.calls], default=str)

    def test_openai_gets_a_bearer_key_a_schema_that_is_strict_and_room_to_think(
        self, serve: Serve
    ) -> None:
        stand_in = stand_ins.openai("sk-a-key", {"gpt-6-luna"})
        seen: list[Seen] = []

        def handler(request: Seen) -> Answer:
            seen.append(request)
            return stand_in(request)

        answer, _ = ask(
            serve,
            catalog.OPENAI,
            handler,
            lambda client: wire.complete(
                client,
                catalog.OPENAI,
                "gpt-6-luna",
                "sk-a-key",
                system="Be brief.",
                prompt="Hello",
                schema=SCHEMA,
                max_tokens=1,
            ),
        )

        assert answer == Completion("OK", 16, 2)
        (request,) = seen
        assert request.path == "/v1/responses"
        assert request.headers["authorization"] == "Bearer sk-a-key"
        assert json.loads(request.body) == {
            "model": "gpt-6-luna",
            "instructions": "Be brief.",
            "input": "Hello",
            "max_output_tokens": 1 + 4096,
            "reasoning": {"effort": "low"},
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "answer",
                    "strict": True,
                    "schema": SCHEMA,
                }
            },
        }

    def test_openai_wont_take_fewer_than_16_output_tokens_from_a_model_that_does_not_think(
        self, serve: Serve
    ) -> None:
        stand_in = stand_ins.openai("sk-a-key", {"gpt-5.4-mini"})
        seen: list[Seen] = []

        def handler(request: Seen) -> Answer:
            seen.append(request)
            return stand_in(request)

        ask(
            serve,
            catalog.OPENAI,
            handler,
            lambda client: wire.complete(
                client,
                catalog.OPENAI,
                "gpt-5.4-mini",
                "sk-a-key",
                system="s",
                prompt="p",
                max_tokens=1,
            ),
        )

        body = json.loads(seen[0].body)
        assert body["max_output_tokens"] == 16
        assert "reasoning" not in body

    def test_openai_is_asked_for_the_least_it_takes_from_a_model_that_is_not_in_the_list(
        self, serve: Serve
    ) -> None:
        stand_in = stand_ins.openai("sk-a-key", {"gpt-next"})
        seen: list[Seen] = []

        def handler(request: Seen) -> Answer:
            seen.append(request)
            return stand_in(request)

        ask(
            serve,
            catalog.OPENAI,
            handler,
            lambda client: wire.complete(
                client,
                catalog.OPENAI,
                "gpt-next",
                "sk-a-key",
                system=LONG_SYSTEM,
                prompt="p",
                max_tokens=1,
                cache_key="aresgate",
            ),
        )

        assert json.loads(seen[0].body) == {
            "model": "gpt-next",
            "instructions": LONG_SYSTEM,
            "input": "p",
            "max_output_tokens": 16,
            "store": False,
        }

    def test_openai_is_asked_without_a_schema_for_plain_text(self, serve: Serve) -> None:
        seen: list[Seen] = []
        stand_in = stand_ins.openai("sk-a-key", {"gpt-6-luna"})

        def handler(request: Seen) -> Answer:
            seen.append(request)
            return stand_in(request)

        ask(
            serve,
            catalog.OPENAI,
            handler,
            lambda client: wire.complete(
                client,
                catalog.OPENAI,
                "gpt-6-luna",
                "sk-a-key",
                system="s",
                prompt="p",
                max_tokens=300,
            ),
        )

        body = json.loads(seen[0].body)
        assert "text" not in body
        assert body["max_output_tokens"] == 300 + 4096

    def test_an_ollama_gets_the_schema_as_its_format_and_no_key_at_home(self, serve: Serve) -> None:
        seen: list[Seen] = []
        stand_in = stand_ins.ollama("", {"llama3.2:3b"})

        def handler(request: Seen) -> Answer:
            seen.append(request)
            return stand_in(request)

        answer, _ = ask(
            serve,
            catalog.OLLAMA,
            handler,
            lambda client: wire.complete(
                client,
                catalog.OLLAMA,
                "llama3.2:3b",
                None,
                system="Be brief.",
                prompt="Hello",
                schema=SCHEMA,
                max_tokens=7,
            ),
            key=None,
        )

        assert answer == Completion("OK", 12, 1, 0, truncated=True)
        (request,) = seen
        assert "authorization" not in request.headers
        assert json.loads(request.body) == {
            "model": "llama3.2:3b",
            "messages": [
                {"role": "system", "content": "Be brief."},
                {"role": "user", "content": "Hello"},
            ],
            "stream": False,
            "options": {"temperature": 0, "num_predict": 7},
            "format": SCHEMA,
        }

    def test_ollamas_cloud_gets_a_bearer_key(self, serve: Serve) -> None:
        seen: list[Seen] = []
        stand_in = stand_ins.ollama("sk-a-key", {"gemma4:31b"})

        def handler(request: Seen) -> Answer:
            seen.append(request)
            return stand_in(request)

        ask(
            serve,
            catalog.OLLAMA_CLOUD,
            handler,
            lambda client: wire.complete(
                client, catalog.OLLAMA_CLOUD, "gemma4:31b", "sk-a-key", system="s", prompt="p"
            ),
        )

        assert seen[0].headers["authorization"] == "Bearer sk-a-key"
        assert "format" not in json.loads(seen[0].body)

    def test_a_refusal_to_answer_is_an_answer_that_says_so(self, serve: Serve) -> None:
        def handler(request: Seen) -> Answer:
            return Answer(401, "{}")

        with pytest.raises(AiFailed, match="didn't accept the API key"):
            ask(
                serve,
                catalog.ANTHROPIC,
                handler,
                lambda client: wire.complete(
                    client, catalog.ANTHROPIC, "m", "k", system="s", prompt="p"
                ),
            )


class TestReadingAnswers:
    def read(self, definition: ProviderDef, body: object, status: int = 200) -> Completion:
        return wire.read_completion(definition, Reply(status, json.dumps(body)))

    def test_anthropic_joins_its_text_blocks_and_counts_its_tokens(self) -> None:
        answer = self.read(
            catalog.ANTHROPIC,
            {
                "content": [
                    {"type": "thinking", "thinking": "hm"},
                    {"type": "text", "text": '{"a":'},
                    {"type": "text", "text": "1}"},
                    {"type": "text", "text": ""},
                ],
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 30,
                    "output_tokens": 9,
                    "cache_read_input_tokens": 20,
                    "cache_creation_input_tokens": 6,
                },
            },
        )

        # Anthropic's input_tokens leaves out what was read from the cache and what was written to
        # it, so the whole is the three together.
        assert answer == Completion('{"a":1}', 56, 9, 20, 6, truncated=False)

    def test_anthropic_that_declines_says_so(self) -> None:
        with pytest.raises(AiFailed, match="declined"):
            self.read(catalog.ANTHROPIC, {"content": [], "stop_reason": "refusal"})

    def test_anthropic_that_was_cut_short_says_the_answer_may_be_incomplete(self) -> None:
        answer = self.read(
            catalog.ANTHROPIC,
            {"content": [{"type": "text", "text": "{"}], "stop_reason": "max_tokens"},
        )

        assert answer.truncated
        assert (answer.input_tokens, answer.output_tokens) == (0, 0)

    def test_openai_reads_the_text_of_its_messages_and_counts_the_tokens(self) -> None:
        body: dict[str, object] = {
            "status": "completed",
            "output": [
                {"type": "reasoning", "summary": []},
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "He"},
                        {"type": "output_text", "text": "llo"},
                    ],
                },
            ],
            "usage": {
                "input_tokens": 50,
                "output_tokens": 7,
                "input_tokens_details": {"cached_tokens": 32},
            },
        }
        answer = self.read(catalog.OPENAI, body)

        assert answer == Completion("Hello", 50, 7, 32, truncated=False)

    def test_openai_that_declines_says_so(self) -> None:
        with pytest.raises(AiFailed, match="declined"):
            self.read(
                catalog.OPENAI,
                {
                    "output": [
                        {"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}
                    ]
                },
            )

    def test_openai_that_could_not_answer_says_so_without_quoting_it(self) -> None:
        with pytest.raises(AiFailed) as caught:
            self.read(catalog.OPENAI, {"error": {"message": "secret detail"}})

        assert "secret detail" not in str(caught.value)

    def test_openai_that_ran_out_of_tokens_has_nothing_to_read_and_says_so(self) -> None:
        answer = self.read(
            catalog.OPENAI,
            {
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "output": [],
                "usage": {"input_tokens": 9, "output_tokens": 16},
            },
        )

        assert answer == Completion("", 9, 16, 0, truncated=True)

    def test_an_ollama_gives_its_message_and_how_many_tokens_it_counted(self) -> None:
        answer = self.read(
            catalog.OLLAMA,
            {
                "message": {"role": "assistant", "content": "hi"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 11,
                "eval_count": 3,
            },
        )

        assert answer == Completion("hi", 11, 3, 0, truncated=False)

    def test_an_ollama_that_stopped_at_the_limit_says_so(self) -> None:
        answer = self.read(catalog.OLLAMA, {"message": {"content": "hi"}, "done_reason": "length"})

        assert answer.truncated

    @pytest.mark.parametrize("definition", catalog.PROVIDERS)
    def test_something_that_is_not_an_object_is_not_understood(
        self, definition: ProviderDef
    ) -> None:
        for text in ("[]", "nonsense", '"hi"'):
            reply = Reply(200, text)

            with pytest.raises(AiFailed, match="not in a form AresGate understands"):
                wire.read_completion(definition, reply)

    @pytest.mark.parametrize("definition", catalog.PROVIDERS)
    def test_nonsense_in_the_numbers_counts_as_none(self, definition: ProviderDef) -> None:
        body: dict[str, object] = {
            "usage": {"input_tokens": True, "output_tokens": "9"},
            "prompt_eval_count": -4,
            "eval_count": 1.5,
        }

        answer = self.read(definition, body)

        assert (answer.input_tokens, answer.output_tokens) == (0, 0)


class TestExplaining:
    @pytest.mark.parametrize("status", [401, 403])
    def test_a_key_that_is_not_accepted(self, status: int) -> None:
        message = wire.explain(status, catalog.OPENAI)

        assert message.startswith("OpenAI didn't accept the API key")
        assert str(status) in message

    def test_a_model_that_is_not_known(self) -> None:
        assert "Choose another model" in wire.explain(404, catalog.ANTHROPIC)
        assert "Fetch the models" in wire.explain(404, catalog.OLLAMA)

    def test_too_many_requests_or_no_credit(self) -> None:
        assert "out of credit" in wire.explain(429, catalog.OPENAI)

    @pytest.mark.parametrize("status", [400, 413, 422])
    def test_a_request_that_was_not_accepted(self, status: int) -> None:
        assert "didn't accept the request" in wire.explain(status, catalog.ANTHROPIC)

    def test_a_problem_at_the_provider(self) -> None:
        assert "problem of its own" in wire.explain(503, catalog.ANTHROPIC)

    def test_anything_else(self) -> None:
        assert "HTTP 418" in wire.explain(418, catalog.ANTHROPIC)


class TestFindingModels:
    def list_from(self, serve: Serve, body: object, status: int = 200) -> list[wire.FoundModel]:
        found, _ = ask(
            serve,
            catalog.OLLAMA,
            lambda seen: Answer(status, json.dumps(body)),
            lambda client: wire.list_models(client, catalog.OLLAMA, None),
            key=None,
        )
        return found  # type: ignore[no-any-return]

    def test_the_models_come_with_their_size_and_family_by_name(self, serve: Serve) -> None:
        found = self.list_from(
            serve,
            {
                "models": [
                    {
                        "name": "qwen3:8b",
                        "size": 5_200_000_000,
                        "details": {
                            "family": "qwen3",
                            "parameter_size": "8.2B",
                            "quantization_level": "Q4_K_M",
                        },
                    },
                    {"model": "llama3.2:3b"},
                    {"name": "qwen3:8b"},
                ]
            },
        )

        assert found == [
            wire.FoundModel("llama3.2:3b", None, None, None, None),
            wire.FoundModel("qwen3:8b", 5_200_000_000, "qwen3", "8.2B", "Q4_K_M"),
        ]

    def test_what_is_not_a_model_is_left_out(self, serve: Serve) -> None:
        found = self.list_from(
            serve,
            {
                "models": [
                    "text",
                    {"name": "has a space"},
                    {"name": ""},
                    {"name": "ok:1b", "size": True},
                    {"name": "big:1b", "size": -1},
                ]
            },
        )

        assert found == [
            wire.FoundModel("big:1b", None, None, None, None),
            wire.FoundModel("ok:1b", None, None, None, None),
        ]

    def test_a_list_that_is_not_one_is_empty(self, serve: Serve) -> None:
        assert self.list_from(serve, {"models": "many"}) == []

    def test_no_more_than_500_are_kept(self, serve: Serve) -> None:
        body = {"models": [{"name": f"m{index:04d}:1b"} for index in range(wire.MAX_MODELS + 20)]}

        assert len(self.list_from(serve, body)) == wire.MAX_MODELS

    def test_an_answer_that_is_not_an_object_is_not_understood(self, serve: Serve) -> None:
        with pytest.raises(AiFailed, match="not in a form AresGate understands"):
            self.list_from(serve, [])

    def test_a_refusal_is_explained(self, serve: Serve) -> None:
        with pytest.raises(AiFailed, match="didn't accept the API key"):
            self.list_from(serve, {}, 401)


class TestCaching:
    """What is sent so that the start of a prompt that is the same every time is cached, and what
    is counted when it was."""

    def body(
        self,
        serve: Serve,
        definition: ProviderDef,
        model: str,
        system: str,
        *,
        cache_key: str | None = None,
    ) -> dict[str, Any]:
        handler = (
            stand_ins.anthropic("sk-a-key", {model})
            if definition is catalog.ANTHROPIC
            else stand_ins.openai("sk-a-key", {model})
        )
        seen: list[Seen] = []

        def record(request: Seen) -> Answer:
            seen.append(request)
            return handler(request)

        ask(
            serve,
            definition,
            record,
            lambda client: wire.complete(
                client,
                definition,
                model,
                "sk-a-key",
                system=system,
                prompt="The incident",
                cache_key=cache_key,
            ),
        )
        return json.loads(seen[0].body)

    @pytest.mark.parametrize("model", [model.id for model in catalog.ANTHROPIC.models])
    def test_a_claude_is_told_where_the_fixed_start_of_the_prompt_ends(
        self, serve: Serve, model: str
    ) -> None:
        body = self.body(serve, catalog.ANTHROPIC, model, LONG_SYSTEM)

        assert body["system"] == [
            {"type": "text", "text": LONG_SYSTEM, "cache_control": {"type": "ephemeral"}}
        ]
        assert body["messages"] == [{"role": "user", "content": "The incident"}]

    def test_a_start_too_short_to_be_cached_is_not_marked(self, serve: Serve) -> None:
        # 2,043 characters is 510 tokens by the rule of thumb, two short of the 512 Claude needs.
        body = self.body(serve, catalog.ANTHROPIC, "claude-haiku-5-5", "x" * 2043)

        assert body["system"] == "x" * 2043

    def test_a_claude_not_in_the_list_is_not_marked(self, serve: Serve) -> None:
        body = self.body(serve, catalog.ANTHROPIC, "claude-next", LONG_SYSTEM)

        assert body["system"] == LONG_SYSTEM

    @pytest.mark.parametrize(
        "model", [model.id for model in catalog.OPENAI.models if model.id.startswith("gpt-6")]
    )
    def test_a_gpt_6_gets_an_explicit_breakpoint_after_the_fixed_start_in_a_developer_message(
        self, serve: Serve, model: str
    ) -> None:
        body = self.body(serve, catalog.OPENAI, model, LONG_SYSTEM)

        assert body["prompt_cache_options"] == {"mode": "explicit", "ttl": "30m"}
        assert "instructions" not in body
        assert body["input"] == [
            {
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": LONG_SYSTEM,
                        "prompt_cache_breakpoint": {"mode": "explicit"},
                    }
                ],
            },
            {"role": "user", "content": "The incident"},
        ]
        assert body["reasoning"] == {"effort": "low"}

    def test_a_gpt_6_with_a_short_start_is_sent_the_plain_way(self, serve: Serve) -> None:
        body = self.body(serve, catalog.OPENAI, "gpt-6-luna", "Be brief.")

        assert "prompt_cache_options" not in body
        assert (body["instructions"], body["input"]) == ("Be brief.", "The incident")

    @pytest.mark.parametrize("model", ["gpt-5.4-mini", "gpt-5.4-nano"])
    def test_an_older_gpt_caches_by_itself_and_is_helped_to_find_the_last_request(
        self, serve: Serve, model: str
    ) -> None:
        body = self.body(serve, catalog.OPENAI, model, LONG_SYSTEM, cache_key="aresgate-triage")

        assert body["prompt_cache_key"] == "aresgate-triage"
        assert "prompt_cache_options" not in body
        assert (body["instructions"], body["input"]) == (LONG_SYSTEM, "The incident")

    def test_an_older_gpt_without_a_key_is_left_to_find_it_itself(self, serve: Serve) -> None:
        body = self.body(serve, catalog.OPENAI, "gpt-5.4-mini", LONG_SYSTEM)

        assert "prompt_cache_key" not in body

    def test_a_gpt_6_has_no_use_for_a_key(self, serve: Serve) -> None:
        body = self.body(serve, catalog.OPENAI, "gpt-6-luna", LONG_SYSTEM, cache_key="aresgate")

        assert "prompt_cache_key" not in body

    def test_anthropic_counts_what_it_read_and_what_it_wrote_on_top_of_what_it_was_sent(
        self,
    ) -> None:
        reply = Reply(
            200,
            json.dumps(
                {
                    "content": [{"type": "text", "text": "x"}],
                    "usage": {
                        "input_tokens": 50,
                        "cache_read_input_tokens": 1800,
                        "cache_creation_input_tokens": 248,
                        "output_tokens": 503,
                    },
                }
            ),
        )

        answer = wire.read_completion(catalog.ANTHROPIC, reply)

        assert (answer.input_tokens, answer.cached_tokens, answer.cache_write_tokens) == (
            2098,
            1800,
            248,
        )

    def test_openai_counts_the_cache_reads_and_writes_and_the_thinking(self) -> None:
        reply = Reply(
            200,
            json.dumps(
                {
                    "output": [
                        {"type": "message", "content": [{"type": "output_text", "text": "x"}]}
                    ],
                    "usage": {
                        "input_tokens": 6000,
                        "input_tokens_details": {
                            "cached_tokens": 2048,
                            "cache_write_tokens": 1500,
                            "cache_write_tokens_details": {
                                "ttl_30m_tokens": 1500,
                                "ttl_12h_tokens": 0,
                            },
                        },
                        "output_tokens": 1186,
                        "output_tokens_details": {"reasoning_tokens": 1024},
                    },
                }
            ),
        )

        answer = wire.read_completion(catalog.OPENAI, reply)

        assert answer.input_tokens == 6000
        assert (answer.cached_tokens, answer.cache_write_tokens) == (2048, 1500)
        assert (answer.output_tokens, answer.reasoning_tokens) == (1186, 1024)
