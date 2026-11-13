"""The incidents the threat hunter flagged: from the findings of its last finished run that name
them, beside the incident, in a search, and on the Threats page."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents import flags
from app.models import Agent, AgentRun, Incident, utcnow
from tests.test_ai_triage import incident

NOW = utcnow()


def agent(session: Session, template: str = "threat_hunter", name: str = "Night watch") -> Agent:
    found = Agent(name=name, template=template, goal="")
    session.add(found)
    session.commit()
    return found


def run(
    session: Session,
    owner: Agent,
    findings: list[dict[str, object]],
    *,
    status: str = "succeeded",
    ago: int = 0,
) -> AgentRun:
    made = AgentRun(
        agent_id=owner.id,
        trigger="schedule",
        status=status,
        requested_at=NOW - timedelta(minutes=ago),
        finished_at=NOW - timedelta(minutes=ago),
        findings=findings,
    )
    session.add(made)
    session.commit()
    return made


def finding(
    seen: Incident | str, severity: str = "high", title: str = "Looks real", **more: object
) -> dict[str, object]:
    key = str(seen.id) if isinstance(seen, Incident) else seen
    return {
        "severity": severity,
        "title": title,
        "detail": "",
        "action": "Check the device.",
        "confidence": "high",
        "cites": [{"kind": "incident", "key": key, "label": f"Incident {key}"}],
        **more,
    }


def two(session: Session) -> tuple[Incident, Incident]:
    return incident(session, subject="203.0.113.7"), incident(session, subject="203.0.113.8")


class TestWhatTheHunterFlagged:
    def test_a_serious_finding_that_names_an_incident_flags_it(self, session: Session) -> None:
        named, other = two(session)
        owner = agent(session)
        made = run(session, owner, [finding(named)])

        found = flags.of_incidents(session, [named.id, other.id])

        assert list(found) == [named.id]
        [flag] = found[named.id]
        assert (flag.agent_id, flag.agent_name, flag.run_id) == (owner.id, "Night watch", made.id)
        assert (flag.severity, flag.title, flag.action, flag.confidence) == (
            "high",
            "Looks real",
            "Check the device.",
            "high",
        )

    def test_only_what_is_worth_acting_on_by_the_hunter_in_its_last_run_counts(
        self, session: Session
    ) -> None:
        named, other = two(session)
        hunter = agent(session)
        run(session, hunter, [finding(named)], ago=30)
        run(session, hunter, [finding(other)], ago=10)
        # A run that failed after it, an agent of another kind and findings that are minor or that
        # name something else do not count.
        run(session, hunter, [finding(named)], status="failed", ago=1)
        run(session, agent(session, "firewall_reviewer", "Reviewer"), [finding(named)])
        both: list[dict[str, object]] = [
            finding(other, "low"),
            finding("99999", "critical"),
            {**finding(other), "cites": [{"kind": "device", "key": str(other.id)}]},
            {**finding(other), "cites": "nothing"},
            {"severity": "critical", "title": "No cites"},
        ]
        run(session, agent(session, name="Another hunter"), both)

        found = flags.of_incidents(session, [named.id, other.id])

        assert list(found) == [other.id]
        assert [flag.agent_name for flag in found[other.id]] == ["Night watch"]

    def test_nothing_asked_is_nothing(self, session: Session) -> None:
        assert flags.of_incidents(session, []) == {}

    def test_the_incidents_going_on_come_most_serious_first_with_the_worst_thing_said(
        self, session: Session
    ) -> None:
        minor = incident(session, subject="203.0.113.7", severity=1)
        major = incident(session, subject="203.0.113.8", severity=4)
        over = incident(session, subject="203.0.113.9", severity=4, status="dismissed")
        hunter = agent(session)
        run(
            session,
            hunter,
            [
                finding(minor, "medium", "Might be"),
                finding(major, "medium", "Maybe"),
                finding(major, "critical", "Certainly"),
                finding(over),
            ],
        )

        total, shown = flags.going_on(session, 5)

        assert total == 2
        assert [(each.id, said.title) for each, said in shown] == [
            (major.id, "Certainly"),
            (minor.id, "Might be"),
        ]
        assert flags.going_on(session, 1)[0] == 2
        assert len(flags.going_on(session, 1)[1]) == 1


class TestWhereItShows:
    def flagged(self, session: Session) -> tuple[Incident, Incident]:
        named, other = two(session)
        run(session, agent(session), [finding(named, "critical", "Needs you")])
        return named, other

    def test_it_is_found_by_a_search_and_its_opposite(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        named, other = self.flagged(session)

        for words, wanted in (
            ("hunted:yes", named),
            ("flagged:yes", named),
            ("hunter:yes", named),
            ("hunted:no", other),
        ):
            body = client.get("/api/incidents", params={"q": words}).json()
            assert [item["id"] for item in body["items"]] == [wanted.id], words
        assert client.get("/api/incidents", params={"q": "hunted:maybe"}).status_code == 422

    def test_the_list_and_the_incident_say_what_the_hunter_thinks(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        named, other = self.flagged(session)

        items = {item["id"]: item for item in client.get("/api/incidents").json()["items"]}
        detail = client.get(f"/api/incidents/{named.id}").json()

        assert items[other.id]["hunter"] == []
        for said in (items[named.id]["hunter"], detail["hunter"]):
            [one] = said
            assert (one["agent_name"], one["severity"], one["title"]) == (
                "Night watch",
                "critical",
                "Needs you",
            )
            assert (one["action"], one["confidence"]) == ("Check the device.", "high")
        assert client.get(f"/api/incidents/{other.id}").json()["hunter"] == []

    def test_the_threats_page_names_the_first_few(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        named, _ = self.flagged(session)

        body = client.get("/api/threats/overview").json()

        assert body["hunted"]["total"] == 1
        [shown] = body["hunted"]["items"]
        assert (shown["id"], shown["finding"], shown["agent_name"]) == (
            named.id,
            "Needs you",
            "Night watch",
        )
        assert shown["action"] == "Check the device."

    def test_a_quiet_hunter_flags_nothing(self, client: TestClient, csrf_token: str) -> None:
        body = client.get("/api/threats/overview").json()

        assert body["hunted"] == {"total": 0, "items": []}
