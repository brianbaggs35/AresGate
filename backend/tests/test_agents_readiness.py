"""Whether an agent has what it needs: each kind says what it needs, and the page says whether it
is there and where to get it."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents import catalog, readiness
from app.models import Device, IntegrationConnection
from app.models.base import utcnow
from tests.test_agents_api import BASE, make


def connected(session: Session, integration: str) -> None:
    session.add(
        IntegrationConnection(integration=integration, connection="api", base_url="https://x:1")
    )
    session.commit()


def checks(session: Session, template: catalog.Template) -> dict[str, bool]:
    return {check.key: check.ok for check in readiness.checks(session, utcnow(), template)}


def test_every_need_a_template_names_is_a_check_and_every_template_says_how_to_set_it_up() -> None:
    for item in catalog.TEMPLATES:
        assert set(item.needs) <= set(readiness.NEEDS)
        assert item.setup
        assert all(step.endswith(".") for step in item.setup)


def test_nothing_is_ready_before_anything_is_connected(session: Session) -> None:
    found = readiness.checks(session, utcnow(), catalog.INTELLIGENCE_ANALYST)

    assert [check.key for check in found] == ["ai", "intel", "alerts"]
    assert not readiness.ready(found)
    assert all(check.fix and check.link.startswith("/") for check in found)


def test_connecting_an_integration_makes_what_needs_it_ready(session: Session) -> None:
    assert checks(session, catalog.INTELLIGENCE_ANALYST)["intel"] is False
    assert checks(session, catalog.HEALTH_WATCH)["integrations"] is False
    connected(session, "virustotal")

    assert checks(session, catalog.INTELLIGENCE_ANALYST)["intel"] is True
    assert checks(session, catalog.HEALTH_WATCH)["integrations"] is True
    assert checks(session, catalog.INTELLIGENCE_ANALYST)["alerts"] is False
    connected(session, "wazuh")
    assert checks(session, catalog.INTELLIGENCE_ANALYST)["alerts"] is True
    assert checks(session, catalog.THREAT_HUNTER)["alerts"] is True


def test_the_firewall_and_the_devices_are_their_own_checks(session: Session) -> None:
    firewall = readiness.NEEDS["firewall"]
    assert firewall(session, utcnow()).ok is False
    assert checks(session, catalog.EXPOSURE_SCANNER)["devices"] is False
    connected(session, "opnsense")
    session.add(Device(mac="aa:bb:cc:00:00:01", first_seen_at=utcnow(), last_seen_at=utcnow()))
    session.commit()

    assert firewall(session, utcnow()).ok is True
    assert checks(session, catalog.EXPOSURE_SCANNER)["devices"] is True


def test_the_ai_check_says_why_when_the_agents_cannot_ask_one(session: Session) -> None:
    [ai] = [
        check
        for check in readiness.checks(session, utcnow(), catalog.HEALTH_WATCH)
        if check.key == "ai"
    ]

    assert ai.ok is False
    assert ai.fix
    assert ai.link == "/settings/agents"


class TestTheApi:
    def test_each_kind_comes_with_what_it_needs_and_how_to_set_it_up(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = client.get(BASE).json()

        analyst = next(item for item in body["templates"] if item["key"] == "intelligence_analyst")
        assert analyst["ready"] is False
        assert [check["key"] for check in analyst["checks"]] == ["ai", "intel", "alerts"]
        assert analyst["setup"][0].startswith("Make a free VirusTotal account")

    def test_an_agent_shows_whether_its_kind_is_ready(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        connected(session, "opnsense")
        made = make(client, csrf_token, template="health_watch", name="Watch")

        info = client.get(f"{BASE}/{made['id']}").json()["template_info"]

        assert info["key"] == "health_watch"
        assert {check["key"]: check["ok"] for check in info["checks"]}["integrations"] is True
