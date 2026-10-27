import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.ai import catalog, service, wire
from app.ai.service import API_KEY, Incomplete, Submission
from app.config import Settings
from app.integrations import netguard
from app.integrations.client import Call, Target
from app.integrations.netguard import (
    HOME_NETWORK_AND_LOOPBACK,
    PUBLIC_INTERNET_AND_LOOPBACK,
    AddressPolicy,
)
from app.integrations.probes import Verdict
from app.integrations.registry import SettingsError
from app.integrations.service import Status
from app.models import AiProvider, AiSettings
from app.security import credential_store
from app.security.credential_store import Kind
from app.security.vault import VaultError
from e2e import stand_ins
from tests.stubs import Serve

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
HOME_URL = "http://192.168.1.50:11434"
KEY = "sk-a-key-for-tests-0123456789"
HOME = HOME_NETWORK_AND_LOOPBACK


def saved(
    db: Session,
    settings: Settings,
    definition: catalog.ProviderDef,
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> AiProvider:
    """Sets a provider up the way the page would, with whatever is left out made up."""
    row = service.save(
        db,
        settings,
        HOME,
        definition,
        Submission(
            model=definition.default_model or "" if model is None else model,
            base_url=base_url or (None if definition.needs_key else HOME_URL),
            api_key=api_key or (KEY if definition.needs_key else None),
        ),
        NOW,
    )
    db.commit()
    return row


class Log:
    def __init__(self) -> None:
        self.calls: list[Call] = []

    async def __call__(self, call: Call) -> None:
        self.calls.append(call)


class TestSaving:
    def test_a_hosted_provider_keeps_its_model_and_seals_its_key(
        self, session: Session, settings: Settings
    ) -> None:
        row = saved(session, settings, catalog.ANTHROPIC)

        assert (row.provider, row.model, row.base_url) == ("anthropic", "claude-haiku-5-5", None)
        assert row.last_attempt_at is None
        assert service.key_saved(session, catalog.ANTHROPIC)
        assert not service.key_saved(session, catalog.OPENAI)
        assert (
            credential_store.reveal(session, settings, Kind.AI_PROVIDER, "anthropic", API_KEY)
            == KEY
        )

    def test_a_model_left_blank_is_the_default_one(
        self, session: Session, settings: Settings
    ) -> None:
        row = saved(session, settings, catalog.OPENAI, model="  ")

        assert row.model == "gpt-6-luna"

    def test_a_hosted_provider_takes_a_model_from_its_list_only(
        self, session: Session, settings: Settings
    ) -> None:
        submission = Submission(model="claude-nothing", api_key=KEY)

        with pytest.raises(SettingsError) as caught:
            service.save(session, settings, HOME, catalog.ANTHROPIC, submission, NOW)

        assert list(caught.value.problems) == ["model"]
        assert session.get(AiProvider, "anthropic") is None
        assert not service.key_saved(session, catalog.ANTHROPIC)

    @pytest.mark.parametrize("key", [None, "", "   "])
    def test_a_key_is_needed_the_first_time(
        self, session: Session, settings: Settings, key: str | None
    ) -> None:
        submission = Submission(model="gpt-6-luna", api_key=key)

        with pytest.raises(SettingsError) as caught:
            service.save(session, settings, HOME, catalog.OPENAI, submission, NOW)

        assert caught.value.problems == {API_KEY: "Enter the API key."}

    def test_a_key_left_out_keeps_the_one_that_is_kept_and_asks_for_a_new_test(
        self, session: Session, settings: Settings
    ) -> None:
        row = saved(session, settings, catalog.ANTHROPIC)
        row.last_attempt_at = NOW
        row.last_error = "It broke."

        again = service.save(
            session,
            settings,
            HOME,
            catalog.ANTHROPIC,
            Submission(model="claude-sonnet-5-5"),
            NOW + timedelta(minutes=1),
        )

        assert again is row
        assert row.model == "claude-sonnet-5-5"
        assert (row.last_attempt_at, row.last_error) == (None, None)
        assert row.updated_at == NOW + timedelta(minutes=1)
        assert (
            credential_store.reveal(session, settings, Kind.AI_PROVIDER, "anthropic", API_KEY)
            == KEY
        )

    @pytest.mark.parametrize("key", ["has a space", "tab\tin", "x" * (service.MAX_KEY + 1)])
    def test_a_key_that_cannot_be_one_is_refused(
        self, session: Session, settings: Settings, key: str
    ) -> None:
        submission = Submission(model="gpt-6-luna", api_key=key)

        with pytest.raises(SettingsError) as caught:
            service.save(session, settings, HOME, catalog.OPENAI, submission, NOW)

        assert list(caught.value.problems) == [API_KEY]
        assert key not in json.dumps(caught.value.problems)

    def test_a_new_key_replaces_the_old_one(self, session: Session, settings: Settings) -> None:
        saved(session, settings, catalog.OPENAI)

        saved(session, settings, catalog.OPENAI, api_key="  sk-the-new-key  ")

        assert (
            credential_store.reveal(session, settings, Kind.AI_PROVIDER, "openai", API_KEY)
            == "sk-the-new-key"
        )

    def test_an_ollama_at_home_has_an_address_and_may_have_no_model_yet(
        self, session: Session, settings: Settings
    ) -> None:
        row = saved(
            session, settings, catalog.OLLAMA, model="", base_url="http://192.168.1.50:11434/"
        )

        assert (row.model, row.base_url) == ("", "http://192.168.1.50:11434")

    @pytest.mark.parametrize(
        "address",
        ["", "nonsense", "http://8.8.8.8:11434", "ftp://192.168.1.2", "http://169.254.169.254"],
    )
    def test_an_ollama_at_home_must_be_somewhere_at_home(
        self, session: Session, settings: Settings, address: str
    ) -> None:
        submission = Submission(model="", base_url=address)

        with pytest.raises(SettingsError) as caught:
            service.save(session, settings, HOME, catalog.OLLAMA, submission, NOW)

        assert list(caught.value.problems) == ["base_url"]

    def test_an_ollama_at_home_takes_no_key_and_a_name_that_is_a_name(
        self, session: Session, settings: Settings
    ) -> None:
        submission = Submission(
            model="not a name", base_url="http://192.168.1.50:11434", api_key="sk-a-key"
        )

        with pytest.raises(SettingsError) as caught:
            service.save(session, settings, HOME, catalog.OLLAMA, submission, NOW)

        assert set(caught.value.problems) == {"model", API_KEY}

    def test_ollamas_cloud_starts_on_the_free_plan_and_keeps_the_plan_that_was_said(
        self, session: Session, settings: Settings
    ) -> None:
        first = saved(session, settings, catalog.OLLAMA_CLOUD, model="gpt-oss:20b")
        assert first.plan == "free"

        said = service.save(
            session,
            settings,
            HOME,
            catalog.OLLAMA_CLOUD,
            Submission(model="gpt-oss:20b", plan="paid"),
            NOW,
        )
        again = service.save(
            session, settings, HOME, catalog.OLLAMA_CLOUD, Submission(model="glm-5.3"), NOW
        )

        assert (said.plan, again.plan) == ("paid", "paid")

    def test_a_plan_is_free_or_paid_and_only_for_a_provider_that_has_them(
        self, session: Session, settings: Settings
    ) -> None:
        gold = Submission(model="", api_key=KEY, plan="gold")
        free_anthropic = Submission(model="claude-haiku-5-5", api_key=KEY, plan="free")

        with pytest.raises(SettingsError) as odd:
            service.save(session, settings, HOME, catalog.OLLAMA_CLOUD, gold, NOW)
        with pytest.raises(SettingsError) as none:
            service.save(session, settings, HOME, catalog.ANTHROPIC, free_anthropic, NOW)

        assert odd.value.problems == {"plan": "Choose free or paid."}
        assert none.value.problems == {"plan": "Anthropic has no plans."}
        assert saved(session, settings, catalog.ANTHROPIC).plan is None

    def test_ollamas_cloud_has_no_address_to_fill_in(
        self, session: Session, settings: Settings
    ) -> None:
        row = saved(
            session, settings, catalog.OLLAMA_CLOUD, model="gemma4:31b", base_url="http://x"
        )

        assert (row.model, row.base_url) == ("gemma4:31b", None)


class TestStatusAndChoice:
    def test_how_a_provider_is_doing(self, session: Session, settings: Settings) -> None:
        assert service.status_of(None) is Status.NOT_CONNECTED
        row = saved(session, settings, catalog.ANTHROPIC)
        assert service.status_of(row) is Status.UNTESTED
        service.record_attempt(row, Verdict(False, "Nope."), NOW)
        assert service.status_of(row) is Status.PROBLEM
        service.record_attempt(row, Verdict(True, "Fine."), NOW)
        assert service.status_of(row) is Status.CONNECTED

    def test_a_failure_is_kept_and_a_success_clears_it(
        self, session: Session, settings: Settings
    ) -> None:
        row = saved(session, settings, catalog.ANTHROPIC)

        service.record_attempt(row, Verdict(False, "x" * 900), NOW)
        assert row.last_error is not None
        assert len(row.last_error) <= 500
        assert (row.last_attempt_at, row.last_success_at) == (NOW, None)

        later = NOW + timedelta(hours=1)
        service.record_attempt(row, Verdict(True, "Fine."), later)
        assert (row.last_error, row.last_attempt_at, row.last_success_at) == (None, later, later)

    def test_the_models_an_ollama_has_are_kept_and_count_as_it_working(
        self, session: Session, settings: Settings
    ) -> None:
        row = saved(session, settings, catalog.OLLAMA)

        service.record_models(row, [wire.FoundModel("qwen3:8b", 5, "qwen3", "8.2B", "Q4_K_M")], NOW)

        assert row.models_found == [
            {
                "name": "qwen3:8b",
                "size": 5,
                "family": "qwen3",
                "parameters": "8.2B",
                "quantization": "Q4_K_M",
            }
        ]
        assert (row.models_found_at, row.last_success_at, row.last_error) == (NOW, NOW, None)

    def test_ai_is_off_until_it_is_turned_on(self, session: Session) -> None:
        first = service.usage(session, NOW)

        assert (first.enabled, first.provider) == (False, None)
        assert service.usage(session, NOW + timedelta(days=1)) is first
        assert first.updated_at == NOW

    def test_ai_is_turned_on_for_a_provider_that_is_set_up_with_a_model(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.ANTHROPIC)

        chosen = service.choose(session, enabled=True, provider="anthropic", now=NOW)

        assert (chosen.enabled, chosen.provider) == (True, "anthropic")

    def test_ai_can_be_off_with_a_provider_picked_or_with_none(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.ANTHROPIC)

        assert (
            service.choose(session, enabled=False, provider="anthropic", now=NOW).provider
            == "anthropic"
        )
        assert service.choose(session, enabled=False, provider=None, now=NOW).provider is None

    def test_ai_is_not_turned_on_without_a_provider_that_is_ready(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.OLLAMA, model="")

        for enabled, provider, message in (
            (True, "openai", "Set that provider up first."),
            (False, "openai", "Set that provider up first."),
            (True, "ollama", "Choose a model for it first."),
            (True, None, "Choose which provider to ask."),
        ):
            with pytest.raises(SettingsError) as caught:
                service.choose(session, enabled=enabled, provider=provider, now=NOW)
            assert caught.value.problems == {"provider": message}
        assert session.get(AiSettings, 1) is None

    def test_the_providers_that_are_set_up_are_listed_by_key(
        self, session: Session, settings: Settings
    ) -> None:
        assert service.configured(session) == {}
        row = saved(session, settings, catalog.OPENAI)

        assert service.configured(session) == {"openai": row}


class TestRemoving:
    def test_it_forgets_the_settings_and_the_key(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.ANTHROPIC)
        service.choose(session, enabled=True, provider="anthropic", now=NOW)

        removed = service.remove(session, catalog.ANTHROPIC, NOW + timedelta(minutes=1))
        session.commit()

        assert removed

        assert session.get(AiProvider, "anthropic") is None
        assert not service.key_saved(session, catalog.ANTHROPIC)
        chosen = service.usage(session, NOW)
        assert (chosen.enabled, chosen.provider) == (False, None)
        assert chosen.updated_at == NOW + timedelta(minutes=1)

    def test_another_provider_staying_chosen_is_left_alone(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.ANTHROPIC)
        saved(session, settings, catalog.OPENAI)
        service.choose(session, enabled=True, provider="openai", now=NOW)

        removed = service.remove(session, catalog.ANTHROPIC, NOW)

        assert removed
        chosen = service.usage(session, NOW)
        assert (chosen.enabled, chosen.provider) == (True, "openai")

    def test_a_key_left_behind_is_forgotten_too(self, session: Session, settings: Settings) -> None:
        saved(session, settings, catalog.OPENAI)
        session.delete(session.get(AiProvider, "openai"))
        session.flush()

        removed = service.remove(session, catalog.OPENAI, NOW)

        assert removed
        assert not service.key_saved(session, catalog.OPENAI)

    def test_nothing_set_up_is_nothing_to_forget(self, session: Session) -> None:
        removed = service.remove(session, catalog.OPENAI, NOW)

        assert not removed


class TestReachingAProvider:
    def test_a_hosted_provider_is_at_its_one_address(
        self, session: Session, settings: Settings
    ) -> None:
        row = saved(session, settings, catalog.ANTHROPIC)

        origin = service.origin_of(catalog.ANTHROPIC, row, {})

        assert origin.url == "https://api.anthropic.com"

    def test_the_test_server_may_point_it_at_a_stand_in(
        self, session: Session, settings: Settings
    ) -> None:
        row = saved(session, settings, catalog.ANTHROPIC)

        origin = service.origin_of(catalog.ANTHROPIC, row, {"anthropic": "http://127.0.0.1:9999"})

        assert origin.url == "http://127.0.0.1:9999"

    def test_a_provider_at_home_is_where_it_was_said_to_be(
        self, session: Session, settings: Settings
    ) -> None:
        row = saved(session, settings, catalog.OLLAMA)

        origin = service.origin_of(catalog.OLLAMA, row, {"ollama": "http://127.0.0.1:1"})

        assert origin.url == "http://192.168.1.50:11434"

    def test_a_target_has_the_key_opened_for_it(self, session: Session, settings: Settings) -> None:
        row = saved(session, settings, catalog.OPENAI)

        target = service.load_target(session, settings, catalog.OPENAI, row, {})

        assert (target.integration, target.connection) == ("ai", "openai")
        assert target.secrets == {API_KEY: KEY}
        assert target.origin.url == "https://api.openai.com"

    def test_one_at_home_has_no_key_to_open(self, session: Session, settings: Settings) -> None:
        row = saved(session, settings, catalog.OLLAMA)

        assert service.load_target(session, settings, catalog.OLLAMA, row, {}).secrets == {}

    def test_a_key_that_is_gone_is_said_to_be_missing(
        self, session: Session, settings: Settings
    ) -> None:
        row = saved(session, settings, catalog.OPENAI)
        credential_store.remove(session, Kind.AI_PROVIDER, "openai", API_KEY)

        with pytest.raises(Incomplete, match="missing or can't be opened"):
            service.load_target(session, settings, catalog.OPENAI, row, {})

    def test_a_key_that_cannot_be_opened_is_said_to_be_missing_too(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row = saved(session, settings, catalog.OPENAI)

        def broken(*args: object, **kwargs: object) -> str:
            raise VaultError("wrong key")

        monkeypatch.setattr(credential_store, "reveal", broken)

        with pytest.raises(Incomplete, match="missing or can't be opened"):
            service.load_target(session, settings, catalog.OPENAI, row, {})


class TestTesting:
    def target(
        self, session: Session, settings: Settings, definition: catalog.ProviderDef, url: str
    ) -> Target:
        row = saved(session, settings, definition)
        return service.load_target(session, settings, definition, row, {definition.key: url})

    def run(
        self,
        target: Target,
        definition: catalog.ProviderDef,
        model: str,
        policy: AddressPolicy = PUBLIC_INTERNET_AND_LOOPBACK,
        plan: str | None = None,
    ) -> tuple[Verdict, Log]:
        log = Log()
        verdict = asyncio.run(service.check(target, log, policy, definition, model, plan))
        return verdict, log

    def test_a_hosted_provider_answers_and_says_what_it_counted(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(stand_ins.anthropic(KEY, {"claude-haiku-5-5"}))
        target = self.target(session, settings, catalog.ANTHROPIC, server.url)

        verdict, log = self.run(target, catalog.ANTHROPIC, "claude-haiku-5-5")

        assert verdict == Verdict(
            True, "claude-haiku-5-5 answered. It counted 14 tokens in and 1 out."
        )
        assert [(call.method, call.path) for call in log.calls] == [("POST", "/v1/messages")]
        assert (log.calls[0].integration, log.calls[0].connection) == ("ai", "anthropic")

    def test_a_key_that_is_refused_is_explained(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(stand_ins.openai("another-key", {"gpt-6-luna"}))
        target = self.target(session, settings, catalog.OPENAI, server.url)

        verdict, _ = self.run(target, catalog.OPENAI, "gpt-6-luna")

        assert not verdict.ok
        assert verdict.message.startswith("OpenAI didn't accept the API key")
        assert KEY not in verdict.message

    def test_a_provider_that_cannot_be_reached_is_explained(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(stand_ins.openai(KEY, {"gpt-6-luna"}))
        target = self.target(session, settings, catalog.OPENAI, server.url)
        server.stop()

        verdict, _ = self.run(target, catalog.OPENAI, "gpt-6-luna")

        assert not verdict.ok
        assert KEY not in verdict.message

    def test_an_address_the_policy_refuses_is_not_called(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(stand_ins.anthropic(KEY, {"claude-haiku-5-5"}))
        target = self.target(session, settings, catalog.ANTHROPIC, server.url)

        verdict, log = self.run(
            target, catalog.ANTHROPIC, "claude-haiku-5-5", netguard.PUBLIC_INTERNET
        )

        assert not verdict.ok
        assert not any(call.status_code for call in log.calls)

    def test_an_ollama_with_no_model_chosen_is_asked_what_it_has(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(stand_ins.ollama("", {"llama3.2:3b", "qwen3:8b"}))
        row = saved(session, settings, catalog.OLLAMA, model="", base_url=server.url)
        target = service.load_target(session, settings, catalog.OLLAMA, row, {})

        verdict, log = self.run(target, catalog.OLLAMA, "", HOME)

        assert verdict == Verdict(True, "Reached it. It has 2 models: choose one to use.")
        assert [call.path for call in log.calls] == ["/api/tags"]

    def test_an_ollama_with_a_model_is_asked_for_a_token_as_well(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(stand_ins.ollama("", {"llama3.2:3b"}))
        row = saved(session, settings, catalog.OLLAMA, model="llama3.2:3b", base_url=server.url)
        target = service.load_target(session, settings, catalog.OLLAMA, row, {})

        verdict, log = self.run(target, catalog.OLLAMA, "llama3.2:3b", HOME)

        assert verdict == Verdict(True, "Reached it (1 model), and llama3.2:3b answered.")
        assert [call.path for call in log.calls] == ["/api/tags", "/api/chat"]

    def test_an_ollama_that_does_not_have_the_model_says_so(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(stand_ins.ollama("", {"llama3.2:3b"}))
        row = saved(session, settings, catalog.OLLAMA, model="gone:1b", base_url=server.url)
        target = service.load_target(session, settings, catalog.OLLAMA, row, {})

        verdict, _ = self.run(target, catalog.OLLAMA, "gone:1b", HOME)

        assert not verdict.ok
        assert "Fetch the models" in verdict.message

    def cloud(
        self,
        session: Session,
        settings: Settings,
        serve: Serve,
        model: str,
        plan: str | None = None,
    ) -> tuple[Target, str]:
        """Ollama's cloud: ``big:675b`` needs a paid plan, ``gpt-oss:20b`` does not."""
        server = serve(stand_ins.ollama("key-1", {"gpt-oss:20b", "big:675b"}, {"big:675b"}))
        row = service.save(
            session,
            settings,
            HOME,
            catalog.OLLAMA_CLOUD,
            Submission(model=model, api_key="key-1", plan=plan),
            NOW,
        )
        session.commit()
        target = service.load_target(
            session, settings, catalog.OLLAMA_CLOUD, row, {"ollama_cloud": server.url}
        )
        return target, row.plan or ""

    def test_a_model_a_free_account_cannot_use_says_so_and_names_the_ones_it_can(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        target, plan = self.cloud(session, settings, serve, "big:675b")

        verdict, log = self.run(target, catalog.OLLAMA_CLOUD, "big:675b", plan=plan)

        assert plan == "free"
        assert not verdict.ok
        assert verdict.message == (
            "Reached it (2 models), but big:675b didn't answer. "
            "It isn't one of the models free usage covers (HTTP 402), so it needs a paid plan. "
            "Try gpt-oss:20b, or set the account to Paid if it is."
        )
        assert [call.path for call in log.calls] == ["/api/tags", "/api/chat"]

    def test_a_model_that_is_refused_on_a_paid_plan_points_at_the_credits(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        target, plan = self.cloud(session, settings, serve, "big:675b", "paid")

        verdict, _ = self.run(target, catalog.OLLAMA_CLOUD, "big:675b", plan=plan)

        assert verdict.message.endswith(
            "Ollama says payment is required (HTTP 402), though the account is set to Paid. "
            "Check the plan and the credits at ollama.com/settings/usage."
        )

    def test_it_suggests_up_to_three_of_the_free_models_the_account_has(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        has = {"big:675b", "beam", "gemma4:31b", "gpt-oss:120b", "gpt-oss:20b", "other:1b"}
        server = serve(stand_ins.ollama("key-1", has, {"big:675b"}))
        row = saved(session, settings, catalog.OLLAMA_CLOUD, model="big:675b", api_key="key-1")
        target = service.load_target(
            session, settings, catalog.OLLAMA_CLOUD, row, {"ollama_cloud": server.url}
        )

        verdict, _ = self.run(target, catalog.OLLAMA_CLOUD, "big:675b", plan="free")

        assert "Try beam, gemma4:31b or gpt-oss:120b, or set the account to Paid" in verdict.message
        assert "gpt-oss:20b" not in verdict.message

    def test_it_suggests_the_free_list_when_the_account_has_none_of_them(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(stand_ins.ollama("key-1", {"big:675b"}, {"big:675b"}))
        row = saved(session, settings, catalog.OLLAMA_CLOUD, model="big:675b", api_key="key-1")
        target = service.load_target(
            session, settings, catalog.OLLAMA_CLOUD, row, {"ollama_cloud": server.url}
        )

        verdict, _ = self.run(target, catalog.OLLAMA_CLOUD, "big:675b", plan="free")

        assert "Try beam, gemma4:31b or gpt-oss:120b, or set" in verdict.message

    def test_a_free_model_that_is_refused_says_what_ollama_said(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        # A free model that answers 402 anyway: the list may be out of date, so say what the
        # provider said, not that it is not on the list.
        server = serve(stand_ins.ollama("key-1", {"gpt-oss:20b"}, {"gpt-oss:20b"}))
        row = saved(session, settings, catalog.OLLAMA_CLOUD, model="gpt-oss:20b", api_key="key-1")
        target = service.load_target(
            session, settings, catalog.OLLAMA_CLOUD, row, {"ollama_cloud": server.url}
        )

        verdict, _ = self.run(target, catalog.OLLAMA_CLOUD, "gpt-oss:20b", plan="free")

        assert "payment is required (HTTP 402) for this model" in verdict.message
        assert "free usage credits cover" not in verdict.message

    def test_a_free_model_is_answered_on_a_free_plan(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        target, plan = self.cloud(session, settings, serve, "gpt-oss:20b")

        verdict, _ = self.run(target, catalog.OLLAMA_CLOUD, "gpt-oss:20b", plan=plan)

        assert verdict == Verdict(True, "Reached it (2 models), and gpt-oss:20b answered.")

    def test_the_models_an_ollama_has_are_listed(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(stand_ins.ollama("", {"b:1b", "a:1b"}))
        row = saved(session, settings, catalog.OLLAMA, base_url=server.url)
        target = service.load_target(session, settings, catalog.OLLAMA, row, {})

        found = asyncio.run(service.find_models(target, Log(), HOME, catalog.OLLAMA))

        assert isinstance(found, list)
        assert [model.name for model in found] == ["a:1b", "b:1b"]

    def test_ollamas_cloud_needs_its_key_to_list_models(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(stand_ins.ollama("another-key", {"gemma4:31b"}))
        row = saved(session, settings, catalog.OLLAMA_CLOUD, model="")
        target = service.load_target(
            session, settings, catalog.OLLAMA_CLOUD, row, {"ollama_cloud": server.url}
        )

        found = asyncio.run(
            service.find_models(target, Log(), PUBLIC_INTERNET_AND_LOOPBACK, catalog.OLLAMA_CLOUD)
        )

        assert isinstance(found, str)
        assert found.startswith("Ollama Cloud didn't accept the API key")

    def test_models_that_cannot_be_asked_for_are_explained(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(stand_ins.ollama("", set()))
        row = saved(session, settings, catalog.OLLAMA, base_url=server.url)
        target = service.load_target(session, settings, catalog.OLLAMA, row, {})
        server.stop()

        found = asyncio.run(service.find_models(target, Log(), HOME, catalog.OLLAMA))

        assert isinstance(found, str)
        assert found
