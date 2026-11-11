"""Chains from the web app: the attack across two devices, its steps and the evidence."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Incident, utcnow
from e2e import factories
from tests.test_threats_chains import ATTACKER, DEVICE, SERVER

BASE = "/api/threats/chains"


def made(session: Session, settings: Settings, *, beacon: bool = True) -> None:
    """An outside address that exploited a device, and the device calling out afterwards."""
    factories.incidents(
        session,
        settings,
        utcnow(),
        [
            factories.IncidentSpec(
                address=ATTACKER, exploit=True, minutes_ago=40, device_name="Kitchen camera"
            ),
            factories.IncidentSpec(
                address=SERVER,
                outbound=True,
                compromise=beacon,
                exploit=not beacon,
                minutes_ago=5,
                signals=1,
                programs=("suricata",),
            ),
        ],
    )
    session.commit()


def test_it_is_only_for_someone_signed_in(client: TestClient) -> None:
    assert client.get(BASE).status_code == 401
    assert client.get(f"{BASE}/1").status_code == 401


def test_a_quiet_install_has_no_chains(client: TestClient, csrf_token: str) -> None:
    assert client.get(BASE).json() == {"total": 0, "items": []}


def test_there_is_no_such_chain(client: TestClient, csrf_token: str) -> None:
    assert client.get(f"{BASE}/7").status_code == 404


class TestAConfirmedChain:
    def test_it_is_listed_as_a_threat_with_a_sentence_about_it(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        made(session, settings)

        body = client.get(BASE).json()

        assert body["total"] == 1
        [chain] = body["items"]
        assert chain["device"] == DEVICE
        assert chain["device_name"] == "Kitchen camera"
        assert chain["confirmed"] is True
        assert chain["steps"] == 2
        assert chain["lane"] == "threat"
        assert chain["severity"] == "critical"
        assert chain["summary"] == f"{ATTACKER} attacked {DEVICE}, which then called {SERVER}."

    def test_it_can_be_asked_for_by_whether_it_was_seen(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        made(session, settings)

        assert client.get(BASE, params={"confirmed": "true"}).json()["total"] == 1
        assert client.get(BASE, params={"confirmed": "false"}).json() == {"total": 0, "items": []}

    def test_its_steps_come_in_the_order_they_happened_with_their_evidence(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        made(session, settings)
        [chain] = client.get(BASE).json()["items"]

        body = client.get(f"{BASE}/{chain['id']}").json()

        attacker, callout = body["path"]
        assert (attacker["role"], attacker["link"], attacker["subject"]) == (
            "attacker",
            "confirmed",
            ATTACKER,
        )
        assert (callout["role"], callout["link"], callout["subject"]) == (
            "callout",
            "confirmed",
            SERVER,
        )
        assert "aimed at" in attacker["reason"]
        assert attacker["stages"] == ["access"]
        assert callout["stages"] == ["foothold"]
        assert {each["signal"]["dst_address"] for each in attacker["evidence"]} == {DEVICE}
        assert any("Beacon" in each["signal"]["signature"] for each in callout["evidence"])
        assert callout["sources"] == [{"key": "suricata", "name": "suricata"}]
        assert body["why"][0].startswith("A chain is more than scanning")
        assert len(body["why"]) == 3

    def test_the_incident_says_it_is_a_step_of_it(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        made(session, settings)
        [chain] = client.get(BASE).json()["items"]

        found = client.get("/api/incidents", params={"lane": "threat"}).json()["items"]

        steps = {each["subject"]: each for each in found}
        assert steps[ATTACKER]["chain_id"] == chain["id"]
        assert steps[ATTACKER]["chain_role"] == "attacker"
        assert steps[SERVER]["chain_link"] == "confirmed"
        assert steps[SERVER]["chain_reason"]


class TestAnInferredChain:
    def test_it_says_so_and_keeps_that_apart_from_what_was_seen(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        made(session, settings, beacon=False)
        [chain] = client.get(BASE).json()["items"]

        body = client.get(f"{BASE}/{chain['id']}").json()

        assert chain["confirmed"] is False
        assert body["path"][1]["link"] == "inferred"
        assert "this link is inferred" in body["path"][1]["reason"]
        assert "Nothing seen proves the device was taken over" in body["why"][-1]


class TestAChainThatIsOver:
    def test_it_is_in_no_lane_once_every_step_has_been_dealt_with(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        made(session, settings)
        for incident in session.scalars(select(Incident)):
            incident.status = "resolved"
        session.commit()

        [chain] = client.get(BASE).json()["items"]

        assert chain["lane"] is None
