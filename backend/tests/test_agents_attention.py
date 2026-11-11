"""What the agents together say needs the owner, and the daily briefing, on the overview."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents import attention
from app.models.base import utcnow
from tests.test_agents_api import BASE, item, ran, stored


def finding(severity: str, title: str, status: str = "new") -> dict[str, object]:
    return {**item(severity, title), "detail": f"{title} in detail", "status": status}


def test_with_no_agent_nothing_needs_anyone(client: TestClient, csrf_token: str) -> None:
    body = client.get(BASE).json()

    assert body["attention"] == []
    assert body["attention_total"] == 0
    assert body["briefing"] is None


def test_the_serious_findings_of_each_agents_last_run_are_listed_the_worst_first(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    hunter = stored(session, name="Hunter")
    scanner = stored(session, "exposure_scanner", name="Scanner")
    now = utcnow()
    ran(
        session,
        hunter,
        finished_at=now - timedelta(hours=5),
        findings=[finding("high", "An old one that is gone now")],
    )
    ran(
        session,
        hunter,
        finished_at=now - timedelta(hours=1),
        findings=[finding("medium", "Odd logins", "ongoing"), finding("info", "Routine")],
    )
    ran(
        session,
        scanner,
        finished_at=now - timedelta(hours=2),
        findings=[finding("critical", "Telnet")],
    )
    ran(
        session,
        scanner,
        "failed",
        finished_at=now,
        findings=[finding("critical", "From a failure")],
    )
    ran(session, stored(session, name="Quiet"), finished_at=now, findings=[finding("low", "Minor")])

    body = client.get(BASE).json()

    assert [(each["severity"], each["title"], each["status"]) for each in body["attention"]] == [
        ("critical", "Telnet", "new"),
        ("medium", "Odd logins", "ongoing"),
    ]
    first = body["attention"][0]
    assert first["agent_name"] == "Scanner"
    assert first["icon"] == "scan-search"
    assert first["detail"] == "Telnet in detail"
    assert body["attention_total"] == 2


def test_no_more_than_the_most_serious_are_shown_but_all_are_counted(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    agent = stored(session)
    many = [finding("medium", f"Thing {number}") for number in range(attention.SHOWN + 3)]
    ran(session, agent, finished_at=utcnow(), findings=[*many, finding("high", "The worst")])

    body = client.get(BASE).json()

    assert len(body["attention"]) == attention.SHOWN
    assert body["attention"][0]["title"] == "The worst"
    assert body["attention_total"] == attention.SHOWN + 4


def test_an_agent_made_from_a_template_that_is_gone_is_still_listed_with_a_robot(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    agent = stored(session, "retired", name="Old")
    ran(session, agent, finished_at=utcnow(), findings=[finding("high", "Still true")])

    shown = client.get(BASE).json()["attention"][0]

    assert shown["icon"] == "bot"


def test_the_newest_briefing_is_what_the_overview_carries(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    older = stored(session, "daily_briefing", name="Morning")
    newer = stored(session, "daily_briefing", name="Evening")
    empty = stored(session, "daily_briefing", name="Silent")
    now = utcnow()
    ran(session, older, finished_at=now - timedelta(days=1), summary="Yesterday was quiet.")
    ran(session, newer, finished_at=now - timedelta(hours=1), summary="Nothing needs you today.")
    ran(session, empty, finished_at=now, summary="")
    ran(session, stored(session, name="Hunter"), finished_at=now, summary="Not a briefing.")

    briefing = client.get(BASE).json()["briefing"]

    assert briefing["agent_name"] == "Evening"
    assert briefing["summary"] == "Nothing needs you today."
