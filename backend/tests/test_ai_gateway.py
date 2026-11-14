"""Asking an AI provider: what it is shown, what is kept of it, and every way it can not happen.
The providers are servers on this machine that answer the way each one's API does."""

import ast
import asyncio
import json
from collections.abc import Callable, Sequence
from decimal import Decimal
from pathlib import Path

import anyio.to_thread
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import catalog, gateway, redaction, service, wire
from app.ai.gateway import Answer, Context, Prepared, Question, Unavailable
from app.ai.redaction import Level, Redactor
from app.config import Settings
from app.integrations.client import Call
from app.models import AiCall
from app.security import credential_store
from app.security.credential_store import Kind
from tests.stubs import Answer as Reply
from tests.stubs import Handler, Seen, Serve
from tests.test_ai_service import KEY, NOW, saved

DEVICE = "192.168.1.20"
ATTACKER = "203.0.113.5"


class Log:
    def __init__(self) -> None:
        self.calls: list[Call] = []

    async def __call__(self, call: Call) -> None:
        self.calls.append(call)


def anthropic_says(text: str, tokens: tuple[int, int] = (1000, 200)) -> Handler:
    """Anthropic's Messages API, answering with a text and counting these tokens."""

    def handle(seen: Seen) -> Reply:
        if seen.headers.get("x-api-key") != KEY:
            return Reply(status=401, body=json.dumps({"error": {"type": "authentication_error"}}))
        return Reply(
            body=json.dumps(
                {
                    "content": [{"type": "text", "text": text}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": tokens[0], "output_tokens": tokens[1]},
                }
            ),
            headers={"Content-Type": "application/json"},
        )

    return handle


def turned_on(session: Session, provider: str, redaction_level: str = "balanced") -> None:
    chosen = service.usage(session, NOW)
    chosen.enabled = True
    chosen.provider = provider
    chosen.redaction = redaction_level
    session.commit()


def context(
    settings: Settings, log: Log, url: str | None = None, key: str = "anthropic"
) -> Context:
    from app.integrations import netguard

    return Context(
        settings=settings,
        recorder=log,
        hosted=netguard.PUBLIC_INTERNET_AND_LOOPBACK,
        local=netguard.HOME_NETWORK_AND_LOOPBACK,
        origins={key: url} if url else {},
    )


def scanned(redactor: Redactor) -> str:
    return (
        f"{redactor.address(DEVICE)} ({redactor.name('Sam')}) was scanned by "
        f"{redactor.address(ATTACKER)}.\n"
        + redactor.data("log", f"{DEVICE} <- {ATTACKER} api_key=abcdef123456")
    )


def question(
    build: Callable[[Redactor], str] = scanned,
    about: str | None = "incident 12",
    own: Sequence[str] = (),
    names: Sequence[str] = (),
    users: Sequence[str] = (),
) -> Question:
    return Question(
        purpose="triage",
        system="Judge the incident.",
        build=build,
        about=about,
        own=own,
        names=names,
        users=users,
    )


def asked(
    session: Session, settings: Settings, server_url: str, ask: Question | None = None
) -> tuple[Answer | Unavailable, Log]:
    log = Log()
    ask = ask or question()
    prepared = gateway.prepare(session, context(settings, log, server_url), ask, NOW)
    if isinstance(prepared, Unavailable):
        return prepared, log
    sent = asyncio.run(gateway.send(prepared, context(settings, log, server_url)))
    return gateway.record(session, prepared, sent, NOW), log


class TestWhenNothingCanBeAsked:
    def test_ai_that_is_off_says_so(self, session: Session, settings: Settings) -> None:
        saved(session, settings, catalog.ANTHROPIC)

        said = gateway.prepare(session, context(settings, Log()), question(), NOW)

        assert said == Unavailable("AI is turned off. Turn it on under Settings > AI to use it.")
        assert session.scalars(select(AiCall)).all() == []

    def test_ai_that_is_on_without_a_provider_says_so(
        self, session: Session, settings: Settings
    ) -> None:
        service.usage(session, NOW).enabled = True
        session.commit()

        said = gateway.prepare(session, context(settings, Log()), question(), NOW)

        assert isinstance(said, Unavailable)
        assert said.reason.startswith("No AI provider is chosen.")

    def test_a_provider_without_a_model_says_so(self, session: Session, settings: Settings) -> None:
        saved(session, settings, catalog.OLLAMA, model="")
        turned_on(session, "ollama")

        said = gateway.prepare(session, context(settings, Log()), question(), NOW)

        assert isinstance(said, Unavailable)
        assert said.reason.startswith("The AI provider has no model yet.")

    def test_a_provider_whose_key_is_gone_says_so(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")
        credential_store.remove(session, Kind.AI_PROVIDER, "anthropic", service.API_KEY)
        session.commit()

        said = gateway.prepare(session, context(settings, Log()), question(), NOW)

        assert said == Unavailable("The API key is missing or can't be opened. Enter it again.")

    def test_a_provider_the_catalog_no_longer_knows_says_so(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")

        def unknown(key: str) -> None:
            return None

        monkeypatch.setattr(gateway, "provider_def", unknown)

        said = gateway.prepare(session, context(settings, Log()), question(), NOW)

        assert isinstance(said, Unavailable)
        assert said.reason.startswith("The AI provider that was chosen is gone.")

    def test_ask_stops_there_too(self, session: Session, settings: Settings) -> None:
        said = gateway.ask(session, context(settings, Log()), question(), NOW)

        assert isinstance(said, Unavailable)


class TestWhatTheProviderIsShown:
    def test_the_prompt_has_stand_ins_and_no_secrets(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(anthropic_says("ok"))
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")

        answer, _ = asked(session, settings, server.url)

        assert isinstance(answer, Answer)
        body = json.loads(server.seen[0].body)
        sent = json.dumps(body)
        assert DEVICE not in sent
        assert "Sam" not in sent
        assert "abcdef123456" not in sent
        assert KEY not in sent
        assert ATTACKER in sent
        assert "HOST_" in sent
        assert redaction.GLOSSARY in sent
        assert redaction.DATA_NOTICE in sent
        assert "Judge the incident." in sent

    def test_strict_hides_the_attacker_too(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(anthropic_says("ok"))
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic", "strict")

        asked(session, settings, server.url)

        sent = json.dumps(json.loads(server.seen[0].body))
        assert ATTACKER not in sent
        assert "EXT_" in sent

    def test_the_key_is_taken_out_of_the_prompt_even_if_a_builder_puts_it_in(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(anthropic_says("ok"))
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")

        asked(session, settings, server.url, question(build=lambda redactor: f"key {KEY} used"))

        assert KEY not in json.dumps(json.loads(server.seen[0].body))

    def test_the_home_networks_own_names_are_stand_ins_in_free_text(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(anthropic_says("ok"))
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")

        ask = question(
            build=lambda redactor: redactor.text("Garage-Cam from 198.51.100.7 by garagecam-user"),
            own=["198.51.100.7"],
            names=["Garage-Cam"],
            users=["garagecam-user"],
        )

        asked(session, settings, server.url, ask)

        sent = json.dumps(json.loads(server.seen[0].body))
        assert "Garage-Cam" not in sent
        assert "198.51.100.7" not in sent
        assert "garagecam-user" not in sent
        assert "WAN_" in sent

    def test_only_a_provider_on_the_owners_network_is_shown_everything(self) -> None:
        assert gateway.effective_level(catalog.OLLAMA, "local") is Level.LOCAL
        assert gateway.effective_level(catalog.OLLAMA_CLOUD, "local") is Level.BALANCED
        assert gateway.effective_level(catalog.ANTHROPIC, "local") is Level.BALANCED
        assert gateway.effective_level(catalog.ANTHROPIC, "strict") is Level.STRICT

    def test_the_stand_ins_are_explained_only_where_there_are_any(self) -> None:
        assert redaction.GLOSSARY in gateway.system_for(Level.BALANCED, "Do this.")
        assert redaction.GLOSSARY not in gateway.system_for(Level.LOCAL, "Do this.")
        assert gateway.system_for(Level.LOCAL, "Do this.").endswith("Do this.")

    def test_an_ollama_on_the_owners_network_is_shown_everything_when_chosen(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(
            lambda seen: Reply(
                body=json.dumps(
                    {
                        "message": {"content": f"{DEVICE} looks fine"},
                        "done": True,
                        "prompt_eval_count": 50,
                        "eval_count": 5,
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
        )
        saved(session, settings, catalog.OLLAMA, model="qwen3:8b", base_url=server.url)
        turned_on(session, "ollama", "local")

        answer, _ = asked(
            session, settings, "", question(build=lambda redactor: f"look at {DEVICE}")
        )

        assert isinstance(answer, Answer)
        assert DEVICE in json.dumps(json.loads(server.seen[0].body))
        call = session.scalars(select(AiCall)).one()
        assert (call.level, call.cost_micros) == ("local", 0)


class TestWhatIsKept:
    def test_an_answer_is_recorded_with_what_was_seen_and_counted(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(anthropic_says("HOST_1 was scanned."))
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")

        answer, log = asked(session, settings, server.url)

        call = session.scalars(select(AiCall)).one()
        assert isinstance(answer, Answer)
        assert answer.call_id == call.id
        assert (call.purpose, call.about, call.provider) == ("triage", "incident 12", "anthropic")
        assert (call.model, call.level, call.ok) == ("claude-haiku-5-5", "balanced", True)
        assert (call.input_tokens, call.output_tokens) == (1000, 200)
        assert (call.cached_tokens, call.cache_write_tokens, call.reasoning_tokens) == (0, 0, 0)
        assert call.truncated is False
        assert call.error is None
        assert call.duration_ms >= 0
        assert call.occurred_at == NOW
        assert DEVICE not in call.prompt
        assert "HOST_" in call.prompt
        assert call.answer == "HOST_1 was scanned."
        # 1000 tokens in at $0.10 and 200 out at $0.50 per million: $0.0002.
        assert call.cost_micros == 200
        assert [(c.integration, c.path) for c in log.calls] == [("ai", "/v1/messages")]

    def test_the_answer_comes_back_with_the_real_values(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        written = {"text": ""}

        def says(seen: Seen) -> Reply:
            return anthropic_says(written["text"])(seen)

        server = serve(says)
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")
        where = context(settings, Log(), server.url)
        prepared = gateway.prepare(session, where, question(), NOW)
        assert isinstance(prepared, Prepared)
        written["text"] = f"{prepared.redactor.address(DEVICE)} is Sam's. {ATTACKER} did it."
        sent = asyncio.run(gateway.send(prepared, where))

        answer = gateway.record(session, prepared, sent, NOW)

        assert isinstance(answer, Answer)
        assert answer.text == f"{DEVICE} is Sam's. {ATTACKER} did it."
        assert answer.ok
        assert answer.reason is None
        assert not answer.truncated
        assert session.scalars(select(AiCall)).one().answer.startswith("HOST_")  # type: ignore[union-attr]

    def test_the_providers_status_follows_the_real_requests(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(anthropic_says("ok"))
        row = saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")

        asked(session, settings, server.url)

        assert (row.last_attempt_at, row.last_success_at, row.last_error) == (NOW, NOW, None)

    def test_a_refused_key_is_recorded_as_a_failed_call_and_a_problem_with_the_provider(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(anthropic_says("ok"))
        row = saved(session, settings, catalog.ANTHROPIC, api_key="another-key-0123456789")
        turned_on(session, "anthropic")

        answer, _ = asked(session, settings, server.url)

        call = session.scalars(select(AiCall)).one()
        assert isinstance(answer, Answer)
        assert not answer.ok
        assert answer.text == ""
        assert answer.reason is not None
        assert answer.reason.startswith("Anthropic didn't accept the API key")
        assert (call.ok, call.input_tokens, call.cost_micros, call.answer) == (False, 0, None, None)
        assert call.error == answer.reason
        assert row.last_error == answer.reason
        assert "another-key" not in call.prompt + (call.error or "")

    def test_a_provider_that_cannot_be_reached_is_a_failed_call(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(anthropic_says("ok"))
        url = server.url
        server.stop()
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")

        answer, _ = asked(session, settings, url)

        assert isinstance(answer, Answer)
        assert not answer.ok
        assert session.scalars(select(AiCall)).one().ok is False

    def test_a_long_about_and_a_missing_one_are_kept_short_or_empty(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(anthropic_says("ok"))
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")

        asked(session, settings, server.url, question(about="x" * 500))
        asked(session, settings, server.url, question(about=None))

        abouts = [call.about for call in session.scalars(select(AiCall).order_by(AiCall.id))]
        assert abouts == ["x" * gateway.MAX_ABOUT, None]

    def test_an_answer_that_ran_out_of_room_is_marked(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(
            lambda seen: Reply(
                body=json.dumps(
                    {
                        "content": [{"type": "text", "text": "cut off"}],
                        "stop_reason": "max_tokens",
                        "usage": {"input_tokens": 5, "output_tokens": 5},
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
        )
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")

        answer, _ = asked(session, settings, server.url)

        assert isinstance(answer, Answer)
        assert answer.truncated
        assert session.scalars(select(AiCall)).one().truncated

    def test_a_provider_that_was_forgotten_meanwhile_still_gets_its_call_recorded(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(anthropic_says("ok"))
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")
        prepared = gateway.prepare(session, context(settings, Log(), server.url), question(), NOW)
        assert isinstance(prepared, Prepared)
        sent = asyncio.run(gateway.send(prepared, context(settings, Log(), server.url)))
        service.remove(session, catalog.ANTHROPIC, NOW)
        session.commit()

        answer = gateway.record(session, prepared, sent, NOW)

        assert isinstance(answer, Answer)
        assert answer.ok
        assert session.scalars(select(AiCall)).one().ok

    def test_recording_without_a_time_uses_the_time_it_is(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(anthropic_says("ok"))
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")
        where = context(settings, Log(), server.url)
        prepared = gateway.prepare(session, where, question(), NOW)
        assert isinstance(prepared, Prepared)
        sent = asyncio.run(gateway.send(prepared, where))

        gateway.record(session, prepared, sent)

        assert session.scalars(select(AiCall)).one().occurred_at > NOW

    def test_a_call_is_asked_and_recorded_in_one_go_from_one_of_the_apis_threads(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(anthropic_says("done"))
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")
        where = context(settings, Log(), server.url)

        async def from_a_thread() -> Answer | Unavailable:
            return await anyio.to_thread.run_sync(gateway.ask, session, where, question(), None)

        answer = anyio.run(from_a_thread)

        assert isinstance(answer, Answer)
        assert answer.text == "done"
        assert (answer.provider, answer.model) == ("anthropic", catalog.ANTHROPIC.default_model)
        assert session.scalars(select(AiCall)).one().answer == "done"


class TestWhatItCosts:
    def completion(self, cached: int = 0, written: int = 0) -> wire.Completion:
        return wire.Completion(
            text="x",
            input_tokens=1000,
            output_tokens=100,
            cached_tokens=cached,
            cache_write_tokens=written,
        )

    def test_a_known_model_costs_what_the_catalog_says(self) -> None:
        price = catalog.ANTHROPIC.model("claude-haiku-5-5")
        assert price is not None
        cost = price.price.cost(1000, 100, 400, 100)

        assert gateway.cost_micros(
            catalog.ANTHROPIC,
            "claude-haiku-5-5",
            self.completion(cached=400, written=100),
        ) == int(cost * 1_000_000 + Decimal("0.5"))

    def test_a_model_without_a_known_price_has_no_cost(self) -> None:
        assert gateway.cost_micros(catalog.OLLAMA_CLOUD, "gpt-oss:120b", self.completion()) is None

    def test_a_model_on_the_owners_own_computer_costs_nothing(self) -> None:
        assert gateway.cost_micros(catalog.OLLAMA, "qwen3:8b", self.completion()) == 0


class TestWhereProvidersAre:
    def test_a_local_provider_may_be_on_the_home_network_and_a_hosted_one_on_the_internet(
        self, settings: Settings
    ) -> None:
        here = Context(settings=settings, recorder=Log())

        assert here.policy_for(catalog.OLLAMA) is here.local
        assert here.policy_for(catalog.ANTHROPIC) is here.hosted
        assert here.policy_for(catalog.OLLAMA_CLOUD) is here.hosted

    def test_the_worker_reaches_an_ollama_where_the_container_says(
        self, settings: Settings
    ) -> None:
        outside = gateway.context_for_worker(settings, Log())
        inside = gateway.context_for_worker(
            settings.model_copy(update={"in_container": True}), Log()
        )

        assert outside.local is not inside.local
        assert outside.origins == {}


def test_no_one_but_the_gateway_and_the_connection_test_asks_a_model() -> None:
    """The promises of the gateway only hold if nothing goes around it."""
    asking: set[str] = set()
    for path in Path(gateway.__file__).parents[1].rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("complete", "stream")
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "wire"
            ):
                asking.add(path.name)

    assert asking == {"gateway.py", "service.py"}
