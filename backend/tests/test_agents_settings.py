"""How the agents use AI: which provider they ask and with which model, what they may spend, how
the gateway follows that, and what each run says it used."""

from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import settings as agent_settings
from app.ai import catalog, gateway, limits, service
from app.ai.gateway import Question, Unavailable
from app.audit import Action
from app.config import Settings
from app.integrations.registry import SettingsError
from app.models import AgentRun, AgentSettings, AiCall, AiProvider, AuditEvent
from app.models.base import utcnow
from tests.stubs import Serve
from tests.test_agents_api import BASE, headers, ran, stored
from tests.test_agents_run import (
    Scripted,
    asked,
    execute,
    finished,
    made,
    said,
    with_incident,
)
from tests.test_ai_gateway import Log, context, turned_on
from tests.test_ai_service import NOW, saved

MINUTE = timedelta(minutes=1)


def spent_on(session: Session, purpose: str, micros: int, *, ago: timedelta = MINUTE) -> None:
    session.add(
        AiCall(
            occurred_at=NOW - ago,
            purpose=purpose,
            provider="anthropic",
            model="claude-haiku-5-5",
            level="balanced",
            ok=True,
            cost_micros=micros,
            prompt="x",
        )
    )
    session.commit()


def own(session: Session, provider: str = "anthropic", model: str | None = None) -> None:
    agent_settings.save(
        session, source="own", provider=provider, model=model, daily=None, monthly=None, now=NOW
    )
    session.commit()


class TestWhichProviderTheAgentsAsk:
    def test_by_default_they_ask_what_settings_ai_chose(
        self, session: Session, settings: Settings
    ) -> None:
        assert agent_settings.get(session, NOW).ai_source == "shared"
        assert agent_settings.pick(session, NOW) == agent_settings.Pick(
            None, None, "AI is turned off. Turn it on under Settings > AI to use it."
        )

        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")

        assert agent_settings.pick(session, NOW) == agent_settings.Pick("anthropic", None, None)

    def test_they_can_ask_none(self, session: Session) -> None:
        agent_settings.save(
            session, source="off", provider=None, model=None, daily=None, monthly=None, now=NOW
        )

        picked = agent_settings.pick(session, NOW)

        assert picked.provider is None
        assert (
            picked.reason == "AI is turned off for the agents. Turn it on under Settings > Agents."
        )

    def test_they_can_ask_a_provider_of_their_own_even_while_ai_is_off_elsewhere(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.ANTHROPIC)

        own(session, model="claude-sonnet-5-5")

        assert service.usage(session, NOW).enabled is False
        assert agent_settings.pick(session, NOW) == agent_settings.Pick(
            "anthropic", "claude-sonnet-5-5", None
        )

    def test_a_provider_that_was_forgotten_leaves_them_with_none_chosen(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.ANTHROPIC)
        own(session)

        service.remove(session, catalog.ANTHROPIC, NOW)
        session.commit()

        assert agent_settings.pick(session, NOW) == agent_settings.Pick(
            None,
            None,
            "No AI provider is chosen for the agents. Choose one under Settings > Agents.",
        )

    def test_their_own_choice_is_kept_only_while_it_is_their_own(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.ANTHROPIC)
        own(session, model="claude-sonnet-5-5")

        agent_settings.save(
            session,
            source="shared",
            provider="anthropic",
            model="x",
            daily=None,
            monthly=None,
            now=NOW,
        )

        kept = agent_settings.get(session, NOW)
        assert (kept.provider, kept.model) == (None, None)

    def test_an_own_provider_that_is_not_chosen_is_asked_for(self, session: Session) -> None:
        with pytest.raises(SettingsError) as raised:
            agent_settings.save(
                session, source="own", provider=None, model=None, daily=None, monthly=None, now=NOW
            )
        assert raised.value.problems == {"provider": "Choose which provider the agents ask."}

    def test_a_provider_that_is_not_set_up_can_not_be_chosen(self, session: Session) -> None:
        with pytest.raises(SettingsError) as raised:
            agent_settings.save(
                session,
                source="own",
                provider="openai",
                model=None,
                daily=None,
                monthly=None,
                now=NOW,
            )
        assert raised.value.problems == {
            "provider": "Set that provider up under Settings > AI first."
        }

    def test_the_model_has_to_be_one_the_provider_offers(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.ANTHROPIC)

        with pytest.raises(SettingsError) as raised:
            own(session, model="gpt-9")

        assert raised.value.problems == {"model": "Choose one of the models the provider offers."}

    def test_a_provider_with_no_model_needs_one(self, session: Session, settings: Settings) -> None:
        saved(session, settings, catalog.OLLAMA, model="")

        with pytest.raises(SettingsError) as raised:
            own(session, "ollama")

        assert raised.value.problems == {"model": "Choose a model for it first."}

    def test_a_provider_on_the_owners_computer_takes_any_model_name(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.OLLAMA, model="llama3")

        own(session, "ollama", "qwen3:8b")

        assert agent_settings.pick(session, NOW).model == "qwen3:8b"

    def test_a_source_that_is_not_one_is_refused(self, session: Session) -> None:
        with pytest.raises(SettingsError) as raised:
            agent_settings.save(
                session, source="both", provider=None, model=None, daily=None, monthly=None, now=NOW
            )
        assert raised.value.problems == {"ai_source": "Choose shared, own or off."}


class TestWhatTheAgentsMaySpend:
    def test_only_what_the_agents_spent_counts_against_their_limits(self, session: Session) -> None:
        spent_on(session, "agent", 400_000)
        spent_on(session, "chat", 900_000)
        spent_on(session, "agent", 100_000, ago=timedelta(days=2))
        agent_settings.save(
            session,
            source="shared",
            provider=None,
            model=None,
            daily=Decimal("1.00"),
            monthly=Decimal("5.00"),
            now=NOW,
        )

        day, month = agent_settings.status(session, NOW)

        assert (day.limit_micros, day.spent_micros, day.state) == (1_000_000, 400_000, "ok")
        assert month.spent_micros == 500_000
        assert agent_settings.reached(session, NOW) is None

    def test_a_limit_that_is_used_up_says_where_to_raise_it(self, session: Session) -> None:
        spent_on(session, "agent", 1_500_000)
        agent_settings.save(
            session,
            source="shared",
            provider=None,
            model=None,
            daily=Decimal("1.00"),
            monthly=None,
            now=NOW,
        )

        assert agent_settings.reached(session, NOW) == (
            "The daily agents' spending limit ($1.00) is used up. Requests start again when "
            "spending in the last 24 hours falls below it. Raise it under Settings > Agents."
        )

    def test_a_month_that_is_used_up_waits_for_the_next(self, session: Session) -> None:
        spent_on(session, "agent", 6_000_000)
        agent_settings.save(
            session,
            source="shared",
            provider=None,
            model=None,
            daily=None,
            monthly=Decimal("5.00"),
            now=NOW,
        )

        assert agent_settings.reached(session, NOW) == (
            "The monthly agents' spending limit ($5.00) is used up. Requests start again next "
            "month. Raise it under Settings > Agents."
        )


class TestWhatTheGatewayDoes:
    def question(self, purpose: str = "agent") -> Question:
        return Question(purpose=purpose, system="s", build=lambda _: "what")

    def test_an_agent_asks_its_own_provider_and_model_while_the_rest_ask_theirs(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")
        own(session, model="claude-sonnet-5-5")

        for_agents = gateway.prepare(session, context(settings, Log()), self.question(), NOW)
        for_chat = gateway.prepare(session, context(settings, Log()), self.question("chat"), NOW)

        assert not isinstance(for_agents, Unavailable)
        assert not isinstance(for_chat, Unavailable)
        assert for_agents.model == "claude-sonnet-5-5"
        assert for_chat.model == "claude-haiku-5-5"

    def test_an_agent_is_told_when_its_own_limit_is_used_up_but_chat_is_not(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")
        spent_on(session, "agent", 2_000_000)
        agent_settings.save(
            session,
            source="shared",
            provider=None,
            model=None,
            daily=Decimal("1"),
            monthly=None,
            now=NOW,
        )

        assert gateway.availability(session, NOW, "agent") == agent_settings.reached(session, NOW)
        assert gateway.availability(session, NOW) is None

    def test_an_agent_that_may_ask_none_asks_none(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")
        agent_settings.save(
            session, source="off", provider=None, model=None, daily=None, monthly=None, now=NOW
        )

        assert gateway.availability(session, NOW, "agent") == (
            "AI is turned off for the agents. Turn it on under Settings > Agents."
        )
        assert gateway.availability(session, NOW) is None

    def test_it_says_where_to_fix_an_agents_own_provider(
        self, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.OLLAMA, model="llama3")
        own(session, "ollama")
        provider = session.get_one(AiProvider, "ollama")
        provider.model = ""
        session.commit()

        assert gateway.availability(session, NOW, "agent") == (
            "The AI provider has no model yet. Choose one under Settings > Agents."
        )

    def test_a_provider_the_catalog_forgot_is_said_to_be_gone(self, session: Session) -> None:
        session.add(AiProvider(provider="ghost", model="x"))
        session.commit()
        session.add(AgentSettings(id=1, ai_source="own", provider="ghost", updated_at=NOW))
        session.commit()

        assert gateway.availability(session, NOW, "agent") == (
            "The AI provider that was chosen is gone. Choose one under Settings > Agents."
        )


def test_a_run_notes_what_it_used_of_the_ai_and_who_answered(
    session: Session, settings: Settings, serve: Serve
) -> None:
    with_incident(session)
    provider = Scripted(said())
    server = serve(provider)
    saved(session, settings, catalog.ANTHROPIC)
    own(session, model="claude-sonnet-5-5")
    found = made(session)
    run_id = asked(session, found)

    execute(session, settings, run_id, server.url)

    done = finished(session, run_id)
    assert done.status == "succeeded"
    assert (done.calls, done.input_tokens, done.output_tokens, done.cached_tokens) == (
        1,
        1000,
        200,
        0,
    )
    # Sonnet 5.5 costs $2 per million tokens in and $10 per million out.
    assert done.cost_micros == 4_000
    assert done.unpriced_calls == 0
    assert (done.provider, done.model) == ("anthropic", "claude-sonnet-5-5")
    [call] = session.scalars(select(AiCall)).all()
    assert (call.provider, call.model) == ("anthropic", "claude-sonnet-5-5")


def test_a_run_the_ai_took_no_part_in_used_nothing(session: Session, settings: Settings) -> None:
    with_incident(session)
    run_id = asked(session, made(session))

    execute(session, settings, run_id)

    done = finished(session, run_id)
    assert (done.calls, done.input_tokens, done.cost_micros, done.provider) == (0, 0, 0, None)


def test_a_model_the_catalog_has_no_price_for_is_counted_unpriced(
    session: Session, settings: Settings, serve: Serve
) -> None:
    with_incident(session)
    server = serve(Scripted(said()))
    saved(session, settings, catalog.ANTHROPIC)
    own(session, model="claude-sonnet-5-5")
    # What the agents ask may have been renamed since it was chosen.
    session.get_one(AgentSettings, 1).model = "claude-from-the-future"
    run_id = asked(session, made(session))

    execute(session, settings, run_id, server.url)

    done = finished(session, run_id)
    assert (done.calls, done.unpriced_calls, done.cost_micros) == (1, 1, 0)


class TestTheSettingsApi:
    def test_by_default_the_agents_ask_what_settings_ai_chose(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = client.get(f"{BASE}/settings").json()

        assert body["ai_source"] == "shared"
        assert body["asking"] is None
        assert body["reason"] == "AI is turned off. Turn it on under Settings > AI to use it."
        assert [item["state"] for item in body["limits"]] == ["none", "none"]

    def test_it_says_who_is_asked_when_one_is(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.ANTHROPIC)
        turned_on(session, "anthropic")

        body = client.get(f"{BASE}/settings").json()

        assert body["asking"] == {
            "provider": "anthropic",
            "label": "Anthropic",
            "model": "claude-haiku-5-5",
            "charges": True,
        }
        assert body["reason"] is None

    def test_the_agents_can_be_given_a_provider_a_model_and_limits_of_their_own(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        saved(session, settings, catalog.ANTHROPIC)

        response = client.put(
            f"{BASE}/settings",
            json={
                "ai_source": "own",
                "provider": "anthropic",
                "model": "claude-sonnet-5-5",
                "daily": "1.50",
                "monthly": "20",
            },
            headers=headers(csrf_token),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ai_source"] == "own"
        assert body["asking"]["model"] == "claude-sonnet-5-5"
        assert [item["limit_micros"] for item in body["limits"]] == [1_500_000, 20_000_000]
        assert client.get(f"{BASE}/settings").json() == body
        session.expire_all()
        [event] = session.scalars(
            select(AuditEvent).where(AuditEvent.action == Action.AGENT_SETTINGS_CHANGED.value)
        )
        assert event.detail == {"ai_source": "own", "provider": "anthropic"}

    def test_what_is_wrong_is_said_by_the_name_of_the_setting(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.put(
            f"{BASE}/settings",
            json={"ai_source": "own", "provider": "openai"},
            headers=headers(csrf_token),
        )

        assert response.status_code == 422
        [problem] = response.json()["detail"]
        assert problem["loc"] == ["body", "provider"]
        assert problem["msg"] == "Set that provider up under Settings > AI first."

    def test_a_limit_of_nothing_is_refused(self, client: TestClient, csrf_token: str) -> None:
        response = client.put(
            f"{BASE}/settings",
            json={"ai_source": "shared", "daily": "0"},
            headers=headers(csrf_token),
        )

        assert response.status_code == 422

    def test_a_provider_that_went_is_said_to_be_gone(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        session.add(AiProvider(provider="ghost", model="x"))
        session.commit()
        session.add(AgentSettings(id=1, ai_source="own", provider="ghost", updated_at=NOW))
        session.commit()

        body = client.get(f"{BASE}/settings").json()

        assert body["asking"] is None
        assert body["reason"] == (
            "The AI provider the agents ask is gone. Choose one under Settings > Agents."
        )


class TestWhatTheAgentsUsed:
    def test_the_overview_adds_up_the_last_30_days_and_shows_the_limits(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        first = stored(session)
        second = stored(session, name="Other")
        finished_at = utcnow()
        for agent, cost in ((first, 3_000), (first, 1_500), (second, 500)):
            ran(
                session,
                agent,
                finished_at=finished_at,
                calls=2,
                input_tokens=1_000,
                output_tokens=200,
                cached_tokens=300,
                cost_micros=cost,
                unpriced_calls=1,
            )
        ran(session, first, finished_at=utcnow() - timedelta(days=40), cost_micros=99_999)

        body = client.get(BASE).json()

        assert body["usage"] == {
            "runs": 3,
            "calls": 6,
            "input_tokens": 3_000,
            "output_tokens": 600,
            "cached_tokens": 900,
            "cost_micros": 5_000,
            "unpriced_calls": 3,
        }
        by_agent = {agent["name"]: agent["usage"]["cost_micros"] for agent in body["agents"]}
        assert by_agent == {"Stored": 4_500, "Other": 500}
        assert [item["period"] for item in body["limits"]] == ["day", "month"]

    def test_a_run_says_what_it_used(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)
        run = ran(
            session,
            agent,
            finished_at=utcnow(),
            calls=1,
            input_tokens=10,
            output_tokens=5,
            cost_micros=7,
            provider="anthropic",
            model="claude-haiku-5-5",
        )

        shown = client.get(f"{BASE}/{agent.id}/runs/{run.id}").json()

        assert shown["usage"]["cost_micros"] == 7
        assert (shown["provider"], shown["model"]) == ("anthropic", "claude-haiku-5-5")

    def test_an_agent_shows_each_of_the_last_30_days(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)
        today = utcnow()
        ran(session, agent, finished_at=today, input_tokens=100, cached_tokens=50, cost_micros=40)
        ran(session, agent, finished_at=today, output_tokens=10, cost_micros=2)
        ran(session, agent, finished_at=today - timedelta(days=3), cost_micros=1)
        ran(session, agent, finished_at=today - timedelta(days=45), cost_micros=500)

        days = client.get(f"{BASE}/{agent.id}").json()["days"]

        assert len(days) == 30
        assert days[-1]["day"] == today.date().isoformat()
        assert (days[-1]["runs"], days[-1]["tokens"], days[-1]["cost_micros"]) == (2, 160, 42)
        assert days[-4]["cost_micros"] == 1
        assert sum(item["cost_micros"] for item in days) == 43

    def test_the_new_settings_need_a_signed_in_owner(
        self, client: TestClient, account: object
    ) -> None:
        assert client.get(f"{BASE}/settings").status_code == 401
        assert client.put(f"{BASE}/settings", json={"ai_source": "off"}).status_code == 401


def test_the_limits_helper_words_both_periods_alike(session: Session) -> None:
    day = limits.Limit("day", 1_000_000, 2_000_000)
    month = limits.Limit("month", 1_000_000, 2_000_000)

    assert "daily AI spending limit" in (limits.words_for(day) or "")
    assert "on the AI usage page" in (limits.words_for(month) or "")
    assert limits.words_for(limits.Limit("day", None, 5)) is None
    assert limits.words_for(limits.Limit("day", 10, 1)) is None


def test_a_run_row_has_no_usage_until_it_ends(session: Session) -> None:
    agent = stored(session)
    run = ran(session, agent, "queued")

    kept = session.get_one(AgentRun, run.id)

    assert (kept.calls, kept.cost_micros, kept.provider) == (0, 0, None)
