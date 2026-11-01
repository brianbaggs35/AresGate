import csv
import io
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import catalog
from app.audit import Action
from app.models import AiCall, AuditEvent, User
from tests.test_ai_usage import call

BASE = "/api/ai"


def recent() -> datetime:
    return datetime.now(UTC) - timedelta(minutes=5)


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    for method, path in (
        ("get", f"{BASE}/usage"),
        ("get", f"{BASE}/usage/calls"),
        ("get", f"{BASE}/usage/calls/1"),
        ("get", f"{BASE}/usage.csv"),
        ("put", f"{BASE}/limits"),
        ("put", f"{BASE}/level"),
    ):
        assert client.request(method, path).status_code == 401, (method, path)


class TestTheUsage:
    def test_a_new_install_has_nothing_to_show(self, client: TestClient, csrf_token: str) -> None:
        body = client.get(f"{BASE}/usage").json()

        assert body["ever"] is False
        assert body["totals"]["calls"] == 0
        assert body["uses"] == []
        assert body["by_model"] == []
        assert body["month"]["projected_micros"] is None
        assert [limit["state"] for limit in body["limits"]] == ["none", "none"]
        assert len(body["days"]) == 30
        assert body["level"] == "medium"
        assert [item["key"] for item in body["levels"]] == [
            "very_low",
            "low",
            "medium",
            "high",
            "maximum",
        ]

    def test_it_says_what_was_used_and_what_it_cost(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        call(
            session,
            recent(),
            purpose="triage",
            about="incident 12",
            provider="anthropic",
            model="claude-haiku-5-5",
            cost=2_500,
            cached=300,
        )
        call(session, recent(), purpose="triage", about="incident 12", cost=1_500)
        call(
            session,
            recent(),
            purpose="chat",
            provider="ollama",
            model="llama3",
            cost=0,
            tokens=(4000, 100),
        )
        call(session, recent(), provider="openai", model="not-a-model", cost=None)

        body = client.get(f"{BASE}/usage?range=7d").json()

        assert body["ever"] is True
        assert (body["range"], len(body["days"])) == ("7d", 7)
        assert body["totals"] == {
            "calls": 4,
            "failed": 0,
            "input_tokens": 7000,
            "cached_tokens": 300,
            "output_tokens": 700,
            "cost_micros": 4_000,
            "unpriced": 1,
        }
        assert [use["purpose"] for use in body["uses"]] == ["chat", "triage"]
        assert sum(sum(use["calls"]) for use in body["uses"]) == 4
        assert sum(sum(use["cost_micros"]) for use in body["uses"]) == 4_000
        assert [(g["key"], g["label"]) for g in body["by_provider"]] == [
            ("anthropic", "Anthropic"),
            ("ollama", "Ollama (on your computer)"),
            ("openai", "OpenAI"),
        ]
        labels = {g["key"]: g["label"] for g in body["by_model"]}
        assert labels["claude-haiku-5-5"] == "Claude Haiku 5.5"
        assert labels["not-a-model"] == "not-a-model"
        assert body["top"][0] == {
            "about": "incident 12",
            "purpose": "triage",
            "calls": 2,
            "tokens": 2400,
            "cost_micros": 4_000,
            "incident_id": 12,
        }
        assert body["month"]["spent_micros"] >= 0
        assert body["prices"]["as_of"] == catalog.PRICES_AS_OF
        assert {source["provider"] for source in body["prices"]["sources"]} == {
            "Anthropic",
            "OpenAI",
        }

    def test_a_thing_that_is_not_an_incident_has_no_link(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        call(session, recent(), about="the daily summary")

        body = client.get(f"{BASE}/usage").json()

        assert body["top"][0]["incident_id"] is None

    def test_the_limits_show_how_much_is_gone(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        call(session, recent(), cost=900_000)
        client.put(
            f"{BASE}/limits", json={"daily": "1", "monthly": "50"}, headers=headers(csrf_token)
        )

        body = client.get(f"{BASE}/usage").json()

        assert [
            (item["period"], item["limit_micros"], item["state"]) for item in body["limits"]
        ] == [
            ("day", 1_000_000, "warning"),
            ("month", 50_000_000, "ok"),
        ]

    def test_days_are_counted_in_the_zone_asked_for(
        self, client: TestClient, csrf_token: str
    ) -> None:
        utc = client.get(f"{BASE}/usage?timezone=UTC").json()
        halifax = client.get(f"{BASE}/usage?timezone=America/Halifax").json()

        assert utc["days"][0].endswith("T00:00:00Z")
        assert halifax["days"][0][11:19] in ("03:00:00", "04:00:00")

    @pytest.mark.parametrize("query", ["timezone=Mars/Olympus", "timezone=../etc"])
    def test_a_zone_that_does_not_exist_is_refused(
        self, client: TestClient, csrf_token: str, query: str
    ) -> None:
        for path in ("usage", "usage/calls", "usage.csv"):
            refused = client.get(f"{BASE}/{path}?{query}")
            assert refused.status_code == 422, path

    def test_a_range_that_is_not_offered_is_refused(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert client.get(f"{BASE}/usage?range=1y").status_code == 422


class TestTheCalls:
    def test_they_are_listed_newest_first_with_their_totals(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        call(session, recent() - timedelta(minutes=3), about="incident 1")
        call(session, recent(), about="incident 2", ok=False, error="It didn't answer in time.")

        page = client.get(f"{BASE}/usage/calls?limit=1").json()
        rest = client.get(f"{BASE}/usage/calls?limit=1&offset=1").json()

        assert page["total"] == 2
        assert page["items"][0]["about"] == "incident 2"
        assert page["items"][0]["ok"] is False
        assert page["items"][0]["error"] == "It didn't answer in time."
        assert page["items"][0]["provider_label"] == "Anthropic"
        assert page["items"][0]["model_label"] == "Claude Haiku 5.5"
        assert "prompt" not in page["items"][0]
        assert rest["items"][0]["about"] == "incident 1"

    def test_the_page_is_limited(self, client: TestClient, csrf_token: str) -> None:
        assert client.get(f"{BASE}/usage/calls?limit=101").status_code == 422
        assert client.get(f"{BASE}/usage/calls?offset=-1").status_code == 422

    def test_one_call_shows_what_the_provider_was_sent_and_said(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        row = call(session, recent(), about="incident 1")

        body = client.get(f"{BASE}/usage/calls/{row.id}").json()

        assert body["prompt"] == "HOST_1 was scanned"
        assert body["answer"] == "HOST_1 is a scanner"
        assert body["about"] == "incident 1"

    def test_a_call_that_is_not_there_is_not_found(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert client.get(f"{BASE}/usage/calls/99999").status_code == 404


class TestTheFile:
    def test_it_is_a_spreadsheet_of_the_calls(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        call(session, recent(), about="incident 1", cost=2_500, cached=100)
        call(session, recent(), ok=False, cost=None, error='=HYPERLINK("http://example")')

        response = client.get(f"{BASE}/usage.csv?range=7d")

        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment" in response.headers["content-disposition"]
        assert "aresgate-ai-usage-" in response.headers["content-disposition"]
        assert response.headers["content-disposition"].endswith('-7d.csv"')
        rows = list(csv.reader(io.StringIO(response.text)))
        assert rows[0][0] == "time (UTC)"
        assert len(rows) == 3
        first = dict(zip(rows[0], rows[1], strict=True))
        assert first["about"] == "incident 1"
        assert first["input tokens"] == "1000"
        assert first["cost (US dollars, estimated)"] == "0.002500"
        assert first["succeeded"] == "yes"
        second = dict(zip(rows[0], rows[2], strict=True))
        assert second["succeeded"] == "no"
        assert second["cost (US dollars, estimated)"] == ""
        assert second["error"].startswith("'=HYPERLINK")

    def test_it_holds_nothing_that_was_asked_or_answered(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        call(session, recent())

        response = client.get(f"{BASE}/usage.csv")

        assert "HOST_1" not in response.text


class TestTheLimits:
    def test_they_are_kept_and_the_change_is_noted(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        put = client.put(
            f"{BASE}/limits", json={"daily": "2.50", "monthly": None}, headers=headers(csrf_token)
        )

        assert put.status_code == 200
        assert [(item["period"], item["limit_micros"]) for item in put.json()] == [
            ("day", 2_500_000),
            ("month", None),
        ]
        session.expire_all()
        events = list(
            session.scalars(
                select(AuditEvent).where(AuditEvent.action == Action.AI_LIMITS_CHANGED.value)
            )
        )
        assert [event.detail for event in events] == [{"daily": "2.50", "monthly": "none"}]

    def test_a_limit_can_be_taken_away(self, client: TestClient, csrf_token: str) -> None:
        client.put(f"{BASE}/limits", json={"daily": "2"}, headers=headers(csrf_token))

        put = client.put(f"{BASE}/limits", json={}, headers=headers(csrf_token))

        assert [item["limit_micros"] for item in put.json()] == [None, None]

    @pytest.mark.parametrize("amount", ["0", "-1", "1000001", "1.234", "lots"])
    def test_an_amount_that_makes_no_sense_is_refused(
        self, client: TestClient, csrf_token: str, amount: str
    ) -> None:
        refused = client.put(f"{BASE}/limits", json={"daily": amount}, headers=headers(csrf_token))

        assert refused.status_code == 422

    def test_it_needs_the_token(self, client: TestClient, csrf_token: str) -> None:
        assert client.put(f"{BASE}/limits", json={"daily": "1"}).status_code == 403


class TestTheLevel:
    def test_it_is_kept_and_the_change_is_noted(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        put = client.put(f"{BASE}/level", json={"level": "high"}, headers=headers(csrf_token))

        assert put.status_code == 200
        assert put.json() == {"level": "high"}
        assert client.get(f"{BASE}/usage").json()["level"] == "high"
        session.expire_all()
        events = list(
            session.scalars(
                select(AuditEvent).where(AuditEvent.action == Action.AI_LEVEL_CHANGED.value)
            )
        )
        assert [event.detail for event in events] == [{"from": "medium", "to": "high"}]

    def test_each_level_says_what_it_reads(self, client: TestClient, csrf_token: str) -> None:
        levels = {item["key"]: item for item in client.get(f"{BASE}/usage").json()["levels"]}

        assert levels["very_low"]["per_hour"] == 0
        assert levels["maximum"]["per_hour"] == 150
        assert "high or higher" in levels["low"]["summary"]

    @pytest.mark.parametrize("level", ["", "extreme", "Medium", "none"])
    def test_a_level_that_is_not_offered_is_refused(
        self, client: TestClient, csrf_token: str, level: str
    ) -> None:
        refused = client.put(f"{BASE}/level", json={"level": level}, headers=headers(csrf_token))

        assert refused.status_code == 422

    def test_it_needs_the_token(self, client: TestClient, csrf_token: str) -> None:
        assert client.put(f"{BASE}/level", json={"level": "low"}).status_code == 403


def test_the_record_is_kept_when_the_page_is_read(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    call(session, recent())

    client.get(f"{BASE}/usage")

    assert len(session.scalars(select(AiCall)).all()) == 1
